import { useEffect, useState } from "react";

import { api } from "../api";
import type { HealthProfile } from "../api";

type Draft = Omit<HealthProfile, "updated_at">;

const EMPTY: Draft = {
  allergies: [],
  conditions: [],
  blood_group: "",
  doctor_name: "",
  doctor_contact: "",
  prescription_notes: "",
  emergency_notes: "",
};

const toList = (text: string): string[] =>
  text
    .split(/[\n,]/)
    .map((x) => x.trim())
    .filter(Boolean);

/**
 * The family records allergies, conditions, the doctor and notes here. It is shown back to her word for word on her
 * "my information" screen. Arjun never gives advice from it and it is never sent to the AI model.
 */
export function HealthProfileCard({ userId, name }: { userId: number; name: string }) {
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [allergies, setAllergies] = useState("");
  const [conditions, setConditions] = useState("");
  const [status, setStatus] = useState("");
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .healthProfile(userId)
      .then((p) => {
        if (!live) return;
        const { updated_at, ...rest } = p;
        setDraft(rest);
        setAllergies(p.allergies.join(", "));
        setConditions(p.conditions.join(", "));
        setSaved(updated_at);
      })
      .catch(() => live && setStatus("Could not load the health information."));
    return () => {
      live = false;
    };
  }, [userId]);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setDraft({ ...draft, [k]: v });

  const save = async () => {
    setStatus("Saving...");
    try {
      const p = await api.saveHealthProfile(userId, { ...draft, allergies: toList(allergies), conditions: toList(conditions) });
      setAllergies(p.allergies.join(", "));
      setConditions(p.conditions.join(", "));
      setSaved(p.updated_at);
      setStatus("Saved.");
    } catch {
      setStatus("Could not save. Try again.");
    }
  };

  return (
    <section className="fam-card" aria-label={`Health information for ${name}`}>
      <h2>Health information</h2>
      <p className="fam-note">
        Enter what the doctor and the prescription say. {name} sees it word for word on her information screen. Arjun
        does not give medical advice from it, and it is not sent to the AI model.
      </p>
      <form
        className="fam-form"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <label className="fam-field" style={{ flex: "1 1 260px" }}>
          Allergies (comma or new line)
          <textarea className="fam-input" rows={2} value={allergies} onChange={(e) => setAllergies(e.target.value)} />
        </label>
        <label className="fam-field" style={{ flex: "1 1 260px" }}>
          Conditions (comma or new line)
          <textarea className="fam-input" rows={2} value={conditions} onChange={(e) => setConditions(e.target.value)} />
        </label>
        <label className="fam-field">
          Blood group
          <input className="fam-input" maxLength={10} style={{ width: 90 }} value={draft.blood_group} onChange={(e) => set("blood_group", e.target.value)} />
        </label>
        <label className="fam-field">
          Doctor
          <input className="fam-input" maxLength={100} value={draft.doctor_name} onChange={(e) => set("doctor_name", e.target.value)} />
        </label>
        <label className="fam-field">
          Doctor contact
          <input className="fam-input" maxLength={100} value={draft.doctor_contact} onChange={(e) => set("doctor_contact", e.target.value)} />
        </label>
        <label className="fam-field" style={{ flex: "1 1 100%" }}>
          Prescription notes
          <textarea className="fam-input" rows={3} maxLength={2000} value={draft.prescription_notes} onChange={(e) => set("prescription_notes", e.target.value)} />
        </label>
        <label className="fam-field" style={{ flex: "1 1 100%" }}>
          Emergency notes (what a neighbour or ambulance should know)
          <textarea className="fam-input" rows={2} maxLength={2000} value={draft.emergency_notes} onChange={(e) => set("emergency_notes", e.target.value)} />
        </label>
        <button className="fbtn solid" type="submit">
          Save health information
        </button>
        <span role="status" className="fam-note">
          {status || (saved ? `Last saved ${saved.replace("T", " ").slice(0, 16)}` : "Not saved yet.")}
        </span>
      </form>
    </section>
  );
}
