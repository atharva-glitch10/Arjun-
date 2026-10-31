/** Emergency alerts that reach the family even when the dashboard tab is in the background.
 *
 * The normal dashboard refresh pauses in a hidden tab (polling.ts). This watcher does NOT: it keeps checking
 * the notifications every `ms`, visible or not, and reports every emergency of the last 24 h that nobody has
 * acknowledged on this device yet. The alarm (sound, pop-up, tab title) keeps going until someone taps
 * "I have seen it". Browsers slow timers in background tabs (Chrome: about once a minute after a few
 * minutes), so a background alert can take up to ~1 minute. A closed tab or a sleeping laptop gets nothing:
 * there is still no SMS / call / WhatsApp (telephony is frozen).
 *
 * The decisions are pure functions, so they are tested; the browser side effects live in alarm.ts.
 */

import { recentEmergencies, type AlertNote } from "./alerts";

/** Emergencies of the last 24 h that were not acknowledged on this device, newest first. */
export function unacknowledged<T extends AlertNote>(notes: T[], acked: ReadonlySet<number>, now: Date): T[] {
  return recentEmergencies(notes, now).filter((n) => !acked.has(n.id));
}

/** The ones that still need a system pop-up (each emergency gets exactly one). */
export function needsPopup<T extends AlertNote>(open: T[], popped: ReadonlySet<number>): T[] {
  return open.filter((n) => !popped.has(n.id));
}

export interface Timers {
  setInterval(fn: () => void, ms: number): unknown;
  clearInterval(id: unknown): void;
}

/** Check now and then every `ms`, whether or not the tab is visible. Never two checks at a time; a failed
 * check never stops the watch. Returns a stop function. */
export function startEmergencyWatch(
  check: () => Promise<void>,
  ms: number,
  timers: Timers = { setInterval: (f, t) => setInterval(f, t), clearInterval: (id) => clearInterval(id as number) },
): () => void {
  let inFlight = false;
  const run = () => {
    if (inFlight) return;
    inFlight = true;
    void check()
      .catch(() => {})
      .finally(() => {
        inFlight = false;
      });
  };
  run();
  const id = timers.setInterval(run, ms);
  return () => timers.clearInterval(id);
}

const KEY = "arjun.acked-emergencies";

/** Acknowledged ids, kept per browser so a reload does not ring again. Storage can be missing or throw. */
export function loadAcked(storage: Pick<Storage, "getItem"> | undefined): Set<number> {
  try {
    const raw = storage?.getItem(KEY);
    const ids = raw ? (JSON.parse(raw) as unknown) : [];
    return new Set(Array.isArray(ids) ? ids.filter((x): x is number => typeof x === "number") : []);
  } catch {
    return new Set();
  }
}

export function saveAcked(storage: Pick<Storage, "setItem"> | undefined, acked: ReadonlySet<number>): void {
  try {
    storage?.setItem(KEY, JSON.stringify([...acked].slice(-200)));
  } catch {
    // private mode / storage full: the alarm then rings again after a reload, which is the safe side
  }
}
