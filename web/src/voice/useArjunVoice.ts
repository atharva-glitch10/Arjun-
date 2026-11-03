import { ParticipantKind, Room, RoomEvent, Track } from "livekit-client";
import type { Participant, RemoteParticipant } from "livekit-client";
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api";
import { isFreshAction, parseActionAttribute, parseAttributes } from "./state";
import type { ActionAttribute, AgentScreen, AgentState, Failure, Phase, VoiceSnapshot } from "./state";

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
  /** The SQL item the agent last delivered ("reminder:<id>" | "dose:<id>"), else "". */
  item: string;
  /** The one-time Start tap: unlocks sound and asks for the mic once. Must be called from a click. */
  arm: () => Promise<void>;
  /** Join a room quietly (no mic) when the page opens, so the first tap is fast. Best effort, never an error. */
  prewarm: () => Promise<void>;
  /** Tap बोला, or (after the Start tap) an automatic start for a waiting reminder: join a room and open the mic. */
  start: () => Promise<void>;
  /** A tap on "touch to hear": lets the browser play Arjun's audio. */
  unlockAudio: () => Promise<void>;
  /** Leave the room (OK / back). */
  stop: () => void;
  /** A tapped answer ("हो", "नाही"): goes to the agent as text and takes the same path as speech. */
  sendText: (text: string) => Promise<void>;
  dismissSafety: () => void;
  /** Arjun is working out the answer (reasoning / the LLM): show the "thinking" marker. */
  thinking: boolean;
  /** The newest "arjun.action" (open a video / WhatsApp / a link, or a media control). Run each once, by `turn`. */
  action: ActionAttribute | null;
  /** Tell the agent whether the video player is playing ("arjun.media"): it ignores the video's own audio meanwhile. */
  reportMedia: (state: "playing" | "stopped") => void;
  /** Arjun's voice volume, 0..1 (the slider on the elder screen). Kept on this device. */
  volume: number;
  setVolume: (v: number) => void;
}

const VOLUME_KEY = "arjun.volume";
function savedVolume(): number {
  try {
    const v = Number.parseFloat(window.localStorage.getItem(VOLUME_KEY) ?? "");
    return Number.isFinite(v) ? Math.min(1, Math.max(0.1, v)) : 1;
  } catch {
    return 1;
  }
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
  const [item, setItem] = useState("");
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [action, setAction] = useState<ActionAttribute | null>(null);
  const [volume, setVolumeState] = useState(savedVolume);
  const volumeRef = useRef(volume);
  const audioEls = useRef(new Set<HTMLMediaElement>());

  const room = useRef<Room | null>(null);
  const stopping = useRef(false);
  const timers = useRef<number[]>([]);
  const phaseRef = useRef<Phase>("idle");
  const turnRef = useRef(0);
  const actionTurn = useRef(0); // the last action turn taken: an attribute that returns after a reconnect never runs twice
  const warm = useRef(false); // a room joined without the mic, waiting for the first tap
  const joining = useRef(false);

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
    warm.current = false;
    if (r) {
      stopping.current = true;
      void r.disconnect();
    }
  }, []);

  const resetSession = useCallback(() => {
    setPhaseBoth("idle");
    setFailure(undefined);
    setAgentState(undefined);
    setScreen(undefined);
    setTurn(0);
    turnRef.current = 0;
    actionTurn.current = 0;
    setReply("");
    setHeard("");
    setItem("");
    setAudioBlocked(false);
    setThinking(false);
    setAction(null);
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

  const applyAgent = useCallback(
    (p: Participant, t0: number) => {
      const a = parseAttributes(p.attributes);
      if (a.screen === "closed") {
        // Arjun ended an idle session on purpose: a normal end, never the "connection dropped" screen.
        teardown();
        resetSession();
        return;
      }
      setAgentState(a.agentState);
      setThinking(p.attributes["arjun.thinking"] === "1" || a.agentState === "thinking");
      if (a.screen) setScreen(a.screen);
      if (a.item) setItem(a.item);
      const act = parseActionAttribute(p.attributes["arjun.action"]);
      if (act && isFreshAction(act, actionTurn.current)) {
        actionTurn.current = act.turn;
        setAction(act);
      }
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
    },
    [resetSession, teardown],
  );

  /** Fetch a token and join a fresh room with every handler attached. null = it did not work (nothing left open). */
  const join = useCallback(
    async (t0: number): Promise<Room | null> => {
      let tok;
      try {
        tok = await api.livekitToken(userId);
      } catch {
        return null;
      }

      // Browser echo cancellation and noise suppression stay ON: the agent has no noise filter yet
      // (CLAUDE.md open question 6), and without echo cancellation Arjun would hear himself on a speaker.
      const r = new Room({
        audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      room.current = r;
      stopping.current = false;

      r.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === Track.Kind.Audio) {
          const el = track.attach();
          el.style.display = "none";
          el.volume = volumeRef.current;
          audioEls.current.add(el);
          document.body.appendChild(el);
        }
      });
      r.on(RoomEvent.TrackUnsubscribed, (track) =>
        track.detach().forEach((el) => {
          audioEls.current.delete(el);
          el.remove();
        }),
      );
      r.on(RoomEvent.AudioPlaybackStatusChanged, () => setAudioBlocked(!r.canPlaybackAudio));
      r.on(RoomEvent.ParticipantAttributesChanged, (_changed, p) => {
        if (isAgent(p)) applyAgent(p, t0);
      });
      r.on(RoomEvent.ParticipantConnected, (p) => {
        if (isAgent(p)) applyAgent(p, t0);
      });
      const lost = () => {
        if (stopping.current) return;
        if (phaseRef.current === "idle") {
          // a quiet (pre-warmed) room went away: forget it, the next tap joins a fresh one
          room.current = null;
          warm.current = false;
          return;
        }
        fail("dropped");
      };
      r.on(RoomEvent.ParticipantDisconnected, (p) => {
        if (isAgent(p)) lost();
      });
      r.on(RoomEvent.Reconnecting, () => {
        timers.current.push(window.setTimeout(() => fail("dropped"), RECONNECT_GIVE_UP_MS));
      });
      r.on(RoomEvent.Reconnected, () => clearTimers());
      r.on(RoomEvent.Disconnected, lost);
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
        room.current = null;
        return null;
      }
      return r;
    },
    [applyAgent, fail, userId],
  );

  const agentOf = (r: Room) => Array.from(r.remoteParticipants.values()).find(isAgent);

  const prewarm = useCallback(async () => {
    if (phaseRef.current !== "idle" || room.current || joining.current) return;
    joining.current = true;
    try {
      const r = await join(performance.now());
      if (r) warm.current = true;
    } finally {
      joining.current = false;
    }
  }, [join]);

  const arm = useCallback(async () => {
    try {
      // Ask for the mic once, inside the tap, so a later automatic start can open it without a prompt.
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
    } catch {
      // a refused mic is reported as the plain "mic" failure when a session is started
    }
    try {
      await room.current?.startAudio();
    } catch {
      // see audioBlocked
    }
  }, []);

  const start = useCallback(async () => {
    if (phaseRef.current === "connecting" || phaseRef.current === "waiting" || phaseRef.current === "live") return;
    const t0 = performance.now();
    turnRef.current = 0;
    actionTurn.current = 0;
    setFailure(undefined);
    setAgentState(undefined);
    setScreen(undefined);
    setTurn(0);
    setReply("");
    setHeard("");
    setItem("");
    setSafetyDismissedTurn(0);

    let r = room.current && room.current.state === "connected" && warm.current ? room.current : null;
    if (r) {
      warm.current = false; // the pre-warmed room is now this session
      setPhaseBoth("waiting");
    } else {
      if (room.current) teardown(); // a half-dead quiet room: start clean
      setPhaseBoth("connecting");
      r = await join(t0);
      if (!r) {
        fail("connect");
        return;
      }
      setPhaseBoth("waiting");
    }
    const tConnected = performance.now();
    timers.current.push(window.setTimeout(() => fail("timeout"), READY_TIMEOUT_MS));
    try {
      await r.startAudio(); // inside the tap's user gesture (or after the Start tap), so playback is allowed
      setAudioBlocked(!r.canPlaybackAudio);
      await r.localParticipant.setMicrophoneEnabled(true);
    } catch {
      fail("mic");
      return;
    }
    console.info(`[arjun] joined, mic on ${Math.round(performance.now() - tConnected)} ms; total ${Math.round(performance.now() - t0)} ms`);
    const a = agentOf(r); // the agent may already be in the room
    if (a) applyAgent(a, t0);
  }, [applyAgent, fail, join, teardown]);

  const unlockAudio = useCallback(async () => {
    const r = room.current;
    if (!r) return;
    try {
      await r.startAudio();
    } catch {
      // still blocked: the card stays on the screen
    }
    setAudioBlocked(!r.canPlaybackAudio);
  }, []);

  const stop = useCallback(() => {
    teardown();
    resetSession();
  }, [resetSession, teardown]);

  const sendText = useCallback(async (text: string) => {
    const r = room.current;
    if (!r || phaseRef.current !== "live") return;
    await r.localParticipant.sendText(text, { topic: "lk.chat" });
  }, []);

  const dismissSafety = useCallback(() => setSafetyDismissedTurn(turnRef.current), []);

  const reportMedia = useCallback((state: "playing" | "stopped") => {
    const r = room.current;
    if (!r || r.state !== "connected") return;
    void r.localParticipant.setAttributes({ "arjun.media": state }).catch(() => {
      // a failed report only means the agent keeps its own guess (it assumes "playing" after an open action)
    });
  }, []);

  const setVolume = useCallback((v: number) => {
    const next = Math.min(1, Math.max(0.1, v));
    volumeRef.current = next;
    setVolumeState(next);
    audioEls.current.forEach((el) => {
      el.volume = next;
    });
    try {
      window.localStorage.setItem(VOLUME_KEY, String(next));
    } catch {
      // private mode: the volume is kept for this page load only
    }
  }, []);

  useEffect(() => teardown, [teardown]);

  const snapshot: VoiceSnapshot = {
    phase,
    failure,
    agentState,
    screen,
    turn,
    safetyDismissedTurn,
    armed: false, // the page owns "armed"; ElderApp fills it in
    hasCard: false, // ... and "hasCard" (it comes from SQL)
    audioBlocked,
  };
  return {
    snapshot, reply, heard, readyMs, item, arm, prewarm, start, unlockAudio, stop, sendText, dismissSafety,
    thinking, volume, setVolume, action, reportMedia,
  };
}
