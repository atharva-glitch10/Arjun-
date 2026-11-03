import { useState } from "react";

import type { AppLink, AppLinkInput, Contact, MediaStatus } from "../api";
import { KIND_LABELS, testUrl, warning } from "./applinks";

const KINDS = Object.keys(KIND_LABELS) as AppLink["kind"][];
const HINT: Record<AppLink["kind"], string> = {
  youtube_playlist: "playlist link or id (PL...)",
  youtube_video: "video link or id",
  youtube_query: "search words, e.g. जुनी मराठी भजनं",
  youtube_channel_live: "channel link or id (UC...)",
  youtube_live: "channel link or id (UC...)",
  rss: "https:// feed address",
  whatsapp: "",
  link: "https:// address",
};

/** "Apps and links": what Arjun may open when she asks by voice. Only the family can add, edit or remove entries. */
export function AppLinksCard({
  links,
  contacts,
  mediaStatus,
  onAdd,
  onDelete,
}: {
  links: AppLink[];
  contacts: Contact[];
  mediaStatus?: MediaStatus | null;
  onAdd: (body: AppLinkInput) => void;
  onDelete: (id: number) => void;
}) {
  const [kind, setKind] = useState<AppLink["kind"]>("youtube_playlist");
  const [label, setLabel] = useState("");
  const [value, setValue] = useState("");
  const [contactId, setContactId] = useState("");
  const [names, setNames] = useState("");
  const [other, setOther] = useState(false);
  const web = kind === "rss" || kind === "link";

  const nameOf = (l: AppLink) =>
    l.kind === "whatsapp" ? contacts.find((c) => String(c.id) === l.value)?.name ?? "(contact removed)" : l.value;

  return (
    <section className="fam-card" style={{ flex: "1 1 520px" }}>
      <h2>Apps and links</h2>
      <p className="fam-note">
        What she can open by voice: songs on YouTube, the news (read aloud or on screen), WhatsApp, a photo link. WhatsApp only opens her
        chat; she taps the green button herself. Phone numbers stay in Family contacts.
      </p>
      {mediaStatus && (
        <p className="fam-note" role="status">
          {mediaStatus.youtube_key
            ? "YouTube search: ready"
            : "YouTube search: add YOUTUBE_API_KEY (now opens search pages)"}
        </p>
      )}
      <ul className="fam-list">
        {links.length === 0 && <li>Nothing added yet.</li>}
        {links.map((l) => {
          const url = testUrl(l, contacts);
          return (
            <li key={l.id}>
              <span style={{ fontWeight: 800 }}>{l.label}</span> · {KIND_LABELS[l.kind]} · <code>{nameOf(l)}</code>
              {l.spoken_names.length > 0 && <> · she says: {l.spoken_names.join(", ")}</>}
              {warning(l) && <div className="fam-warn" role="alert">⚠ {warning(l)}</div>}{" "}
              {url && (
                <a className="fbtn" href={url} target="_blank" rel="noreferrer noopener">
                  Test open
                </a>
              )}{" "}
              <button
                className="fbtn"
                type="button"
                onClick={() => {
                  if (window.confirm(`Remove "${l.label}"?`)) onDelete(l.id);
                }}
              >
                Remove
              </button>
            </li>
          );
        })}
      </ul>
      <form
        className="fam-form"
        onSubmit={(e) => {
          e.preventDefault();
          onAdd({
            kind,
            label,
            value: kind === "whatsapp" ? contactId : value,
            spoken_names: names.split(",").map((n) => n.trim()).filter(Boolean),
            allow_other_host: other,
          });
          setLabel("");
          setValue("");
          setNames("");
          setOther(false);
        }}
      >
        <select className="fam-input" aria-label="Kind" value={kind} onChange={(e) => setKind(e.target.value as AppLink["kind"])}>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {KIND_LABELS[k]}
            </option>
          ))}
        </select>
        <input className="fam-input" required placeholder="Name shown (e.g. भक्तिगीते)" aria-label="Label" value={label} onChange={(e) => setLabel(e.target.value)} />
        {kind === "whatsapp" ? (
          <select className="fam-input" required aria-label="Contact" value={contactId} onChange={(e) => setContactId(e.target.value)}>
            <option value="">Choose a contact…</option>
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        ) : (
          <input className="fam-input" required placeholder={HINT[kind]} aria-label="Value" value={value} onChange={(e) => setValue(e.target.value)} />
        )}
        <input className="fam-input" placeholder="Names she may say, comma separated (भजन, bhajan)" aria-label="Spoken names" value={names} onChange={(e) => setNames(e.target.value)} />
        {web && (
          <label className="fam-note">
            <input type="checkbox" checked={other} onChange={(e) => setOther(e.target.checked)} /> Allow a website that is not on the known list
            (only if you trust it)
          </label>
        )}
        <button className="fbtn solid" type="submit">
          Add
        </button>
      </form>
    </section>
  );
}
