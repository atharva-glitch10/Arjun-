"""Phone apps Arjun may open by voice (Spotify, JioSaavn, YouTube Music, Google Maps).

Only an app the family approved on the dashboard (app_links kind "app", value = app id) ever opens. reasoning
only names the app id and her search words; the elder page builds the link from its own fixed table, and the
phone needs one tap to leave the browser (Android does not let a page open another app by itself)."""

from __future__ import annotations

from .textutil import normalize

# id -> (Marathi label, spoken names). Names are matched as substrings of the normalised sentence, so a case
# ending ("स्पॉटिफायवर", "मॅपमध्ये") still matches. Longer / more specific names first.
APPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "youtube_music": ("यूट्यूब म्युझिक", ("यूट्यूब म्युझिक", "युट्युब म्युझिक", "यूट्यूब म्यूझिक", "youtube music", "yt music")),
    "spotify": ("स्पॉटिफाय", ("स्पॉटिफाय", "स्पोटिफाय", "स्पॉटीफाय", "स्पॉटिफाई", "स्पोटीफाई", "spotify")),
    "jiosaavn": ("जिओसावन", ("जिओसावन", "जिओ सावन", "जियो सावन", "जिओसावण", "सावन", "jiosaavn", "jio saavn", "saavn")),
    "google_maps": ("गूगल मॅप्स", ("गूगल मॅप", "गुगल मॅप", "मॅप्स", "मॅपवर", "मॅपमध्ये", "मॅप", "नकाशा", "google maps", "maps")),
}
APP_IDS = frozenset(APPS)


def _norm(s: str) -> str:
    return normalize(s).replace("‍", "").replace("‌", "")


_NAMES = [(app_id, _norm(n)) for app_id, (_, names) in APPS.items() for n in names]


def detect_app(text: str) -> tuple[str, str] | None:
    """(app id, the matched name as normalised) for the first app named in the sentence, else None."""
    norm = _norm(text)
    for app_id, name in _NAMES:
        if name and name in norm:
            return app_id, name
    return None


def label(app_id: str) -> str:
    return APPS[app_id][0] if app_id in APPS else app_id
