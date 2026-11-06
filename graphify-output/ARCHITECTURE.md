# Arjun architecture

Source: Graphify graph of 201 code files (3,342 nodes, 8,592 edges), confirmed by reading the code.
The graph was built with `graphify extract . --code-only` (AST only), so docs (`*.md`) are not in the graph.
Mermaid diagrams were **not rendered to SVG** because `mmdc` is not installed (see the end of this file).

## 1. Overall system

```mermaid
flowchart LR
  subgraph Browser
    ELDER["Elder app<br/>(web/src/elder)"]
    DASH["Family dashboard<br/>(web/src/family)"]
    JOIN["JoinCall page<br/>(?view=join)"]
  end
  VITE["Vite dev server + proxy<br/>/core -> core-api, adds X-API-Key"]
  LK["LiveKit room"]
  VA["voice-agent<br/>(LiveKit worker 'arjun')"]
  RS["reasoning<br/>(FastAPI :8001)"]
  CORE["core-api<br/>(FastAPI :8000)"]
  DB[("SQLite / Postgres")]
  SCH["scheduler<br/>(30 s loop)"]
  ELDER -->|"/core/*"| VITE
  DASH -->|"/core/*, WS"| VITE
  JOIN -->|"/core/family/join"| VITE
  VITE --> CORE
  ELDER <-->|"audio, lk.chat, attributes"| LK
  JOIN <-->|"audio"| LK
  LK <--> VA
  VA -->|"POST /turn, /delivery/*"| RS
  RS -->|"X-API-Key"| CORE
  CORE --> DB
  SCH -->|"/internal/*"| CORE
  SCH -->|"/conversations/flush-idle, /briefing, /opener"| RS
```

## 2. Web (React) component hierarchy

```mermaid
flowchart TD
  MAIN["main.tsx<br/>view = elder | caregiver | join | gallery"]
  MAIN --> EA["ElderApp"]
  MAIN --> DB["Dashboard"]
  MAIN --> JC["JoinCall"]
  MAIN --> GAL["Gallery (design preview)"]
  EA --> UAV["useArjunVoice<br/>(LiveKit Room)"]
  EA --> UAA["useAppActions"]
  EA --> MS["MediaScreen / LinkPrompt<br/>(YouTube iframe)"]
  EA --> SCR["ghar/Screens + Motifs"]
  EA --> CARDS["cards.ts, format.ts"]
  UAV --> STATE["voice/state.ts"]
  UAA --> MEDIA["elder/media.ts (planAction)"]
  MS --> ACT["voice/action.ts (reducer)"]
  DB --> ALC["AppLinksCard"]
  DB --> FEED["feed.ts (WS + polling)"]
  DB --> EW["emergencyWatch.ts + alarm.ts + alerts.ts"]
  DB --> HELP["daycard, deliveries, activity, guard, polling"]
  EA --> API["api.ts"]
  DB --> API
  JC --> API
```

## 3. Backend services

```mermaid
flowchart LR
  subgraph core-api
    MAIN["main.py<br/>users, reminders, stories, actions, distress"]
    MED["medicines.py"]
    CHK["checkins.py + checkin_plan.py"]
    DEL["deliveries.py"]
    FEEDM["feed.py (before_flush hook, WS)"]
    WELL["wellbeing.py"]
    TG["telegram.py"]
    LKT["livekit_token.py"]
    FJ["family_call.py + joins.py"]
    MEDIA["media.py (YouTube, RSS)"]
    APPL["applinks.py"]
    DAY["day.py"]
    DEPS["deps.py (require_key)"]
    MODELS["models.py + db.py"]
  end
  subgraph reasoning
    RMAIN["main.py (/turn, /delivery/*, /media/gate)"]
    TURN["turn.py TurnEngine"]
    DIST["distress.py (safety rules)"]
    PARSER["parser.py (rule parser)"]
    EVON["evon.py (LLM client, name is legacy)"]
    REPL["replies.py (fixed templates)"]
    CC["core_client.py"]
    APPC["appcmd.py, app_replies.py"]
    MU["media_understanding.py"]
  end
  subgraph voice-agent
    AGENT["agent.py (entrypoint)"]
    BR["bridge.py"]
    RESP["responder.py"]
    DLV["delivery.py (DeliveryLoop)"]
    MM["mediamode.py + media.py + safety_words.py"]
    SCRN["screenstate.py"]
  end
  SCHED["scheduler.py"]
  RMAIN --> TURN
  TURN --> DIST
  TURN --> PARSER
  TURN --> EVON
  TURN --> REPL
  TURN --> CC
  TURN --> APPC
  APPC --> MU
  CC -->|HTTP| MAIN
  AGENT --> RESP --> BR -->|HTTP| RMAIN
  AGENT --> DLV --> BR
  AGENT --> MM
  AGENT --> SCRN
  MAIN --> MODELS
  MAIN --> TG
  MAIN --> FJ
  FEEDM --> MODELS
  SCHED -->|HTTP| MAIN
  SCHED -->|HTTP| RMAIN
```

## 4. API flow across services

```mermaid
sequenceDiagram
  participant W as Web (elder)
  participant C as core-api
  participant L as LiveKit
  participant V as voice-agent
  participant R as reasoning
  W->>C: POST /livekit/token {user_id} (via Vite proxy, API key added)
  C-->>W: url + JWT, room elder-<id>-<ts>, agent dispatch "arjun"
  W->>L: join room, publish mic
  L->>V: dispatch job (agent_name=arjun)
  V->>L: STT audio in, TTS audio out
  V->>R: POST /turn {user_id, text}
  R->>C: GET /users/{id}, pending, propose/confirm (X-API-Key)
  C-->>R: JSON
  R-->>V: TurnOut (speech, screen, action)
  V->>L: participant attributes arjun.screen, arjun.action
  L-->>W: attributes -> UI card / media
  V->>R: POST /delivery/next (every few seconds)
```

## 5. Database tables and relationships (core-api/models.py)

Every table except `youtube_search_cache` points at `users.id`. `medicine_doses` also points at `medicines.id`.
`deliveries.ref_id` is **polymorphic with no foreign key** (reminder, medicine dose or check-in, chosen by `kind`).

```mermaid
erDiagram
  USERS ||--o{ CONTACTS : has
  USERS ||--o{ REMINDERS : has
  USERS ||--o{ APPOINTMENTS : has
  USERS ||--o{ STORY_MEMORIES : has
  USERS ||--o{ PENDING_ACTIONS : has
  USERS ||--o{ CAREGIVER_REQUESTS : has
  USERS ||--o{ NOTIFICATIONS : has
  USERS ||--o{ DISTRESS_EVENTS : has
  USERS ||--|| ACTIVITY : has
  USERS ||--o{ WELLBEING : has
  USERS ||--o{ FEED_EVENTS : has
  USERS ||--o{ TOPIC_DECLINES : has
  USERS ||--o{ CHECKINS : has
  USERS ||--o{ BP_READINGS : has
  USERS ||--o{ WATCH_SAMPLES : has
  USERS ||--o{ MEDICINES : has
  USERS ||--o{ DELIVERIES : has
  USERS ||--o{ MEDICINE_DOSES : has
  USERS ||--o{ APP_LINKS : has
  MEDICINES ||--o{ MEDICINE_DOSES : schedules
  NOTIFICATIONS ||..o{ FEED_EVENTS : "mirrored by flush hook"
  WELLBEING ||..o{ FEED_EVENTS : "mirrored by flush hook"
  DELIVERIES }o..o{ MEDICINE_DOSES : "ref_id when kind=medicine (no FK)"
  DELIVERIES }o..o{ REMINDERS : "ref_id when kind=reminder (no FK)"
  DELIVERIES }o..o{ CHECKINS : "ref_id when kind=checkin (no FK)"
```

## 6. Auth

```mermaid
flowchart TD
  B["Browser"] -->|"no key in bundle"| P["Vite proxy /core"]
  P -->|"X-API-Key from CORE_API_KEY env"| CA["core-api: require_key on every router"]
  RS["reasoning CoreClient"] -->|"X-API-Key"| CA
  SC["scheduler"] -->|"X-API-Key"| CA
  WS["WS /ws/users/id/feed"] -->|"header x-api-key OR ?key="| CA
  CA -->|"hmac.compare_digest"| OK["allowed"]
  CA -->|"POST /livekit/token"| TOK["elder JWT: identity elder-id, 10 min, agent dispatch"]
  TG["Telegram button"] -->|"join_url: user.expiry.HMAC (30 min)"| JP["?view=join&t=..."]
  JP --> FJ["GET /family/join: verify HMAC, then family JWT, 1 h, mic only"]
  RSN["reasoning :8001"] -.->|"NO auth, bound to 127.0.0.1"| X["(none)"]
```

Notes: there is one shared API key and no per-user authorization. Any caller with the key can read or write any `user_id`. `reasoning` has no authentication at all and relies on the loopback bind.

## 7. Data pipeline

```mermaid
flowchart LR
  MIC["Elder mic"] --> LKR["LiveKit"]
  LKR --> STT["Gnani Prisma STT<br/>(Sarvam Saaras only if the test switch is on)"]
  STT --> AG["agent.on_user_turn_completed<br/>family-in-room, media gate, endpoint hold"]
  AG --> TURN["reasoning /turn"]
  TURN --> SAFE["1. safety rules<br/>(emergency, distress)"]
  SAFE -->|none| LLM["2. ONE LLM understanding call<br/>(Sarvam-105B, hosted, non-Gnani)"]
  LLM -->|"timeout / low confidence"| RULES["3. rule parser fallback"]
  LLM --> DISP["_dispatch"]
  RULES --> DISP
  DISP -->|"propose, confirm"| CORE["core-api (SQL)"]
  DISP --> REPLY["fixed template or companion reply"]
  REPLY --> TTS["Gnani Timbre v3 TTS"]
  TTS --> SPK["Elder speaker"]
  SAFE -->|emergency| ALERT["core-api /distress -> Notification + Telegram"]
  CORE -->|"before_flush hook"| FE["FeedEvent"]
  FE -->|"WS push / REST poll"| DASHB["Family dashboard"]
  SCHED["scheduler tick"] --> CORE
  CORE --> Q["deliveries queue (reminder, medicine, check-in)"]
  Q -->|"/delivery/next"| TURN
  ALERT --> TGM["Telegram bot message + join button"]
```

## 8. External integrations

```mermaid
flowchart LR
  subgraph Arjun
    VA["voice-agent"]
    RS["reasoning"]
    CORE["core-api"]
    WEB["web"]
  end
  VA -->|"STT + TTS (GNANI_API_KEY)"| GN["Gnani Prisma / Timbre"]
  VA -.->|"test switch only"| SV1["Sarvam Saaras / Bulbul"]
  VA <--> LKS["LiveKit server"]
  CORE -->|"mint JWTs (LIVEKIT_API_SECRET)"| LKS
  RS -->|"chat completions (SARVAM_API_KEY / LLM_API_KEY)"| SV2["Sarvam-105B or other OpenAI-compatible LLM"]
  CORE -->|"sendMessage (bot token)"| TGA["Telegram Bot API"]
  CORE -->|"search.list (YOUTUBE_API_KEY)"| YT["YouTube Data API"]
  CORE -->|"GET user-configured URLs"| RSS["RSS / news feeds"]
  WEB -->|"iframe embed"| YTE["YouTube player"]
  TUN["Cloudflare quick tunnel<br/>scripts/dev-up.ps1 -Phone"] --> WEB
```
