/** Pure helpers for the elder YouTube player (no DOM, no network: the screen injects both), so every rule is unit-tested.
 *
 *  Root cause hunt (2026-11-09): "Your browser can't play this video" is YouTube's generic HTML5 player error (code 5, or
 *  101/150/153 when embedding is refused). We cannot make every video embeddable, so the player (a) embeds through the
 *  IFrame Player API on youtube-nocookie.com with an explicit referrer policy, (b) never autoplays before a tap, and
 *  (c) on an error tries up to 3 other search results, then offers a one-tap "open in YouTube" - never a dead dark box. */

export const YT_HOST = "https://www.youtube-nocookie.com";
/** onError codes that mean "this video will not play here": 2 bad id, 5 HTML5 error, 100 removed/private, 101/150 embedding
 *  blocked, 153 missing referrer/origin. */
export const FALLBACK_ERRORS: readonly number[] = [2, 5, 100, 101, 150, 153];
export const MAX_ALTERNATES = 3;
export const IFRAME_ALLOW = "autoplay; encrypted-media; picture-in-picture; fullscreen";
export const REFERRER_POLICY = "strict-origin-when-cross-origin";

export type EmbedKind = "youtube_video" | "youtube_playlist" | "youtube_channel_live";

/** What to embed. A channel is played as its UPLOADS playlist (newest first): a /live_stream embed fails whenever the
 *  channel is not live right now, which is most of the day. */
export function embedTarget(kind: EmbedKind, value: string): { videoId?: string; list?: string } | null {
  if (kind === "youtube_video") return /^[\w-]{11}$/.test(value) ? { videoId: value } : null;
  if (kind === "youtube_playlist") return /^[\w-]{10,64}$/.test(value) ? { list: value } : null;
  if (kind === "youtube_channel_live") return /^UC[\w-]{22}$/.test(value) ? { list: `UU${value.slice(2)}` } : null;
  return null;
}

/** The iframe URL for the IFrame Player API on youtube-nocookie.com. No autoplay: playback starts from a tap. */
export function embedUrl(target: { videoId?: string; list?: string }, origin: string): string {
  const vars = `enablejsapi=1&playsinline=1&rel=0&modestbranding=1&origin=${encodeURIComponent(origin)}`;
  if (target.videoId) return `${YT_HOST}/embed/${target.videoId}?${vars}`;
  return `${YT_HOST}/embed?listType=playlist&list=${target.list ?? ""}&${vars}`;
}

/** True when this browser can play YouTube's H.264 / VP9 video through MSE (or natively, as iPhone Safari does). A WebView
 *  without it can only show "can't play this video", so the screen goes straight to the YouTube-app link. */
export function supportsPlayback(win: {
  MediaSource?: { isTypeSupported(t: string): boolean };
  ManagedMediaSource?: unknown;
  document?: { createElement(tag: string): unknown };
}): boolean {
  const types = ['video/mp4; codecs="avc1.42E01E"', 'video/webm; codecs="vp9"'];
  const mse = win.MediaSource;
  if (mse && typeof mse.isTypeSupported === "function" && types.some((t) => mse.isTypeSupported(t))) return true;
  if (win.ManagedMediaSource) return true; // iOS 17+
  try {
    const v = win.document?.createElement("video") as { canPlayType?: (t: string) => string } | undefined;
    return !!v?.canPlayType && types.some((t) => v.canPlayType?.(t) !== "");
  } catch {
    return false;
  }
}

/** One tap to open the video in YouTube itself: the Android intent opens the app (or the browser page when the app is
 *  missing); everywhere else youtu.be, which iOS and desktop route to the app / site. */
export function appLink(videoId: string, userAgent: string): string {
  if (/android/i.test(userAgent)) {
    return `intent://www.youtube.com/watch?v=${videoId}#Intent;package=com.google.android.youtube;scheme=https;S.browser_fallback_url=${encodeURIComponent(
      `https://youtu.be/${videoId}`,
    )};end`;
  }
  return `https://youtu.be/${videoId}`;
}

/** The ids to try after the first one failed: other search results, never the failed ones, at most MAX_ALTERNATES. */
export function alternates(results: { video_id?: string }[], tried: string[]): string[] {
  const out: string[] = [];
  for (const r of results) {
    const id = r.video_id ?? "";
    if (/^[\w-]{11}$/.test(id) && !tried.includes(id) && !out.includes(id)) out.push(id);
    if (out.length === MAX_ALTERNATES) break;
  }
  return out;
}

/** Load the YouTube IFrame API and hand it over; if the script cannot be loaded, say so (never throw into the screen). */
export function whenApiReady<T>(load: () => Promise<T>, onReady: (api: T) => void, onFail: () => void): Promise<void> {
  return load().then(onReady, onFail);
}

export interface Recovery {
  /** Call on every player error. Resolves once it has either loaded another video or given up. */
  onError(code: number): Promise<void>;
  /** A tap happened: later videos may start by themselves. */
  tapped(): void;
}

/** Error recovery: a video that will not play -> the next search result (up to 3) -> the YouTube-app link. */
export function createRecovery(o: {
  title: string;
  firstId: string | null;
  fetchAlternates: (query: string) => Promise<{ video_id?: string }[]>;
  load: (id: string, autoplay: boolean) => void;
  notice: () => void;
  giveUp: (videoId: string | null) => void;
}): Recovery {
  const tried: string[] = o.firstId ? [o.firstId] : [];
  let queue: string[] | null = null;
  let userTapped = false;
  return {
    tapped() {
      userTapped = true;
    },
    async onError(code) {
      if (!FALLBACK_ERRORS.includes(code)) return;
      o.notice();
      if (queue === null) {
        try {
          queue = o.firstId && o.title ? alternates(await o.fetchAlternates(o.title), tried) : [];
        } catch {
          queue = [];
        }
      }
      const next = queue.shift();
      if (next) {
        tried.push(next);
        o.load(next, userTapped);
      } else {
        o.giveUp(o.firstId);
      }
    },
  };
}
