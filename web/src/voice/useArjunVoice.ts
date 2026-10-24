import { ParticipantKind, Room, RoomEvent, Track } from "livekit-client";
import type { Participant, RemoteParticipant } from "livekit-client";
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api";
import { parseAttributes } from "./state";
import type { AgentScreen, AgentState, Failure, Phase, VoiceSnapshot } from "./state";

/** Give the agent this long to come up after joining before telling the elder plainly. */
export const READY_TIMEOUT_MS = 20_000;
/** A connection that is only "reconnecting" for this long counts as dropped. */
export const RECONNECT_GIVE_UP_MS = 8_000;

export interface ArjunVoice {
  snapshot: VoiceSnapshot;
  /** The exact line Arjun is speaking ("arjun.reply"). */
  reply: string;
  /** What Arjun heard the elder say (live transcription), best effort. */
  heard: string;
  /** Milliseconds from the tap to the agent listening, for the last session (console + here). */
  readyMs: number | null;
  /** Tap बोला: fetch a token, join a fresh room, publish the mic. Must be called from a click. */
  start: () => Promise<void>;
  /** Leave the room (OK / back). */
  stop: () => void;
  /** A tapped answer ("हो", "नाही"): goes to the agent as text and takes the same path as speech. */
  sendText: (text: string) => Promise<void>;
  dismissSafety: () => void;
}

const isAgent = (p: Participant): p is RemoteParticipant => p.kind === ParticipantKind.AGENT;

export function useArjunVoice(userId: number): ArjunVoice {
  const [phase, setPhase] = useState<Phase>("idle");
  const [failure, setFailure] = useState<Failure | undefined>();
  const [agentState, setAgentState] = useState<AgentState | undefined>();
  const [screen, setScreen] = useState<AgentScreen | undefined>();
  const [turn, setTurn] = useState(0);
  const [safetyDismissedTurn, setSafetyDismissedTurn] = useState(0);
  const [reply, setReply] = useState("");
  const [heard, setHeard] = useState("");
  const [readyMs, setReadyMs] = useState<number | null>(null);

  const room = useRef<Room | null>(null);
  const stopping = useRef(false);
  const timers = useRef<number[]>([]);
  const phaseRef = useRef<Phase>("idle");
  const turnRef = useRef(0);

  const setPhaseBoth = (p: Phase) => {
    phaseRef.current = p;
    setPhase(p);
  };
  const clearTimers = () => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
  };

  const teardown = useCallback(() => {
    clearTimers();
    const r = room.current;
    room.current = null;
    if (r) {
      stopping.current = true;
      void r.disconnect();
    }
  }, []);

  const fail = useCallback(
    (why: Failure) => {
      if (phaseRef.current === "failed" || phaseRef.current === "idle") return;
      setFailure(why);
      setPhaseBoth("failed");
      teardown();
    },
    [teardown],
  );

  const applyAgent = useCallback((p: Participant, t0: number) => {
    const a = parseAttributes(p.attributes);
    setAgentState(a.agentState);
    if (a.screen) setScreen(a.screen);
    if (a.turn > turnRef.current) {
      turnRef.current = a.turn;
      setTurn(a.turn);
    }
    const text = p.attributes["arjun.reply"];
    if (typeof text === "string") setReply(text);
    if (a.agentState === "listening" && phaseRef.current === "waiting") {
      const ms = Math.round(performance.now() - t0);
      console.info(`[arjun] ready ${ms} ms after the tap`);
      setReadyMs(ms);
      clearTimers();
      setPhaseBoth("live");
    }
  }, []);

  const start = useCallback(async () => {
    if (phaseRef.current === "connecting" || phaseRef.current === "waiting" || phaseRef.current === "live") return;
    const t0 = performance.now();
    stopping.current = false;
    turnRef.current = 0;
    setFailure(undefined);
    setAgentState(undefined);
    setScreen(undefined);
    setTurn(0);
    setReply("");
    setHeard("");
    setSafetyDismissedTurn(0);
    setPhaseBoth("connecting");

    let tok;
    try {
      tok = await api.livekitToken(userId);
    } catch {
      fail("connect");
      return;
    }
    const tToken = performance.now();

    // Browser echo cancellation and noise suppression stay ON: the agent has no noise filter yet
    // (CLAUDE.md open question 6), and without echo cancellation Arjun would hear himself on a speaker.
    const r = new Room({
      audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    room.current = r;

    const agentOf = () => Array.from(r.remoteParticipants.values()).find(isAgent);

    r.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === Track.Kind.Audio) {
        const el = track.attach();
        el.style.display = "none";
        document.body.appendChild(el);
      }
    });
    r.on(RoomEvent.TrackUnsubscribed, (track) => track.detach().forEach((el) => el.remove()));
    r.on(RoomEvent.ParticipantAttributesChanged, (_changed, p) => {
      if (isAgent(p)) applyAgent(p, t0);
    });
    r.on(RoomEvent.ParticipantConnected, (p) => {
      if (isAgent(p)) applyAgent(p, t0);
    });
    r.on(RoomEvent.ParticipantDisconnected, (p) => {
      if (isAgent(p) && !stopping.current) fail("dropped");
    });
    r.on(RoomEvent.Reconnecting, () => {
      timers.current.push(window.setTimeout(() => fail("dropped"), RECONNECT_GIVE_UP_MS));
    });
    r.on(RoomEvent.Reconnected, () => clearTimers());
    r.on(RoomEvent.Disconnected, () => {
      if (!stopping.current) fail("dropped");
    });
    try {
      r.registerTextStreamHandler("lk.transcription", async (reader, info) => {
        const text = (await reader.readAll()).trim();
        if (text && info.identity === r.localParticipant.identity) setHeard(text);
      });
    } catch {
      // live transcription is a nicety; the screens work without it
    }

    try {
      await r.connect(tok.url, tok.token);
    } catch {
      fail("connect");
      return;
    }
    const tConnected = performance.now();
    setPhaseBoth("waiting");
    timers.current.push(window.setTimeout(() => fail("timeout"), READY_TIMEOUT_MS));
    try {
      await r.startAudio(); // inside the tap's user gesture, so playback is allowed
      await r.localParticipant.setMicrophoneEnabled(true);
    } catch {
      fail("mic");
      return;
    }
    console.info(
      `[arjun] token ${Math.round(tToken - t0)} ms, joined ${Math.round(tConnected - tToken)} ms, mic on ${Math.round(performance.now() - tConnected)} ms`,
    );
    const a = agentOf(); // the agent may already be in the room
    if (a) applyAgent(a, t0);
  }, [applyAgent, fail, userId]);

  const stop = useCallback(() => {
    teardown();
    setPhaseBoth("idle");
    setFailure(undefined);
    setAgentState(undefined);
    setScreen(undefined);
    setTurn(0);
    turnRef.current = 0;
    setReply("");
    setHeard("");
  }, [teardown]);

  const sendText = useCallback(async (text: string) => {
    const r = room.current;
    if (!r || phaseRef.current !== "live") return;
    await r.localParticipant.sendText(text, { topic: "lk.chat" });
  }, []);

  const dismissSafety = useCallback(() => setSafetyDismissedTurn(turnRef.current), []);

  useEffect(() => teardown, [teardown]);

  const snapshot: VoiceSnapshot = { phase, failure, agentState, screen, turn, safetyDismissedTurn };
  return { snapshot, reply, heard, readyMs, start, stop, sendText, dismissSafety };
}
