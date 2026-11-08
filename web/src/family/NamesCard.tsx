import { useEffect, useState } from "react";

import type { User } from "../api";

type Lang = User["language"];

const LANGS: [Lang, string][] = [
  ["mr", "मराठी (Marathi)"],
  ["hi", "हिंदी (Hindi)"],
  ["en", "English"],
  ["ta", "தமிழ் (Tamil)"],
  ["kn", "ಕನ್ನಡ (Kannada)"],
  ["te", "తెలుగు (Telugu)"],
  ["ml", "മലയാളം (Malayalam)"],
  ["bn", "বাংলা (Bengali)"],
  ["gu", "ગુજરાતી (Gujarati)"],
  ["pa", "ਪੰਜਾਬੀ (Punjabi)"],
];

type Patch = Partial<Pick<User, "address_as" | "language" | "preferred_languages" | "speech_style">>;

/** What Arjun calls her, what she calls Arjun, and the language she speaks. */
export function NamesCard({ user, onSave }: { user: User; onSave: (patch: Patch) => Promise<unknown> | void }) {
  const [address, setAddress] = useState(user.address_as ?? "");
  const [companion, setCompanion] = useState(user.speech_style?.companion_name ?? "");
  const [lang, setLang] = useState<Lang>((user.preferred_languages?.[0] as Lang) || user.language);
  const [note, setNote] = useState("");

  useEffect(() => {
    setAddress(user.address_as ?? "");
    setCompanion(user.speech_style?.companion_name ?? "");
    setLang((user.preferred_languages?.[0] as Lang) || user.language);
  }, [user]);

  const save = async () => {
    await onSave({
      address_as: address.trim(),
      language: lang,
      preferred_languages: [lang],
      speech_style: { ...user.speech_style, companion_name: companion.trim() },
    });
    setNote("Saved. Restart her screen (or wait for the next conversation) to hear the change.");
  };

  const shown = companion.trim() || "Arjun";
  return (
    <section className="fam-card names-card">
      <h2>Names and language</h2>
      <div className="fam-form">
        <label>
          What should {shown} call her?
          <input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="आजी, हीराबाई, Amma" maxLength={60} />
        </label>
        <label>
          What does she call the companion? (blank = Arjun)
          <input value={companion} onChange={(e) => setCompanion(e.target.value)} placeholder="Arjun" maxLength={24} />
        </label>
        <label>
          The language she speaks
          <select value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
            {LANGS.map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="fam-note" style={{ margin: 0 }}>
        Marathi, Hindi and English are understood together (she can mix them). Any other language is listened to on its
        own, with her English words kept. Safety messages stay in Marathi, Hindi or English.
      </p>
      <button className="fbtn solid" style={{ alignSelf: "flex-start" }} onClick={() => void save()}>
        Save names and language
      </button>
      {note && <p className="fam-note">{note}</p>}
    </section>
  );
}
