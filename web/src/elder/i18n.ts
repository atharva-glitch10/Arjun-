export type ElderLanguage = "mr" | "hi" | "en";

export const ELDER_STRINGS: Record<ElderLanguage, { greeting: string; help: string; retry: string }> = {
  mr: { greeting: "शुभ सकाळ", help: "मदत हवी आहे?", retry: "काहीतरी चुकलं. पुन्हा प्रयत्न करा." },
  hi: { greeting: "सुप्रभात", help: "मदद चाहिए?", retry: "कुछ गलत हुआ। फिर से कोशिश करें।" },
  en: { greeting: "Good morning", help: "Do you need help?", retry: "Something went wrong. Please try again." },
};

export function elderLanguage(language: string | undefined): ElderLanguage {
  return language === "mr" || language === "hi" ? language : "en";
}

export function elderText(language: string | undefined) {
  return ELDER_STRINGS[elderLanguage(language)];
}

/** Greeting that fits the time of day ("शुभ सकाळ" at 10 PM was wrong). Night uses a plain hello, never "good night". */
export function timeGreeting(language: ElderLanguage, hour: number): string {
  const slot = hour >= 4 && hour < 12 ? 0 : hour < 17 && hour >= 12 ? 1 : hour < 21 && hour >= 17 ? 2 : 3;
  const words: Record<ElderLanguage, [string, string, string, string]> = {
    mr: ["शुभ सकाळ", "नमस्कार", "शुभ संध्याकाळ", "नमस्कार"],
    hi: ["सुप्रभात", "नमस्ते", "शुभ संध्या", "नमस्ते"],
    en: ["Good morning", "Good afternoon", "Good evening", "Hello"],
  };
  return (words[language] ?? words.mr)[slot];
}

export type OrbLabelState = "idle" | "connecting" | "listening" | "thinking" | "speaking";

/** What the orb is doing, in words (screen readers and captions). */
export const ORB_LABELS: Record<ElderLanguage, Record<OrbLabelState, string>> = {
  mr: { idle: "अर्जुन तयार आहे", connecting: "जोडत आहे", listening: "मी ऐकतोय", thinking: "विचार करतोय", speaking: "अर्जुन बोलतोय" },
  hi: { idle: "अर्जुन तैयार है", connecting: "जुड़ रहा है", listening: "मैं सुन रहा हूँ", thinking: "सोच रहा हूँ", speaking: "अर्जुन बोल रहा है" },
  en: { idle: "Arjun is ready", connecting: "Connecting", listening: "Listening", thinking: "Thinking", speaking: "Arjun is speaking" },
};

export function orbLabel(language: string | undefined, state: OrbLabelState): string {
  return ORB_LABELS[elderLanguage(language)][state];
}
