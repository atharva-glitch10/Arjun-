# Arjun - voice care companion for elderly Indians (MVP)

Spec and hard boundaries: [CLAUDE.md](CLAUDE.md). Arjun is an AI, a bridge to people - not a
replacement for them. No medical advice; physical-emergency and distress phrases get a fixed safety reply (lexicons unverified); stories private by default.

## New on 2026-10-31 (see STATUS.md for what is verified)
- **Talk, nothing to press**: the elder page connects by itself and keeps listening; no "... ठेवू का? हो किंवा नाही" -
  Arjun does it, says it in one line, and "नको" undoes it. Run the elder device with `scripts\elder-kiosk.ps1`.
- **The family knows how she is**: seriousness level + mood + short summary per conversation (never her words),
  pushed live over a WebSocket (`/ws/users/{id}/feed`) with REST polling as fallback (`/users/{id}/feed?after=`).
- **Sarvam-105B** for conversation and summaries (`SARVAM_API_KEY`), **Timbre v3.0 over SSE** with voice tags the
  LLM chooses, **Prisma transcribe + native numerals**, rate limits on every entry point.
- Engineering notes (latency, concurrency, rate limiting, polling/WS, error handling, boundaries, identity):
  [docs/ENGINEERING.md](docs/ENGINEERING.md).

## Apps by voice (2026-11-02; tests + scripted runs, NOT heard with a real voice or seen in the elder page)
YouTube (songs, bhajans, live news), headlines read aloud, WhatsApp, and family-approved links, all by voice.
- "मला यूट्यूब बघायचं आहे" opens the family's favourite; "भीमसेन जोशींचं भजन लावा" searches YouTube and plays the first match; "बातम्या बघायच्या
  आहेत" plays the family's live news channel; "बातम्या ऐकवा" reads 5 headlines aloud from the family's RSS feeds, verbatim, source first (no LLM);
  "चंद्रकांतला व्हॉट्सॲप कर" opens her WhatsApp chat (she taps the green button); "नातवाचे फोटो दाखव" opens the family link of that name.
- While a video plays: "अर्जुन, थांबव / बंद कर / आवाज कमी कर / पुढचं गाणं". Everything else the mic hears is ignored (media mode), except safety phrases.
  Say **"अर्जुन" first** for any new request while a video plays; a bare stop / pause / next / volume phrase also works.
- The family adds, tests and removes entries in the dashboard section "Apps and links" (https only; a website off the known list needs an explicit tick
  and shows a warning). `python scripts/seed_apps.py --apply` seeds the synthetic household through core-api; without `--apply` it only verifies and
  prints what it would add.
- **YouTube search key**: put `YOUTUBE_API_KEY=<your key>` in the root `.env` and restart core-api (the key stays on the server; the browser never sees
  it). Without it, a search opens the YouTube results page instead of playing the first match.
- **Adding a link by hand**: Family dashboard -> "Apps and links" -> choose the kind, type a name she will see and the value (a playlist / video /
  channel link or id, an RSS feed, or an https page), then comma-separated spoken names ("भजन, भक्तिगीते"). "Test open" opens it on this device.
- **WhatsApp needs one tap**: Arjun opens her chat with that contact; she taps the green call / send button herself.

## What works today (verified by tests / smoke run)
Text/transcript in -> reasoning -> core-api (SQL) -> templated reply out, in Marathi / Hindi / English.

| Piece | State |
|---|---|
| `services/core-api` | FastAPI + SQLAlchemy. Reminders, appointments, contacts, **family-managed medicines + dose tracking (self-reported, family-only notice when unconfirmed)**, propose/confirm/reject actions, private stories + caregiver-visible Memory Book, distress events with consent gate, scheduler hook. 38 pytest tests (incl. API-key checks; core-api refuses to start without `CORE_API_KEY`). |
| `services/reasoning` | `POST /turn`: physical-emergency check, then distress check, first on every turn -> AI disclosure -> intent (rule-based parser; the hosted LLM only for chat and for turns the rules cannot read) -> dispatch. 281 pytest tests incl. distress and physical-emergency test sets (both lexicons unverified by a native speaker), core-api-outage handling, and dedicated medicine-path tests (intake with spoken yes, deflected medicine questions, no voice-created medicines). |
| `services/scheduler` | Polls core-api to mark due reminders, tick medicines, and fetch briefing/opener text. **Logs only: nothing is spoken on the elder device yet (T8).** 3 pytest tests. |
| `web/` | Vite + React + strict TS, rebuilt to the "Ghar" design in `design/` (tokens, toran/diya motifs, Devanagari elder screens, family dashboard). Elder home -> listen -> confirm -> saved is wired to reasoning `/turn` + core-api pending actions. `npm run build` passes; the screens were rendered in headless Edge (`/?preview` gallery, dashboard, elder home) but not tested on a real device or with real speech. |
| `eval/` | `python eval/run_eval.py` - intent / slot / distress on 33 synthetic text cases. |
| `services/voice-agent` | `agent.py` imports and its plugin arguments match livekit-plugins-gnani 1.8.6 (STT `mr-IN`, TTS, silero VAD, `StopResponse`). Verified 2026-10-21: the worker starts and registers with LiveKit Cloud. Gnani TTS returned audio through the plugin (2026-10-21). **No full spoken turn has run yet (T4).** The worker registers as `agent_name="arjun"`; `scripts/make_token.py` dispatches it explicitly. Reasoning failures become a spoken fallback line. 9 pytest tests (`test_bridge.py`, `test_turnlog.py`). Elder web app still uses **browser** speech, not Gnani (T6). |

## Run
```
cp .env.example .env            # set CORE_API_KEY; leave LLM_BASE_URL empty for rules-only mode
docker compose up --build       # postgres, core-api :8000, reasoning :8001, scheduler, web :5173
```
Local without Docker: `scripts\dev-up.ps1` starts core-api (SQLite), reasoning, voice-agent and web, in that order, one window
each (logs also go to `logs/`). It reads the one root `.env`, passes each service only the variables it needs and overrides the
compose-only hosts. `-Only <service>` starts one. The scheduler is not started by it. voice-agent loads only `GNANI_*` and
`LIVEKIT_*` from `.env` itself and exits naming any missing required variable. Tests: create a venv, `pip install -r services/core-api/requirements.txt -r services/reasoning/requirements.txt`,
then `pytest` inside each service and `ruff check .` at the root.

### Run on phone (Cloudflare quick tunnel)

The phone needs an HTTPS origin for the microphone. On Windows:

```
scripts\dev-up.ps1 -Phone
```

- Starts the normal stack and a Cloudflare quick tunnel from `web\`
  (`npx cloudflared tunnel --url http://localhost:5173`) in its own window, output also in
  `logs\tunnel.log`.
- Waits up to 30 s for the `https://<random>.trycloudflare.com` URL, writes it to `BASE_URL` in `.env`
  (only that line changes; comments, order and line endings stay as they were), then starts/restarts
  core-api so family-call links use it.
- If a tunnel is already running and its URL in `logs\tunnel.log` answers HTTP 200, it is reused instead
  of starting a second one. If the stack is already running, the other services are left alone and only
  core-api is restarted. That restart clears core-api's in-memory room map, so open the elder URL once
  afterwards before testing a family-call link.
- **Needs `ARJUN_ACCESS_CODE`** (6+ letters/digits/`-`/`_`) in the root `.env`; without it the script stops
  before starting the tunnel. It also restarts the web window so the lock is applied.
- Prints the two URLs to open on the phone, WITH the code:
  - Elder: `https://<random>.trycloudflare.com/?user=1&k=<code>`
  - Family: `https://<random>.trycloudflare.com/?view=family&user=1&k=<code>`
- The first open swaps the code for a 12 h HttpOnly cookie and removes `k` from the address bar. Without a valid
  cookie the tunnel shows "हा दुवा चालत नाही. घरच्यांना नवीन दुवा मागा." and the Vite proxy adds NO API key.
  An elder cookie reaches only the routes the elder page uses; a family cookie only the dashboard routes. The
  Telegram join link (`/?view=join&t=...`) needs no code (its token is signed). This laptop is always trusted.
  Code: `web/server/access.ts`, tests `web/server/access.test.ts`.
- Use synthetic demo data only, and close the
  "arjun tunnel" window when finished. Node/npm is required; the first run may download `cloudflared`.
- `-Only web -Phone` does not restart core-api (the warning says so); use `-Only core-api -Phone` or no
  `-Only` to apply the new `BASE_URL`.
- The URL parser / `.env` line replacer is `scripts\tunnel_url.py`; its standard-library unit tests run
  with `.venv\Scripts\python scripts\test_tunnel_url.py` (pytest also collects them).

## Demo user: Heerabai

Seed synthetic user 1 through core-api. The first command is a dry run; add `--apply` to write the changes.
Existing user names cannot be changed with the current core-api profile endpoint; if user 1 has a different name,
the script reports that limitation while seeding the other requested data.

```
.venv\Scripts\python scripts/seed_heerabai.py
.venv\Scripts\python scripts/seed_heerabai.py --apply
```

- Elder app: http://localhost:5173/?user=1
- Family dashboard: http://localhost:5173/?view=family&user=1

## Safety design in code
- LLM never writes to the DB. Reasoning proposes -> core-api validates and stores a *pending* action ->
  only a spoken yes (`CONFIRM_YES`) executes it.
- Reminders / appointments / contacts are answered from SQL only.
- Ambiguous AM/PM, missing date, or "after the meal" without which meal -> Arjun asks, never guesses.
- Distress: rule-based keyword net (recall-biased), overrides everything, rejects any pending action,
  mentions Elderline 14567 (8 AM-8 PM) and offers a family call. Caregiver is alerted only if
  `consent_distress_alert` is set, and no conversation text is stored or sent.
- Care-mode replies are fixed templates, so nothing medical or invented can be spoken.
- Stories: saved only after a spoken yes, private by default, shared only after a second spoken yes;
  `/memory-book` returns shared stories only; "he visar" deletes.

## Known limitations (honest list)
- **Apps by voice (2026-11-02) is tested, not hand-tested**: no real voice session, and the elder page was never opened in a browser with the new
  MediaScreen (the Chrome extension was not connected). Word lists are UNVERIFIED (no native speaker, no real Prisma output).
- **WhatsApp needs one tap**: Arjun only opens her chat with the contact; she presses the green call / send button. A pop-up blocker turns the open
  into one big tap button. Numbers are made up in the demo.
- **Media mode needs the wake word**: while a video plays, a new request must start with "अर्जुन" (or be a bare stop / next / volume phrase). The page's
  own report (`arjun.media`) and the agent's guess can disagree for a few seconds. Arjun's voice plays OVER the video (no ducking yet).
- **YouTube quota**: search.list costs 100 of 10,000 daily units; results are cached 24 h and uncached searches are capped at 80/day
  (`YOUTUBE_MAX_SEARCHES_PER_DAY`). No key or no quota = the results page opens. Embeds can be refused by a video's owner (the page shows an error).
- **Kiosk autoplay**: sound autoplay works in the kiosk profile (`scripts/elder-kiosk.ps1`); in a normal browser the first video shows one big
  "▶ सुरू करा" tap. A long headline is cut at a whole word at 120 characters.
- **2026-11-02 Windows crash fix not yet confirmed live**: "Assertion failed LSX_FFT_BR == NULL" (livekit_ffi.dll / soxr) should be fixed by warming the resampler once per process (`audiowarm.py`, `prewarm_fnc`); unit tests pass, but no live session has run on it.
- **2026-10-31 night (conversation mode, symptoms, endpointing) is tested and measured on text only**: a 15-turn Marathi run with the
  real Sarvam key (11/15 answered by the LLM, 0 "not understood"), but NO spoken session on the new code. Chat turns now wait 1.6 s of
  silence (0.8 s for commands), so a chat reply arrives about 0.9 s later; the symptom and health-advice word lists are unverified.
  After a Sarvam timeout the next chat turns wait 4 s each again (no cool-down yet).
- **2026-10-31 changes are tested, not hand-tested**: no real voice, browser, Sarvam key or Timbre v3.0 call yet.
- **Always listening costs credits**: hands-free keeps one Prisma stream open all day; cost per day is unmeasured.
  `ARJUN_IDLE_CLOSE_S=60` brings back the idle close.
- **No question also means no safety net for a misheard reminder** except the read-back and "नको" within 150 s.
- **Conversation summaries send the conversation to Sarvam** (only with the consent flag on and a key set). Rules
  summaries ("set a reminder, chatted") are used otherwise. Synthetic data only for the demo.
- Openers and morning briefings are still only logged by the scheduler, not spoken.
- **Memory is partly in process memory.** The session history and its summary live in reasoning's memory and
  are lost on a restart; only the `user_facts` (core-api) last. Facts are extracted after a conversation ends
  (scheduler tick) with the hosted LLM; they were checked only against Gemini and SQLite so far.
- One shared API key; no per-person login yet (frozen until after Nov 10). The tunnel has a role-limited access cookie
  (elder / family), but the roles are not per person: an elder link for user 1 can still read user 2.
- The access code is dev-server only (Vite). Docker compose and a production proxy do not have it.
- **Parser quality is unmeasured.** The 42 eval cases were written alongside the parser, so 100% there
  says nothing about real speech. Needs real transcripts of elderly Marathi speakers.
- Task text is the leftover words after removing time/command words (e.g. "doctor jaycha"), not a clean noun phrase.
- **Emergency vs consent (decided 2026-10-24):** a physical emergency (chest pain, can't breathe, a fall, fainting,
  bleeding) ALWAYS creates a family alert on the dashboard, even with distress-alert consent off; emotional distress
  still alerts only with consent. The alert is a red dashboard banner that names the configured family contacts and
  states that **no call or message was sent**: there is no SMS / phone delivery yet (telephony is frozen). Both
  lexicons are still unverified by a native speaker.
- **A pending yes/no is protected** (fix B, from the first hand test): while Arjun waits for an answer, anything that
  is not yes / no / cancel / a restated reminder gets the SAME question again; chat, a "keep your story?" offer or
  any other proposal can never replace it. A pending action expires after `PENDING_TTL_S` (default 300 s) in core-api.
  Runaway repetition from the recognizer ("हो हो हो कर कर कर ...") is collapsed on every turn. UNVERIFIED with a
  real voice after these fixes.
- The voice session serves the user id carried in the token's dispatch metadata (`ARJUN_USER_ID` is only the fallback
  for Console rooms). The dashboard refreshes every 10 s and on focus; "Create demo user" asks first. The demo uses
  ONE synthetic user (user 1): `python scripts/clean_demo_db.py` lists what would be removed (dry run), `--apply`
  does it after a backup.
- **Spoken clock hours** (एक..बारा, ek..barah, साडे/सव्वा/पावणे, दीड, अडीच) are read as times only next to a clock
  word ("दहा वाजता") or a day-part ("सकाळी दहा"); other spellings Prisma may produce are untested. If a clock word is
  heard with no readable hour, Arjun asks "किती वाजता?". A bare day-part with no clock word ("सकाळी") still means the
  family-set wake/meal time.
- **Open conversation needs the hosted LLM.** Without `LLM_BASE_URL` the companion rotates four fixed lines, so
  anything that is not a care command gets an off-topic answer (seen in the first real-speech test). With it set,
  only companion/chat replies and turns the rules cannot read go to the provider; care commands, times, medicines,
  confirmations and safety never do. See the next bullets for what is and is not verified.
- "उद्या काय आहे" reads tomorrow from SQL (medicines are computed from the family schedule, nothing is written). A
  sentence naming two days ("उद्या आज काय आहे") asks which day; the answer "उद्या" alone is not understood yet.
- A stale reply (the user spoke again first) is dropped only if it is a plain care or companion reply. Safety replies
  (emergency / distress) and any reply that asks a yes/no are always spoken, so a later "yes" never confirms an action
  the user did not hear. UNVERIFIED live.
- Gnani TTS: each spoken reply opens a new WebSocket (~0.9-1.2 s connect on this laptop, measured) before audio
  starts; see STATUS.md. Not changed yet.
- Only the first interest is used for openers; opener delivery to the voice session is not wired (scheduler logs it).
- Distress check is keyword + stem-pattern rules (spelling folded: anusvara/chandrabindu, i/u length, nukta) and
  now answers even if core-api is down. The lexicon is **unverified**: written without a native speaker or real
  Prisma output, and its tests were written by the same author, so they are not an independent recall measure.
  Loneliness phrases have their own gentle path (see above). Not handled here: some
  everyday phrases ("sab khatam ho gaya" for milk) still trigger a check-in. Distress check was keywords only; Evon can additionally return `DISTRESS` but there is no separate classifier.
- Slot-filling drafts live in reasoning's memory (single instance; lost on restart).
- Single shared API key, no caregiver/elder role separation or login yet. The Memory Book endpoint is
  caregiver-safe by construction, but the elder-side `/stories/latest` is not protected from a caregiver
  holding the key. Do not expose beyond a demo.
- Timestamps are naive local time (IST); no timezone handling. Tables created with `create_all`; no Alembic migrations yet.
- **Do not publish Prisma/Timbre accuracy numbers yet.** Gnani's EULA clause 16 bars disclosing benchmark results
  outside your organization, and it is unknown whether it applies to the challenge API platform. Ask on the Gnani
  Discord first. Until then, report results for Arjun as a system (e.g. reminders completed correctly), not WER for
  Prisma. Also unanswered: credit cost per call, what happens when credits run out, and whether a teammate may use
  the primary registrant's key (credits and the key belong to the primary registrant).
- **The conversation LLM is a hosted, non-Gnani provider** (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`,
  `LLM_PROVIDER_NAME`; `EVON_*` still work as aliases; `LLM_SEND_TEMPLATE_KWARGS=0` for non-vLLM). Gnani = Prisma
  (hearing) + Timbre (voice); Evon is not used. **Whatever the elder says in an open-conversation turn is sent to
  that provider**, so the demo uses synthetic data only. CLAUDE.md open question 5 (is a non-Gnani LLM allowed in
  the entry?) is still unanswered on Discord: say plainly in the posts which model does what. No provider is
  configured yet, so nothing has run through it live. Reply quality in Marathi is unmeasured (`eval/llm_compare.py`
  measures it once a provider is set). Limits: one ~4 s budget per turn, 80 tokens, last eight exchanges, no name
  or contact details sent; replies that claim to be human, say "I missed you", give medical advice, or recite
  recipes/facts are replaced by a fixed line.
- Companion conversation: the elder screen now keeps listening after a CHAT reply (ends on silence, "nako", or the
  back button), and reasoning sends the LLM the last eight exchanges (care turns as short text) of this conversation plus the user's interests
  (in memory only, dropped after 30 min idle or on distress, never stored). Covered by mock-provider tests only:
  **no real LLM reply and no real speech has run through it**, so reply quality, Marathi fluency and the
  hands-free loop on a real device are unverified. Without `LLM_BASE_URL` the replies are still the 4 canned lines.
- Companion CHAT replies are rotating templates unless an LLM is configured. `COMPANION_TEMPERATURE=0.6`
  is Gnani's recommendation for Evon, **not yet chosen by our testing**. The client is only tested against a mock
  transport.

- **Medicines (new):** family creates/edits them on the dashboard; Arjun can only record "taken" / "snooze"
  after a spoken yes (or a tap) and deflects every medicine question to "ask the doctor". Verified by tests
  and one local end-to-end run (core-api + reasoning + web in headless Edge). Not verified: real speech, a real
  device, the scheduler container. Spoken delivery is built (see the T8 bullets) but has not been tried with a real
  voice session. No browser speech is used anywhere.
- Medicines are anchored to wake / lunch / dinner (+ family offset) or a fixed time; there is no
  "after breakfast" because no breakfast time exists yet. Snoozes are capped at the medicine's
  "ask up to" count. "On time" = within the medicine's window (default 30 min), all self-reported.
- Voice reminders that mention a medicine are refused on purpose (family sets medicine times); this also
  means a plain voice reminder like "tablet remind kar" now gets the "your family sets medicine times" reply.
- **Proactive day check-ins (2026-11-03, built, NOT tried with a real voice session):** when the family switches
  `daily_checkins` on, Arjun asks one short Marathi question at a time about her day (sleep, breakfast, lunch,
  a walk, one listening interest, whether she spoke to one family member, dinner, and a mention one hour before
  an appointment / reminder). Times and names come from her own data. She is never asked inside 22:00-07:00, or
  (except the appointment / reminder mention) outside her opener window; at most `ARJUN_CHECKIN_MAX_PER_DAY` (8)
  a day, 45 minutes apart; a busy moment (media playing, a safety reply, she spoke in the last 2 minutes, a
  reminder being spoken) postpones a question 10 minutes, 3 times at most. Word lists for her answers are
  UNVERIFIED (no native speaker). Medicines are NOT a separate check-in: the medicine flow already asks at the
  due time and every 15 minutes, with name and dose verbatim, and the day card reads those doses.
  The family card "आजचा दिवस" shows done / not done / no answer with times and never her words.
- **Still not built:** BP / sugar readings, "Export for doctor", medicine-strip photo
  upload (the dashboard takes a link). The dashboard keeps "Not set up" for those; the BP screen exists in
  `web/src/ghar/Screens.tsx` (shown at `/?preview`) but is not wired.
- New tables (`medicines`, `medicine_doses`) are added by `create_all`; there are no migrations, and an
  existing database is not altered otherwise.
- The elder UI talks only through LiveKit + Gnani (T6): tap बोला -> `POST /livekit/token` (fresh room, explicit
  "arjun" dispatch) -> mic -> the screen mirrors the agent's `arjun.screen` attribute. No browser speech API is
  used anywhere (`scripts/check_no_browser_speech.py`, also a test). Verified without a browser by a LiveKit client
  script; **not yet verified in a real browser**. Browser echo cancellation + noise suppression are ON because the
  agent has no noise filter (open question 6).
- The elder page needs a secure origin for the microphone: `http://localhost` works; a phone needs HTTPS. Options:
  (1) `scripts\dev-up.ps1 -Phone` (Cloudflare quick tunnel; see "Run on phone" above); (2) Android + USB:
  `adb reverse tcp:5173 tcp:5173`, then open `http://localhost:5173` on the phone; (3) `vite --https` with a local
  certificate (mkcert) and the laptop's LAN address; (4) Chrome's
  `unsafely-treat-insecure-origin-as-secure` flag on the phone, for a quick test only. A tunnel exposes the dev
  proxy and its API key, so demo data only.
- **T8, spoken reminders and medicines (built 2026-10-26, UNVERIFIED with real audio or in a browser):** the scheduler
  (started by `scripts/dev-up.ps1`) queues each due reminder / medicine prompt in core-api; an open voice session
  claims one at a time and speaks it with the fixed wording from SQL, and the item is "spoken" only after playback
  finished. The elder page needs ONE tap on "सुरू करा" per page load (browsers block sound before a tap) and then
  opens a voice session by itself when something is waiting (at most once a minute). "Spoken" means Arjun finished
  saying it, not that Aaji heard it; the card stays on her screen until she taps OK / घेतली. A medicine prompt that
  waited past its window is NOT spoken (the family is told) and says "not spoken" on the screen; a late plain
  reminder keeps its original time and says when it was due; at most 3 late items are offered for speech, the rest
  stay on the screen. An item that is interrupted or fails speech is retried at most twice, then marked "not
  delivered" (family told once; it stays on the screen). An idle session closes itself after 60 s.
- **No quiet hours:** a due reminder or medicine is spoken at any hour if the elder page is open and started, including
  at night. There is no do-not-disturb setting yet.
- **Browser sound can still be blocked** (for example after the page lost focus for long): the page then shows "ऐका"
  (touch to hear), but a line Arjun already finished saying is NOT repeated (no "repeat last line" yet), so the
  card on the screen is the fallback. If the elder page is closed, reminders queue and the dashboard says they were
  not delivered.
- **The emergency alert is dashboard-only:** a physical emergency shows a red banner for the family; no call, SMS or
  WhatsApp is sent (telephony is frozen) and the banner says so.
- **Emergency alarm in a background tab (new 2026-10-29, UNVERIFIED in a real browser):** the dashboard checks the
  notifications every 15 s even when its tab is hidden (the normal 10 s refresh still pauses), and rings until
  someone taps "I have seen it - stop the alarm": a repeating Web Audio tone (no speech API), one system pop-up
  per emergency and a flashing tab title. The family taps "Turn on emergency alarm" once per page load (browsers
  block sound before a tap; pop-ups need permission once). Acknowledged ids are kept per browser (localStorage).
  Limits: browsers slow background timers (Chrome: about once a minute), so a background alert can take up to
  ~1 minute; a closed tab, a sleeping laptop or a phone with the page closed gets nothing.
- **"Last talked to Arjun" (new 2026-10-29):** every `/turn` (safety turns included) and every tap on an elder card
  records ONE timestamp in core-api (`activity` table, `GET/POST /users/{id}/activity`): time and voice/tap only,
  never words. It is written after the reply was sent (no added latency). The dashboard's first tile shows it;
  3 h after the family-set wake time with nothing today it says she has not talked to Arjun today and suggests a
  call, without calling it a problem (she may simply not have used the app). Not an inactivity alarm: nothing is
  sent and nothing escalates.
- **Loneliness phrases (new 2026-10-29, lexicon UNVERIFIED):** "मला एकटं वाटतं", "अकेलापन", "I feel lonely" and
  similar get a fixed warm reply that names up to three family contacts and offers a call, then keeps listening
  (companion mode). Only for chat / unreadable turns with nothing pending: a care command or a pending yes/no
  wins, and distress / emergency still override it. With the family-alert consent ON, the family gets ONE
  "said she is feeling lonely today" note a day (`POST /users/{id}/lonely`), never her words. Written without a
  native speaker or real Prisma output; needs the T12 review like the other two lexicons.
- **The मदत (help) button needs a second yes:** a tap starts a voice session that says "मदत", which proposes
  REQUEST_CAREGIVER and asks "shall I tell your caregiver? yes or no". Not changed (team decision needed): a tap
  on a dedicated help button could arguably alert directly.
- Pre-warming joins a quiet room as the page opens; it ends by itself after 60 s without a tap. Credits used by
  that were not measured.
- Honorific ("आजी") and the animation switch are not stored server-side: honorific is a constant, "turn off
  animations" is per-device (localStorage). Evening theme is chosen by clock (17:00-05:00) or `?theme=evening`.
- Design open questions still need testing with real elders: diya-only speak button, motion, script preference.

- **Clock and day guidance (new):** every service reads the household clock (`ARJUN_TZ`, default
  Asia/Kolkata) instead of the machine clock, so containers in UTC are not 5h30 off. `GET /users/{id}/day`
  is the single SQL-backed view of today (items, what is due now, what is next). Arjun answers "kiti vajle",
  "aaj konta divas" and "ata kay karaycha" from that clock + SQL through fixed templates, `/briefing/{id}`
  gives a once-a-day greeting + plan (the scheduler logs it; delivery to a voice session is not wired), and
  LLM prompts receive the current time. The elder screen shows the clock using server time (corrects a
  phone with a wrong clock). Verified by tests and a local run; not yet verified in a container.
- Time guidance only reads what the family set (reminders, appointments, medicines, wake/lunch/dinner
  times). It does not suggest activities. "Next" can be a meal time, which is a family-set marker, not a
  confirmed meal. Day boundaries are midnight in the household timezone; no DST handling is needed for IST.

## Deferred (per CLAUDE.md "stretch" / not started)
pgvector RAG over stories and past-story recall, RSS topic news, S3 TTS cache, MongoDB trace logging
(per-stage timings are only logged to stdout), nginx 2-replica load balancing, noise-cancellation A/B,
WER and latency measurement.

## Open questions (need a human / credentials - not guessed)
Prisma streaming support for the target language; credit cost per Gnani call; whether noise
cancellation helps or hurts Prisma; whether LiveKit turn-detection can change mid-session (the
1.0s / 3.0s endpointing values (`ARJUN_MIN/MAX_ENDPOINTING_S`) are placeholders); which embedding model
works for the target language. Target language was assumed to be Marathi from the spec's examples.
