// Display helpers for the elder screens (Marathi by default; follows setElderLang for the other nine languages). Pure functions so they are easy to test.

import { getElderLang } from "./strings";
import type { ElderLang } from "./strings";

const DIGITS = "०१२३४५६७८९";
/** Marathi numerals (the original look). Other languages show 0-9. */
export const mr = (n: number | string): string => String(n).replace(/\d/g, (d) => DIGITS[Number(d)] ?? d);
const num = (n: number | string): string => (getElderLang() === "mr" ? mr(n) : String(n));

interface Pack {
  weekdays: string[]; // Sunday first (JS getDay)
  months: string[];
  periods: [string, string, string, string]; // morning, afternoon, evening, night
  day: [string, string, string]; // today, tomorrow, day after
  at: string; // word after a clock time ("वाजता")
}
const pack = (weekdays: string[], months: string[], periods: Pack["periods"], day: Pack["day"], at: string): Pack => ({
  weekdays, months, periods, day, at,
});
// bn..te are UNVERIFIED by a native speaker.
const PACKS: Record<ElderLang, Pack> = {
  mr: pack(["रविवार", "सोमवार", "मंगळवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार"],
    ["जानेवारी", "फेब्रुवारी", "मार्च", "एप्रिल", "मे", "जून", "जुलै", "ऑगस्ट", "सप्टेंबर", "ऑक्टोबर", "नोव्हेंबर", "डिसेंबर"],
    ["सकाळी", "दुपारी", "संध्याकाळी", "रात्री"], ["आज", "उद्या", "परवा"], " वाजता"),
  hi: pack(["रविवार", "सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार"],
    ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
    ["सुबह", "दोपहर", "शाम", "रात"], ["आज", "कल", "परसों"], " बजे"),
  en: pack(["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    ["morning", "afternoon", "evening", "night"], ["today", "tomorrow", "day after tomorrow"], ""),
  bn: pack(["রবিবার", "সোমবার", "মঙ্গলবার", "বুধবার", "বৃহস্পতিবার", "শুক্রবার", "শনিবার"],
    ["জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর"],
    ["সকাল", "দুপুর", "সন্ধ্যা", "রাত"], ["আজ", "কাল", "পরশু"], " টায়"),
  gu: pack(["રવિવાર", "સોમવાર", "મંગળવાર", "બુધવાર", "ગુરુવાર", "શુક્રવાર", "શનિવાર"],
    ["જાન્યુઆરી", "ફેબ્રુઆરી", "માર્ચ", "એપ્રિલ", "મે", "જૂન", "જુલાઈ", "ઑગસ્ટ", "સપ્ટેમ્બર", "ઑક્ટોબર", "નવેમ્બર", "ડિસેમ્બર"],
    ["સવારે", "બપોરે", "સાંજે", "રાત્રે"], ["આજે", "કાલે", "પરમ દિવસે"], " વાગ્યે"),
  kn: pack(["ಭಾನುವಾರ", "ಸೋಮವಾರ", "ಮಂಗಳವಾರ", "ಬುಧವಾರ", "ಗುರುವಾರ", "ಶುಕ್ರವಾರ", "ಶನಿವಾರ"],
    ["ಜನವರಿ", "ಫೆಬ್ರವರಿ", "ಮಾರ್ಚ್", "ಏಪ್ರಿಲ್", "ಮೇ", "ಜೂನ್", "ಜುಲೈ", "ಆಗಸ್ಟ್", "ಸೆಪ್ಟೆಂಬರ್", "ಅಕ್ಟೋಬರ್", "ನವೆಂಬರ್", "ಡಿಸೆಂಬರ್"],
    ["ಬೆಳಿಗ್ಗೆ", "ಮಧ್ಯಾಹ್ನ", "ಸಂಜೆ", "ರಾತ್ರಿ"], ["ಇಂದು", "ನಾಳೆ", "ನಾಡಿದ್ದು"], " ಗಂಟೆಗೆ"),
  ml: pack(["ഞായറാഴ്ച", "തിങ്കളാഴ്ച", "ചൊവ്വാഴ്ച", "ബുധനാഴ്ച", "വ്യാഴാഴ്ച", "വെള്ളിയാഴ്ച", "ശനിയാഴ്ച"],
    ["ജനുവരി", "ഫെബ്രുവരി", "മാർച്ച്", "ഏപ്രിൽ", "മേയ്", "ജൂൺ", "ജൂലൈ", "ഓഗസ്റ്റ്", "സെപ്റ്റംബർ", "ഒക്ടോബർ", "നവംബർ", "ഡിസംബർ"],
    ["രാവിലെ", "ഉച്ചയ്ക്ക്", "വൈകുന്നേരം", "രാത്രി"], ["ഇന്ന്", "നാളെ", "മറ്റന്നാൾ"], " മണിക്ക്"),
  pa: pack(["ਐਤਵਾਰ", "ਸੋਮਵਾਰ", "ਮੰਗਲਵਾਰ", "ਬੁੱਧਵਾਰ", "ਵੀਰਵਾਰ", "ਸ਼ੁੱਕਰਵਾਰ", "ਸ਼ਨੀਵਾਰ"],
    ["ਜਨਵਰੀ", "ਫ਼ਰਵਰੀ", "ਮਾਰਚ", "ਅਪ੍ਰੈਲ", "ਮਈ", "ਜੂਨ", "ਜੁਲਾਈ", "ਅਗਸਤ", "ਸਤੰਬਰ", "ਅਕਤੂਬਰ", "ਨਵੰਬਰ", "ਦਸੰਬਰ"],
    ["ਸਵੇਰੇ", "ਦੁਪਹਿਰ", "ਸ਼ਾਮ", "ਰਾਤ"], ["ਅੱਜ", "ਕੱਲ੍ਹ", "ਪਰਸੋਂ"], " ਵਜੇ"),
  ta: pack(["ஞாயிறு", "திங்கள்", "செவ்வாய்", "புதன்", "வியாழன்", "வெள்ளி", "சனி"],
    ["ஜனவரி", "பிப்ரவரி", "மார்ச்", "ஏப்ரல்", "மே", "ஜூன்", "ஜூலை", "ஆகஸ்ட்", "செப்டம்பர்", "அக்டோபர்", "நவம்பர்", "டிசம்பர்"],
    ["காலை", "மதியம்", "மாலை", "இரவு"], ["இன்று", "நாளை", "நாளை மறுநாள்"], " மணிக்கு"),
  te: pack(["ఆదివారం", "సోమవారం", "మంగళవారం", "బుధవారం", "గురువారం", "శుక్రవారం", "శనివారం"],
    ["జనవరి", "ఫిబ్రవరి", "మార్చి", "ఏప్రిల్", "మే", "జూన్", "జూలై", "ఆగస్టు", "సెప్టెంబర్", "అక్టోబర్", "నవంబర్", "డిసెంబర్"],
    ["ఉదయం", "మధ్యాహ్నం", "సాయంత్రం", "రాత్రి"], ["ఈరోజు", "రేపు", "ఎల్లుండి"], " గంటలకు"),
};
const P = (): Pack => PACKS[getElderLang()];

export function periodOfDay(hour: number): string {
  const p = P().periods;
  return hour < 12 ? p[0] : hour < 16 ? p[1] : hour < 20 ? p[2] : p[3];
}

/** "सकाळी १०:००" style. `hhmm` is "HH:MM" (24 h). */
export function timeLabel(hhmm: string): string {
  const [h = "0", m = "0"] = hhmm.split(":");
  const hour = Number(h);
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  return `${periodOfDay(hour)} ${num(h12)}:${num(m.padStart(2, "0"))}`;
}

/** "दुपारी ४ वाजता" for cards on the home screen. */
export function spokenTime(hhmm: string): string {
  const [h = "0", m = "0"] = hhmm.split(":");
  const hour = Number(h);
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  const minutes = Number(m) === 0 ? "" : `:${num(m.padStart(2, "0"))}`;
  return `${periodOfDay(hour)} ${num(h12)}${minutes}${P().at}`;
}

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());

export function dayDiff(target: Date, now: Date): number {
  return Math.round((startOfDay(target).getTime() - startOfDay(now).getTime()) / 86_400_000);
}

export function weekday(d: Date): string {
  return P().weekdays[d.getDay()] ?? "";
}

/** "आज", "उद्या", "परवा" or the weekday + date. */
export function dayWord(target: Date, now: Date): string {
  const diff = dayDiff(target, now);
  if (diff >= 0 && diff <= 2) return P().day[diff] ?? "";
  return `${weekday(target)}, ${num(target.getDate())} ${P().months[target.getMonth()] ?? ""}`;
}

export function dayBand(target: Date, now: Date): string {
  const diff = dayDiff(target, now);
  return diff >= 0 && diff <= 2 ? `${dayWord(target, now)} · ${weekday(target)}` : dayWord(target, now);
}

export function dateLine(now: Date): string {
  return `${weekday(now)}, ${num(now.getDate())} ${P().months[now.getMonth()] ?? ""}`;
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
