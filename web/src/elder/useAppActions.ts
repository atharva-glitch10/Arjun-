import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { Contact, VideoCall } from "../api";
import { isFreshAction } from "../voice/state";
import type { ArjunAction } from "../voice/action";
import type { ArjunVoice } from "../voice/useArjunVoice";
import type { MediaControlEvent } from "./MediaScreen";
import { planAction } from "./media";
import { isVideoCallStopCommand } from "./videoCall";

/** Performs the agent's "arjun.action" on the elder page, each action exactly once:
 *  - a YouTube video / playlist / live channel -> the full-screen MediaScreen,
 *  - WhatsApp and family links -> one window we keep a handle to ("परत" closes it and focuses Arjun again),
 *  - a control (stop / pause / resume / next / volume) -> the screen that is open.
 *  A pop-up blocker is not hidden: if the window cannot open, one big tap button does it instead.
 *  Emergencies win: a safety screen closes the video. The voice session keeps running underneath all of this. */
export function useAppActions(voice: ArjunVoice, userId: number, contacts: Contact[], safety: boolean, resume: () => void) {
  const [media, setMedia] = useState<ArjunAction | null>(null);
  const [control, setControl] = useState<MediaControlEvent | null>(null);
  const [blocked, setBlocked] = useState<{ url: string; title: string } | null>(null);
  const [link, setLink] = useState<{ title: string } | null>(null);
  const [videoCall, setVideoCall] = useState<VideoCall | null>(null);
  const [videoCallStarting, setVideoCallStarting] = useState<{ name: string } | null>(null);
  const stopHeard = useRef("");
  const callAttempt = useRef(0);
  const performed = useRef(0);
  const seq = useRef(0);
  const win = useRef<Window | null>(null);
  const blockedWeb = useRef<string>("");

  const closeWindow = useCallback(() => {
    win.current?.close();
    win.current = null;
    setLink(null);
    window.focus();
  }, []);

  const openWindow = useCallback((url: string, title: string) => {
    if (url.startsWith("intent:")) {
      // an Android app: leave Arjun's tab where it is; if the app did not start (not installed), open the web page
      const web = blockedWeb.current;
      setBlocked(null);
      window.location.href = url;
      window.setTimeout(() => {
        if (!document.hidden && web) window.open(web, "arjun_link");
      }, 1500);
      return;
    }
    const w = window.open(url, "arjun_link"); // the house's own handle: a later "बंद कर" closes exactly this window
    if (w) {
      win.current = w;
      setBlocked(null);
      setLink({ title });
    } else {
      setLink(null);
      setBlocked({ url, title }); // the browser refused (pop-up blocker): ask for one tap
    }
  }, []);

  const action = voice.action;
  const finishVideoCall = useCallback(async (reason = "button") => {
    const stoppingCall = Boolean(videoCall || videoCallStarting);
    if (stoppingCall) console.info("video call stopped", reason);
    callAttempt.current += 1;
    const current = videoCall;
    setVideoCall(null);
    setVideoCallStarting(null);
    if (stoppingCall && voice.snapshot.phase === "live") {
      void voice.sendText("[video_call_stopped]");
    }
    const room = voice.room;
    if (room) {
      void room.localParticipant.setAttributes({ "arjun.video_call": "stopped" });
      void room.localParticipant.setCameraEnabled(false);
      if (!document.hidden) {
        void room.localParticipant.setMicrophoneEnabled(false).then(() => room.localParticipant.setMicrophoneEnabled(true));
      } else {
        void room.localParticipant.setMicrophoneEnabled(false);
      }
    }
    if (current) {
      try {
        await api.endVideoCall(userId, current.id);
      } catch {
        // the camera is still released by the screen cleanup if the API is offline
      }
    }
  }, [userId, videoCall, videoCallStarting, voice.room, voice.snapshot.phase, voice.sendText]);

  useEffect(() => {
    if (!action || !isFreshAction(action, performed.current)) return;
    performed.current = action.turn;
    if (action.type === "call" && action.kind === "video") {
      const contactId = Number(action.value);
      if (!Number.isInteger(contactId) || contactId <= 0) return;
      closeWindow();
      setMedia(null);
      setBlocked(null);
      setVideoCall(null);
      const name = action.title || "कुटुंब";
      if (voice.snapshot.phase === "live") void voice.sendText("[video_call_stopped]");
      setVideoCallStarting({ name });
      const attempt = ++callAttempt.current;
      void api.startVideoCall(userId, contactId)
        .then((started) => {
          if (attempt !== callAttempt.current) {
            void api.endVideoCall(userId, started.id).catch(() => {});
            return;
          }
          stopHeard.current = voice.heard;
          void voice.room?.localParticipant.setAttributes({ "arjun.video_call": "ringing" });
          setVideoCall(started);
          setVideoCallStarting(null);
        })
        .catch(() => {
          if (attempt !== callAttempt.current) return;
          setVideoCallStarting(null);
          if (voice.snapshot.phase === "live") void voice.sendText("कॉल लागला नाही, मी पुन्हा प्रयत्न करतो.");
        });
      return;
    }
    const plan = planAction(action, contacts, window.location.origin);
    if (plan.do === "none") return;
    if (plan.do === "control") {
      if (plan.command === "stop") {
        setMedia(null);
        setBlocked(null);
        closeWindow();
      }
      seq.current += 1;
      setControl({ kind: plan.command, seq: seq.current });
      return;
    }
    if (plan.do === "app") {
      // leaving the browser always needs her tap: show the big "उघडा" button straight away
      setMedia(null);
      closeWindow();
      blockedWeb.current = plan.web;
      setBlocked({ url: plan.url, title: plan.title });
      return;
    }
    if (plan.do === "window") {
      setMedia(null);
      openWindow(plan.url, plan.title);
      return;
    }
    // an embed: one full-screen player, keyed by the turn so a new song really reloads
    closeWindow();
    setBlocked(null);
    setMedia({ type: "open", kind: plan.kind, value: plan.value, title: plan.title, turn: action.turn });
  }, [action, contacts, closeWindow, openWindow, userId, voice.heard]);

  useEffect(() => {
    if (safety) {
      setMedia(null);
      setBlocked(null);
      void finishVideoCall();
    }
  }, [safety, finishVideoCall]);

  useEffect(() => {
    if (!videoCall || !isVideoCallStopCommand(voice.heard) || voice.heard === stopHeard.current) return;
    stopHeard.current = voice.heard;
    void finishVideoCall("voice stop command");
  }, [finishVideoCall, videoCall, voice.heard]);

  const missedVideoCall = useCallback((name: string) => {
    console.info("video call stopped", "missed timeout");
    if (voice.snapshot.phase === "live") void voice.sendText(`[video_call_missed] ${name}`);
    void voice.room?.localParticipant.setAttributes({ "arjun.video_call": "stopped" });
    setVideoCall(null);
    setVideoCallStarting(null);
  }, [voice]);

  // when the person closes the WhatsApp / link window herself, come back to Arjun and make sure he is still listening
  useEffect(() => {
    const id = window.setInterval(() => {
      const w = win.current;
      if (w && w.closed) {
        win.current = null;
        setLink(null);
        window.focus();
        resume();
      }
    }, 1000);
    return () => window.clearInterval(id);
  }, [resume]);

  return {
    media,
    control,
    blocked,
    link,
    videoCall,
    videoCallStarting,
    finishVideoCall,
    missedVideoCall,
    reportMedia: voice.reportMedia,
    onMediaClosed: useCallback(() => setMedia(null), []),
    closeLink: closeWindow,
    openBlocked: () => {
      if (blocked) openWindow(blocked.url, blocked.title);
    },
    cancelBlocked: () => setBlocked(null),
  };
}
