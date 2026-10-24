import { describe, expect, it } from "vitest";

import { recentEmergencies } from "./alerts";

const now = new Date("2026-10-24T18:00:00");
const note = (id: number, kind: string, at: string) => ({ id, kind, body: `b${id}`, created_at: at });

describe("emergency banner", () => {
  it("shows emergency alerts from the last 24 hours, newest first", () => {
    const got = recentEmergencies(
      [
        note(1, "emergency", "2026-10-24T09:00:00"),
        note(2, "emergency", "2026-10-24T17:16:00"),
        note(3, "distress", "2026-10-24T17:20:00"),
        note(4, "caregiver_request", "2026-10-24T17:30:00"),
      ],
      now,
    );
    expect(got.map((n) => n.id)).toEqual([2, 1]);
  });

  it("ignores old emergencies, so yesterday's alert does not stay on screen forever", () => {
    expect(recentEmergencies([note(1, "emergency", "2026-10-22T17:16:00")], now)).toEqual([]);
  });

  it("is empty when there is nothing", () => {
    expect(recentEmergencies([], now)).toEqual([]);
  });
});
