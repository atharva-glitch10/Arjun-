/** "Last talked to Arjun": one honest line for the family. Pure, so it is tested.
 *
 * Arjun only sees the elder app: a quiet day can simply mean she did not use it. So the line never says
 * anything is wrong; past the cut-off it only suggests a call.
 */

export interface ActivityLine {
  text: string;
  /** ok = heard from today (or it is still early); quiet = nothing yet today, suggest a call; none = never. */
  tone: "ok" | "quiet" | "none";
}

/** Hours after the family-set wake time before a silent day is pointed out. */
export const QUIET_AFTER_WAKE_H = 3;

const clock = (d: Date) => d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();

function ago(then: Date, now: Date): string {
  const min = Math.max(0, Math.round((now.getTime() - then.getTime()) / 60_000));
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const h = Math.floor(min / 60);
  return `${h} h ${min % 60} min ago`;
}

function wakeAt(now: Date, wake: string): Date {
  const [h, m] = wake.split(":").map(Number);
  const d = new Date(now);
  d.setHours(Number.isFinite(h) ? (h as number) : 7, Number.isFinite(m) ? (m as number) : 0, 0, 0);
  return d;
}

export function activityLine(lastSeen: string | null, now: Date, wakeTime: string, name = "She"): ActivityLine {
  const quietFrom = new Date(wakeAt(now, wakeTime).getTime() + QUIET_AFTER_WAKE_H * 3_600_000);
  if (!lastSeen) {
    return { text: "Has not talked to Arjun yet.", tone: "none" };
  }
  const seen = new Date(lastSeen);
  if (sameDay(seen, now)) {
    return { text: `Last talked to Arjun at ${clock(seen)} (${ago(seen, now)}).`, tone: "ok" };
  }
  const when = `${seen.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" })} ${clock(seen)}`;
  if (now >= quietFrom) {
    return {
      text: `${name} has not talked to Arjun today (last: ${when}). She may just not have used it; a call would tell you.`,
      tone: "quiet",
    };
  }
  return { text: `Last talked to Arjun ${when}.`, tone: "ok" };
}
