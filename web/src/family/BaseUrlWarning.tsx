import { useEffect, useState } from "react";

import { api } from "../api";
import type { BaseUrlDiag } from "../api";

/** The words for the settings banner, or "" when family-call links work. Pure: unit-tested. */
export function baseUrlMessage(d: BaseUrlDiag | null): string {
  if (!d || d.ok) return "";
  return `Family-call links are not working: ${d.reason || "BASE_URL is not usable"}. ${d.hint}`;
}

/** A small warning on the family dashboard Settings tab when BASE_URL (the address in every Telegram "join call"
 *  button) is not https, is a dead quick tunnel, or does not answer. Silent when all is well or the check fails. */
export function BaseUrlWarning() {
  const [diag, setDiag] = useState<BaseUrlDiag | null>(null);
  useEffect(() => {
    let live = true;
    api.baseUrlDiag().then((d) => live && setDiag(d)).catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  const text = baseUrlMessage(diag);
  if (!text) return null;
  return (
    <section className="fam-card" role="alert" style={{ borderLeft: "10px solid var(--emergency)" }}>
      <h2 style={{ margin: 0 }}>Call link needs attention</h2>
      <p className="fam-note">{text}</p>
      <p className="fam-note t-muted">
        Until it is fixed, Telegram alerts still arrive, but without the join button, and a video call from {" "}
        the elder screen says it did not connect.
      </p>
    </section>
  );
}
