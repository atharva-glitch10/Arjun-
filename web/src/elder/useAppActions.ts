import { useCallback, useEffect, useRef, useState } from "react";

import type { Contact } from "../api";
import { isFreshAction } from "../voice/state";
import type { ArjunAction } from "../voice/action";
import type { ArjunVoice } from "../voice/useArjunVoice";
import type { MediaControlEvent } from "./MediaScreen";
import { planAction } from "./media";

/** Performs the agent's "arjun.action" on the elder page, each action exactly once:
 *  - a YouTube video / playlist / live channel -> the full-screen MediaScreen,
 *  - WhatsApp and family links -> one window we keep a handle to ("परत" closes it and focuses Arjun again),
 *  - a control (stop / pause / resume / next / volume) -> the screen that is open.
 *  A pop-up blocker is not hidden: if the window cannot open, one big tap button does it instead.
 *  Emergencies win: a safety screen closes the video. The voice session keeps running underneath all of this. */
export function useAppActions(voice: ArjunVoice, contacts: Contact[], safety: boolean, resume: () => void) {
  const [media, setMedia] = useState<ArjunAction | null>(null);
  const [control, setControl] = useState<MediaControlEvent | null>(null);
  const [blocked, setBlocked] = useState<{ url: string; title: string } | null>(null);
  const [link, setLink] = useState<{ title: string } | null>(null);
  const performed = useRef(0);
  const seq = useRef(0);
  const win = useRef<Window | null>(null);

  const closeWindow = useCallback(() => {
    win.current?.close();
    win.current = null;
    setLink(null);
    window.focus();
  }, []);

  const openWindow = useCallback((url: string, title: string) => {
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
  useEffect(() => {
    if (!action || !isFreshAction(action, performed.current)) return;
    performed.current = action.turn;
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
    if (plan.do === "window") {
      setMedia(null);
      openWindow(plan.url, plan.title);
      return;
    }
    // an embed: one full-screen player, keyed by the turn so a new song really reloads
    closeWindow();
    setBlocked(null);
    setMedia({ type: "open", kind: plan.kind, value: plan.value, title: plan.title, turn: action.turn });
  }, [action, contacts, closeWindow, openWindow]);

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
    reportMedia: voice.reportMedia,
    onMediaClosed: useCallback(() => setMedia(null), []),
    closeLink: closeWindow,
    openBlocked: () => {
      if (blocked) openWindow(blocked.url, blocked.title);
    },
    cancelBlocked: () => setBlocked(null),
  };
}
