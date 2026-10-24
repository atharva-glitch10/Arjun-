import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { startPolling } from "./polling";

class FakeTarget {
  handlers = new Map<string, Set<() => void>>();
  hidden = false;
  addEventListener(type: string, fn: () => void) {
    if (!this.handlers.has(type)) this.handlers.set(type, new Set());
    this.handlers.get(type)?.add(fn);
  }
  removeEventListener(type: string, fn: () => void) {
    this.handlers.get(type)?.delete(fn);
  }
  fire(type: string) {
    this.handlers.get(type)?.forEach((fn) => fn());
  }
  count() {
    return Array.from(this.handlers.values()).reduce((n, s) => n + s.size, 0);
  }
}

describe("dashboard polling", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("refreshes every interval while the tab is visible", async () => {
    const refresh = vi.fn(async () => {});
    const doc = new FakeTarget();
    const win = new FakeTarget();
    startPolling(refresh, 10_000, doc, win);
    expect(refresh).not.toHaveBeenCalled(); // the caller loads once itself
    await vi.advanceTimersByTimeAsync(10_000);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(refresh).toHaveBeenCalledTimes(2);
  });

  it("does not poll a hidden tab, and refreshes at once when it becomes visible", async () => {
    const refresh = vi.fn(async () => {});
    const doc = new FakeTarget();
    const win = new FakeTarget();
    startPolling(refresh, 10_000, doc, win);
    doc.hidden = true;
    await vi.advanceTimersByTimeAsync(30_000);
    expect(refresh).not.toHaveBeenCalled();
    doc.hidden = false;
    doc.fire("visibilitychange");
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("refreshes when the window gets focus", () => {
    const refresh = vi.fn(async () => {});
    const win = new FakeTarget();
    startPolling(refresh, 10_000, new FakeTarget(), win);
    win.fire("focus");
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("never runs two refreshes at once", async () => {
    let release: () => void = () => {};
    const refresh = vi.fn(() => new Promise<void>((r) => (release = r)));
    const win = new FakeTarget();
    startPolling(refresh, 10_000, new FakeTarget(), win);
    win.fire("focus");
    win.fire("focus");
    await vi.advanceTimersByTimeAsync(10_000);
    expect(refresh).toHaveBeenCalledTimes(1); // the first is still in flight
    release();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(refresh).toHaveBeenCalledTimes(2);
  });

  it("a failing refresh does not stop the polling", async () => {
    const refresh = vi.fn(async () => {
      throw new Error("network");
    });
    startPolling(refresh, 10_000, new FakeTarget(), new FakeTarget());
    await vi.advanceTimersByTimeAsync(30_000);
    expect(refresh).toHaveBeenCalledTimes(3);
  });

  it("stop() removes the timer and every listener", async () => {
    const refresh = vi.fn(async () => {});
    const doc = new FakeTarget();
    const win = new FakeTarget();
    const stop = startPolling(refresh, 10_000, doc, win);
    expect(doc.count() + win.count()).toBeGreaterThan(0);
    stop();
    await vi.advanceTimersByTimeAsync(30_000);
    win.fire("focus");
    expect(refresh).not.toHaveBeenCalled();
    expect(doc.count() + win.count()).toBe(0);
  });
});
