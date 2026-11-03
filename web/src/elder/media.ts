/** What the elder page does with one "arjun.action". Pure and tested: the decision, never a side effect.
 *
 * reasoning only chooses among the family's own `app_links` and core-api validated every value, but the page
 * checks again (a URL from the network is never trusted): only a real YouTube id, an https page or a wa.me chat
 * can open. WhatsApp needs the contact's number from `api.contacts`; the number itself is never in the action.
 */

import type { Contact } from "../api";
import type { ControlKind, VideoKind } from "../voice/action";
import type { ActionAttribute } from "../voice/state";

export type MediaPlan =
  | { do: "embed"; kind: VideoKind; value: string; title: string; canNext: boolean; src: string }
  | { do: "window"; url: string; title: string }
  | { do: "control"; command: ControlKind }
  | { do: "none" };

const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/;
const PLAYLIST_ID = /^[A-Za-z0-9_-]{12,64}$/;
const CHANNEL_ID = /^UC[A-Za-z0-9_-]{22}$/;
const CONTROLS: readonly ControlKind[] = ["stop", "pause", "resume", "next", "volume_up", "volume_down"];
const YT_HOSTS = ["youtube.com", "youtube-nocookie.com", "youtu.be"];

/** A plain https web address, or null. No http, no userinfo, no local / numeric hosts. */
export function safeUrl(value: string): URL | null {
  try {
    const u = new URL(value);
    if (u.protocol !== "https:" || u.username || u.password) return null;
    const host = u.hostname.toLowerCase();
    if (!host.includes(".") || host === "localhost" || /^[\d.]+$/.test(host) || host.includes(":")) return null;
    return u;
  } catch {
    return null;
  }
}

const isYoutube = (u: URL): boolean =>
  YT_HOSTS.some((h) => u.hostname === h || u.hostname.endsWith(`.${h}`));

function fromUrl(value: string): URL | null {
  try {
    return new URL(value);
  } catch {
    return null;
  }
}

function videoFromUrl(u: URL): string | null {
  if (!isYoutube(u)) return null;
  if (u.hostname === "youtu.be" || u.hostname.endsWith(".youtu.be")) {
    const id = u.pathname.split("/").filter(Boolean)[0] ?? "";
    return VIDEO_ID.test(id) ? id : null;
  }
  const v = u.searchParams.get("v") ?? "";
  if (VIDEO_ID.test(v)) return v;
  const live = u.pathname.match(/\/(?:live|embed|shorts)\/([A-Za-z0-9_-]{11})(?:\/|$)/);
  return live ? (live[1] ?? null) : null;
}

function channelFromUrl(u: URL): string | null {
  if (!isYoutube(u)) return null;
  const path = u.pathname.match(/\/channel\/(UC[A-Za-z0-9_-]{22})(?:\/|$)/);
  if (path) return path[1] ?? null;
  const query = u.searchParams.get("channel") ?? "";
  return CHANNEL_ID.test(query) ? query : null;
}

/** The YouTube target for an action: a video id, a playlist id or a channel id. */
export function youtubeTarget(action: ActionAttribute): { kind: VideoKind; value: string } | null {
  const value = action.value ?? "";
  const url = value.startsWith("http") ? fromUrl(value) : null;
  if (action.kind === "youtube_video") {
    const id = action.video_id ?? (url ? videoFromUrl(url) : value);
    return id && VIDEO_ID.test(id) ? { kind: "youtube_video", value: id } : null;
  }
  if (action.kind === "youtube_playlist") {
    if (url && !isYoutube(url)) return null;
    const id = (url ? url.searchParams.get("list") : value) ?? "";
    return PLAYLIST_ID.test(id) ? { kind: "youtube_playlist", value: id } : null;
  }
  if (action.kind === "youtube_live" || action.kind === "youtube_channel_live") {
    const direct = action.video_id ?? "";
    if (VIDEO_ID.test(direct)) return { kind: "youtube_video", value: direct };
    if (url) {
      const video = videoFromUrl(url);
      if (video) return { kind: "youtube_video", value: video };
      const channel = channelFromUrl(url);
      return channel ? { kind: "youtube_channel_live", value: channel } : null;
    }
    if (CHANNEL_ID.test(value)) return { kind: "youtube_channel_live", value };
    if (VIDEO_ID.test(value)) return { kind: "youtube_video", value };
    return null;
  }
  return null;
}

/** The IFrame Player API URL. No API key in the browser: only a public id. */
export function embedSrc(kind: VideoKind, id: string, origin: string): string {
  const common = `autoplay=1&rel=0&modestbranding=1&playsinline=1&enablejsapi=1&origin=${encodeURIComponent(origin)}`;
  if (kind === "youtube_video") return `https://www.youtube.com/embed/${id}?${common}`;
  if (kind === "youtube_playlist") return `https://www.youtube.com/embed?listType=playlist&list=${id}&${common}`;
  return `https://www.youtube.com/embed/live_stream?channel=${id}&${common}`;
}

/** Digits only; an Indian 10-digit mobile gets 91 (the same rule reasoning uses). "" = no usable number. */
export function waNumber(phone: string): string {
  let digits = phone.replace(/\D/g, "");
  if (digits.length === 10) digits = `91${digits}`;
  return digits.length >= 10 && digits.length <= 15 ? digits : "";
}

/** https://wa.me/<digits>, from the contact's own phone or from a wa.me value the agent already built. */
export function whatsappUrl(action: ActionAttribute, contacts: Contact[]): string | null {
  const contact = action.contact_id ? contacts.find((c) => c.id === action.contact_id) : undefined;
  if (contact) {
    const digits = waNumber(contact.phone);
    if (digits) return `https://wa.me/${digits}`;
  }
  const value = action.value ?? "";
  const asUrl = safeUrl(value);
  const fromLink = asUrl?.hostname === "wa.me" ? asUrl.pathname : value;
  const digits = waNumber(fromLink);
  return digits ? `https://wa.me/${digits}` : null;
}

const control = (value: string): ControlKind | null =>
  (CONTROLS as readonly string[]).includes(value) ? (value as ControlKind) : null;

/** The one decision for an action: play an embed, open a window, drive the player, or do nothing. */
export function planAction(action: ActionAttribute, contacts: Contact[], origin: string): MediaPlan {
  if (action.type === "control") {
    const command = control(action.command ?? action.kind);
    return command ? { do: "control", command } : { do: "none" };
  }
  const title = action.title?.trim() || "अर्जुन";
  const target = youtubeTarget(action);
  if (target) {
    return {
      do: "embed",
      kind: target.kind,
      value: target.value,
      title,
      canNext: target.kind === "youtube_playlist",
      src: embedSrc(target.kind, target.value, origin),
    };
  }
  if (action.kind === "whatsapp") {
    const url = whatsappUrl(action, contacts);
    return url ? { do: "window", url, title } : { do: "none" };
  }
  if (action.kind === "url" || action.kind === "link") {
    const url = safeUrl(action.value ?? "");
    return url ? { do: "window", url: url.toString(), title } : { do: "none" };
  }
  return { do: "none" };
}
