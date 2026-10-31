import { describe, expect, it } from "vitest";

import { lastId, mergeFeed, parseMessage, socketRetryDelay } from "./feed";
import type { FeedEvent } from "./feed";

const ev = (id: number, severity: FeedEvent["severity"] = "normal"): FeedEvent => ({
  id, kind: "x", severity, title: "t", body: "b", created_at: "2026-10-31T10:00:00",
});

describe("family feed", () => {
  it("merges socket and polling rows without duplicates, newest first, capped", () => {
    const merged = mergeFeed([ev(1), ev(3)], [ev(3), ev(2), ev(4, "urgent")]);
    expect(merged.map((e) => e.id)).toEqual([4, 3, 2, 1]);
    expect(mergeFeed([], [ev(1), ev(2), ev(3)], 2).map((e) => e.id)).toEqual([3, 2]);
    expect(lastId(merged)).toBe(4);
  });

  it("ignores rows with an unknown level instead of breaking", () => {
    const bad = { ...ev(9), severity: "panic" } as unknown as FeedEvent;
    expect(mergeFeed([], [bad])).toEqual([]);
  });

  it("parses events and pings, and drops junk", () => {
    expect(parseMessage('{"type":"ping"}')).toBe("ping");
    expect(parseMessage('{"type":"event","id":5,"severity":"emergency","title":"Emergency","body":"x"}')).toMatchObject({
      id: 5, severity: "emergency",
    });
    expect(parseMessage("not json")).toBeNull();
    expect(parseMessage('{"type":"event","id":"5","severity":"normal"}')).toBeNull();
  });

  it("retries the socket with a growing wait", () => {
    expect([0, 1, 2, 3, 4, 50].map(socketRetryDelay)).toEqual([1_000, 2_000, 5_000, 10_000, 30_000, 30_000]);
  });
});
