import { afterEach, describe, expect, it, vi } from "vitest";

import { setElderLang, t } from "./strings";
import {
  FALLBACK_ERRORS,
  IFRAME_ALLOW,
  REFERRER_POLICY,
  YT_HOST,
  alternates,
  appLink,
  createRecovery,
  embedTarget,
  embedUrl,
  supportsPlayback,
  whenApiReady,
} from "./ytPlayer";

afterEach(() => setElderLang("mr"));

const ID = "dQw4w9WgXcQ";
const CH = "UC" + "a".repeat(22);

describe("embed URL: IFrame API on youtube-nocookie, no autoplay, origin set", () => {
  it("builds the video URL", () => {
    const u = embedUrl(embedTarget("youtube_video", ID)!, "https://x.trycloudflare.com");
    expect(u.startsWith(`${YT_HOST}/embed/${ID}?`)).toBe(true);
    expect(YT_HOST).toBe("https://www.youtube-nocookie.com");
    for (const v of ["enablejsapi=1", "playsinline=1", "rel=0", "modestbranding=1", "origin=https%3A%2F%2Fx.trycloudflare.com"]) {
      expect(u).toContain(v);
    }
    expect(u).not.toContain("autoplay"); // never autoplay on load: playback starts from a tap
  });

  it("plays a channel as its uploads playlist (UU...), never /live_stream", () => {
    expect(embedTarget("youtube_channel_live", CH)).toEqual({ list: "UU" + "a".repeat(22) });
    const u = embedUrl(embedTarget("youtube_channel_live", CH)!, "http://localhost:5173");
    expect(u).toContain("listType=playlist&list=UUaaaaaaaaaaaaaaaaaaaaaa");
    expect(u).not.toContain("live_stream");
  });

  it("rejects ids that are not ids", () => {
    expect(embedTarget("youtube_video", "short")).toBeNull();
    expect(embedTarget("youtube_channel_live", "UCshort")).toBeNull();
    expect(embedTarget("youtube_playlist", "x y")).toBeNull();
  });

  it("iframe attributes: allow list and a referrer policy that sends the origin", () => {
    expect(IFRAME_ALLOW).toBe("autoplay; encrypted-media; picture-in-picture; fullscreen");
    expect(REFERRER_POLICY).toBe("strict-origin-when-cross-origin");
  });
});

describe("codec / MSE support", () => {
  const avc = 'video/mp4; codecs="avc1.42E01E"';
  it("accepts MSE with H.264 or VP9, ManagedMediaSource, or a video element that says it can", () => {
    expect(supportsPlayback({ MediaSource: { isTypeSupported: (x) => x === avc } })).toBe(true);
    expect(supportsPlayback({ MediaSource: { isTypeSupported: (x) => x.includes("vp9") } })).toBe(true);
    expect(supportsPlayback({ ManagedMediaSource: {} })).toBe(true);
    expect(supportsPlayback({ document: { createElement: () => ({ canPlayType: () => "probably" }) } })).toBe(true);
  });
  it("rejects a browser with none of them (straight to the app link)", () => {
    expect(supportsPlayback({})).toBe(false);
    expect(supportsPlayback({ MediaSource: { isTypeSupported: () => false }, document: { createElement: () => ({ canPlayType: () => "" }) } })).toBe(false);
  });
});

describe("app link", () => {
  it("Android gets the YouTube intent with a browser fallback; everything else youtu.be", () => {
    const a = appLink(ID, "Mozilla/5.0 (Linux; Android 13) Chrome/120");
    expect(a.startsWith(`intent://www.youtube.com/watch?v=${ID}#Intent;package=com.google.android.youtube;scheme=https;`)).toBe(true);
    expect(a).toContain(encodeURIComponent(`https://youtu.be/${ID}`));
    expect(appLink(ID, "Mozilla/5.0 (Windows NT 10.0) Chrome/120")).toBe(`https://youtu.be/${ID}`);
    expect(appLink(ID, "Mozilla/5.0 (iPhone) Safari")).toBe(`https://youtu.be/${ID}`);
  });
});

describe("alternates", () => {
  it("skips ids already tried, bad ids and duplicates, and stops at three", () => {
    const res = ["AAAAAAAAAAA", ID, "BBBBBBBBBBB", "bad", "AAAAAAAAAAA", "CCCCCCCCCCC", "DDDDDDDDDDD"].map((video_id) => ({ video_id }));
    expect(alternates(res, [ID])).toEqual(["AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC"]);
  });
});

describe("recovery: error -> next result (max 3) -> app link", () => {
  const results = ["AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC", "DDDDDDDDDDD"].map((video_id) => ({ video_id }));
  const make = (fetch = vi.fn().mockResolvedValue(results)) => {
    const load = vi.fn();
    const notice = vi.fn();
    const giveUp = vi.fn();
    const r = createRecovery({ title: "भजन", firstId: ID, fetchAlternates: fetch, load, notice, giveUp });
    return { r, load, notice, giveUp, fetch };
  };

  it.each([...FALLBACK_ERRORS])("error %i tries the next search result and tells her in Marathi", async (code) => {
    const { r, load, notice, fetch } = make();
    await r.onError(code);
    expect(notice).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith("भजन");
    expect(load).toHaveBeenCalledWith("AAAAAAAAAAA", false); // no tap yet: cue, wait for the button
    expect(t("media_error")).toBe("हा व्हिडिओ इथे चालत नाही, दुसरा लावतो");
  });

  it("a harmless player error code is ignored", async () => {
    const { r, load, giveUp, notice } = make();
    await r.onError(3);
    expect(load).not.toHaveBeenCalled();
    expect(giveUp).not.toHaveBeenCalled();
    expect(notice).not.toHaveBeenCalled();
  });

  it("after a tap the next video starts by itself; three failures end in the app link for the ORIGINAL video", async () => {
    const { r, load, giveUp, fetch } = make();
    r.tapped();
    for (let i = 0; i < 3; i++) await r.onError(150);
    expect(load.mock.calls).toEqual([["AAAAAAAAAAA", true], ["BBBBBBBBBBB", true], ["CCCCCCCCCCC", true]]);
    expect(giveUp).not.toHaveBeenCalled();
    await r.onError(101);
    expect(giveUp).toHaveBeenCalledWith(ID);
    expect(fetch).toHaveBeenCalledTimes(1); // the search is done once
  });

  it("no alternates, a failing search, or a playlist/channel (no single id) all go straight to the link", async () => {
    for (const fetch of [vi.fn().mockResolvedValue([]), vi.fn().mockRejectedValue(new Error("down"))]) {
      const { r, giveUp } = make(fetch);
      await r.onError(153);
      expect(giveUp).toHaveBeenCalledWith(ID);
    }
    const giveUp = vi.fn();
    const r = createRecovery({ title: "बातम्या", firstId: null, fetchAlternates: vi.fn(), load: vi.fn(), notice: vi.fn(), giveUp });
    await r.onError(5);
    expect(giveUp).toHaveBeenCalledWith(null);
  });
});

describe("IFrame API loading", () => {
  it("a script that will not load calls onFail and never throws into the screen", async () => {
    const onReady = vi.fn();
    const onFail = vi.fn();
    await whenApiReady(() => Promise.reject(new Error("blocked")), onReady, onFail);
    expect(onFail).toHaveBeenCalledTimes(1);
    expect(onReady).not.toHaveBeenCalled();
  });
  it("hands the API over when it loads", async () => {
    const onReady = vi.fn();
    await whenApiReady(() => Promise.resolve({ Player: 1 }), onReady, vi.fn());
    expect(onReady).toHaveBeenCalledWith({ Player: 1 });
  });
});

describe("player labels follow the elder language", () => {
  const KEYS = ["media_start", "media_close", "media_pause", "media_next", "vol_down", "vol_up", "media_error", "media_open_yt", "media_unsupported"] as const;
  it("exist in mr, hi and en (and the other seven)", () => {
    for (const lang of ["mr", "hi", "en", "bn", "gu", "kn", "ml", "pa", "ta", "te"] as const) {
      for (const k of KEYS) expect(t(k, undefined, lang).trim().length, `${k}/${lang}`).toBeGreaterThan(0);
    }
  });
  it("Marathi uses Marathi words, Hindi keeps its own", () => {
    const mr = Object.fromEntries(KEYS.map((k) => [k, t(k, undefined, "mr")]));
    expect(mr.media_close).toContain("बंद करा");
    expect(mr.media_start).toContain("सुरू करा");
    expect(mr.media_next).toContain("पुढचा");
    expect(mr.vol_down).toContain("कमी");
    expect(mr.vol_up).toContain("जास्त");
    for (const forbidden of ["बंद करें", "शुरू करें", "अगला", "ज़्यादा"]) {
      expect(Object.values(mr).join(" ")).not.toContain(forbidden);
    }
    expect(t("media_close", undefined, "hi")).toContain("बंद करें");
    expect(t("media_start", undefined, "hi")).toContain("शुरू करें");
    expect(t("media_next", undefined, "hi")).toContain("अगला");
    expect(t("vol_up", undefined, "hi")).toContain("ज़्यादा");
    expect(t("media_open_yt", undefined, "mr")).toBe("YouTube मध्ये उघडा");
  });
});
