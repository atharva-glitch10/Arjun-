import { describe, expect, it } from "vitest";

import { embedSrc, idleMedia, isVideoKind, mediaReducer, mediaReport, parseAction, shouldPerform } from "./action";
import type { ArjunAction, MediaState } from "./action";

const ID = "dQw4w9WgXcQ";
const PL = "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf";
const CH = "UCZFMm1mMw0F81Z37aaEzTUA";
const raw = (o: object) => JSON.stringify(o);
const open = (kind: string, value: string, extra: object = {}) =>
  parseAction(raw({ type: "open", kind, value, title: "भजन", turn: 5, ...extra }));

describe("parseAction: only what core-api validated and the agent published", () => {
  it("accepts a video, a playlist, a live channel, WhatsApp and a link", () => {
    expect(open("youtube_video", ID)).toMatchObject({ type: "open", kind: "youtube_video", value: ID, title: "भजन", turn: 5 });
    expect(open("youtube_playlist", PL)).not.toBeNull();
    expect(open("youtube_channel_live", CH)).not.toBeNull();
    expect(open("whatsapp", "https://wa.me/919000000001")).not.toBeNull();
    expect(open("link", "https://photos.google.com/share/abc")).not.toBeNull();
  });

  it("accepts the six controls", () => {
    for (const kind of ["stop", "pause", "resume", "next", "volume_up", "volume_down"]) {
      expect(parseAction(raw({ type: "control", kind, value: "", title: "", turn: 3 }))).toMatchObject({ type: "control", kind });
    }
  });

  it("rejects anything else", () => {
    expect(parseAction(undefined)).toBeNull();
    expect(parseAction("")).toBeNull();
    expect(parseAction("not json")).toBeNull();
    expect(parseAction(raw({ type: "none", kind: "", value: "", title: "", turn: 1 }))).toBeNull();
    expect(open("youtube_video", "short")).toBeNull();
    expect(open("youtube_video", ID + "x")).toBeNull();
    expect(open("youtube_video", "https://evil.example/x")).toBeNull();
    expect(open("youtube_playlist", "x y")).toBeNull();
    expect(open("youtube_channel_live", "not-a-channel")).toBeNull();
    expect(open("whatsapp", "http://wa.me/1")).toBeNull(); // http is never opened
    expect(open("whatsapp", "https://evil.example/1")).toBeNull(); // WhatsApp means wa.me
    expect(open("link", "javascript:alert(1)")).toBeNull();
    expect(open("link", "https://user:pw@photos.google.com/x")).toBeNull();
    expect(open("link", "https://127.0.0.1/x")).toBeNull();
    expect(open("anything_else", "https://photos.google.com/x")).toBeNull();
    expect(parseAction(raw({ type: "control", kind: "format_disk", value: "", title: "", turn: 1 }))).toBeNull();
    expect(open("youtube_video", ID, { turn: 0 })).toBeNull(); // no turn number: cannot be performed once
    expect(open("youtube_video", ID, { turn: "7" })).toBeNull();
  });

  it("knows which kinds are video", () => {
    expect(["youtube_video", "youtube_playlist", "youtube_channel_live"].every(isVideoKind)).toBe(true);
    expect(isVideoKind("whatsapp") || isVideoKind("link")).toBe(false);
  });
});

describe("shouldPerform: every action runs exactly once", () => {
  it("only a newer turn runs", () => {
    const a = open("youtube_video", ID) as ArjunAction;
    expect(shouldPerform(a, 4)).toBe(true);
    expect(shouldPerform(a, 5)).toBe(false); // the same attribute delivered again after a reconnect
    expect(shouldPerform(a, 9)).toBe(false);
  });
});

describe("embedSrc: the IFrame Player API, no key in the browser", () => {
  const origin = "http://localhost:5173";
  it("builds an autoplaying embed for each kind", () => {
    const v = embedSrc(open("youtube_video", ID) as ArjunAction, origin)!;
    expect(v.startsWith(`https://www.youtube.com/embed/${ID}?`)).toBe(true);
    expect(v).toContain("enablejsapi=1");
    expect(v).toContain("autoplay=1");
    expect(v).toContain("rel=0");
    expect(v).toContain(`origin=${encodeURIComponent(origin)}`);
    const p = embedSrc(open("youtube_playlist", PL) as ArjunAction, origin)!;
    expect(p).toContain("listType=playlist");
    expect(p).toContain(`list=${PL}`);
    const l = embedSrc(open("youtube_channel_live", CH) as ArjunAction, origin)!;
    expect(l.startsWith("https://www.youtube.com/embed/live_stream?")).toBe(true);
    expect(l).toContain(`channel=${CH}`);
  });
  it("is null for a link, WhatsApp or a control", () => {
    expect(embedSrc(open("link", "https://photos.google.com/x") as ArjunAction, origin)).toBeNull();
    expect(embedSrc(parseAction(raw({ type: "control", kind: "stop", value: "", title: "", turn: 2 })) as ArjunAction, origin)).toBeNull();
  });
});

describe("mediaReducer: the MediaScreen state machine", () => {
  const video = open("youtube_video", ID) as ArjunAction;
  const playlist = open("youtube_playlist", PL) as ArjunAction;
  const step = (s: MediaState, ...events: Parameters<typeof mediaReducer>[1][]) => events.reduce(mediaReducer, s);

  it("starts closed and loads when a video opens", () => {
    expect(idleMedia().phase).toBe("closed");
    const s = step(idleMedia(), { t: "open", action: video });
    expect(s).toMatchObject({ phase: "loading", title: "भजन", canNext: false });
    expect(step(idleMedia(), { t: "open", action: playlist }).canNext).toBe(true);
  });

  it("follows the player", () => {
    let s = step(idleMedia(), { t: "open", action: video }, { t: "player", state: "playing" });
    expect(s.phase).toBe("playing");
    s = step(s, { t: "player", state: "paused" });
    expect(s.phase).toBe("paused");
    s = step(s, { t: "player", state: "ended" });
    expect(s.phase).toBe("ended");
  });

  it("autoplay blocked shows the big start button, a tap starts it", () => {
    let s = step(idleMedia(), { t: "open", action: video }, { t: "player", state: "blocked" });
    expect(s.phase).toBe("blocked");
    s = step(s, { t: "tap" });
    expect(s.phase).toBe("loading");
  });

  it("controls: stop closes, pause / resume, volume in steps and never out of range", () => {
    let s = step(idleMedia(), { t: "open", action: video }, { t: "player", state: "playing" });
    s = step(s, { t: "control", kind: "pause" });
    expect(s.phase).toBe("paused");
    s = step(s, { t: "control", kind: "resume" });
    expect(s.phase).toBe("playing");
    const start = s.volume;
    s = step(s, { t: "control", kind: "volume_down" });
    expect(s.volume).toBe(start - 20);
    for (let i = 0; i < 10; i++) s = step(s, { t: "control", kind: "volume_down" });
    expect(s.volume).toBe(10); // never silent: "आवाज कमी कर" is not "mute"
    for (let i = 0; i < 10; i++) s = step(s, { t: "control", kind: "volume_up" });
    expect(s.volume).toBe(100);
    expect(step(s, { t: "control", kind: "stop" }).phase).toBe("closed");
    expect(step(s, { t: "close" }).phase).toBe("closed");
  });

  it("controls do nothing when nothing is open", () => {
    expect(step(idleMedia(), { t: "control", kind: "pause" })).toEqual(idleMedia());
    expect(step(idleMedia(), { t: "player", state: "playing" })).toEqual(idleMedia());
  });

  it("keeps the volume across videos", () => {
    let s = step(idleMedia(), { t: "open", action: video }, { t: "control", kind: "volume_down" });
    s = step(s, { t: "control", kind: "stop" }, { t: "open", action: playlist });
    expect(s.volume).toBe(80);
  });
});

describe("mediaReport: what the page tells the agent (arjun.media)", () => {
  const states = (phase: MediaState["phase"]) => ({ ...idleMedia(), phase });
  it("playing / loading count as playing, everything else as stopped", () => {
    expect(mediaReport(states("playing"))).toBe("playing");
    expect(mediaReport(states("loading"))).toBe("playing");
    for (const p of ["closed", "paused", "blocked", "ended", "error"] as const) expect(mediaReport(states(p))).toBe("stopped");
  });
});
