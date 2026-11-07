import { useEffect, useRef, useState } from "react";
import { RoomEvent, Track } from "livekit-client";

import { api } from "../api";
import type { VideoCall } from "../api";
import type { Room } from "livekit-client";

export function VideoCallScreen({
  call, starting, room, userId, onEnd, onMissed,
}: {
  call: VideoCall | null;
  starting: { name: string } | null;
  room: Room | null;
  userId: number;
  onEnd: () => void;
  onMissed: (name: string) => void;
}) {
  const local = useRef<HTMLVideoElement>(null);
  const remote = useRef<HTMLVideoElement>(null);
  const [status, setStatus] = useState<VideoCall["status"]>(call?.status ?? "ringing");
  const [problem, setProblem] = useState(false);
  const callRef = useRef(call);
  callRef.current = call;
  const endRef = useRef(onEnd);
  const missedRef = useRef(onMissed);
  endRef.current = onEnd;
  missedRef.current = onMissed;

  useEffect(() => {
    if (call && room) {
      void room.localParticipant.setCameraEnabled(true).then(() => {
        const track = room.localParticipant.getTrackPublication(Track.Source.Camera)?.track;
        if (track && local.current) {
          const el = track.attach(local.current);
          el.muted = true;
          void el.play().catch(() => {});
        }
      }).catch(() => {
        setProblem(true);
        endRef.current();
      });
    }
    return () => {
      if (room) {
        void room.localParticipant.setCameraEnabled(false);
        if (!document.hidden) void room.localParticipant.setMicrophoneEnabled(true);
      }
    };
  }, [call?.id, room]);

  useEffect(() => {
    if (!call || !room) return;
    void room.localParticipant.setMicrophoneEnabled(status !== "ringing");
  }, [call?.id, room, status]);

  useEffect(() => {
    if (!call || !room) return;
    let alive = true;
    const attach = () => {
      const pub = room.localParticipant.getTrackPublication(Track.Source.Camera);
      const track = pub?.track;
      if (track && local.current) {
        const el = track.attach(local.current);
        el.muted = true;
        el.setAttribute("playsinline", "");
        void el.play().catch(() => {});
      }
    };
    const attachRemote = (track: { kind: string; attach: (el?: HTMLVideoElement) => HTMLVideoElement }, participant: { identity: string }) => {
      if (participant.identity !== "family" || track.kind !== Track.Kind.Video || !remote.current) return;
      const el = track.attach(remote.current);
      el.setAttribute("playsinline", "");
      void el.play().catch(() => {});
    };
    const detachRemote = (track: { detach: () => HTMLElement[] }, participant: { identity: string }) => {
      if (participant.identity === "family") track.detach().forEach((el) => el.remove());
    };
    room.on(RoomEvent.TrackSubscribed, attachRemote as never);
    room.on(RoomEvent.TrackUnsubscribed, detachRemote as never);
    attach();
    for (const participant of room.remoteParticipants.values()) {
      if (participant.identity !== "family") continue;
      for (const publication of participant.trackPublications.values()) {
        if (publication.source === Track.Source.Camera && publication.track) {
          attachRemote(publication.track as never, participant);
        }
      }
    }
    const poll = window.setInterval(() => {
      void api.videoCallStatus(userId, call.id).then((result) => {
        if (!alive) return;
        setStatus(result.status);
        if (result.status === "missed") missedRef.current(callRef.current?.contact_name ?? "घरच्यांनी");
        else if (result.status === "ended") endRef.current();
      }).catch(() => {
        setProblem(true);
        endRef.current();
      });
    }, 1000);
    const hidden = () => {
      if (document.hidden) {
        void room.localParticipant.setCameraEnabled(false);
        void room.localParticipant.setMicrophoneEnabled(false);
        endRef.current();
      }
    };
    document.addEventListener("visibilitychange", hidden);
    return () => {
      alive = false;
      window.clearInterval(poll);
      document.removeEventListener("visibilitychange", hidden);
      room.off(RoomEvent.TrackSubscribed, attachRemote as never);
      room.off(RoomEvent.TrackUnsubscribed, detachRemote as never);
      if (local.current) local.current.srcObject = null;
      if (remote.current) remote.current.srcObject = null;
    };
  }, [call?.id, call?.contact_name, room, userId]);

  useEffect(() => {
    if (!call || status !== "ringing") return;
    let ctx: AudioContext | null = null;
    let timer = 0;
    try {
      ctx = new AudioContext();
      const audio = ctx;
      const ring = () => {
        const osc = audio.createOscillator();
        const gain = audio.createGain();
        osc.frequency.value = 480;
        gain.gain.value = 0.06;
        osc.connect(gain); gain.connect(audio.destination);
        osc.start(); osc.stop(audio.currentTime + 0.3);
      };
      ring(); timer = window.setInterval(ring, 1800);
    } catch { /* device audio may be unavailable */ }
    return () => { window.clearInterval(timer); void ctx?.close(); };
  }, [call, status]);

  if (!call && !starting) return null;
  const name = call?.contact_name ?? starting?.name ?? "कुटुंब";
  const ringing = !call || status === "ringing";
  return (
    <main className="elder-video-call" role="dialog" aria-label="व्हिडिओ कॉल">
      {ringing ? <div className="elder-call-wait"><video ref={local} autoPlay muted playsInline /><h1>{name}ला बोलावतोय…</h1>
        {problem && <p>कॅमेरा किंवा कॉल उपलब्ध नाही.</p>}
      </div> : <><video ref={remote} className="elder-family-video" autoPlay playsInline />
        <video ref={local} className="elder-self-video" autoPlay muted playsInline />
        <p className="elder-call-name">{name}</p>
      </>}
      <button className="elder-call-end" type="button" onClick={onEnd}>🔴 बंद करा</button>
    </main>
  );
}
