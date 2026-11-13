import { describe, expect, it } from "vitest";

import { MAX_CLIP_S, MIN_CLIP_S, SAMPLE_RATE, encodeWav, isTooShort, parseClipResult, recState, shouldAutoStop } from "./clip";

const secs = (s: number, rate = SAMPLE_RATE) => [new Float32Array(Math.floor(s * rate)).fill(0.1)];

describe("push-to-record", () => {
  it("send: a 2 s clip is one 16 kHz mono WAV", () => {
    const { wav, seconds } = encodeWav(secs(2), SAMPLE_RATE);
    const v = new DataView(wav.buffer);
    expect(String.fromCharCode(...wav.slice(0, 4))).toBe("RIFF");
    expect(v.getUint32(24, true)).toBe(SAMPLE_RATE);
    expect(v.getUint16(22, true)).toBe(1);
    expect(seconds).toBeCloseTo(2, 2);
    expect(wav.length).toBe(44 + 2 * SAMPLE_RATE * 2);
  });

  it("resamples a 48 kHz capture down to 16 kHz", () => {
    const { seconds } = encodeWav(secs(1, 48_000), 48_000);
    expect(seconds).toBeCloseTo(1, 2);
  });

  it("too short: under 0.3 s is not sent", () => {
    expect(isTooShort(MIN_CLIP_S - 0.01)).toBe(true);
    expect(isTooShort(MIN_CLIP_S)).toBe(false);
    expect(encodeWav(secs(0.2), SAMPLE_RATE).seconds).toBeLessThan(MIN_CLIP_S);
  });

  it("30 s cap: auto-stops at the cap and never writes more than 30 s", () => {
    expect(shouldAutoStop(29.9)).toBe(false);
    expect(shouldAutoStop(MAX_CLIP_S)).toBe(true);
    expect(encodeWav(secs(35), SAMPLE_RATE).seconds).toBe(MAX_CLIP_S);
  });

  it("states: record only when idle; sending / thinking / speaking all block it", () => {
    expect(recState({ recording: false, sending: false, thinking: false, agentState: "listening" })).toBe("idle");
    expect(recState({ recording: true, sending: false, thinking: false })).toBe("recording");
    expect(recState({ recording: false, sending: true, thinking: false })).toBe("sending");
    expect(recState({ recording: false, sending: false, thinking: true })).toBe("thinking");
    expect(recState({ recording: false, sending: false, thinking: false, agentState: "speaking" })).toBe("speaking");
  });

  it("empty transcript and errors come back as statuses, garbage is ignored", () => {
    expect(parseClipResult('{"id":"a","status":"empty","text":"","lang":""}')?.status).toBe("empty");
    expect(parseClipResult('{"id":"a","status":"error"}')?.status).toBe("error");
    expect(parseClipResult('{"id":"a","status":"heard","text":"नमस्कार","lang":"mr-IN"}')?.text).toBe("नमस्कार");
    expect(parseClipResult("nope")).toBeNull();
    expect(parseClipResult(undefined)).toBeNull();
  });
});
