import { describe, expect, it } from "vitest";

import type { Delivery } from "../api";
import { AUTO_START_COOLDOWN_MS, cardFor, reconnectDelay, restingScreen, shouldAutoStart, shouldConnectHandsFree } from "./cards";

const d = (o: Partial<Delivery>): Delivery => ({
  id: 1,
  kind: "reminder",
  ref_id: 1,
  attempt: 1,
  due_at: "2026-10-26T10:00:00",
  status: "spoken",
  late: false,
  label: "डॉक्टरांकडे जायचं",
  detail: "",
  spoken_at: "2026-10-26T10:00:20",
  acked_at: null,
  outcome: null,
  fail_count: 0,
  ...o,
});

describe("which delivery is shown as the card", () => {
  it("is nothing when nothing is waiting for the elder", () => {
    expect(cardFor([], "")).toBeUndefined();
    expect(cardFor([d({ status: "acknowledged" }), d({ id: 2, status: "superseded" })], "")).toBeUndefined();
  });

  it("does not show an item that is only queued: it has not reached the elder yet", () => {
    expect(cardFor([d({ status: "queued", spoken_at: null })], "")).toBeUndefined();
  });

  it("stays after it was spoken until it is acknowledged", () => {
    expect(cardFor([d({})], "")?.delivery.id).toBe(1);
  });

  it("keeps unspoken items too, and says honestly that they were not spoken", () => {
    for (const status of ["shown_only", "undelivered"] as const) {
      const card = cardFor([d({ status, spoken_at: null })], "");
      expect(card?.spoken).toBe(false);
    }
    expect(cardFor([d({})], "")?.spoken).toBe(true);
  });

  it("shows the oldest first, one at a time", () => {
    const list = [d({ id: 2, due_at: "2026-10-26T11:00:00" }), d({ id: 1 })];
    expect(cardFor(list, "")?.delivery.id).toBe(1);
  });

  it("prefers the item the agent just published (arjun.item)", () => {
    const list = [d({ id: 1 }), d({ id: 2, kind: "medicine", ref_id: 7, label: "Metformin", detail: "500 mg" })];
    expect(cardFor(list, "dose:7")?.delivery.id).toBe(2);
    expect(cardFor(list, "reminder:1")?.delivery.id).toBe(1);
    expect(cardFor(list, "dose:99")?.delivery.id).toBe(1); // unknown item: fall back to the oldest
  });

  it("carries the SQL text untouched", () => {
    const card = cardFor([d({ kind: "medicine", ref_id: 7, label: "Metformin", detail: "500 mg, 1 गोळी" })], "");
    expect(card?.delivery.label).toBe("Metformin");
    expect(card?.delivery.detail).toBe("500 mg, 1 गोळी");
  });
});

describe("when the page starts a voice session by itself", () => {
  const ok = { armed: true, phase: "idle" as const, queued: 1, sinceLastMs: null };

  it("does when something is queued, the elder tapped Start, and no session is open", () => {
    expect(shouldAutoStart(ok)).toBe(true);
  });

  it("never before the one-time Start tap (the browser would block the sound)", () => {
    expect(shouldAutoStart({ ...ok, armed: false })).toBe(false);
  });

  it("never when nothing is queued or a session is already running or starting", () => {
    expect(shouldAutoStart({ ...ok, queued: 0 })).toBe(false);
    for (const phase of ["connecting", "waiting", "live", "failed"] as const) {
      expect(shouldAutoStart({ ...ok, phase })).toBe(false);
    }
  });

  it("waits out a cooldown after the last automatic start, so a stuck item cannot cause a loop", () => {
    expect(shouldAutoStart({ ...ok, sinceLastMs: AUTO_START_COOLDOWN_MS - 1 })).toBe(false);
    expect(shouldAutoStart({ ...ok, sinceLastMs: AUTO_START_COOLDOWN_MS })).toBe(true);
  });
});


describe("hands-free", () => {
  it("connects at once when the page opens, and not when it is turned off", () => {
    expect(shouldConnectHandsFree({ handsFree: true, phase: "idle", sinceLastMs: null, attempt: 0 })).toBe(true);
    expect(shouldConnectHandsFree({ handsFree: false, phase: "idle", sinceLastMs: null, attempt: 0 })).toBe(false);
    expect(shouldConnectHandsFree({ handsFree: true, phase: "live", sinceLastMs: null, attempt: 0 })).toBe(false);
  });

  it("reconnects after a drop with a growing wait, never a tight loop", () => {
    expect(reconnectDelay(0)).toBe(0);
    expect(reconnectDelay(1)).toBe(2_000);
    expect(reconnectDelay(99)).toBe(30_000);
    expect(shouldConnectHandsFree({ handsFree: true, phase: "failed", sinceLastMs: 1_000, attempt: 1 })).toBe(false);
    expect(shouldConnectHandsFree({ handsFree: true, phase: "failed", sinceLastMs: 2_500, attempt: 1 })).toBe(true);
  });

  it("shows home while listening and after a reply was read, but never hides safety or a card", () => {
    expect(restingScreen("listen", 0, 0, true)).toBe("home");
    expect(restingScreen("reply", 3, 2, true)).toBe("reply");
    expect(restingScreen("reply", 3, 3, true)).toBe("home");
    expect(restingScreen("safety", 3, 3, true)).toBe("safety");
    expect(restingScreen("card", 3, 3, true)).toBe("card");
    expect(restingScreen("listen", 0, 0, false)).toBe("listen");
  });
});
