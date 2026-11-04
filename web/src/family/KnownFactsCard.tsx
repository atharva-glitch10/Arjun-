import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import type { Fact } from "../api";

const KIND_LABEL: Record<Fact["kind"], string> = {
  person: "person",
  like: "likes",
  dislike: "dislikes",
  routine: "routine",
  place: "place",
  event: "event",
  concern: "concern",
  note: "she asked to remember",
};

/** "अर्जुनला माहीत असलेल्या गोष्टी": the short facts Arjun keeps about her life, each with a delete button.
 * Facts only, never a transcript. Shown only with the same consent as the conversation summaries; deleting needs none. */
export function KnownFactsCard({ userId, consent, name }: { userId: number; consent: boolean; name: string }) {
  const [facts, setFacts] = useState<Fact[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setFacts(await api.facts(userId));
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load");
    }
  }, [userId]);

  useEffect(() => {
    void load();
  }, [load, consent]);

  const remove = async (id: number) => {
    try {
      await api.deleteFact(userId, id);
    } finally {
      await load();
    }
  };

  return (
    <section className="fam-card" style={{ flex: "1 1 420px" }}>
      <h2>अर्जुनला माहीत असलेल्या गोष्टी</h2>
      <p className="fam-note">
        Short facts {name} told Arjun (names, likes, plans). Never what was said word for word. Arjun never keeps numbers, addresses, money,
        medicines or illnesses.
      </p>
      {!consent && (
        <p className="fam-note" role="status">
          Hidden: switch on &ldquo;share how she is doing&rdquo; to see this list. Arjun still uses what she told him.
        </p>
      )}
      {error && <p className="fam-note" role="alert">{error}</p>}
      {consent && facts.length === 0 && <p>Nothing remembered yet.</p>}
      <ul className="fam-list">
        {facts.map((f) => (
          <li key={f.id} style={{ display: "flex", gap: 12, alignItems: "center", justifyContent: "space-between" }}>
            <span>
              {f.fact} <small className="fam-note">({KIND_LABEL[f.kind]}, {f.source_date})</small>
            </span>
            <button className="fbtn" style={{ minHeight: 44 }} onClick={() => void remove(f.id)} aria-label={`Delete: ${f.fact}`}>
              Delete
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
