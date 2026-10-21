// Marathi display helpers for the elder screens. Pure functions so they are easy to test.

const DIGITS = "०१२३४५६७८९";
export const mr = (n: number | string): string => String(n).replace(/\d/g, (d) => DIGITS[Number(d)] ?? d);

const WEEKDAYS = ["रविवार", "सोमवार", "मंगळवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार"];
const MONTHS = [
  "जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून",
  "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर",
];

export function periodOfDay(hour: number): string {
  if (hour < 12) return "सकाळी";
  if (hour < 16) return "दुपारी";
  if (hour < 20) return "संध्याकाळी";
  return "रात्री";
}

/** "सकाळी १०:००" style. `hhmm` is "HH:MM" (24 h). */
export function timeLabel(hhmm: string): string {
  const [h = "0", m = "0"] = hhmm.split(":");
  const hour = Number(h);
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  return `${periodOfDay(hour)} ${mr(h12)}:${mr(m.padStart(2, "0"))}`;
}

/** "दुपारी ४ वाजता" for cards on the home screen. */
export function spokenTime(hhmm: string): string {
  const [h = "0", m = "0"] = hhmm.split(":");
  const hour = Number(h);
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  const minutes = Number(m) === 0 ? "" : `:${mr(m.padStart(2, "0"))}`;
  return `${periodOfDay(hour)} ${mr(h12)}${minutes} वाजता`;
}

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());

export function dayDiff(target: Date, now: Date): number {
  return Math.round((startOfDay(target).getTime() - startOfDay(now).getTime()) / 86_400_000);
}

export function weekday(d: Date): string {
  return WEEKDAYS[d.getDay()] ?? "";
}

/** "आज", "उद्या", "परवा" or the weekday + date. */
export function dayWord(target: Date, now: Date): string {
  const diff = dayDiff(target, now);
  if (diff === 0) return "आज";
  if (diff === 1) return "उद्या";
  if (diff === 2) return "परवा";
  return `${weekday(target)}, ${mr(target.getDate())} ${MONTHS[target.getMonth()] ?? ""}`;
}

export function dayBand(target: Date, now: Date): string {
  const diff = dayDiff(target, now);
  return diff >= 0 && diff <= 2 ? `${dayWord(target, now)} · ${weekday(target)}` : dayWord(target, now);
}

export function dateLine(now: Date): string {
  return `${weekday(now)}, ${mr(now.getDate())} ${MONTHS[now.getMonth()] ?? ""}`;
}

export function greeting(now: Date, honorific: string): string {
  const h = now.getHours();
  const word = h < 12 ? "शुभ सकाळ" : h < 17 ? "शुभ दुपार" : "शुभ संध्याकाळ";
  return `${word}, ${honorific}`;
}

export const isEvening = (now: Date): boolean => now.getHours() >= 17 || now.getHours() < 5;

/** Parse "YYYY-MM-DD" + "HH:MM" as local time (the API stores naive local time). */
export function localDate(dateIso: string, hhmm: string): Date {
  const [y = 0, mo = 1, d = 1] = dateIso.split("-").map(Number);
  const [h = 0, mi = 0] = hhmm.split(":").map(Number);
  return new Date(y, mo - 1, d, h, mi);
}

export function parseNaive(iso: string): Date {
  const [datePart = "", timePart = "00:00"] = iso.split("T");
  return localDate(datePart, timePart.slice(0, 5));
}
