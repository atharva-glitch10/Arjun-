import { useEffect, useReducer, useRef } from "react";

import { embedSrc, idleMedia, mediaReducer, mediaReport } from "../voice/action";
import type { ArjunAction, ControlKind, MediaState, PlayerState } from "../voice/action";

// The little part of the YouTube IFrame Player API we use (loaded from youtube.com/iframe_api, no key in the browser).
interface YtPlayer {
  playVideo(): void;
  pauseVideo(): void;
  nextVideo(): void;
  setVolume(v: number): void;
  destroy(): void;
}
interface YtApi {
  Player: new (
    el: HTMLIFrameElement,
    opts: { events: { onReady?: () => void; onStateChange?: (e: { data: number }) => void; onError?: () => void; onAutoplayBlocked?: () => void } },
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

const BLOCKED_AFTER_MS = 5000; // still not playing after this long: autoplay with sound was refused

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
}: {
  action: ArjunAction;
  control: MediaControlEvent | null;
  onReport: (state: "playing" | "stopped") => void;
  onClosed: () => void;
}) {
  const [state, dispatch] = useReducer(mediaReducer, undefined, () => mediaReducer(idleMedia(), { t: "open", action }));
  const iframe = useRef<HTMLIFrameElement | null>(null);
  const player = useRef<YtPlayer | null>(null);
  const seen = useRef(0);
  const stateRef = useRef<MediaState>(state);
  stateRef.current = state;

  // one iframe per opened action
  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      if (stateRef.current.phase === "loading") dispatch({ t: "player", state: "blocked" });
    }, BLOCKED_AFTER_MS);
    void loadYouTubeApi()
      .then((YT) => {
        if (cancelled || !iframe.current) return;
        player.current = new YT.Player(iframe.current, {
          events: {
            onReady: () => player.current?.setVolume(stateRef.current.volume),
            onStateChange: (e) => {
              const s = playerStateOf(e.data);
              if (s) dispatch({ t: "player", state: s });
            },
            onError: () => dispatch({ t: "player", state: "error" }),
            onAutoplayBlocked: () => dispatch({ t: "player", state: "blocked" }),
          },
        });
      })
      .catch(() => dispatch({ t: "player", state: "error" }));
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      player.current?.destroy();
      player.current = null;
    };
  }, [action]);

  // a voice command ("अर्जुन, थांबव", "आवाज कमी कर", "पुढचं गाणं"): the reducer for the screen, the player for the sound
  useEffect(() => {
    if (!control || control.seq <= seen.current) return;
    seen.current = control.seq;
    dispatch({ t: "control", kind: control.kind });
    const p = player.current;
    if (control.kind === "pause") p?.pauseVideo();
    else if (control.kind === "resume") p?.playVideo();
    else if (control.kind === "next" && stateRef.current.canNext) p?.nextVideo();
    else if (control.kind === "volume_up") p?.setVolume(Math.min(100, stateRef.current.volume + 20));
    else if (control.kind === "volume_down") p?.setVolume(Math.max(10, stateRef.current.volume - 20));
  }, [control]);

  // Heartbeat: tell the agent the player is still playing every 10 s so media mode can never get stuck.
  useEffect(() => {
    const id = window.setInterval(() => {
      if (stateRef.current.phase === "playing" || stateRef.current.phase === "loading") onReport("playing");
    }, 10_000);
    return () => window.clearInterval(id);
  }, [onReport]);
  useEffect(() => () => onReport("stopped"), [onReport]); // the screen went away: nothing is playing any more

  useEffect(() => {
    onReport(mediaReport(state));
    // A closed screen and a finished video both go home: nothing is playing and the agent must hear her again.
    if (state.phase === "closed" || state.phase === "ended") onClosed();
  }, [state, onReport, onClosed]);

  const src = embedSrc(action, window.location.origin);
  const volume = (delta: number) => {
    const v = Math.min(100, Math.max(10, state.volume + delta));
    dispatch({ t: "control", kind: delta > 0 ? "volume_up" : "volume_down" });
    player.current?.setVolume(v);
  };
  const start = () => {
    dispatch({ t: "tap" });
    player.current?.playVideo();
  };
  const toggle = () => {
    if (state.phase === "paused" || state.phase === "blocked") {
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

  return (
    <div className="media-screen" role="dialog" aria-label={state.title || "वीडियो"}>
      {src && (
        <iframe
          ref={iframe}
          className="media-frame"
          src={src}
          title={state.title || "YouTube"}
          allow="autoplay; encrypted-media; fullscreen"
          allowFullScreen
        />
      )}
      {state.phase === "blocked" && (
        <button type="button" className="media-start" onClick={start}>
          ▶ सुरू करा
        </button>
      )}
      {state.phase === "error" && <p className="media-error">व्हिडिओ सुरू झाला नाही. "अर्जुन, दुसरं लाव" म्हणा किंवा बंद करा दाबा.</p>}
      <h1 className="media-title">{state.title || "व्हिडिओ"}</h1>
      <div className="media-bar">
        <button type="button" className="media-btn media-close" onClick={() => dispatch({ t: "close" })}>
          ✕ बंद करा
        </button>
        <button type="button" className="media-btn media-toggle" onClick={toggle}>
          {paused ? "▶ सुरू करा" : "⏸ थांबवा"}
        </button>
        <button type="button" className="media-btn" onClick={next} disabled={!state.canNext}>
          ⏭ पुढचं
        </button>
        <button type="button" className="media-btn" onClick={() => volume(-20)} aria-label="आवाज कमी">
          🔉 कमी
        </button>
        <button type="button" className="media-btn" onClick={() => volume(20)} aria-label="आवाज जास्त">
          🔊 जास्त
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
        {title} उघडा
      </button>
      <button type="button" className="media-btn media-close" onClick={onCancel}>
        ✕ नको
      </button>
    </div>
  );
}
