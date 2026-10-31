import { describe, expect, it } from "vitest";

import { activityLine } from "./activity";

const at = (s: string) => new Date(s);

describe("last talked to Arjun", () => {
  it("says so when nothing was ever recorded", () => {
    expect(activityLine(null, at("2026-10-29T15:00:00"), "07:00")).toEqual({
      text: "Has not talked to Arjun yet.",
      tone: "none",
    });
  });

  it("shows today's time and how long ago", () => {
    const l = activityLine("2026-10-29T14:35:00", at("2026-10-29T15:00:00"), "07:00");
    expect(l.tone).toBe("ok");
    expect(l.text).toContain("25 min ago");
  });

  it("counts hours for an older turn today", () => {
    expect(activityLine("2026-10-29T08:00:00", at("2026-10-29T10:30:00"), "07:00").text).toContain("2 h 30 min ago");
  });

  it("stays calm early in the morning before the cut-off", () => {
    // wake 07:00 + 3 h = 10:00; at 09:00 a quiet morning is normal
    const l = activityLine("2026-10-28T20:10:00", at("2026-10-29T09:00:00"), "07:00");
    expect(l.tone).toBe("ok");
  });

  it("suggests a call, without alarming, once the day is quiet past the cut-off", () => {
    const l = activityLine("2026-10-28T20:10:00", at("2026-10-29T10:00:00"), "07:00", "Aaji");
    expect(l.tone).toBe("quiet");
    expect(l.text).toMatch(/^Aaji has not talked to Arjun today/);
    expect(l.text).toContain("a call would tell you");
    expect(l.text.toLowerCase()).not.toMatch(/emergency|wrong|danger/);
  });

  it("follows the family-set wake time", () => {
    expect(activityLine("2026-10-28T20:10:00", at("2026-10-29T10:00:00"), "08:30").tone).toBe("ok");
    expect(activityLine("2026-10-28T20:10:00", at("2026-10-29T11:30:00"), "08:30").tone).toBe("quiet");
  });
});
