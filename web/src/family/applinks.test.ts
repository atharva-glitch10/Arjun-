import { describe, expect, it } from "vitest";

import type { AppLink, Contact } from "../api";
import { testUrl, warning } from "./applinks";

const L = (kind: AppLink["kind"], value: string, other_host = false): AppLink => ({
  id: 1, kind, label: "x", value, spoken_names: [], sort: 0, other_host, approved_by_family: other_host,
});
const contacts: Contact[] = [{ id: 7, name: "चंद्रकांत", relation: "son", phone: "+91 90000 00001" }];

describe("testUrl", () => {
  it("opens each kind the way the elder screen would", () => {
    expect(testUrl(L("youtube_video", "dQw4w9WgXcQ"), contacts)).toBe("https://www.youtube.com/watch?v=dQw4w9WgXcQ");
    expect(testUrl(L("youtube_playlist", "PLabc"), contacts)).toBe("https://www.youtube.com/playlist?list=PLabc");
    expect(testUrl(L("youtube_channel_live", "UCabc"), contacts)).toBe("https://www.youtube.com/channel/UCabc/live");
    expect(testUrl(L("youtube_live", "UCabc"), contacts)).toBe("https://www.youtube.com/channel/UCabc/live");
    expect(testUrl(L("youtube_query", "भीमसेन जोशी"), contacts)).toContain("search_query=%E0%A4%AD");
    expect(testUrl(L("rss", "https://www.loksatta.com/feed"), contacts)).toBe("https://www.loksatta.com/feed");
    expect(testUrl(L("link", "https://photos.google.com/x"), contacts)).toBe("https://photos.google.com/x");
  });
  it("WhatsApp uses the contact's number, and says nothing when there is none", () => {
    expect(testUrl(L("whatsapp", "7"), contacts)).toBe("https://wa.me/919000000001");
    expect(testUrl(L("whatsapp", "99"), contacts)).toBeNull();
    expect(testUrl(L("link", "http://insecure.example/x"), contacts)).toBeNull();
  });
});

describe("warning", () => {
  it("flags every rss / link entry as approved by the family, and an unknown host more strongly", () => {
    expect(warning(L("rss", "https://www.loksatta.com/f"))).toContain("Approved by family");
    expect(warning(L("link", "https://photos.google.com/x"))).toContain("Approved by family");
    expect(warning(L("rss", "https://news.example.org/f", true))).toContain("not on the known list");
    expect(warning(L("youtube_video", "dQw4w9WgXcQ"))).toBe("");
    expect(warning(L("whatsapp", "7"))).toBe("");
  });
});
