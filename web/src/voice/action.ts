/** What the elder screen OPENS or does when Arjun hears "यूट्यूब", "बातम्या", "व्हॉट्सॲप", "थांबव" ...
 *
 * The agent publishes it as the participant attribute "arjun.action" (see services/voice-agent/screenstate.py),
 * a JSON object {type, kind, value, title, turn}. reasoning decides it from the family's own app_links and core-api
 * validated every value; the page still checks again (never trust a string): only a YouTube id, a wa.me chat or an
 * https link can open, and every action runs exactly once (by its turn number). Pure on purpose, so it is tested.
 */

export type VideoKind = "youtube_video" | "youtube_playlist" | "youtube_channel_live";
export type OpenKind = VideoKind | "whatsapp" | "link";
export type ControlKind = "stop" | "pause" | "resume" | "next" | "previous" | "volume_up" | "volume_down";

export type ArjunAction =
  | { type: "open"; kind: OpenKind; value: string; title: string; turn: number }
  | { type: "call"; kind: "video"; value: string; title: string; turn: number }
  | { type: "control"; kind: ControlKind; value: string; title: string; turn: number };

const CONTROLS: readonly ControlKind[] = ["stop", "pause", "resume", "next", "previous", "volume_up", "volume_down"];
const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/;
const PLAYLIST_ID = /^[A-Za-z0-9_-]{12,64}$/;
const CHANNEL_ID = /^UC[A-Za-z0-9_-]{22}$/;

export function isVideoKind(kind: string): kind is VideoKind {
  return kind === "youtube_video" || kind === "youtube_playlist" || kind === "youtube_channel_live";
}

function safeHttps(value: string): URL | null {
  try {
    const u = new URL(value);
    if (u.protocol !== "https:" || u.username || u.password) return null;
    const host = u.hostname;
    if (!host.includes(".") || host === "localhost" || /^[\d.]+$/.test(host) || host.includes(":")) return null;
    return u;
  } catch {
    return null;
  }
}

/** The action in the attribute, or null when it is empty, malformed, unknown or unsafe. */
export function parseAction(raw: string | undefined): ArjunAction | null {
  if (!raw) return null;
  let o: unknown;
  try {
    o = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof o !== "object" || o === null) return null;
  const a = o as Record<string, unknown>;
  const { type, kind, value, title, turn } = a;
  if (typeof kind !== "string" || typeof value !== "string" || typeof turn !== "number" || !Number.isInteger(turn) || turn <= 0) {
    return null;
  }
  const name = typeof title === "string" ? title.slice(0, 120) : "";
  if (type === "call") {
    return kind === "video" && /^\d{1,9}$/.test(value)
      ? { type, kind, value, title: name, turn }
      : null;
  }
  if (type === "control") {
    return (CONTROLS as readonly string[]).includes(kind) ? { type, kind: kind as ControlKind, value: "", title: name, turn } : null;
  }
  if (type !== "open") return null;
  const ok =
    (kind === "youtube_video" && VIDEO_ID.test(value)) ||
    (kind === "youtube_playlist" && PLAYLIST_ID.test(value)) ||
    (kind === "youtube_channel_live" && CHANNEL_ID.test(value)) ||
    (kind === "whatsapp" && safeHttps(value)?.hostname === "wa.me") ||
    (kind === "link" && safeHttps(value) !== null);
  return ok ? { type, kind: kind as OpenKind, value, title: name, turn } : null;
}

/** An action runs once: only a turn newer than the last one performed. (The same attribute arrives again after a reconnect.) */
export const shouldPerform = (a: ArjunAction, lastTurn: number): boolean => a.turn > lastTurn;

/** The YouTube embed URL for the IFrame Player API (no key needed in the browser); null for a link or a control. */
export function embedSrc(a: ArjunAction, origin: string): string | null {
  if (a.type !== "open") return null;
  const common = `enablejsapi=1&autoplay=1&rel=0&playsinline=1&modestbranding=1&origin=${encodeURIComponent(origin)}`;
  if (a.kind === "youtube_video") return `https://www.youtube.com/embed/${a.value}?${common}`;
  if (a.kind === "youtube_playlist") return `https://www.youtube.com/embed?listType=playlist&list=${a.value}&${common}`;
  if (a.kind === "youtube_channel_live") return `https://www.youtube.com/embed/live_stream?channel=${a.value}&${common}`;
  return null;
}

// ---- the MediaScreen state machine ------------------------------------------------------------------------------
export type MediaPhase = "closed" | "loading" | "playing" | "paused" | "blocked" | "ended" | "error";
export type PlayerState = "playing" | "paused" | "ended" | "blocked" | "error";

export interface MediaState {
  phase: MediaPhase;
  title: string;
  /** A playlist can go to the next song; a single video or a live channel cannot. */
  canNext: boolean;
  /** 10..100 in steps of 20 from 100: "आवाज कमी कर" never mutes. */
  volume: number;
}

export type MediaEvent =
  | { t: "open"; action: ArjunAction }
  | { t: "player"; state: PlayerState }
  | { t: "control"; kind: ControlKind }
  | { t: "tap" }
  | { t: "close" };

export const idleMedia = (volume = 100): MediaState => ({ phase: "closed", title: "", canNext: false, volume });

export function mediaReducer(s: MediaState, e: MediaEvent): MediaState {
  if (e.t === "open") {
    if (e.action.type !== "open" || !isVideoKind(e.action.kind)) return s;
    return { phase: "loading", title: e.action.title, canNext: e.action.kind === "youtube_playlist", volume: s.volume };
  }
  if (s.phase === "closed") return s; // nothing is open: nothing to change
  if (e.t === "close") return idleMedia(s.volume);
  if (e.t === "tap") return s.phase === "blocked" ? { ...s, phase: "loading" } : s;
  if (e.t === "player") return { ...s, phase: e.state === "blocked" ? "blocked" : e.state };
  switch (e.kind) {
    case "stop":
      return idleMedia(s.volume);
    case "pause":
      return { ...s, phase: "paused" };
    case "resume":
      return { ...s, phase: "playing" };
    case "volume_up":
      return { ...s, volume: Math.min(100, s.volume + 20) };
    case "volume_down":
      return { ...s, volume: Math.max(10, s.volume - 20) };
    default:
      return s; // next/previous are done by the player itself
  }
}

/** What the page tells the agent in "arjun.media": while it says "playing" the agent ignores what the mic hears
 *  unless it starts with "अर्जुन", is a bare control phrase, or is a safety phrase. */
export const mediaReport = (s: MediaState): "playing" | "stopped" =>
  s.phase === "playing" ? "playing" : "stopped";

export const reportableMediaState = (s: MediaState, hidden: boolean): "playing" | "stopped" =>
  hidden ? "stopped" : mediaReport(s);

export const shouldHeartbeatMedia = (phase: MediaPhase, hidden: boolean): boolean =>
  phase === "playing" && !hidden;
