import { ParticipantKind, Room, RoomEvent, Track } from "livekit-client";
import type { Participant, RemoteParticipant } from "livekit-client";
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api";
import { playbackVolume } from "./speechStyle";
import { isFreshAction, microphoneNeedsRepublish, parseActionAttribute, parseAttributes } from "./state";
import type { ActionAttribute, AgentScreen, AgentState, Failure, Phase, VoiceSnapshot } from "./state";

/** Give the agent this long to come up after joining before telling the elder plainly. */
export const READY_TIMEOUT_MS = 20_000;
/** A connection that is only "reconnecting" for this long counts as dropped. */
export const RECONNECT_GIVE_UP_MS = 8_000;

export interface ArjunVoice {
  snapshot: VoiceSnapshot;
  /** The shared room used for the live family call, when connected. */
  room: Room | null;
  /** The exact line Arjun is speaking ("arjun.reply"). */
  reply: string;
  /** What Arjun heard the elder say (live transcription), best effort. */
  heard: string;
  /** Milliseconds from the tap to the agent listening, for the last session (console + here). */
  readyMs: number | null;
  /** The SQL item the agent last delivered ("reminder:<id>" | "dose:<id>"), else "". */
  item: string;
  /** The family member in the room right now ("चंद्रकांत"), else "". Arjun stays quiet while this is set. */
  family: string;
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
  mediaDuck: boolean;
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
  const [roomView, setRoomView] = useState<Room | null>(null);
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
  const [family, setFamily] = useState("");
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [mediaDuck, setMediaDuck] = useState(false);
  const [action, setAction] = useState<ActionAttribute | null>(null);
  const [volume, setVolumeState] = useState(savedVolume);
  const volumeRef = useRef(volume);
  const audioEls = useRef(new Set<HTMLMediaElement>());
  const mediaStateRef = useRef<"playing" | "stopped">("stopped");

  const room = useRef<Room | null>(null);
  const stopping = useRef(false);
  const timers = useRef<number[]>([]);
  const phaseRef = useRef<Phase>("idle");
  const turnRef = useRef(0);
  const actionTurn = useRef(0); // the last action turn taken: an attribute that returns after a reconnect never runs twice
  const warm = useRef(false); // a room joined without the mic, waiting for the first tap
  const joining = useRef(false);
  const recovering = useRef(false);
  const recoverRef = useRef<((freshRoom?: boolean) => Promise<void>) | null>(null);
  const needsFreshRoom = useRef(false);
  const recoverAttempts = useRef(0);

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
    setRoomView(null);
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
    setFamily("");
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
      const styleRaw = p.attributes["arjun.speech_style"];
      if (typeof styleRaw === "string") {
        try {
          const style = JSON.parse(styleRaw) as { volume?: string };
          const nextVolume = playbackVolume({ volume: style.volume === "loud" ? "loud" : "normal" }, savedVolume());
          volumeRef.current = nextVolume;
          setVolumeState(nextVolume);
          audioEls.current.forEach((el) => { el.volume = nextVolume; });
        } catch {
          // Ignore malformed optional profile state.
        }
      }
      if (a.screen === "closed") {
        // Arjun ended an idle session on purpose: a normal end, never the "connection dropped" screen.
        teardown();
        resetSession();
        return;
      }
      setAgentState(a.agentState);
      setThinking(p.attributes["arjun.thinking"] === "1" || a.agentState === "thinking");
      setMediaDuck(a.mediaDuck);
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
      setRoomView(r);
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
      const seeFamily = (p: Participant) => {
        if (p.identity === "family") setFamily(p.name || "कुटुंब");
      };
      r.on(RoomEvent.ParticipantAttributesChanged, (_changed, p) => {
        if (isAgent(p)) applyAgent(p, t0);
        seeFamily(p);
      });
      r.on(RoomEvent.ParticipantConnected, (p) => {
        if (isAgent(p)) {
          recoverAttempts.current = 0;
          applyAgent(p, t0);
        }
        seeFamily(p);
      });
      const lost = () => {
        if (stopping.current) return;
        if (phaseRef.current === "idle") {
          // a quiet (pre-warmed) room went away: forget it, the next tap joins a fresh one
          room.current = null;
          warm.current = false;
          return;
        }
        needsFreshRoom.current = true;
        if (document.hidden) return; // hidden-page teardown is repaired on visibilitychange/pageshow
        void recoverRef.current?.(true);
      };
      r.on(RoomEvent.ParticipantDisconnected, (p) => {
        if (isAgent(p)) lost();
        if (p.identity === "family") setFamily("");
      });
      r.on(RoomEvent.Reconnecting, () => {
        timers.current.push(window.setTimeout(() => {
          if (!document.hidden) fail("dropped");
          else needsFreshRoom.current = true;
        }, RECONNECT_GIVE_UP_MS));
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
        setRoomView(null);
        return null;
      }
      void r.localParticipant.setAttributes({
        "arjun.media": mediaStateRef.current,
        "arjun.media.heartbeat": String(Date.now()),
      }).catch(() => {});
      for (const p of r.remoteParticipants.values()) seeFamily(p);
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

  const recover = useCallback(async (freshRoom = false) => {
    if (recovering.current || document.hidden || !["live", "waiting"].includes(phaseRef.current)) return;
    recovering.current = true;
    try {
      let r = room.current;
      if (freshRoom || !r || r.state !== "connected") {
        if (recoverAttempts.current >= 3) {
          fail("dropped");
          return;
        }
        const delay = Math.min(500 * 2 ** recoverAttempts.current, 2_000);
        recoverAttempts.current += 1;
        await new Promise((resolve) => window.setTimeout(resolve, delay));
        if (document.hidden) {
          needsFreshRoom.current = true;
          return;
        }
        needsFreshRoom.current = false;
        const old = room.current;
        room.current = null;
        stopping.current = true;
        await old?.disconnect();
        stopping.current = false;
        setPhaseBoth("connecting");
        r = await join(performance.now());
        if (!r) {
          fail("dropped");
          return;
        }
        setPhaseBoth("waiting");
        timers.current.push(window.setTimeout(() => fail("timeout"), READY_TIMEOUT_MS));
        console.info("[arjun] recovery: LiveKit room reconnected");
      }
      await r.startAudio(); // resumes LiveKit's suspended AudioContext after browser tab suspension
      const pub = r.localParticipant.getTrackPublication(Track.Source.Microphone);
      const mediaTrack = pub?.track?.mediaStreamTrack;
      const micNeedsRepublish = !pub || pub.isMuted || microphoneNeedsRepublish(mediaTrack);
      if (micNeedsRepublish) {
        await r.localParticipant.setMicrophoneEnabled(false);
        await r.localParticipant.setMicrophoneEnabled(true);
        console.info("[arjun] recovery: microphone republished");
      }
      for (const el of audioEls.current) {
        try {
          await el.play();
        } catch {
          setAudioBlocked(true);
        }
      }
      setAudioBlocked(!r.canPlaybackAudio);
    } catch {
      console.info("[arjun] recovery: audio resume needs another tap");
    } finally {
      recovering.current = false;
    }
  }, [fail, join]);
  recoverRef.current = recover;

  useEffect(() => {
    const resume = () => {
      if (document.visibilityState === "visible") void recoverRef.current?.(needsFreshRoom.current);
    };
    document.addEventListener("visibilitychange", resume);
    window.addEventListener("pageshow", resume);
    window.addEventListener("focus", resume);
    return () => {
      document.removeEventListener("visibilitychange", resume);
      window.removeEventListener("pageshow", resume);
      window.removeEventListener("focus", resume);
    };
  }, []);

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
    mediaStateRef.current = state;
    const r = room.current;
    if (!r || r.state !== "connected") return;
    const attrs = { "arjun.media": state, "arjun.media.heartbeat": String(Date.now()) };
    void r.localParticipant.setAttributes(attrs).catch(() => {
      // The voice-agent clears media mode after 30 seconds without a confirmed page heartbeat.
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
    room: roomView,
    snapshot, reply, heard, readyMs, item, family, arm, prewarm, start, unlockAudio, stop, sendText, dismissSafety,
    thinking, volume, setVolume, action, mediaDuck, reportMedia,
  };
}
