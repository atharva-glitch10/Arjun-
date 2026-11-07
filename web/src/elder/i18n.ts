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
