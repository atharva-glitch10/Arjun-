# Execution flows (file -> function)

Each step names the file and function. Steps marked *(inferred)* come from the graph or from reading the surrounding code, not from a line-by-line trace.

## 1. One voice turn

1. Elder taps once. `web/src/voice/useArjunVoice.ts` (`useArjunVoice`) calls `api` -> `POST /livekit/token`.
2. `core_api/livekit_token.py::livekit_token` builds `elder-<id>-<ts>-<hex>`, signs a JWT with a `RoomAgentDispatch(agent_name="arjun")`, and calls `remember_room`.
3. LiveKit starts the worker job. `services/voice-agent/agent.py::entrypoint` picks the provider (`voiceprovider.make_sarvam` for the test switch, else `working_tts` + `gnani.STT`), builds `Responder`, `DeliveryLoop`, `MediaState`, `FamilyPresence`.
4. Mic audio goes through Prisma STT. When the user's turn ends, `agent.py::Arjun.on_user_turn_completed` runs:
   - drops the turn if `FamilyPresence.present()` (a family member is in the room);
   - drops it if `media.should_send(transcript, playing)` is false (the mic hears the video);
   - `ConjunctionHold.settle` (endpointing.py) waits when the sentence ends in "आणि / पण / म्हणजे / की".
5. `responder.py::Responder.respond` -> `bridge.py::reply_or_fallback` -> `ask_reasoning` -> `POST {REASONING_URL}/turn` (timeout 5 s). Any failure returns a fixed spoken fallback, never silence.
6. `reasoning_svc/main.py::turn` -> `turn.py::TurnEngine.handle`:
   1. `collapse_repeats`, then `is_emergency` / `is_distress` (distress.py), then `_second_look` (rule check on body words).
   2. If safety fires: `_safety` (see flow 2) and return.
   3. `core.user(uid)` (core_client.py). On failure, the fixed `r["error"]` template.
   4. `_understand` -> `evon.py::EvonClient.understand_turn` (one hosted LLM call). If it fails, `_intent` falls back to `parser.py`.
   5. AI-disclosure check, `_family_offer_answer`, pending-action lookup, media choice (`_answer_choice`), BP and check-in answers.
   6. `_dispatch` runs the SQL-backed path (`_create_reminder`, `_complete`, `_medicine_action`, `_chat_reply` ...).
   7. `_guard_cardiac_reply`, `_remember`, return `TurnResult`.
7. Back in voice-agent: `screenstate.publish_screen` sets participant attributes (`arjun.screen`, `arjun.action`). `tts_text(...)` strips or keeps Timbre tags. Timbre speaks through `TtsGate` (one request at a time).
8. Browser: `useArjunVoice` reads the attributes (`parseAttributes`, `parseActionAttribute`) and the card in `ElderApp` changes.

## 2. Emergency detection, family alert, join call

1. `TurnEngine.handle` -> `distress.py::is_emergency(text)` is true.
2. `TurnEngine._safety(kind="emergency")`: clears drafts and history, rejects any pending action (`core.reject`), then `core.distress(uid, "emergency")` -> `POST /users/{id}/distress?kind=emergency`.
3. `core_api/main.py::record_distress`: always `alerted = True` for an emergency. Adds `DistressEvent` and a `Notification(kind="emergency")` whose body comes from `_emergency_body`, then `db.commit()`.
4. `core_api/feed.py::_to_feed` (SQLAlchemy `before_flush`) copies the Notification into a `FeedEvent`. `_wake` (`after_commit`) calls `BROKER.notify(user_id)`. The dashboard socket wakes.
5. `main.py::_family_alert` -> `telegram.claim` (10-minute dedupe) -> `telegram.send_alert` starts a daemon thread -> `_deliver` -> `_post` (`api.telegram.org/bot<token>/sendMessage`, with a button from `joins.join_url`). Result is written as an `alert_sent` or `alert_failed` Notification by `_record`.
6. The spoken reply is a fixed Marathi template ("112 वर फोन करा"). It says the family was told only if `caregiver_alerted` came back true.
7. Dashboard: `family/emergencyWatch.ts::startEmergencyWatch` + `alarm.ts::startAlarm` raise the banner and sound.
8. Family taps the Telegram button -> `/?view=join&t=<user.exp.sig>` -> `main.tsx` renders `JoinCall.tsx` -> `GET /family/join` -> `family_call.py::family_join` -> `joins.verify` (HMAC, 30 min) -> `livekit_token.active_room(user_id)` -> JWT for identity `family`, 1 h, microphone only.
9. In the room, voice-agent `familyroom.FamilyPresence` marks the family present; `on_user_turn_completed` and `on_tapped_text` then stay silent.

## 3. Reminder add and undo

1. The LLM gives intent `CREATE_REMINDER` with slots. `TurnEngine._dispatch` -> `_create_reminder` asks for any missing detail (never guesses AM/PM or date).
2. `_act(uid, "CREATE_REMINDER", payload)`: `core.propose` -> `POST /users/{id}/actions/propose`; with `ask_first` off it then calls `core.confirm` at once.
3. `core_api/main.py` `confirm` handler validates the payload, inserts `Reminder`, stores `_done` info on the `PendingAction`, and returns it. The reply ("ठेवली: ... बदलायचं असेल तर 'नको' म्हणा.") is read from `replies.py`.
4. `_last_done[uid]` remembers the action for the undo window (150 s here, 180 s in core-api).
5. "नको / चुकलं" next turn: `turn.py::_dispatch` (undo branch) -> `core.undo` -> `POST /actions/{id}/undo` -> `main.py::undo`: checks `status == confirmed` and `now - done_at <= UNDO_TTL`, calls `ack_item` to supersede any queued delivery, deletes the `Reminder`.
6. Later, `scheduler.tick` -> `POST /internal/reminders/fire-due` -> `deliveries.enqueue` -> spoken by flow 7.

## 4. Medicine taken

1. Family creates the medicine on the dashboard (`Dashboard.tsx` -> `medicines.py` POST). Voice cannot create or change medicines.
2. `scheduler.tick` -> `POST /internal/medicines/tick` -> `medicines.py::tick` creates `MedicineDose` rows and calls `deliveries.enqueue(kind="medicine")`.
3. `reasoning::TurnEngine.deliver_next` claims it, `_medicine_line` renders name + dose from SQL with a fixed template. `_asked_dose[uid]` is set.
4. Voice-agent `DeliveryLoop.tick` speaks it and calls `bridge.mark_delivery_spoken` -> `/delivery/{id}/spoken` -> core `deliveries.spoken`.
5. Elder says "घेतली". The LLM or the rule parser gives `MED_TAKEN`. `TurnEngine._medicine_action` picks the dose, then `_act(uid, "MEDICINE_TAKEN", {"dose_id": ...})`.
6. core-api `confirm` marks the dose taken (`taken_at`). Taken is self-reported. Undo works through `main.py::undo` (`MEDICINE_TAKEN` branch).
7. Not confirmed after N reminders: `medicines.py::tick` writes a `medicine_unconfirmed` Notification -> feed -> family only.

## 5. YouTube play, choice, stop

1. "भजन लाव" -> `appcmd.py::parse_app_command` / `media_understanding.py` give `OPEN_APP` with a query.
2. `TurnEngine._app_command` -> `_open_media` -> `_search` -> `core.youtube_search` -> `core_api/media.py::youtube_search` (24 h cache in `YoutubeSearchCache`, 80 uncached searches a day).
3. `_offer` / `_results_page` builds cards and stores `_MediaChoice[uid]`. The elder says "पहिलं" -> `_answer_choice` (`_ordinal`, `_named_card`, `_llm_choice_index`) -> `_play_item` -> `_media_action`.
4. `TurnResult.action` is `{"type":"open","kind":"youtube_video",...}`. `screenstate.action_json` publishes it as `arjun.action`; `MediaState.on_action` in voice-agent turns media mode on.
5. Browser: `useArjunVoice` parses the attribute -> `useAppActions` -> `elder/media.ts::planAction` -> `MediaScreen` embeds a YouTube iframe (`embedSrc`) and reports `playing` through the participant attribute `arjun.media`.
6. While playing, `agent.py` ignores transcripts unless `media.should_send` passes (wake word "अर्जुन", a bare control, or a safety phrase from `safety_words.py`). `mediamode.MediaMode.decide` calls `POST /media/gate` for borderline text.
7. Stop: "अर्जुन, थांबव" -> `strip_wake_word` -> `/turn` -> `MEDIA_CONTROL` action `stop` -> browser `mediaReducer` closes the player and reports `stopped`.

## 6. Proactive check-in

1. `scheduler.tick` -> `POST /internal/checkins/tick` -> `checkins.py::tick` plans the day (`checkin_plan.py`), inserts `Checkin` rows for meals, walk, BP when `daily_checkins` is on, and `deliveries.enqueue(kind="checkin")`.
2. `scheduler.tick` -> `POST /internal/deliveries/sweep` -> `deliveries.run_sweep` retires or flags late items.
3. Voice-agent `DeliveryLoop.run` polls `bridge.claim_next_delivery` -> `POST /delivery/next` -> `TurnEngine.deliver_next`. If a yes/no is pending, a safety hold is on, or media is playing, `core.postpone_checkin` (10 min, 3 times at most) and nothing is spoken.
4. Otherwise `_checkin_line` renders text; `agent.py::publish_item` -> `screenstate.publish_delivery`; the line is spoken; `mark_delivery_spoken` is called after playback.
5. Her answer: `TurnEngine._answer_open_checkin` -> `_read_checkin_answer` -> `core.answer_checkin` -> `POST /checkins/{id}/answer`.
6. Unanswered or undelivered items become `checkin` / `undelivered` Notifications -> feed.
7. Briefings and openers (`scheduler.tick`) are **only logged**, never spoken.

## 7. Delivery of a due reminder

1. `scheduler.tick` -> `/internal/reminders/fire-due` -> `main.py` fire-due handler -> `deliveries.enqueue`.
2. Same claim, speak, `spoken`, `ack` path as flow 6 (kind `reminder`, `deliver_reminder` or `deliver_reminder_late` template).

## 8. Family dashboard live feed

1. Any code path that adds a `Notification` or `Wellbeing` triggers `feed.py::_to_feed` in `before_flush`, which adds a `FeedEvent`. After commit, `_wake` -> `BROKER.notify(user_id)`.
2. Browser: `family/Dashboard.tsx` effect -> `feed.ts::connectFeed` opens `WS /core/ws/users/{id}/feed?after=N`. The Vite proxy adds the key to the upgrade.
3. `feed.py::feed_socket` checks `_ws_key_ok`, `BROKER.subscribe`, then loops: `_rows` (in a thread), `send_json({"type":"event"...})`, wait on the event or `RECHECK_S` (5 s), send `ping`.
4. If the socket is down, `feed.ts` falls back to `GET /users/{id}/feed?after=N` (and `polling.ts::startPolling`) with backoff 1, 2, 5, 10, 30 s.
5. `mergeFeed` de-duplicates by id. A serious row (`SEVERITY_RANK`) makes the dashboard reload everything; an emergency also drives `emergencyWatch` and `alarm`.
6. Conversation summaries: `scheduler.tick` -> `POST /conversations/flush-idle` -> `Tracker` in reasoning (wellbeing.py) -> `core.wellbeing` -> `POST /users/{id}/wellbeing` -> `Wellbeing` row -> feed. Shown only when `consent_distress_alert` is on.
