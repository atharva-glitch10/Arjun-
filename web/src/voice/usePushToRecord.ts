import { RoomEvent } from "livekit-client";
import type { Room } from "livekit-client";
import { useCallback, useEffect, useRef, useState } from "react";

import { CLIP_ATTRIBUTE, CLIP_TOPIC, encodeWav, isTooShort, parseClipResult, recState, shouldAutoStop } from "./clip";
import type { ClipStatus, RecState } from "./clip";

const WORKLET = `class Tap extends AudioWorkletProcessor {
  process(inputs) { const c = inputs[0] && inputs[0][0]; if (c) this.port.postMessage(c.slice(0)); return true; }
}
registerProcessor("arjun-tap", Tap);`;

/** Allow enough time for the agent to transcribe a 30-second clip. */
const SEND_TIMEOUT_MS = 50_000;

export type RecHint = "" | "too_short" | "empty" | "error" | "mic";

export interface PushToRecord {
  state: RecState;
  seconds: number;
  hint: RecHint;
  /** What Arjun heard in the last clip, as soon as Prisma returned it. */
  transcript: string;
  canRetry: boolean;
  begin: () => Promise<void>;
  /** Stop and upload the whole clip once. */
  send: () => void;
  /** Stop and throw the clip away. */
  cancel: () => void;
  retry: () => void;
}

/** Tap to start, tap to send. No VAD or silence cut-off; automatically stop and send at 30 seconds. The mic is released on stop.
 *  `agentState` / `thinking` come from the voice session so the button stays off while Arjun works or speaks. */
export function usePushToRecord(room: Room | null, agentState: string | undefined, thinking: boolean): PushToRecord {
  const [recording, setRecording] = useState(false);
  const [sending, setSending] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [hint, setHint] = useState<RecHint>("");
  const [transcript, setTranscript] = useState("");
  const rec = useRef<{ stream: MediaStream; ctx: AudioContext; chunks: Float32Array[]; timer: number; t0: number } | null>(null);
  const pending = useRef("");
  const lastWav = useRef<Uint8Array | null>(null);
  const roomRef = useRef(room);
  roomRef.current = room;

  const release = useCallback(() => {
    const r = rec.current;
    rec.current = null;
    if (!r) return null;
    window.clearInterval(r.timer);
    r.stream.getTracks().forEach((t) => t.stop()); // the microphone is released here
    void r.ctx.close().catch(() => undefined);
    setRecording(false);
    return r;
  }, []);

  const upload = useCallback(async (wav: Uint8Array) => {
    const r = roomRef.current;
    if (!r || r.state !== "connected") {
      setHint("error");
      return;
    }
    const id = `${Date.now()}`;
    pending.current = id;
    lastWav.current = wav;
    setHint("");
    setSending(true);
    try {
      const writer = await r.localParticipant.streamBytes({ topic: CLIP_TOPIC, name: "clip.wav", mimeType: "audio/wav", attributes: { id } });
      await writer.write(wav);
      await writer.close();
    } catch {
      pending.current = "";
      setSending(false);
      setHint("error");
    }
  }, []);

  const finish = useCallback((doSend: boolean) => {
    const r = release();
    if (!r || !doSend) return;
    const { wav, seconds: len } = encodeWav(r.chunks, r.ctx.sampleRate);
    if (isTooShort(len)) {
      setHint("too_short");
      return;
    }
    void upload(wav);
  }, [release, upload]);

  const begin = useCallback(async () => {
    if (rec.current || sending) return;
    setHint("");
    setTranscript("");
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    } catch {
      setHint("mic");
      return;
    }
    try {
      const ctx = new AudioContext({ sampleRate: 16_000 }); // some browsers ignore it; encodeWav resamples
      const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
      await ctx.audioWorklet.addModule(url);
      URL.revokeObjectURL(url);
      const node = new AudioWorkletNode(ctx, "arjun-tap");
      const chunks: Float32Array[] = [];
      node.port.onmessage = (e: MessageEvent<Float32Array>) => chunks.push(e.data);
      ctx.createMediaStreamSource(stream).connect(node);
      const t0 = performance.now();
      const timer = window.setInterval(() => {
        const s = (performance.now() - t0) / 1000;
        setSeconds(s);
        if (shouldAutoStop(s)) finish(true); // the 30 s cap: stop and send
      }, 200);
      rec.current = { stream, ctx, chunks, timer, t0 };
      setSeconds(0);
      setRecording(true);
    } catch {
      stream.getTracks().forEach((t) => t.stop());
      setHint("mic");
    }
  }, [finish, sending]);

  // the agent's answer to the clip: her words (shown at once), or a hint
  useEffect(() => {
    if (!room) return;
    const on = (changed: Record<string, string>) => {
      const res = parseClipResult(changed[CLIP_ATTRIBUTE]);
      if (!res || res.id !== pending.current) return;
      pending.current = "";
      setSending(false);
      const status: ClipStatus = res.status;
      if (status === "heard") {
        setTranscript(res.text);
        lastWav.current = null;
      } else setHint(status);
    };
    room.on(RoomEvent.ParticipantAttributesChanged, on);
    return () => {
      room.off(RoomEvent.ParticipantAttributesChanged, on);
    };
  }, [room]);

  // no answer from the agent (old worker, lost message, dropped room): leave "sending" with a retry instead of hanging
  useEffect(() => {
    if (!sending) return;
    const id = window.setTimeout(() => {
      pending.current = "";
      setSending(false);
      setHint("error");
    }, SEND_TIMEOUT_MS);
    return () => window.clearTimeout(id);
  }, [sending]);

  useEffect(() => {
    if (!room) return;
    const drop = () => {
      if (!pending.current) return;
      pending.current = "";
      setSending(false);
      setHint("error");
    };
    room.on(RoomEvent.Disconnected, drop);
    return () => {
      room.off(RoomEvent.Disconnected, drop);
    };
  }, [room]);

  // a dropped room or a closed page never leaves the mic open
  useEffect(() => () => void release(), [release]);

  return {
    state: recState({ recording, sending, thinking, agentState }),
    seconds,
    hint,
    transcript,
    canRetry: hint === "error" && lastWav.current !== null,
    begin,
    send: () => finish(true),
    cancel: () => finish(false),
    retry: () => {
      if (lastWav.current) void upload(lastWav.current);
    },
  };
}
