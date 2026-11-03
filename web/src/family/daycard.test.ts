import { describe, expect, it } from "vitest";

import type { CheckinCardItem } from "../api";
import { dayCardRows, dayCardSummary } from "./daycard";

const i = (o: Partial<CheckinCardItem>): CheckinCardItem => ({
  kind: "breakfast",
  label: "",
  at: "2026-11-03T08:40:00",
  state: "done",
  ...o,
});

describe("the family's day card", () => {
  it("shows done, not done and no answer with the time, the way the family reads it", () => {
    const rows = dayCardRows([
      i({}),
      i({ kind: "medicine", label: "BP", at: "2026-11-03T09:15:00", state: "not_done" }),
      i({ kind: "walk", at: "2026-11-03T16:00:00", state: "no_answer" }),
    ]);
    expect(rows.map((r) => r.line)).toEqual(["नाश्ता ✅ 08:40", "औषध (BP) ❌ 09:15", "फिरणं — 16:00"]);
    expect(rows.map((r) => r.words)).toEqual([
      "done (self-reported)",
      "not done (self-reported)",
      "asked, no answer",
    ]);
  });

  it("is ordered by time and names the appointment, the contact and the interest from SQL", () => {
    const rows = dayCardRows([
      i({ kind: "home", label: "राहुल", at: "2026-11-03T17:00:00" }),
      i({ kind: "appointment", label: "गायन वर्ग", at: "2026-11-03T10:00:00" }),
      i({ kind: "interest", label: "भजन", at: "2026-11-03T11:30:00" }),
    ]);
    expect(rows.map((r) => r.title)).toEqual(["भेट (गायन वर्ग)", "आवड (भजन)", "घर (राहुल)"]);
  });

  it("does not pretend a question was asked when it was not", () => {
    const rows = dayCardRows([
      i({ state: "not_asked" }),
      i({ kind: "lunch", state: "waiting" }),
      i({ kind: "walk", state: "asking" }),
    ]);
    expect(rows.map((r) => r.mark)).toEqual(["·", "○", "…"]);
    expect(rows.map((r) => r.words)).toEqual(["not asked", "later today", "asked, waiting for her answer"]);
  });

  it("counts only the questions that were really asked", () => {
    expect(dayCardSummary([])).toBe("Nothing asked yet today.");
    expect(dayCardSummary([i({ state: "waiting" }), i({ state: "not_asked" })])).toBe("Nothing asked yet today.");
    expect(
      dayCardSummary([i({}), i({ state: "not_done" }), i({ state: "no_answer" }), i({ state: "waiting" })]),
    ).toBe("2 of 3 answered");
    expect(dayCardSummary([i({}), i({ kind: "walk", state: "asking" })])).toBe("1 of 2 answered");
  });

  it("carries nothing but the card fields: no words of hers, no mood", () => {
    const row = dayCardRows([i({})])[0] ?? {};
    expect(Object.keys(row).sort()).toEqual(["key", "line", "mark", "time", "title", "words"]);
  });
});
