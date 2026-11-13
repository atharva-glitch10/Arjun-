/** Push-to-record helpers. Pure on purpose (tested): the recorder hook only wires them to the microphone.
 *  The clip is ONE whole WAV (16 kHz, mono, 16-bit) sent on the LiveKit byte-stream topic "arjun.clip". */

export const CLIP_TOPIC = "arjun.clip";
export const CLIP_ATTRIBUTE = "arjun.clip";
export const SAMPLE_RATE = 16_000;
/** Shorter than this is not sent ("too short"). */
export const MIN_CLIP_S = 0.3;
/** Auto-stop and send here (Gnani's REST limit is 30 s). */
export const MAX_CLIP_S = 30;

export type RecState = "idle" | "recording" | "sending" | "thinking" | "speaking";
export type ClipStatus = "heard" | "too_short" | "empty" | "error";
export interface ClipResult {
  id: string;
  status: ClipStatus;
  text: string;
  lang: string;
}

export const shouldAutoStop = (seconds: number): boolean => seconds >= MAX_CLIP_S;
export const isTooShort = (seconds: number): boolean => seconds < MIN_CLIP_S;

/** The recorder's one state. Record is allowed only in "idle". */
export function recState(p: { recording: boolean; sending: boolean; thinking: boolean; agentState?: string }): RecState {
  if (p.recording) return "recording";
  if (p.sending) return "sending";
  if (p.agentState === "speaking") return "speaking";
  if (p.thinking || p.agentState === "thinking") return "thinking";
  return "idle";
}

/** Join the Float32 chunks, resample to 16 kHz when the browser could not give it, keep at most MAX_CLIP_S, write a WAV. */
export function encodeWav(chunks: Float32Array[], inRate: number): { wav: Uint8Array; seconds: number } {
  let total = 0;
  for (const c of chunks) total += c.length;
  const joined = new Float32Array(total);
  let at = 0;
  for (const c of chunks) {
    joined.set(c, at);
    at += c.length;
  }
  const ratio = inRate / SAMPLE_RATE;
  const outLen = Math.min(Math.floor(total / ratio), MAX_CLIP_S * SAMPLE_RATE);
  const wav = new Uint8Array(44 + outLen * 2);
  const view = new DataView(wav.buffer);
  const text = (o: number, s: string) => [...s].forEach((ch, i) => view.setUint8(o + i, ch.charCodeAt(0)));
  text(0, "RIFF");
  view.setUint32(4, 36 + outLen * 2, true);
  text(8, "WAVEfmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, SAMPLE_RATE, true);
  view.setUint32(28, SAMPLE_RATE * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, outLen * 2, true);
  for (let i = 0; i < outLen; i++) {
    const pos = i * ratio;
    const lo = Math.floor(pos);
    const frac = pos - lo;
    const v = (joined[lo] ?? 0) * (1 - frac) + (joined[Math.min(lo + 1, total - 1)] ?? 0) * frac;
    view.setInt16(44 + i * 2, Math.round(Math.max(-1, Math.min(1, v)) * 32767), true);
  }
  return { wav, seconds: outLen / SAMPLE_RATE };
}

/** The agent's "arjun.clip" attribute (JSON), or null if it is missing or malformed. */
export function parseClipResult(raw: string | undefined): ClipResult | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as Partial<ClipResult>;
    if (typeof v.id !== "string" || !["heard", "too_short", "empty", "error"].includes(String(v.status))) return null;
    return { id: v.id, status: v.status as ClipStatus, text: typeof v.text === "string" ? v.text : "", lang: typeof v.lang === "string" ? v.lang : "" };
  } catch {
    return null;
  }
}
