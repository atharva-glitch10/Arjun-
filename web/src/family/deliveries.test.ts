import { describe, expect, it } from "vitest";

import type { Delivery } from "../api";
import { deliveryRows, describeDelivery } from "./deliveries";

const d = (o: Partial<Delivery>): Delivery => ({
  id: 1,
  kind: "reminder",
  ref_id: 1,
  attempt: 1,
  due_at: "2026-10-26T10:00:00",
  status: "spoken",
  late: false,
  label: "Doctor",
  detail: "",
  spoken_at: "2026-10-26T10:00:20",
  acked_at: null,
  outcome: null,
  fail_count: 0,
  ...o,
});

describe("what the family reads for each delivery", () => {
  it("says a spoken item that nobody acknowledged is exactly that, not 'done'", () => {
    expect(describeDelivery(d({}))).toEqual({ text: "Spoken, not acknowledged", tone: "neutral" });
    expect(describeDelivery(d({ kind: "medicine", label: "Metformin", detail: "500 mg" })).text).toBe(
      "Spoken, not acknowledged",
    );
  });

  it("labels a taken medicine as self-reported", () => {
    const out = describeDelivery(d({ kind: "medicine", status: "acknowledged", outcome: "taken", acked_at: "2026-10-26T10:01:00" }));
    expect(out).toEqual({ text: "Taken (self-reported)", tone: "ok" });
  });

  it("reports snoozed and 'not taken' answers plainly, without advice", () => {
    expect(describeDelivery(d({ kind: "medicine", status: "acknowledged", outcome: "snoozed" })).text).toBe("Snoozed by Aaji");
    expect(describeDelivery(d({ kind: "medicine", status: "acknowledged", outcome: "not_taken" })).text).toBe(
      "Aaji said not taken",
    );
  });

  it("acknowledged reminders say so; an acknowledged one that was never spoken says that too", () => {
    expect(describeDelivery(d({ status: "acknowledged", outcome: "ok" })).text).toBe("Acknowledged");
    expect(describeDelivery(d({ status: "acknowledged", outcome: "ok", spoken_at: null })).text).toBe(
      "Acknowledged on the screen (not spoken)",
    );
  });

  it("calls everything that was not spoken on time 'not delivered'", () => {
    for (const status of ["shown_only", "undelivered"] as const) {
      const out = describeDelivery(d({ status, spoken_at: null }));
      expect(out.text.startsWith("Not delivered")).toBe(true);
      expect(out.tone).toBe("warn");
    }
    expect(describeDelivery(d({ status: "queued", spoken_at: null, late: true }))).toEqual({
      text: "Not delivered yet (waiting for a voice session)",
      tone: "warn",
    });
  });

  it("a queued item that is not late yet is just waiting", () => {
    expect(describeDelivery(d({ status: "queued", spoken_at: null })).text).toBe("Waiting to be spoken");
  });

  it("being spoken right now", () => {
    expect(describeDelivery(d({ status: "speaking", spoken_at: null })).text).toBe("Being spoken now");
  });
});

describe("the rows", () => {
  it("leave out items that were replaced or no longer needed, oldest first", () => {
    const rows = deliveryRows([
      d({ id: 3, due_at: "2026-10-26T12:00:00" }),
      d({ id: 2, status: "superseded" }),
      d({ id: 1 }),
    ]);
    expect(rows.map((r) => r.id)).toEqual([1, 3]);
  });

  it("show the SQL text verbatim, with the dose for a medicine", () => {
    const [row] = deliveryRows([d({ kind: "medicine", label: "Metformin", detail: "500 mg, 1 गोळी" })]);
    expect(row?.title).toBe("Metformin 500 mg, 1 गोळी");
    expect(row?.kind).toBe("Medicine");
    expect(deliveryRows([d({})])[0]?.title).toBe("Doctor");
  });
});
