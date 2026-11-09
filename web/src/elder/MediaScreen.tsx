import { useEffect, useReducer, useRef, useState } from "react";

import { idleMedia, mediaReducer, reportableMediaState, shouldHeartbeatMedia } from "../voice/action";
import type { ArjunAction, ControlKind, MediaState, PlayerState } from "../voice/action";
import { t } from "./strings";
import {
  IFRAME_ALLOW,
  REFERRER_POLICY,
  appLink,
  createRecovery,
  embedTarget,
  embedUrl,
  supportsPlayback,
  whenApiReady,
} from "./ytPlayer";
import type { Recovery } from "./ytPlayer";

// The little part of the YouTube IFrame Player API we use (loaded from youtube.com/iframe_api, no key in the browser).
interface YtPlayer {
  playVideo(): void;
  pauseVideo(): void;
  nextVideo(): void;
  previousVideo(): void;
  loadVideoById(id: string): void;
  cueVideoById(id: string): void;
  setVolume(v: number): void;
  destroy(): void;
}
interface YtApi {
  Player: new (
    el: HTMLIFrameElement,
    opts: { events: { onReady?: () => void; onStateChange?: (e: { data: number }) => void; onError?: (e: { data: number }) => void; onAutoplayBlocked?: () => void } },
  ) => YtPlayer;
}
declare global {
  interface Window {
    YT?: YtApi;
    onYouTubeIframeAPIReady?: () => void;
  }
}

let apiPromise: Promise<YtApi> | null = null;
function loadYouTubeApi(): Promise<YtApi> {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  apiPromise ??= new Promise<YtApi>((resolve, reject) => {
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previous?.();
      if (window.YT) resolve(window.YT);
    };
    const s = document.createElement("script");
    s.src = "https://www.youtube.com/iframe_api";
    s.onerror = () => {
      apiPromise = null;
      reject(new Error("YouTube API did not load"));
    };
    document.head.appendChild(s);
  });
  return apiPromise;
}

/** YouTube's numeric player states: 1 playing, 2 paused, 0 ended, 3 buffering, 5 cued, -1 unstarted. */
function playerStateOf(code: number): PlayerState | null {
  if (code === 1) return "playing";
  if (code === 2) return "paused";
  if (code === 0) return "ended";
  return null;
}

const STUCK_AFTER_MS = 12_000; // still no 'ready' after this long: the box would stay dark, so treat it as a player error

export interface MediaControlEvent {
  kind: ControlKind;
  seq: number;
}

/** Full-screen video. Huge buttons, everything also by voice. The page tells the agent what the player does
 *  ("arjun.media": playing | stopped) so the agent can ignore the video's own audio. */
export function MediaScreen({
  action,
  control,
  onReport,
  onClosed,
  ducked,
  fetchAlternates,
}: {
  action: ArjunAction;
  control: MediaControlEvent | null;
  onReport: (state: "playing" | "stopped") => void;
  onClosed: () => void;
  ducked: boolean;
  /** Other search results for a title, used when a video will not play here (the elder screen passes the core-api search). */
  fetchAlternates?: (query: string) => Promise<{ video_id?: string }[]>;
}) {
  const [state, dispatch] = useReducer(mediaReducer, undefined, () => mediaReducer(idleMedia(), { t: "open", action }));
  const holder = useRef<HTMLDivElement | null>(null);
  const player = useRef<YtPlayer | null>(null);
  const recovery = useRef<Recovery | null>(null);
  const [notice, setNotice] = useState<"retry" | "unsupported" | null>(null);
  const [fallbackLink, setFallbackLink] = useState<string | null>(null);
  const seen = useRef(0);
  const stateRef = useRef<MediaState>(state);
  stateRef.current = state;

  // one player per opened action: the YouTube IFrame Player API on youtube-nocookie.com, an explicit referrer policy,
  // and NO autoplay before a tap (the big "start" button below). A video that will not play -> the next search result
  // (up to 3) -> a one-tap "open in YouTube" link. Never a dead dark box.
  useEffect(() => {
    let cancelled = false;
    setNotice(null);
    setFallbackLink(null);
    const kind = action.type === "open" ? action.kind : "";
    const target = kind === "youtube_video" || kind === "youtube_playlist" || kind === "youtube_channel_live" ? embedTarget(kind, action.value) : null;
    const ua = navigator.userAgent;
    const link =
      kind === "youtube_playlist" ? `https://www.youtube.com/playlist?list=${action.value}`
      : kind === "youtube_channel_live" ? `https://www.youtube.com/channel/${action.value}`
      : appLink(action.value, ua);
    const giveUp = (why: "retry" | "unsupported") => {
      if (cancelled) return;
      setNotice(why);
      setFallbackLink(link);
      dispatch({ t: "player", state: "fallback" });
    };
    if (!target || !holder.current) {
      giveUp("retry");
      return;
    }
    if (!supportsPlayback(window as unknown as Parameters<typeof supportsPlayback>[0])) {
      giveUp("unsupported");
      return;
    }
    const stuck = window.setTimeout(() => {
      if (stateRef.current.phase === "loading") void recovery.current?.onError(5);
    }, STUCK_AFTER_MS);
    recovery.current = createRecovery({
      title: action.title,
      firstId: target.videoId ?? null,
      fetchAlternates: fetchAlternates ?? (() => Promise.resolve([])),
      load: (id, autoplay) => {
        if (cancelled) return;
        if (autoplay) player.current?.loadVideoById(id);
        else {
          player.current?.cueVideoById(id);
          dispatch({ t: "player", state: "blocked" });
        }
      },
      notice: () => !cancelled && setNotice("retry"),
      giveUp: () => giveUp("retry"),
    });
    void whenApiReady(
      loadYouTubeApi,
      (YT) => {
        if (cancelled || !holder.current) return;
        holder.current.innerHTML = "";
        const frame = document.createElement("iframe");
        frame.className = "media-frame";
        frame.title = action.title || "YouTube";
        frame.setAttribute("referrerpolicy", REFERRER_POLICY); // set BEFORE src: the policy is read when the load starts
        frame.setAttribute("allow", IFRAME_ALLOW);
        frame.allowFullscreen = true;
        frame.src = embedUrl(target, window.location.origin);
        holder.current.appendChild(frame);
        player.current = new YT.Player(frame, {
          events: {
            onReady: () => {
              window.clearTimeout(stuck);
              player.current?.setVolume(stateRef.current.volume);
              dispatch({ t: "player", state: "blocked" }); // ready: wait for her tap, never autoplay on load
            },
            onStateChange: (e) => {
              const s = playerStateOf(e.data);
              if (s) {
                if (s === "playing") setNotice(null);
                dispatch({ t: "player", state: s });
              }
            },
            onError: (e) => void recovery.current?.onError(e?.data ?? 5),
            onAutoplayBlocked: () => dispatch({ t: "player", state: "blocked" }),
          },
        });
      },
      () => giveUp("retry"), // the API script itself would not load
    );
    return () => {
      cancelled = true;
      window.clearTimeout(stuck);
      player.current?.destroy();
      player.current = null;
      recovery.current = null;
    };
  }, [action, fetchAlternates]);

  // a voice command ("अर्जुन, थांबव", "आवाज कमी कर", "पुढचं गाणं"): the reducer for the screen, the player for the sound
  useEffect(() => {
    if (!control || control.seq <= seen.current) return;
    seen.current = control.seq;
    dispatch({ t: "control", kind: control.kind });
    const p = player.current;
    if (control.kind === "pause") p?.pauseVideo();
    else if (control.kind === "resume") p?.playVideo();
    else if (control.kind === "next" && stateRef.current.canNext) p?.nextVideo();
    else if (control.kind === "previous") p?.previousVideo();
    else if (control.kind === "volume_up") p?.setVolume(Math.min(100, stateRef.current.volume + 20));
    else if (control.kind === "volume_down") p?.setVolume(Math.max(10, stateRef.current.volume - 20));
  }, [control]);

  useEffect(() => {
    player.current?.setVolume(ducked ? Math.round(state.volume * 0.2) : state.volume);
  }, [ducked, state.volume]);

  // Heartbeat: tell the agent the player is still playing every 10 s so media mode can never get stuck.
  useEffect(() => {
    const id = window.setInterval(() => {
      if (shouldHeartbeatMedia(stateRef.current.phase, document.hidden)) onReport("playing");
    }, 10_000);
    return () => window.clearInterval(id);
  }, [onReport]);
  useEffect(() => () => onReport("stopped"), [onReport]); // the screen went away: nothing is playing any more

  useEffect(() => {
    const stopWhenHidden = () => {
      if (document.hidden) onReport("stopped");
      else if (stateRef.current.phase === "playing") onReport("playing");
    };
    document.addEventListener("visibilitychange", stopWhenHidden);
    window.addEventListener("pagehide", stopWhenHidden);
    return () => {
      document.removeEventListener("visibilitychange", stopWhenHidden);
      window.removeEventListener("pagehide", stopWhenHidden);
    };
  }, [onReport]);

  useEffect(() => {
    onReport(reportableMediaState(state, document.hidden));
    // A closed screen and a finished video both go home: nothing is playing and the agent must hear her again.
    if (state.phase === "closed" || state.phase === "ended") onClosed();
  }, [state, onReport, onClosed]);

  const volume = (delta: number) => {
    const v = Math.min(100, Math.max(10, state.volume + delta));
    dispatch({ t: "control", kind: delta > 0 ? "volume_up" : "volume_down" });
    player.current?.setVolume(v);
  };
  const start = () => {
    recovery.current?.tapped();
    dispatch({ t: "tap" });
    player.current?.playVideo(); // from the tap: the browser allows sound
  };
  const toggle = () => {
    if (state.phase === "paused" || state.phase === "blocked") {
      tapped();
      dispatch({ t: "control", kind: "resume" });
      player.current?.playVideo();
    } else {
      dispatch({ t: "control", kind: "pause" });
      player.current?.pauseVideo();
    }
  };
  const next = () => {
    if (!state.canNext) return;
    dispatch({ t: "control", kind: "next" });
    player.current?.nextVideo();
  };
  const paused = state.phase === "paused" || state.phase === "blocked";
  const tapped = () => recovery.current?.tapped();

  return (
    <div className="media-screen" role="dialog" aria-label={state.title || t("video_word")}>
      <div ref={holder} className="media-frame-holder" hidden={state.phase === "fallback"} />
      {state.phase === "blocked" && (
        <button type="button" className="media-start" onClick={start}>
          {t("media_start")}
        </button>
      )}
      {notice && <p className="media-error">{t(notice === "unsupported" ? "media_unsupported" : "media_error")}</p>}
      {state.phase === "fallback" && fallbackLink && (
        <a className="media-start" href={fallbackLink} target="_blank" rel="noopener noreferrer">
          {t("media_open_yt")}
        </a>
      )}
      <h1 className="media-title">{state.title || t("video_word")}</h1>
      <div className="media-bar">
        <button type="button" className="media-btn media-close" onClick={() => dispatch({ t: "close" })}>
          {t("media_close")}
        </button>
        <button type="button" className="media-btn media-toggle" onClick={toggle}>
          {paused ? t("media_start") : t("media_pause")}
        </button>
        <button type="button" className="media-btn" onClick={next} disabled={!state.canNext}>
          {t("media_next")}
        </button>
        <button type="button" className="media-btn" onClick={() => volume(-20)} aria-label={t("vol_down_aria")}>
          {t("vol_down")}
        </button>
        <button type="button" className="media-btn" onClick={() => volume(20)} aria-label={t("vol_up_aria")}>
          {t("vol_up")}
        </button>
      </div>
    </div>
  );
}

/** Shown only when the browser refused to open a WhatsApp / link window (a pop-up blocker): one big tap does it. */
export function LinkPrompt({ title, onOpen, onCancel }: { title: string; onOpen: () => void; onCancel: () => void }) {
  return (
    <div className="media-screen link-prompt" role="dialog" aria-label={title}>
      <button type="button" className="media-start" onClick={onOpen}>
        {t("open_x", { title })}
      </button>
      <button type="button" className="media-btn media-close" onClick={onCancel}>
        {t("no_x")}
      </button>
    </div>
  );
}
