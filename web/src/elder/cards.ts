/** Pure decisions for delivered reminders / medicines (T8). Tested; no React, no network. */

import type { Delivery } from "../api";
import type { Phase } from "../voice/state";

/** Do not start another session by itself sooner than this after the last automatic start (no loops). */
export const AUTO_START_COOLDOWN_MS = 60_000;

/** The elder has met these: spoken, being spoken, or put on the screen because they could not be spoken. */
const ON_SCREEN: readonly Delivery["status"][] = ["speaking", "spoken", "shown_only", "undelivered"];

export interface Card {
  delivery: Delivery;
  /** Arjun finished saying it. False = the screen is the only way she learns of it, and the card says so. */
  spoken: boolean;
}

/** The SQL item a delivery is about, in the same form the agent publishes in `arjun.item`. */
export const itemOf = (d: Delivery): string => `${d.kind === "medicine" ? "dose" : "reminder"}:${d.ref_id}`;

/** The one card to show: the item the agent just published, else the oldest unacknowledged one. */
export function cardFor(open: readonly Delivery[], preferredItem: string): Card | undefined {
  const mine = open.filter((d) => ON_SCREEN.includes(d.status));
  if (mine.length === 0) return undefined;
  const oldest = [...mine].sort((a, b) => a.due_at.localeCompare(b.due_at) || a.id - b.id);
  const delivery = (preferredItem ? oldest.find((d) => itemOf(d) === preferredItem) : undefined) ?? oldest[0];
  if (!delivery) return undefined;
  return { delivery, spoken: delivery.status === "spoken" || delivery.status === "speaking" };
}

export function shouldAutoStart(a: {
  armed: boolean;
  phase: Phase;
  queued: number;
  /** ms since the last automatic start, null if none yet. */
  sinceLastMs: number | null;
}): boolean {
  if (!a.armed || a.phase !== "idle" || a.queued <= 0) return false;
  return a.sinceLastMs === null || a.sinceLastMs >= AUTO_START_COOLDOWN_MS;
}

// ---- Hands-free (default since 2026-10-31): no buttons needed -------------------------------------------------
// The page connects by itself when it opens, keeps the mic open, and reconnects by itself after a drop. Aaji just
// talks. Screens go back to the home screen by themselves after a reply; nothing waits for an OK tap.
// Browsers allow sound only after one tap per page load, unless the page runs as an installed app or in the
// kiosk launcher (scripts/elder-kiosk.ps1, which starts Chrome with autoplay allowed).

/** Wait before each reconnect attempt: at once, then 2 s, 5 s, 10 s, then every 30 s. Never a tight loop. */
export const RECONNECT_BACKOFF_MS = [0, 2_000, 5_000, 10_000, 30_000] as const;

export function reconnectDelay(attempt: number): number {
  return RECONNECT_BACKOFF_MS[Math.min(Math.max(attempt, 0), RECONNECT_BACKOFF_MS.length - 1)] ?? 30_000;
}

/** Should the page (re)open the voice session by itself now? */
export function shouldConnectHandsFree(a: {
  handsFree: boolean;
  phase: Phase;
  /** ms since the last attempt, null if none yet. */
  sinceLastMs: number | null;
  /** failed attempts in a row. */
  attempt: number;
}): boolean {
  if (!a.handsFree || (a.phase !== "idle" && a.phase !== "failed")) return false;
  return a.sinceLastMs === null || a.sinceLastMs >= reconnectDelay(a.attempt);
}

/** How long a reply screen stays before the home screen comes back by itself. A story / chat stays longer:
 * she may still be talking. Safety is NOT here: the safety screen stays until it is acknowledged. */
export const REST_AFTER_MS: Record<"reply" | "saved" | "story", number> = { reply: 12_000, saved: 8_000, story: 45_000 };

/** In hands-free mode "listening" IS the home screen (with a small 'मी ऐकतोय' badge), and a reply screen the
 * elder has already had time to read gives way to it. */
export function restingScreen<S extends string>(shown: S, turn: number, restedTurn: number, handsFree: boolean): S | "home" {
  if (!handsFree) return shown;
  if (shown === "listen") return "home";
  if ((shown === "reply" || shown === "saved" || shown === "story") && turn <= restedTurn) return "home";
  return shown;
}
