# Gnani model capability and integration audit

Audit date: 2026-11-07. This records public Gnani documentation/API contracts and the current repository wiring.
No model request was made during this audit and no key or account entitlement was inspected. Public docs establish
the protocol; they do not prove that this account has Prisma v3, Timbre v3, or Warp enabled.

## Current repository wiring

| Model | Current use | Repository evidence |
|---|---|---|
| Prisma STT | Plugin remains default; opt-in `GNANI_STT_IMPL=v3` selects direct Prisma v3 Auto-LID/codemix, per-user hints, locale hints, and 8 kHz. | [`agent.py`](../services/voice-agent/agent.py#L276), [`prisma_v3.py`](../services/voice-agent/prisma_v3.py#L52), [`prisma_v3.py`](../services/voice-agent/prisma_v3.py#L29). |
| Timbre TTS | Configured v3.0 is probed with v2.5 fallback. Reply path selects language from Prisma and can opt into the multilingual v3 voice catalog; default voice config remains as fallback. | [`voice.py`](../services/voice-agent/voice.py#L15), [`agent.py`](../services/voice-agent/agent.py#L352). |
| Warp | Not used. No Warp endpoint/client/configuration exists in the repository. | No Warp references in runtime source; current agent builds a Prisma + Timbre LiveKit pipeline at [`agent.py`](../services/voice-agent/agent.py#L268). |
| Evon | Generic OpenAI-compatible client is present, but Evon is not the default provider. Runtime selection prefers `LLM_*`, then Sarvam when configured, and only then `EVON_*`. | [`config.py`](../services/reasoning/reasoning_svc/config.py#L24) describes provider choice; [`config.py`](../services/reasoning/reasoning_svc/config.py#L52) implements precedence; [`evon.py`](../services/reasoning/reasoning_svc/evon.py#L456) is the compatible client; [`turn.py`](../services/reasoning/reasoning_svc/turn.py#L242) accepts it optionally. |
| User language | Preferred languages can store all ten documented locale families; the elder UI provides Marathi/Hindi/English labels and English fallback. Reasoning carries detected language to Evon/TTS; existing fixed action/safety templates remain primarily mr/hi/en. | [`models.py`](../services/core-api/core_api/models.py#L42), [`schemas.py`](../services/core-api/core_api/schemas.py#L10), [`turn.py`](../services/reasoning/reasoning_svc/turn.py#L345), [`i18n.ts`](../web/src/elder/i18n.ts#L1). |
| Voice cloning | Not used. No consent, embedding storage, cloned TTS, audit, or deletion UI/routes exist. | No voice-clone references in service or web runtime source. |

### Installed LiveKit plugin 1.8.6 check

The repository pin is `livekit-plugins-gnani==1.8.6`. The installed plugin's `STT` signature has `language`,
`sample_rate`, `preferred_language`, `format`, `itn_native_numerals`, and `use_streaming`, but no `model`,
`language_code`, `keyterms`, `topic`, `speaker_names`, or `previous_text` arguments. Its declared format type is
`verbatim|transcribe`. Its `TTS` model literal contains v2.0/v2.5, not v3.0. See the installed local source at
`.venv/Lib/site-packages/livekit/plugins/gnani/stt.py:48-72` and `models.py:25-55` (not tracked repository files).
Newer public LiveKit-plugin documentation describes a wider configuration surface; that must not be confused with
what the pinned wheel in this checkout accepts. A direct adapter is required for v3-only Prisma settings and is now available behind `GNANI_STT_IMPL=v3`; plugin mode remains the default fallback.

## Prisma v3.0 — speech recognition

Public docs describe one model for ten languages: Hindi, Bengali, Marathi, Gujarati, Punjabi, Kannada, Telugu,
Tamil, Malayalam, and English. The list is ten total including English. Hindi-English code-switching/Hinglish is a
speech pattern, not an eleventh Prisma language. `indic-auto` asks Prisma to identify a language; alternatively,
`language_code` accepts one to four locale hints. Each completed realtime utterance includes
`detected_language_code` except transliteration output.

| Capability | Documented API / parameters | In Arjun now? |
|---|---|---|
| Short-clip recognition | `POST https://api.vachana.ai/stt/v3`, multipart `audio_file`, `model=prisma-v3.0`, `language_code`; REST clips up to 30 s. | No direct Prisma v3 client. Current plugin call uses its v2-era option surface. |
| Live recognition | `WSS wss://api.vachana.ai/stt/v3/stream`; required `x-api-key-id`, `language_code`; select model `prisma-v3.0`; stream 16-bit mono PCM, receive documented JSON events; send `{"type":"commit"}` to close an utterance. | Yes, optional through `GNANI_STT_IMPL=v3`; pinned plugin remains selectable as fallback. |
| Batch recognition | `POST /stt/v3/batch/jobs`, `config.model=prisma-v3.0`, asynchronous job flow. | No. Arjun listens live; batch is not relevant to interactive turns. |
| Language identification | `language_code=indic-auto`; response `detected_language_code`. `language_code` may instead contain up to four locale hints. | Yes in v3 mode; configured preferred locales may be sent as hints; detected locale reaches reasoning as `language_code`. |
| Output formatting | `format=verbatim`, `transcribe`, `codemix`, `transliterate`. `codemix` keeps English words in Latin script while other words follow their script; `transliterate` writes the entire transcript in Latin. Streaming selects format at connection or via `update_settings`. `itn_native_numerals` has no effect on v3. | Yes, direct v3 selects `codemix`; plugin fallback continues to use its supported formats. |
| Context hints | Streaming headers `keyterms` (up to 200 items), `topic` (up to 1,600 chars), `speaker_names` (1–4 names), `previous_text` (earlier piece of the same recording). Non-ASCII `keyterms` JSON must be escaped in headers. These values are fixed for a connection. | Yes, bounded interests/contact/medicine names/app labels and up to four contact names are sent in direct v3 mode; topic/previous_text are not sent. Note the actual spellings: `keyterms`, `topic`, `speaker_names`, `previous_text`; there is no documented boolean `previous_context=true`. |
| Keyterm updates | JSON control `update_settings` supports `bias` for Prisma v3 keyterms; `keyterms` header is fixed. Do not send the old `key_terms` spelling. | No. |
| VAD tuning | WS headers include `x-vad-threshold`, `x-min-silence-ms`, `x-min-speech-ms`, `x-min-segment-ms`, `x-max-speech-s`; connection-only. | Current LiveKit path delegates endpointing to LiveKit/plugin, not explicit Prisma VAD headers. |
| Telephony audio | Native 8 kHz PCM supported; WS `x-sample-rate: 8000`. Other documented rates include 16, 44.1, and 48 kHz. | Yes, direct v3 and plugin both accept `GNANI_STT_SAMPLE_RATE=8000`. |
| Session / retry limits | Realtime session max 15 min; idle 60 s default configurable by `x-idle-timeout-sec` from 5–900; per-organization concurrency cap; 429 requires backoff. | Current reconnect/recovery logic exists for the LiveKit stream, but it does not apply Prisma v3-specific stream settings. |
| Segment metadata | Transcript includes text, audio duration, segment ID/index, latency and detected language code. | Direct v3 maps text and detected code into LiveKit speech events and turnlog. |

Correcting request terminology: API docs use `language_code=indic-auto`, not `language.auto_lid=true`; use
`format=codemix`, not `mode=codemix`; use `keyterms`, not `key_terms`; and use `previous_text`, not
`previous_context=true`. `previous_text` is transcript carryover for a recording split into pieces, not a general
conversation-memory switch. Names/interests/places in hints should be bounded to the active user and never logged.

## Timbre — text-to-speech

The public TTS docs expose Timbre v2.5 and v3.0 via REST, SSE, and realtime WebSocket. REST is
`POST https://api.vachana.ai/api/v1/tts/inference`; SSE is `POST .../api/v1/tts/sse`; realtime is
`WSS wss://api.vachana.ai/api/v1/tts`. Requests use `X-API-Key-ID`, `text`, model, voice, language, speed and
audio configuration as applicable. v3 has 13 voices speaking all ten documented TTS languages; v2.5 has 42
model-specific voices, each associated with a preferred language. `language=auto` is available; `hi-en` is the
documented Hinglish locale. Speed is documented from 0.85 to 1.15. TTS normalization handles numbers, dates,
currency, identifiers and other listed patterns; supported language-level normalization covers Hindi, English,
Tamil, Telugu, Kannada, Malayalam, Marathi, Punjabi, Bengali, and Gujarati. v3 supports 13 inline audio tags
(including `slow`, `pauses`, `whispers`, `excited`, and `shouting`); tags are v3-only.

| Capability | In Arjun now? |
|---|---|
| Timbre v3 SSE and v2.5 fallback | Yes, configured v3 / Avinash probes first; known-good v2.5 / Omkar is the fallback. The latest repository handoff says the configured v3 probe failed on this account and v2.5 was selected. |
| REST / realtime WebSocket per-reply transport | Available in official docs; app currently uses SSE per sentence, and an older plugin WS path exists. |
| Per-language voice/model choice and Hinglish | Main reply and queued speech paths select language per transcript; `hi-en` uses documented locale, alternate voice requires `GNANI_TTS_MULTILINGUAL_VOICE=1`. |
| v3 expression tags | Partly. Reasoning can emit tags; `voice.py` passes tags only to a tag model, but active TTS selection depends on the v3 probe. |
| Speed control | Not used; existing `slower_text` inserts pauses as the compatibility fallback. |
| Text normalization / lakh-crore wording | Provider documents normalization. Arjun does not select a language per utterance today; current output is sent with the fixed configured locale. |

## Voice cloning — Timbre API capability

Public docs provide `POST https://api.vachana.ai/api/v1/tts/voice-clone/embeddings` with multipart `audio_file`;
they recommend 5–30 seconds of clean reference audio. The response is a `speaker_embedding` (shape `[1,768]`,
`torch.bfloat16`) which can be passed to cloned TTS REST, SSE, or WebSocket requests. The docs describe reusing
the embedding, but no remote voice-ID create/list/delete endpoint is documented. Consequently this is not a
Gnani-side persistent `voice_id` workflow and the public contract does not provide a remote deletion operation.
Arjun does not currently use cloning. Phase 4 cannot claim remote deletion; it will need provider confirmation
before we promise that consent can revoke/delete the provider-side artifact. Local encrypted storage and local
deletion alone cannot establish provider deletion or retention behavior.

## Warp v2.0 — what it is and why it is not integrated

Warp is Gnani's speech-to-speech model, not a STT mode or transcription endpoint. Gnani's model page describes a
5-billion-parameter native end-to-end speech-to-speech model with no intermediate text layer, real-time/telephony/
agentic positioning, and sub-200 ms P95. That makes it a distinct alternative voice pipeline: it would bypass
Prisma transcript visibility and the current explicit reasoning/core-api safety/action boundary unless the product
offers a documented handoff/tool protocol.

The current public `docs.gnani.ai/llms.txt` indexes STT, TTS, voice-clone, and Agent Builder APIs; it does not list
a Warp API page or Warp OpenAPI/AsyncAPI spec. The app.gnani.ai root loaded as an interactive client with no
readable API reference to inspect in this audit. No Warp endpoint, request schema, auth header, response format,
or key entitlement could therefore be verified. We do not invent a Warp endpoint and do not integrate Warp in this
phase. Ask Gnani for the actual Warp API contract and a key with access before reconsidering it.

## Evon v3.3 — language/reasoning model

The official Evon model card describes text-in/text-out instruction following, reasoning, multilingual RAG, and
tool-calling/agent applications; 128K context; English plus Hindi, Bengali, Telugu, Tamil, Marathi, Gujarati,
Kannada, Malayalam, Odia, and Punjabi; and deployments through Transformers, vLLM, or SGLang. It is an open-weight
model, not STT/TTS. The card's serving examples expose an OpenAI-compatible `/v1/chat/completions` endpoint on
the user's own server. The official Gnani hackathon write-up says the weights are open-weight/on Hugging Face,
not on the API platform (at the time of that write-up). No public hosted Evon endpoint/key contract is documented
in the Speech API reference; hosted API entitlement must not be assumed.

| Capability | In Arjun now? |
|---|---|
| Generic OpenAI-compatible chat client usable with a self-hosted Evon server | Yes. `EvonClient` posts to `/chat/completions` and accepts configured base URL/model/key. |
| Evon as default provider | No. Current precedence is `LLM_*`, then configured Sarvam, then `EVON_*`; Evon is otherwise off. |
| Understand intent / structured extraction / tool calling | The client sends schema-constrained turns; the app uses returned intents as suggestions and core-api validates actions. The model's general tool-calling claims do not authorize direct DB/tool writes. |
| Companion replies and conversation summaries | The client supports companion replies and a summary method. Current summary is hardcoded English; actual runtime provider depends on env configuration. |
| Daily family summary / “Before you call” talking points | No dedicated Gnani-Evon-backed product path is established for these features. |
| Safety/distress | Rules run first; when configured, model safety checks may add a restriction. The model cannot lower the rules floor. |

No model weights were downloaded, no hosted Evon endpoint was called, and no `EVON_*` values were read or printed.
Any move to Evon as primary requires an available supported server/host, acceptable latency, language evals, and a
fallback that preserves the project's fixed safety rules.

## Documentation sources consulted

- [Gnani API docs index](https://docs.gnani.ai/llms.txt) and [Prisma v3.0](https://docs.gnani.ai/api/STT/models/prisma-v3), [Realtime STT](https://docs.gnani.ai/api/STT/stt-websocket), [STT limits](https://docs.gnani.ai/api/STT/limits).
- [Timbre REST](https://docs.gnani.ai/api/TTS/tts-inference), [SSE](https://docs.gnani.ai/api/TTS/tts-sse), [WebSocket](https://docs.gnani.ai/api/TTS/tts-websocket), [voices](https://docs.gnani.ai/api/TTS/available-voices), [normalization](https://docs.gnani.ai/api/TTS/tts-input-formating), [audio tags](https://docs.gnani.ai/api/TTS/tts-audio-tags).
- [Voice clone embeddings](https://docs.gnani.ai/api/VC/voice-clone-embeddings), [cloned TTS REST](https://docs.gnani.ai/api/VC/vc-inference), [SSE](https://docs.gnani.ai/api/VC/vc-sse), [WebSocket](https://docs.gnani.ai/api/VC/vc-websocket).
- [Gnani Warp product/model page](https://www.gnani.ai/models); [official Evon model card](https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B); [Gnani hackathon model guidance](https://www.gnani.ai/resources/blogs/great-indian-ai-internship-challenge-2026).
- The authenticated `app.gnani.ai` console is a JavaScript application; this audit did not establish account-specific model access or inspect an account API-reference screen. Public docs' endpoint schemas are cited above; access must be verified on the registered account before enabling calls.
