// Browser speech APIs stand in for LiveKit + Gnani until credentials exist (see README).
interface RecognitionResultEvent {
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>;
}
interface Recognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: RecognitionResultEvent) => void) | null;
  onerror: ((e: { error?: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
}
type RecognitionCtor = new () => Recognition;
interface SpeechWindow {
  SpeechRecognition?: RecognitionCtor;
  webkitSpeechRecognition?: RecognitionCtor;
}

const LANG_TAG: Record<string, string> = { mr: "mr-IN", hi: "hi-IN", en: "en-IN" };

export const recognitionAvailable = (): boolean => {
  const w = window as unknown as SpeechWindow;
  return Boolean(w.SpeechRecognition ?? w.webkitSpeechRecognition);
};

export interface Listener {
  stop: () => void;
}

/** Start one listening session. `onText` gets the running transcript (interim, then final). */
export function startListening(
  onText: (text: string, final: boolean) => void,
  onEnd: (failed: boolean) => void,
  lang = "mr",
): Listener | null {
  const w = window as unknown as SpeechWindow;
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  if (!Ctor) return null;
  const rec = new Ctor();
  let failed = false;
  rec.lang = LANG_TAG[lang] ?? "mr-IN";
  rec.interimResults = true;
  rec.continuous = false;
  rec.onresult = (e) => {
    let text = "";
    let final = true;
    for (let i = 0; i < e.results.length; i++) {
      const r = e.results[i];
      if (!r) continue;
      text += r[0]?.transcript ?? "";
      if (!r.isFinal) final = false;
    }
    onText(text.trim(), final);
  };
  rec.onerror = (e) => {
    console.warn("speech recognition error:", e.error, "lang:", rec.lang);
    failed = true;
  };
  rec.onend = () => onEnd(failed);
  try {
    rec.start();
  } catch {
    return null;
  }
  return { stop: () => rec.stop() };
}

/** Speak `text`; `onDone` fires when speech ends (or at once when speech is unavailable). */
export function speak(text: string, lang = "mr", onDone?: () => void): void {
  if (!("speechSynthesis" in window) || !text) {
    onDone?.();
    return;
  }
  const u = new SpeechSynthesisUtterance(text);
  u.lang = LANG_TAG[lang] ?? "mr-IN";
  if (onDone) {
    u.onend = onDone;
    u.onerror = onDone;
  }
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(u);
}

export function stopSpeaking(): void {
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
}
