import { useCallback, useEffect, useRef, useState } from "react";

import { isVideoKind, shouldPerform } from "../voice/action";
import type { ArjunAction } from "../voice/action";
import type { ArjunVoice } from "../voice/useArjunVoice";
import type { MediaControlEvent } from "./MediaScreen";

/** Performs the agent's "arjun.action" on the elder page, each action exactly once:
 *  - a YouTube video / playlist / live channel -> the full-screen MediaScreen,
 *  - WhatsApp and family links -> one new window that we keep a handle to ("बंद कर" closes it and focuses Arjun again),
 *  - a control (stop / pause / resume / next / volume) -> the screen that is open.
 *  A pop-up blocker is not hidden: if the window cannot open, one big tap button does it instead.
 *  Emergencies win: a safety screen closes the video. The voice session keeps running underneath all of this. */
export function useAppActions(voice: ArjunVoice, safety: boolean, resume: () => void) {
  const [media, setMedia] = useState<ArjunAction | null>(null);
  const [control, setControl] = useState<MediaControlEvent | null>(null);
  const [blocked, setBlocked] = useState<ArjunAction | null>(null);
  const performed = useRef(0);
  const seq = useRef(0);
  const win = useRef<Window | null>(null);

  const closeWindow = useCallback(() => {
    win.current?.close();
    win.current = null;
    window.focus();
  }, []);

  const openWindow = useCallback((a: ArjunAction) => {
    const w = window.open(a.value, "arjun-link");
    if (w) {
      win.current = w;
      setBlocked(null);
    } else {
      setBlocked(a); // the browser refused (pop-up blocker): ask for one tap
    }
  }, []);

  const action = voice.action;
  useEffect(() => {
    if (!action || !shouldPerform(action, performed.current)) return;
    performed.current = action.turn;
    if (action.type === "control") {
      if (action.kind === "stop") {
        setMedia(null);
        setBlocked(null);
        closeWindow();
      }
      seq.current += 1;
      setControl({ kind: action.kind, seq: seq.current });
      return;
    }
    if (isVideoKind(action.kind)) {
      closeWindow();
      setBlocked(null);
      setMedia(action);
    } else {
      setMedia(null);
      openWindow(action);
    }
  }, [action, closeWindow, openWindow]);

  useEffect(() => {
    if (safety) {
      setMedia(null);
      setBlocked(null);
    }
  }, [safety]);

  // when the person closes the WhatsApp / link window herself, come back to Arjun and make sure he is still listening
  useEffect(() => {
    const id = window.setInterval(() => {
      const w = win.current;
      if (w && w.closed) {
        win.current = null;
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
    reportMedia: voice.reportMedia,
    onMediaClosed: useCallback(() => setMedia(null), []),
    openBlocked: () => {
      if (blocked) openWindow(blocked);
    },
    cancelBlocked: () => setBlocked(null),
  };
}
