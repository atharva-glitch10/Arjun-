import { ELDER_LANGUAGES, isElderLang } from "./strings";
import type { ElderLang } from "./strings";

/** All ten Gnani languages (mr hi en bn gu kn ml pa ta te). bn..te are UNVERIFIED by a native speaker. */
export type ElderLanguage = ElderLang;

const L = ELDER_LANGUAGES;
const by = <T,>(...v: T[]): Record<ElderLanguage, T> => Object.fromEntries(L.map((l, i) => [l, v[i]])) as Record<ElderLanguage, T>;

export const ELDER_STRINGS: Record<ElderLanguage, { greeting: string; help: string; retry: string }> = by(
  { greeting: "शुभ सकाळ", help: "मदत हवी आहे?", retry: "काहीतरी चुकलं. पुन्हा प्रयत्न करा." },
  { greeting: "सुप्रभात", help: "मदद चाहिए?", retry: "कुछ गलत हुआ। फिर से कोशिश करें।" },
  { greeting: "Good morning", help: "Do you need help?", retry: "Something went wrong. Please try again." },
  { greeting: "শুভ সকাল", help: "সাহায্য লাগবে?", retry: "কিছু গোলমাল হয়েছে। আবার চেষ্টা করুন।" },
  { greeting: "સુપ્રભાત", help: "મદદ જોઈએ છે?", retry: "કંઈક ગડબડ થઈ. ફરી પ્રયત્ન કરો." },
  { greeting: "ಶುಭೋದಯ", help: "ಸಹಾಯ ಬೇಕೇ?", retry: "ಏನೋ ತೊಂದರೆಯಾಯಿತು. ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ." },
  { greeting: "സുപ്രഭാതം", help: "സഹായം വേണോ?", retry: "എന്തോ പിശക് പറ്റി. വീണ്ടും ശ്രമിക്കൂ." },
  { greeting: "ਸ਼ੁਭ ਸਵੇਰ", help: "ਮਦਦ ਚਾਹੀਦੀ ਹੈ?", retry: "ਕੁਝ ਗੜਬੜ ਹੋ ਗਈ। ਫਿਰ ਕੋਸ਼ਿਸ਼ ਕਰੋ।" },
  { greeting: "காலை வணக்கம்", help: "உதவி வேண்டுமா?", retry: "ஏதோ தவறு ஏற்பட்டது. மீண்டும் முயலுங்கள்." },
  { greeting: "శుభోదయం", help: "సహాయం కావాలా?", retry: "ఏదో తప్పు జరిగింది. మళ్లీ ప్రయత్నించండి." },
);

/** Her language if it is one of the ten, else English. */
export function elderLanguage(language: string | undefined): ElderLanguage {
  return isElderLang(language) ? language : "en";
}

export function elderText(language: string | undefined) {
  return ELDER_STRINGS[elderLanguage(language)];
}

/** Greeting that fits the time of day ("शुभ सकाळ" at 10 PM was wrong). Night uses a plain hello, never "good night". */
export function timeGreeting(language: ElderLanguage, hour: number): string {
  const slot = hour >= 4 && hour < 12 ? 0 : hour < 17 && hour >= 12 ? 1 : hour < 21 && hour >= 17 ? 2 : 3;
  const words: Record<ElderLanguage, [string, string, string, string]> = by(
    ["शुभ सकाळ", "नमस्कार", "शुभ संध्याकाळ", "नमस्कार"],
    ["सुप्रभात", "नमस्ते", "शुभ संध्या", "नमस्ते"],
    ["Good morning", "Good afternoon", "Good evening", "Hello"],
    ["শুভ সকাল", "নমস্কার", "শুভ সন্ধ্যা", "নমস্কার"],
    ["સુપ્રભાત", "નમસ્તે", "શુભ સંધ્યા", "નમસ્તે"],
    ["ಶುಭೋದಯ", "ನಮಸ್ಕಾರ", "ಶುಭ ಸಂಜೆ", "ನಮಸ್ಕಾರ"],
    ["സുപ്രഭാതം", "നമസ്കാരം", "ശുഭ സായാഹ്നം", "നമസ്കാരം"],
    ["ਸ਼ੁਭ ਸਵੇਰ", "ਸਤ ਸ੍ਰੀ ਅਕਾਲ", "ਸ਼ੁਭ ਸ਼ਾਮ", "ਸਤ ਸ੍ਰੀ ਅਕਾਲ"],
    ["காலை வணக்கம்", "வணக்கம்", "மாலை வணக்கம்", "வணக்கம்"],
    ["శుభోదయం", "నమస్కారం", "శుభ సాయంత్రం", "నమస్కారం"],
  );
  return (words[language] ?? words.mr)[slot];
}

export type OrbLabelState = "idle" | "connecting" | "listening" | "thinking" | "speaking";

type OrbRow = Record<OrbLabelState, string>;
const orb = (idle: string, connecting: string, listening: string, thinking: string, speaking: string): OrbRow => ({
  idle, connecting, listening, thinking, speaking,
});

/** What the orb is doing, in words (screen readers and captions). */
export const ORB_LABELS: Record<ElderLanguage, OrbRow> = by(
  orb("अर्जुन तयार आहे", "जोडत आहे", "मी ऐकतोय", "विचार करतोय", "अर्जुन बोलतोय"),
  orb("अर्जुन तैयार है", "जुड़ रहा है", "मैं सुन रहा हूँ", "सोच रहा हूँ", "अर्जुन बोल रहा है"),
  orb("Arjun is ready", "Connecting", "Listening", "Thinking", "Arjun is speaking"),
  orb("অর্জুন তৈরি", "যুক্ত হচ্ছে", "আমি শুনছি", "ভাবছি", "অর্জুন বলছে"),
  orb("અર્જુન તૈયાર છે", "જોડાઈ રહ્યું છે", "હું સાંભળું છું", "વિચારું છું", "અર્જુન બોલે છે"),
  orb("ಅರ್ಜುನ್ ಸಿದ್ಧ", "ಸಂಪರ್ಕಿಸುತ್ತಿದೆ", "ನಾನು ಕೇಳುತ್ತಿದ್ದೇನೆ", "ಯೋಚಿಸುತ್ತಿದ್ದೇನೆ", "ಅರ್ಜುನ್ ಮಾತನಾಡುತ್ತಿದ್ದಾನೆ"),
  orb("അർജുൻ തയ്യാർ", "ബന്ധിപ്പിക്കുന്നു", "ഞാൻ കേൾക്കുന്നു", "ആലോചിക്കുന്നു", "അർജുൻ സംസാരിക്കുന്നു"),
  orb("ਅਰਜੁਨ ਤਿਆਰ ਹੈ", "ਜੁੜ ਰਿਹਾ ਹੈ", "ਮੈਂ ਸੁਣ ਰਿਹਾ ਹਾਂ", "ਸੋਚ ਰਿਹਾ ਹਾਂ", "ਅਰਜੁਨ ਬੋਲ ਰਿਹਾ ਹੈ"),
  orb("அர்ஜுன் தயார்", "இணைகிறது", "நான் கேட்கிறேன்", "யோசிக்கிறேன்", "அர்ஜுன் பேசுகிறார்"),
  orb("అర్జున్ సిద్ధం", "కలుస్తోంది", "నేను వింటున్నాను", "ఆలోచిస్తున్నాను", "అర్జున్ మాట్లాడుతున్నాడు"),
);

export function orbLabel(language: string | undefined, state: OrbLabelState): string {
  return ORB_LABELS[elderLanguage(language)][state];
}
