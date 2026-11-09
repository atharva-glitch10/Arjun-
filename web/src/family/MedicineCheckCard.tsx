import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import type { DoseCheck } from "../api";

const LABEL: Record<DoseCheck["timing"], { text: string; ok: boolean }> = {
  on_time: { text: "On time", ok: true },
  late: { text: "Late", ok: false },
  pending: { text: "Not yet", ok: false },
  overdue: { text: "Not confirmed yet", ok: false },
  not_confirmed: { text: "Not confirmed after reminders", ok: false },
  said_no: { text: "Said she did not take it", ok: false },
};

const hhmm = (iso: string): string => iso.slice(11, 16);

/**
 * Today's doses against what she SELF-REPORTED. Arjun cannot see her take a tablet, so every row says "reported".
 * Raw rows only: no score, no streak, no ranking (CLAUDE.md boundary 6).
 */
export function MedicineCheckCard({ userId, name }: { userId: number; name: string }) {
  const [rows, setRows] = useState<DoseCheck[] | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    api
      .medicineCheck(userId)
      .then((r) => {
        setRows(r);
        setError(false);
      })
      .catch(() => setError(true));
  }, [userId]);

  useEffect(() => {
    load();
    const id = window.setInterval(load, 30_000);
    return () => window.clearInterval(id);
  }, [load]);

  return (
    <section className="fam-card" aria-label={`Today's medicine check for ${name}`}>
      <h2>Today's medicines</h2>
      <p className="fam-note">
        What {name} reported to Arjun against the time you set. Reports are self-reported: Arjun cannot see her take a
        tablet. If a medicine is not confirmed after the set number of reminders, only you are told.
      </p>
      {error && <p className="error-block" role="alert">Could not load today's medicines.</p>}
      {rows && rows.length === 0 && <p>No medicine doses scheduled yet today.</p>}
      <ul className="fam-list">
        {(rows ?? []).map((r) => {
          const l = LABEL[r.timing];
          return (
            <li key={r.dose_id}>
              <span style={{ fontWeight: 700, minWidth: 54 }}>{hhmm(r.due_at)}</span>
              <span style={{ fontWeight: 700 }}>{r.name}</span>
              <span>{r.dose}</span>
              {r.instructions && <span className="t-muted">{r.instructions}</span>}
              <span style={{ flex: 1 }} />
              {r.taken_at && (
                <span className="t-muted">
                  reported {hhmm(r.taken_at)}
                  {r.timing === "late" && r.minutes_late ? ` (${r.minutes_late} min after)` : ""}
                </span>
              )}
              <span className={`status${l.ok ? " ok" : ""}`}>{l.text}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
