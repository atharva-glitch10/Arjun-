import { Room, RoomEvent, Track, type RemoteParticipant, type RemoteTrack } from "livekit-client";
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api";
import { joinProblem, joinTokenFrom, statusFromError } from "./join";

type Status = "connecting" | "live" | "ended" | "noroom" | "error";

/**
 * The family's side of the call: opened from the Telegram button (`?view=join&t=<token>`).
 * The token is checked by core-api, which returns a LiveKit token for the elder's current room.
 * The microphone is on; the elder's page shows "… बोलत आहेत" and Arjun stays quiet.
 */
export function JoinCall() {
  const [status, setStatus] = useState<Status>("connecting");
  const [problem, setProblem] = useState("");
  const [name, setName] = useState("");
  const [blocked, setBlocked] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [mode, setMode] = useState<"voice" | "video">("voice");
  const [camera, setCamera] = useState(true);
  const [muted, setMuted] = useState(false);
  const [callToken, setCallToken] = useState("");
  const [callId, setCallId] = useState<number | null>(null);
  const [callUserId, setCallUserId] = useState<number | null>(null);
  const familyVideo = useRef<HTMLVideoElement>(null);
  const elderVideo = useRef<HTMLVideoElement>(null);
  const localVideo = useRef<HTMLVideoElement>(null);
  const room = useRef<Room | null>(null);
  const hungUp = useRef(false);

  useEffect(() => {
    if (status === "connecting") hungUp.current = false;
  }, [status]);

  const retry = useCallback(() => {
    setProblem("");
    setStatus("connecting");
    setAttempt((n) => n + 1);
  }, []);

  const hangUp = useCallback(() => {
    hungUp.current = true;
    const r = room.current;
    room.current = null;
    if (r) {
      if (callToken) void api.familyCallEnd(callToken).catch(() => {});
      void r.localParticipant.setMicrophoneEnabled(false);
      void r.localParticipant.setCameraEnabled(false);
      void r.disconnect();
    }
    setStatus("ended");
  }, [callToken]);

  const toggleMute = () => {
    const r = room.current;
    if (!r) return;
    const next = !muted;
    setMuted(next);
    void r.localParticipant.setMicrophoneEnabled(!next);
  };
  const toggleCamera = () => {
    const r = room.current;
    if (!r) return;
    const next = !camera;
    setCamera(next);
    void r.localParticipant.setCameraEnabled(next);
  };

  const unlock = useCallback(async () => {
    const r = room.current;
    if (!r) return;
    try {
      await r.startAudio();
    } catch {
      // still blocked: the button stays
    }
    setBlocked(!r.canPlaybackAudio);
  }, []);

  useEffect(() => {
    const token = joinTokenFrom(window.location.search);
    if (!token) {
      setProblem(joinProblem(403));
      setStatus("error");
      return;
    }
    let cancelled = false;

    void (async () => {
      let info;
      try {
        info = await api.familyJoin(token);
      } catch (err) {
        if (!cancelled) {
          const code = statusFromError(err);
          setProblem(joinProblem(code));
          // No room means the elder is not in the app right now: never open a LiveKit connection.
          setStatus(code === 409 ? "noroom" : "error");
        }
        return;
      }
      if (cancelled) return;
      setName(info.name);
      setMode(info.mode);
      setCallToken(token);
      setCallId(info.call_id);
      setCallUserId(Number(token.split(".", 1)[0]) || null);

      const r = new Room({
        audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      room.current = r;
      r.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === Track.Kind.Audio) {
          const el = track.attach();
          document.body.appendChild(el);
        }
      });
      r.on(RoomEvent.TrackUnsubscribed, (track) => track.detach().forEach((el) => { el.srcObject = null; }));
      r.on(RoomEvent.AudioPlaybackStatusChanged, () => setBlocked(!r.canPlaybackAudio));
      r.on(RoomEvent.Disconnected, () => {
        if (!cancelled && !hungUp.current) {
          if (info.mode === "video") window.setTimeout(() => void api.familyCallEnd(token).catch(() => {}), 15_000);
          setStatus("ended");
        }
      });

      try {
        await r.connect(info.url, info.token);
        await r.startAudio().catch(() => undefined);
        await r.localParticipant.setMicrophoneEnabled(true);
        if (info.mode === "video") {
          await r.localParticipant.setCameraEnabled(true);
        }
      } catch {
        if (!cancelled) {
          if (info.mode === "video") void api.familyCallEnd(token).catch(() => {});
          void r.localParticipant.setMicrophoneEnabled(false);
          void r.localParticipant.setCameraEnabled(false);
          void r.disconnect();
          setProblem("आवाजाची लिंक उघडता आली नाही. मायक्रोफोनची परवानगी द्या आणि पुन्हा प्रयत्न करा.");
          setStatus("error");
        }
        return;
      }
      if (!cancelled) setStatus("live");
    })();

    return () => {
      cancelled = true;
      const r = room.current;
      room.current = null;
      if (r) {
        if (mode === "video" && !hungUp.current) void api.familyCallEnd(token).catch(() => {});
        void r.localParticipant.setCameraEnabled(false);
        void r.disconnect();
      }
    };
  }, [attempt]);

  useEffect(() => {
    if (status !== "live" || mode !== "video" || callId === null || callUserId === null) return;
    const id = window.setInterval(() => {
      void api.videoCallStatus(callUserId, callId).then((call) => {
        if (call.status !== "ended" && call.status !== "missed") return;
        hungUp.current = true;
        const r = room.current;
        room.current = null;
        if (r) {
          void r.localParticipant.setMicrophoneEnabled(false);
          void r.localParticipant.setCameraEnabled(false);
          void r.disconnect();
        }
        setStatus("ended");
      }).catch(() => {});
    }, 1000);
    return () => window.clearInterval(id);
  }, [callId, callUserId, mode, status]);

  useEffect(() => {
    if (status !== "live" || mode !== "video") return;
    const r = room.current;
    if (!r) return;
    const attach = (track: RemoteTrack, participant: RemoteParticipant) => {
      if (track.source !== Track.Source.Camera) return;
      const target = participant.identity === "family" ? familyVideo.current : elderVideo.current;
      if (!target) return;
      const el = track.attach(target);
      el.setAttribute("playsinline", "");
      void el.play().catch(() => {});
    };
    const subscribed = (track: RemoteTrack, _publication: unknown, participant: RemoteParticipant) => attach(track, participant);
    r.on(RoomEvent.TrackSubscribed, subscribed);
    for (const participant of r.remoteParticipants.values()) {
      for (const publication of participant.trackPublications.values()) {
        if (publication.track?.source === Track.Source.Camera) attach(publication.track as RemoteTrack, participant);
      }
    }
    const localTrack = r.localParticipant.getTrackPublication(Track.Source.Camera)?.track;
    if (localTrack && localVideo.current) {
      const el = localTrack.attach(localVideo.current);
      el.muted = true;
      el.setAttribute("playsinline", "");
      void el.play().catch(() => {});
    }
    return () => { r.off(RoomEvent.TrackSubscribed, subscribed); };
  }, [mode, status]);

  return (
    <main className="join-shell">
      <h1 className="join-title">घरच्यांशी बोला</h1>
      {status === "connecting" && (
        <p className="join-line" role="status">
          जोडत आहे…
        </p>
      )}
      {status === "live" && (
        <>
          <p className="join-line" role="status" aria-live="polite">
            {name} जोडले आहेत. बोला.
          </p>
          {blocked && (
            <button type="button" className="join-audio" onClick={() => void unlock()}>
              🔊 ऐकायला सुरु करा
            </button>
          )}
          {mode === "video" && (
            <section className="join-video-grid" aria-label="व्हिडिओ कॉल">
              <video ref={elderVideo} className="join-elder-video" autoPlay playsInline />
              <video ref={localVideo} className="join-self-video" autoPlay muted playsInline />
              <div className="join-video-controls">
                <button type="button" onClick={toggleMute}>{muted ? "माइक सुरू करा" : "माइक बंद करा"}</button>
                <button type="button" onClick={toggleCamera}>{camera ? "कॅमेरा बंद करा" : "कॅमेरा सुरू करा"}</button>
              </div>
            </section>
          )}
          <button type="button" className="join-hangup" onClick={hangUp}>
            बंद करा
          </button>
        </>
      )}
      {status === "ended" && (
        <p className="join-line" role="status">
          कॉल बंद झाला.
        </p>
      )}
      {status === "noroom" && (
        <>
          <p className="join-problem" role="status">
            {joinProblem(409)}
          </p>
          <button type="button" className="join-retry" onClick={retry}>
            पुन्हा प्रयत्न करा
          </button>
        </>
      )}
      {status === "error" && (
        <p className="join-problem" role="alert">
          {problem}
        </p>
      )}
    </main>
  );
}
