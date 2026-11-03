import { Room, RoomEvent, Track } from "livekit-client";
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
  const room = useRef<Room | null>(null);
  const hungUp = useRef(false);

  const retry = useCallback(() => {
    setProblem("");
    setStatus("connecting");
    setAttempt((n) => n + 1);
  }, []);

  const hangUp = useCallback(() => {
    hungUp.current = true;
    const r = room.current;
    room.current = null;
    if (r) void r.disconnect();
    setStatus("ended");
  }, []);

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
      r.on(RoomEvent.TrackUnsubscribed, (track) => track.detach().forEach((el) => el.remove()));
      r.on(RoomEvent.AudioPlaybackStatusChanged, () => setBlocked(!r.canPlaybackAudio));
      r.on(RoomEvent.Disconnected, () => {
        if (!cancelled && !hungUp.current) setStatus("ended");
      });

      try {
        await r.connect(info.url, info.token);
        await r.startAudio().catch(() => undefined);
        await r.localParticipant.setMicrophoneEnabled(true);
      } catch {
        if (!cancelled) {
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
      if (r) void r.disconnect();
    };
  }, [attempt]);

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
