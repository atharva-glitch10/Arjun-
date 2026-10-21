# Arjun UI — Design Handoff ("Ghar" direction)

Read `CLAUDE.md` first (product rules, safety boundaries). This file covers the UI only.

## What's in this folder
- `design-source/*.html` — the design mockups. **They are NOT runnable app code.** They were
  authored in a design-canvas format: `{{name}}` holes, `<sc-if>` (conditional) and `<sc-for>`
  (loop) tags, and a `class Component extends DCLogic` block at the bottom that holds sample
  data and click-state. Treat them as the source of truth for **layout, sizes, colours, copy,
  icons and screen states**, then rebuild them as React + TypeScript components in `web/`.
  - `{{x}}` → a prop/state value. `<sc-if value="{{cond}}">` → `{cond && …}`.
    `<sc-for list="{{items}}" as="item">` → `items.map(item => …)`.
  - `onClick="{{fn}}"` → the screen-state transitions to reproduce.
  - The `<script src="./support.js">` line is the canvas runtime — drop it.
- `tokens.css` — design tokens as CSS variables. Use these, never raw hex in components.
- `CLAUDE.md` — project rules (copy to repo root if not already there).

## Screens (elder screens are phone 390×844 reference; must also work on a tablet)
| File | Screen | States to implement |
|---|---|---|
| `Ghar.html` | Elder home → speak → confirm → saved | `home` → tap बोला → `listen` (indigo bg, flickering diya, live transcript) → "झालं, पुढे" → `confirm` (big time card, हो/नाही) → "हो, बरोबर" → `saved` → "ठीक आहे" → `home` (new reminder card appears). "थांबा" from listen → home. "नाही" from confirm → listen. |
| `GharMedicine.html` | Medicine time | `due` → "घेतली" → `taken` ("छान, आजी!") ; `due` → "१५ मिनिटांनी सांग" → `snoozed`. Medicine name/dose come from SQL verbatim. Strip-photo slot = family-uploaded image (S3). |
| `GharVitals.html` | BP check | `confirm` (Aaji's words + parsed numbers read back) → "हो, बरोबर" → `saved` ("नोंद केली"). "नाही, परत सांगते" → re-listen. No good/bad judgement anywhere. |
| `GharKahani.html` | Story mode as "आजीची वही" | Arjun prompt chip, ruled notebook with live transcript, share card (हो, पाठवा / नको) with grandchildren avatars; lock note "private until हो". |
| `GharEvening.html` | Evening home theme | Same structure as morning home; dark indigo ground, diya speak button, next evening medicine card. |
| `GharDashboard.html` | Family dashboard (web page, fluid, 1280 reference) | Summary tiles, Today timeline, 7-day grid (on time / late / not confirmed), Health checks (BP log, Export for doctor, Sugar "Not set up" CTA). All data from API; sample data in the file is fake. |

Elder screen flow is driven by the **voice agent**, not only taps: every state must be reachable
by voice ("हो", "नाही", "घेतली", "नंतर") and by tap. The screen mirrors what Arjun says.

## Design tokens (also in tokens.css)
| Token | Hex | Use |
|---|---|---|
| `--ghar-ground` | #FBF1DE | elder app background (khadi) |
| `--ghar-surface` | #FFFFFF | cards |
| `--ghar-ink` | #2A1E14 | main text |
| `--ghar-ink-muted` | #5C4632 | secondary text (still ≥ 4.5:1 on ground) |
| `--ghar-indigo` | #23305E | primary buttons, listening bg (white text) |
| `--ghar-night` | #1B2447 | evening theme ground |
| `--ghar-haldi` | #F2B632 | accent, highlights (dark text only) |
| `--ghar-kumkum` | #B3261E | HELP button only (white text) |
| `--ghar-leaf` | #2F6B3A | success / taken (white text) |
| `--ghar-card-shadow` | #EAD9B8 | 0 2px 0 card "lip" shadow |

Fonts (Google Fonts): **Tiro Devanagari Marathi** (headings, weight 400) and **Mukta**
(400/600/800, body + buttons). Elder copy in Devanagari Marathi.

## Non-negotiable accessibility rules (evidence-based)
- Tap targets ≥ 14 mm: elder buttons 76–92 px tall; family dashboard ≥ 44 px.
- Elder body text ≥ 24 px; key info (time, medicine name, readings) 40–56 px.
- Contrast ≥ 4.5:1 for all text (3:1 only for ≥ 24 px bold). Haldi takes dark text only.
- Every icon has a text label; icon-only buttons need `aria-label`.
- One decision per screen. No swipe/pinch gestures. No auto-dismiss timeouts.
- Everything shown is also spoken by Arjun; yes/no always works by voice.
- Status is never colour-only: dashboard grid uses shape + lightness (filled check / filled
  clock / outlined cross).
- Real `<button>` elements, never clickable divs.

## Motion (CSS keyframes in the source files)
- `breathe` — speak button glow, 2.8 s loop.
- `flicker` — diya flame while listening, 1.5 s loop.
- `halo` — glow behind diya, 2.4–3 s loop.
- `pop` — success check entrance, 0.55 s once.
- ALL disabled under `@media (prefers-reduced-motion: reduce)`. Keep motion slow; add a
  family setting to turn it off.

## Cultural motifs (inline SVG in Ghar.html)
Mango-leaf + marigold toran (home top), diya = Arjun's presence, thali icon for meal timing,
ruled notebook for stories, sunrise / moon for time of day. Make motifs a **theme** (swappable
per region), not hard-coded.

## Content rules visible in the UI
- Footer on home: "अर्जुन — तुमचा AI सोबती" (AI disclosure always visible).
- Medicine screen footer: "औषधाबद्दल प्रश्न? डॉक्टरांना विचारा".
- BP screen footer: "हे आकडे राहुललाही दिसतील" (transparency).
- Dashboard notes: statuses are self-reported; Arjun never judges readings.
- Placeholders in `[brackets]` (e.g. `[डोस]`, `[राहुलचा फोटो]`) must be filled from real
  data at runtime — never hard-code medicine doses.

## Open questions to test with real elders before finalising
1. Evening screen's diya-only speak button (no mic icon) — do testers understand it?
2. Is the motion pleasant or distracting?
3. Devanagari vs other script preference.
