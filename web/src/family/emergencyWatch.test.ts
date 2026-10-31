import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadAcked, needsPopup, saveAcked, startEmergencyWatch, unacknowledged } from "./emergencyWatch";

const now = new Date("2026-10-29T15:00:00");
const note = (id: number, kind: string, iso: string) => ({ id, kind, body: `n${id}`, created_at: iso });

describe("emergency watch decisions", () => {
  const notes = [
    note(1, "emergency", "2026-10-29T14:58:00"),
    note(2, "reminder", "2026-10-29T14:59:00"),
    note(3, "emergency", "2026-10-28T10:00:00"), // older than 24 h: not rung again
    note(4, "emergency", "2026-10-29T09:00:00"),
  ];

  it("rings for every recent emergency nobody acknowledged here, newest first", () => {
    expect(unacknowledged(notes, new Set(), now).map((n) => n.id)).toEqual([1, 4]);
  });

  it("stops ringing for an acknowledged one", () => {
    expect(unacknowledged(notes, new Set([1]), now).map((n) => n.id)).toEqual([4]);
  });

  it("pops up each emergency exactly once", () => {
    const open = unacknowledged(notes, new Set(), now);
    expect(needsPopup(open, new Set([4])).map((n) => n.id)).toEqual([1]);
  });
});

describe("acknowledged ids storage", () => {
  it("round-trips and survives broken or missing storage", () => {
    const box = new Map<string, string>();
    const store = { getItem: (k: string) => box.get(k) ?? null, setItem: (k: string, v: string) => void box.set(k, v) };
    saveAcked(store, new Set([5, 9]));
    expect([...loadAcked(store)]).toEqual([5, 9]);
    expect(loadAcked(undefined).size).toBe(0);
    expect(loadAcked({ getItem: () => "not json" }).size).toBe(0);
    expect(loadAcked({ getItem: () => { throw new Error("blocked"); } }).size).toBe(0);
    expect(() => saveAcked({ setItem: () => { throw new Error("full"); } }, new Set([1]))).not.toThrow();
  });
});

describe("emergency watcher", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("checks at once and then on every interval, with no visibility check at all", async () => {
    const check = vi.fn(async () => {});
    const stop = startEmergencyWatch(check, 15_000);
    await vi.advanceTimersByTimeAsync(0);
    expect(check).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(check).toHaveBeenCalledTimes(3);
    stop();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(check).toHaveBeenCalledTimes(3);
  });

  it("keeps watching after a failed check and never overlaps two checks", async () => {
    let release: () => void = () => {};
    const check = vi
      .fn<() => Promise<void>>()
      .mockRejectedValueOnce(new Error("offline"))
      .mockImplementationOnce(() => new Promise<void>((r) => (release = r)))
      .mockResolvedValue(undefined);
    startEmergencyWatch(check, 1_000);
    await vi.advanceTimersByTimeAsync(1_000); // 2nd check starts and hangs
    await vi.advanceTimersByTimeAsync(3_000); // still in flight: no new checks
    expect(check).toHaveBeenCalledTimes(2);
    release();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(check).toHaveBeenCalledTimes(3);
  });
});
