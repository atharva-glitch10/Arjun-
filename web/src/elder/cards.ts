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
