import { describe, expect, it } from "vitest";

import type { Contact } from "../api";
import { idleMedia, mediaReducer, mediaReport, reportableMediaState, shouldHeartbeatMedia } from "../voice/action";
import type { ActionAttribute } from "../voice/state";
import { isFreshAction } from "../voice/state";
import { embedSrc, planAction, waNumber, whatsappUrl, youtubeTarget } from "./media";

const ID = "dQw4w9WgXcQ";
const PL = "PL01mceoBxHCiCj28l-viryuhBh7nXsqZN";
const CH = "UCH7nv1A9xIrAifZJNvt7cgA";
const origin = "http://localhost:5173";
const contacts: Contact[] = [
  { id: 7, name: "चंद्रकांत", relation: "मुलगा", phone: "00000 00003" },
  { id: 8, name: "अनिता", relation: "मुलगी", phone: "+91 90000 00001" },
];
const A = (o: Partial<ActionAttribute>): ActionAttribute => ({ turn: 5, type: "open", kind: "link", ...o });
const src = (a: ActionAttribute) => {
  const plan = planAction(a, contacts, origin);
  return plan.do === "embed" ? plan.src : "";
};

describe("planAction: YouTube embeds (no key in the browser)", () => {
  it("a video plays its id, with the autoplay / no-branding player vars", () => {
    const s = src(A({ kind: "youtube_video", value: ID, title: "भजन" }));
    expect(s.startsWith(`https://www.youtube.com/embed/${ID}?`)).toBe(true);
    expect(s).toContain("autoplay=1");
    expect(s).toContain("rel=0");
    expect(s).toContain("modestbranding=1");
    expect(s).toContain("playsinline=1");
    expect(s).toContain(`origin=${encodeURIComponent(origin)}`);
    expect(planAction(A({ kind: "youtube_video", value: ID, title: "भजन" }), contacts, origin)).toMatchObject({
      do: "embed",
      kind: "youtube_video",
      value: ID,
      title: "भजन",
      canNext: false,
    });
  });

  it("prefers video_id and accepts a watch URL", () => {
    expect(youtubeTarget(A({ kind: "youtube_video", value: "https://www.youtube.com/watch?v=" + ID }))).toEqual({
      kind: "youtube_video",
      value: ID,
    });
    expect(youtubeTarget(A({ kind: "youtube_video", value: "bad", video_id: ID }))).toEqual({ kind: "youtube_video", value: ID });
  });

  it("a youtube_video action always plays in the in-app IFrame, never a window", () => {
    const plan = planAction(A({ kind: "youtube_video", video_id: ID, title: "भजन" }), contacts, origin);
    expect(plan).toMatchObject({ do: "embed", kind: "youtube_video", value: ID, title: "भजन" });
    expect(plan.do).not.toBe("window");
    if (plan.do === "embed") expect(plan.src).toBe(embedSrc("youtube_video", ID, origin));
  });

  it("a playlist takes its list id from the URL and can go next", () => {
    const plan = planAction(A({ kind: "youtube_playlist", value: `https://www.youtube.com/playlist?list=${PL}` }), contacts, origin);
    expect(plan).toMatchObject({ do: "embed", kind: "youtube_playlist", value: PL, canNext: true });
    expect(src(A({ kind: "youtube_playlist", value: PL }))).toContain(`listType=playlist&list=${PL}`);
  });

  it("a live channel uses live_stream?channel=, unless its URL carries a video", () => {
    const channel = planAction(A({ kind: "youtube_live", value: `https://www.youtube.com/channel/${CH}/live` }), contacts, origin);
    expect(channel).toMatchObject({ do: "embed", kind: "youtube_channel_live", value: CH });
    expect(src(A({ kind: "youtube_live", value: CH }))).toContain(`live_stream?channel=${CH}`);
    expect(youtubeTarget(A({ kind: "youtube_live", value: `https://www.youtube.com/watch?v=${ID}` }))).toEqual({
      kind: "youtube_video",
      value: ID,
    });
  });

  it("never builds an embed from a missing or malformed id", () => {
    expect(planAction(A({ kind: "youtube_video", value: "short" }), contacts, origin)).toEqual({ do: "none" });
    expect(planAction(A({ kind: "youtube_playlist", value: "https://evil.example/playlist?list=" + PL }), contacts, origin)).toEqual({
      do: "none",
    });
    expect(embedSrc("youtube_video", ID, origin)).toContain(ID);
  });
});

describe("planAction: links and WhatsApp", () => {
  it("opens an https link (and the url alias) in a window, never http or javascript", () => {
    expect(planAction(A({ kind: "link", value: "https://photos.google.com/share/abc", title: "फोटो" }), contacts, origin)).toEqual({
      do: "window",
      url: "https://photos.google.com/share/abc",
      title: "फोटो",
    });
    expect(planAction(A({ kind: "url", value: "https://www.youtube.com/results?search_query=x" }), contacts, origin)).toMatchObject({
      do: "window",
    });
    expect(planAction(A({ kind: "link", value: "http://insecure.example/x" }), contacts, origin)).toEqual({ do: "none" });
    expect(planAction(A({ kind: "link", value: "javascript:alert(1)" }), contacts, origin)).toEqual({ do: "none" });
    expect(planAction(A({ kind: "link", value: "https://127.0.0.1/x" }), contacts, origin)).toEqual({ do: "none" });
  });

  it("WhatsApp needs the contact's own number; a 10-digit number gets 91", () => {
    expect(waNumber("00000 00003")).toBe("910000000003");
    expect(waNumber("+91 90000 00001")).toBe("919000000001");
    expect(waNumber("123")).toBe("");
    expect(whatsappUrl(A({ kind: "whatsapp", contact_id: 7 }), contacts)).toBe("https://wa.me/910000000003");
    expect(whatsappUrl(A({ kind: "whatsapp", value: "https://wa.me/919000000001" }), contacts)).toBe("https://wa.me/919000000001");
    expect(planAction(A({ kind: "whatsapp", contact_id: 7, title: "चंद्रकांत" }), contacts, origin)).toEqual({
      do: "window",
      url: "https://wa.me/910000000003",
      title: "चंद्रकांत",
    });
    expect(planAction(A({ kind: "whatsapp", contact_id: 99 }), contacts, origin)).toEqual({ do: "none" });
    expect(planAction(A({ kind: "whatsapp", value: "https://wa.me/1" }), contacts, origin)).toEqual({ do: "none" });
  });
});

describe("planAction: controls and unknown kinds", () => {
  it("maps every player command, from command or kind", () => {
    for (const command of ["stop", "pause", "resume", "next", "volume_up", "volume_down"] as const) {
      expect(planAction(A({ type: "control", kind: command, command }), contacts, origin)).toEqual({ do: "control", command });
      expect(planAction(A({ type: "control", kind: command }), contacts, origin)).toEqual({ do: "control", command });
    }
    expect(planAction(A({ type: "control", kind: "format_disk" }), contacts, origin)).toEqual({ do: "none" });
  });

  it("does nothing for an unknown open kind", () => {
    expect(planAction(A({ kind: "news_read" }), contacts, origin)).toEqual({ do: "none" });
  });

  it("runs each action once per turn", () => {
    const a = A({ kind: "youtube_video", value: ID, turn: 8 });
    expect(isFreshAction(a, 7)).toBe(true);
    expect(isFreshAction(a, 8)).toBe(false);
  });
});

describe("the MediaScreen state machine: playing -> stop -> home", () => {
  const video = A({ kind: "youtube_video", value: ID, title: "भजन" });
  const action = { type: "open" as const, kind: "youtube_video" as const, value: video.value!, title: "भजन", turn: 5 };

  it("opens, plays, stops and ends closed (the screen calls onClosed for both closed and ended)", () => {
    let s = mediaReducer(idleMedia(), { t: "open", action });
    expect(s.phase).toBe("loading");
    expect(mediaReport(s)).toBe("stopped"); // loading is not confirmation that YouTube actually started
    s = mediaReducer(s, { t: "player", state: "playing" });
    expect(s.phase).toBe("playing");
    s = mediaReducer(s, { t: "control", kind: "stop" });
    expect(s.phase).toBe("closed");
    expect(mediaReport(s)).toBe("stopped");
    const ended = mediaReducer({ ...idleMedia(), phase: "playing" }, { t: "player", state: "ended" });
    expect(ended.phase).toBe("ended");
    expect(mediaReport(ended)).toBe("stopped");
    const error = mediaReducer({ ...idleMedia(), phase: "playing" }, { t: "player", state: "error" });
    expect(mediaReport(error)).toBe("stopped");
  });
});

describe("media reporting and heartbeat", () => {
  it("reports playing only when playback is confirmed and the elder page is visible", () => {
    const state = { ...idleMedia(), phase: "playing" as const };
    expect(reportableMediaState(state, false)).toBe("playing");
    expect(reportableMediaState(state, true)).toBe("stopped");
    expect(shouldHeartbeatMedia("playing", false)).toBe(true);
    expect(shouldHeartbeatMedia("playing", true)).toBe(false);
    expect(shouldHeartbeatMedia("loading", false)).toBe(false);
    // Six 10-second heartbeats keep a 60-second playback session actively reported.
    for (let elapsed = 0; elapsed < 60; elapsed += 10) expect(shouldHeartbeatMedia("playing", false)).toBe(true);
  });
});
