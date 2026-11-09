import { useRef, useState } from "react";

import { embedSrc } from "../voice/action";
import type { ArjunAction } from "../voice/action";

/** DEV-ONLY (`/?debug=yt`): the YouTube embed under test, same iframe as the elder media screen plus the IFrame Player
 *  API logging onReady / onError(code) / onStateChange. Never shipped: main.tsx mounts it only when import.meta.env.DEV.
 *  Error codes: 2 bad id, 5 HTML5 player error, 100 removed/private, 101/150 embedding blocked, 153 missing referrer/origin. */
const SAMPLES: [string, string][] = [
  ["dQw4w9WgXcQ", "known embeddable #1 (Rick Astley)"],
  ["jNQXAC9IVRM", "known embeddable #2 (Me at the zoo)"],
  ["aqz-KE-bpKQ", "known embeddable #3 (Big Buck Bunny)"],
  ["kJQP7kiw5Fk", "label video, often embed-blocked (Despacito)"],
];

interface Yt {
  Player: new (el: string | HTMLElement, o: Record<string, unknown>) => { destroy(): void; getPlayerState(): number };
}

function loadApi(): Promise<Yt> {
  const w = window as unknown as { YT?: Yt; onYouTubeIframeAPIReady?: () => void };
  if (w.YT?.Player) return Promise.resolve(w.YT);
  return new Promise((resolve, reject) => {
    w.onYouTubeIframeAPIReady = () => w.YT && resolve(w.YT);
    const s = document.createElement("script");
    s.src = "https://www.youtube.com/iframe_api";
    s.onerror = () => reject(new Error("iframe_api failed to load"));
    document.head.appendChild(s);
  });
}

export function YtDebug() {
  const [log, setLog] = useState<string[]>([]);
  const [id, setId] = useState(SAMPLES[0]?.[0] ?? "");
  const [host, setHost] = useState("https://www.youtube.com");
  const [mode, setMode] = useState<"raw" | "api">("raw");
  const box = useRef<HTMLDivElement | null>(null);
  const say = (m: string) => {
    const line = `${new Date().toISOString().slice(11, 23)} ${m}`;
    console.log("[yt-debug]", line);
    setLog((l) => [...l, line]);
  };

  const run = async () => {
    if (!box.current) return;
    box.current.innerHTML = "";
    say(`--- ${mode} | ${host} | ${id} | origin=${window.location.origin} | referrerPolicy=${(document as unknown as { referrerPolicy?: string }).referrerPolicy || "(default)"}`);
    say(`MediaSource=${typeof MediaSource !== "undefined"} h264=${typeof MediaSource !== "undefined" && MediaSource.isTypeSupported('video/mp4; codecs="avc1.42E01E"')} ua=${navigator.userAgent.slice(0, 90)}`);
    const events = {
      onReady: () => say("onReady"),
      onError: (e: { data: number }) => say(`onError code=${e.data}`),
      onStateChange: (e: { data: number }) => say(`onStateChange ${e.data}`),
      onAutoplayBlocked: () => say("onAutoplayBlocked"),
    };
    try {
      const YT = await loadApi();
      say("iframe_api loaded");
      if (mode === "raw") {
        const a = { type: "open", kind: "youtube_video", value: id, video_id: id, title: "x", turn: 1 } as unknown as ArjunAction;
        const iframe = document.createElement("iframe");
        iframe.src = (embedSrc(a, window.location.origin) ?? "").replace("https://www.youtube.com", host);
        iframe.allow = "autoplay; encrypted-media; fullscreen";
        iframe.allowFullscreen = true;
        iframe.style.cssText = "width:100%;aspect-ratio:16/9;border:0;background:black";
        say(`iframe src=${iframe.src}`);
        box.current.appendChild(iframe);
        new YT.Player(iframe, { events });
      } else {
        const div = document.createElement("div");
        box.current.appendChild(div);
        new YT.Player(div, {
          videoId: id, host, width: "100%", height: "360",
          playerVars: { playsinline: 1, rel: 0, modestbranding: 1, enablejsapi: 1, origin: window.location.origin },
          events,
        });
      }
    } catch (e) {
      say(`FAILED: ${(e as Error).message}`);
    }
  };

  return (
    <div style={{ padding: 16, fontFamily: "monospace", maxWidth: 900 }}>
      <h1>YouTube embed debug (dev only)</h1>
      <label>
        video{" "}
        <select value={id} onChange={(e) => setId(e.target.value)}>
          {SAMPLES.map(([v, d]) => (
            <option key={v} value={v}>{`${v} ${d}`}</option>
          ))}
        </select>{" "}
        or id <input value={id} onChange={(e) => setId(e.target.value)} size={14} />
      </label>{" "}
      <select value={host} onChange={(e) => setHost(e.target.value)} aria-label="host">
        <option>https://www.youtube.com</option>
        <option>https://www.youtube-nocookie.com</option>
      </select>{" "}
      <select value={mode} onChange={(e) => setMode(e.target.value as "raw" | "api")} aria-label="mode">
        <option value="raw">current iframe (autoplay=1 in URL)</option>
        <option value="api">IFrame API player (no autoplay)</option>
      </select>{" "}
      <button id="yt-run" onClick={() => void run()}>run</button>
      <div ref={box} style={{ marginTop: 12, background: "black", minHeight: 120 }} />
      <pre id="yt-log" style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>{log.join("\n")}</pre>
    </div>
  );
}
