import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import type { EmergencyCallRow, EmergencySettings } from "../api";

const STATUS: Record<EmergencyCallRow["status"], string> = {
  placed: "call placed",
  failed: "call FAILED",
  skipped_disabled: "not called (calls are switched off)",
  skipped_no_number: "not called (no number saved)",
};

/** Who Arjun phones in an emergency (family first; the saved help number if she does not answer in 10 s), and
 * what actually happened. Arjun never dials 112 itself. */
export function EmergencyCard({ userId, name }: { userId: number; name: string }) {
  const [form, setForm] = useState<EmergencySettings>({ help_label: "", help_phone: "", address: "", call_family: true });
  const [calls, setCalls] = useState<EmergencyCallRow[]>([]);
  const [note, setNote] = useState("");
  const [enabled, setEnabled] = useState<boolean | undefined>(undefined);

  const load = useCallback(async () => {
    try {
      const s = await api.emergencySettings(userId);
      setForm({ help_label: s.help_label, help_phone: s.help_phone, address: s.address, call_family: s.call_family });
      setEnabled(s.calls_enabled);
      setCalls(await api.emergencyCalls(userId));
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Could not load");
    }
  }, [userId]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    try {
      await api.saveEmergencySettings(userId, form);
      setNote("Saved.");
      await load();
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Could not save");
    }
  };

  return (
    <section className="fam-card emergency-card">
      <h2>Emergency help</h2>
      <p className="fam-note" style={{ marginTop: 0 }}>
        If {name} reports a physical emergency (chest pain, a fall, breathlessness), Arjun alerts you on Telegram with
        her live location and phones the family numbers in Contacts. If she does not answer within 10 seconds, Arjun
        phones the help number below and reads her address. Arjun never dials 112 by itself.
      </p>
      {enabled === false && (
        <p className="fam-note" role="note">
          Phone calls are switched off on this server (CALLS_ENABLED). Alerts still go to Telegram and this dashboard.
        </p>
      )}
      <div className="fam-form">
        <label>
          Help to call if she does not answer (name)
          <input
            value={form.help_label}
            onChange={(e) => setForm({ ...form, help_label: e.target.value })}
            placeholder="Sunrise Home nurse desk"
            maxLength={80}
          />
        </label>
        <label>
          Help phone number
          <input
            value={form.help_phone}
            onChange={(e) => setForm({ ...form, help_phone: e.target.value })}
            placeholder="98765 43210"
            inputMode="tel"
            maxLength={20}
          />
        </label>
        <label style={{ gridColumn: "1 / -1" }}>
          Address read out on the call
          <input
            value={form.address}
            onChange={(e) => setForm({ ...form, address: e.target.value })}
            placeholder="Room 12, Sunrise Home, Kothrud, Pune"
            maxLength={300}
          />
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={form.call_family}
            onChange={(e) => setForm({ ...form, call_family: e.target.checked })}
          />
          Also phone the family contacts first
        </label>
      </div>
      <button className="fbtn solid" onClick={() => void save()}>
        Save emergency settings
      </button>
      {note && <p className="fam-note">{note}</p>}
      <h3 style={{ marginBottom: 6 }}>Calls in the last 24 hours</h3>
      <ul className="fam-list">
        {calls.length === 0 && <li>No emergency calls.</li>}
        {calls.map((c, i) => (
          <li key={i}>
            {new Date(c.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} · {c.stage === "family" ? "Family" : "Help"}:{" "}
            {c.target}
            {c.phone_tail ? ` (…${c.phone_tail})` : ""} — <strong>{STATUS[c.status] ?? c.status}</strong>
            {c.detail && c.status === "failed" ? ` (${c.detail})` : ""}
          </li>
        ))}
      </ul>
    </section>
  );
}
