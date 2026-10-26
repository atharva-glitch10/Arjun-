/** What the family dashboard says about each reminder / medicine prompt. Pure, so it is tested.
 *
 * Honest by construction (CLAUDE.md boundaries 6 and 14): "spoken" is never "heard", "taken" is always
 * "self-reported", and anything that did not reach Aaji by voice says "not delivered".
 */

import type { Delivery } from "../api";

export interface DeliveryText {
  text: string;
  tone: "ok" | "warn" | "neutral";
}

export interface DeliveryRow extends DeliveryText {
  id: number;
  kind: "Reminder" | "Medicine";
  /** Reminder task / medicine name and dose, verbatim from SQL. */
  title: string;
  dueAt: string;
}

export function describeDelivery(d: Delivery): DeliveryText {
  switch (d.status) {
    case "acknowledged":
      if (d.kind === "medicine" && d.outcome === "taken") return { text: "Taken (self-reported)", tone: "ok" };
      if (d.outcome === "snoozed") return { text: "Snoozed by Aaji", tone: "neutral" };
      if (d.outcome === "not_taken") return { text: "Aaji said not taken", tone: "warn" };
      if (d.spoken_at === null) return { text: "Acknowledged on the screen (not spoken)", tone: "neutral" };
      return { text: "Acknowledged", tone: "ok" };
    case "spoken":
      return { text: "Spoken, not acknowledged", tone: "neutral" };
    case "speaking":
      return { text: "Being spoken now", tone: "neutral" };
    case "queued":
      return d.late
        ? { text: "Not delivered yet (waiting for a voice session)", tone: "warn" }
        : { text: "Waiting to be spoken", tone: "neutral" };
    case "shown_only":
      return { text: "Not delivered by voice (shown on the screen only)", tone: "warn" };
    case "undelivered":
      return { text: "Not delivered (speech was interrupted or failed 3 times)", tone: "warn" };
    case "superseded":
      return { text: "No longer needed", tone: "neutral" };
  }
}

export function deliveryRows(list: readonly Delivery[]): DeliveryRow[] {
  return list
    .filter((d) => d.status !== "superseded")
    .sort((a, b) => a.due_at.localeCompare(b.due_at) || a.id - b.id)
    .map((d) => ({
      ...describeDelivery(d),
      id: d.id,
      kind: d.kind === "medicine" ? "Medicine" : "Reminder",
      title: d.detail ? `${d.label} ${d.detail}` : d.label,
      dueAt: d.due_at,
    }));
}
