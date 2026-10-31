/** The family's live feed: WebSocket push first, REST polling as the fallback. Same rows, same ids either way.
 *
 *   WS   /core/ws/users/{id}/feed?after=N  -> {"type":"event", ...} as rows are committed, {"type":"ping"} when idle
 *   REST /core/users/{id}/feed?after=N     -> every row after N (used while the socket is down)
 *
 * The socket is retried with a growing wait; while it is down the feed is polled every few seconds, so the
 * family never silently stops getting updates. The decisions are pure (tested); `connectFeed` does the I/O.
 */

export type Severity = "info" | "normal" | "watch" | "urgent" | "emergency";

export interface FeedEvent {
  id: number;
  kind: string;
  severity: Severity;
  title: string;
  body: string;
  created_at: string;
}

export const SEVERITY_RANK: Record<Severity, number> = { info: 0, normal: 1, watch: 2, urgent: 3, emergency: 4 };

/** Plain words and colours for the family (same order as the backend). */
export const SEVERITY_LABEL: Record<Severity, string> = {
  info: "Info",
  normal: "All well",
  watch: "Keep an eye",
  urgent: "Call her soon",
  emergency: "Emergency",
};

export const SEVERITY_STYLE: Record<Severity, { bg: string; fg: string }> = {
  info: { bg: "var(--ghar-sand)", fg: "var(--ghar-ink)" },
  normal: { bg: "var(--ghar-leaf)", fg: "#fff" },
  watch: { bg: "var(--ghar-haldi-soft)", fg: "var(--ghar-ink)" },
  urgent: { bg: "var(--ghar-kumkum)", fg: "#fff" },
  emergency: { bg: "var(--ghar-kumkum)", fg: "#fff" },
};

const isSeverity = (s: unknown): s is Severity => typeof s === "string" && s in SEVERITY_RANK;

/** Add new rows: no duplicates (WS and polling may overlap), newest first, at most `cap`. */
export function mergeFeed(have: readonly FeedEvent[], incoming: readonly FeedEvent[], cap = 200): FeedEvent[] {
  const byId = new Map<number, FeedEvent>();
  for (const e of have) byId.set(e.id, e);
  for (const e of incoming) if (Number.isFinite(e.id) && isSeverity(e.severity)) byId.set(e.id, e);
  return [...byId.values()].sort((a, b) => b.id - a.id).slice(0, cap);
}

export const lastId = (rows: readonly FeedEvent[]): number => rows.reduce((m, e) => Math.max(m, e.id), 0);

/** Wait before the next WebSocket attempt: 1 s, 2 s, 5 s, 10 s, then 30 s. */
export function socketRetryDelay(attempt: number): number {
  const steps = [1_000, 2_000, 5_000, 10_000, 30_000];
  return steps[Math.min(Math.max(attempt, 0), steps.length - 1)] ?? 30_000;
}

/** Parse one socket message; anything unexpected is ignored, never thrown. */
export function parseMessage(raw: string): FeedEvent | "ping" | null {
  try {
    const m = JSON.parse(raw) as Record<string, unknown>;
    if (m.type === "ping") return "ping";
    if (m.type !== "event" || typeof m.id !== "number" || !isSeverity(m.severity)) return null;
    return {
      id: m.id,
      kind: String(m.kind ?? ""),
      severity: m.severity,
      title: String(m.title ?? ""),
      body: String(m.body ?? ""),
      created_at: String(m.created_at ?? ""),
    };
  } catch {
    return null;
  }
}

export type FeedStatus = "connecting" | "live" | "polling";

/** Open the feed. Returns a stop function. The dev proxy adds the API key to both the WS and the REST calls. */
export function connectFeed(opts: {
  userId: number;
  onEvents: (rows: FeedEvent[]) => void;
  onStatus: (s: FeedStatus) => void;
  pollMs?: number;
}): () => void {
  let stopped = false;
  let ws: WebSocket | null = null;
  let after = 0;
  let attempt = 0;
  let pollTimer: number | null = null;
  let retryTimer: number | null = null;

  const take = (rows: FeedEvent[]) => {
    if (rows.length === 0) return;
    after = Math.max(after, lastId(rows));
    opts.onEvents(rows);
  };

  const poll = async () => {
    try {
      const res = await fetch(`/core/users/${opts.userId}/feed?after=${after}`);
      if (res.ok) take(((await res.json()) as FeedEvent[]).filter((e) => isSeverity(e.severity)));
    } catch {
      // offline: the next poll tries again
    }
  };

  const startPolling = () => {
    if (pollTimer !== null || stopped) return;
    opts.onStatus("polling");
    void poll();
    pollTimer = window.setInterval(() => void poll(), opts.pollMs ?? 5_000);
  };
  const stopPolling = () => {
    if (pollTimer !== null) window.clearInterval(pollTimer);
    pollTimer = null;
  };

  const open = () => {
    if (stopped) return;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    try {
      ws = new WebSocket(`${proto}://${window.location.host}/core/ws/users/${opts.userId}/feed?after=${after}`);
    } catch {
      startPolling();
      retryTimer = window.setTimeout(open, socketRetryDelay(attempt++));
      return;
    }
    ws.onopen = () => {
      attempt = 0;
      stopPolling();
      opts.onStatus("live");
    };
    ws.onmessage = (ev) => {
      const m = parseMessage(String(ev.data));
      if (m && m !== "ping") take([m]);
    };
    ws.onclose = () => {
      ws = null;
      if (stopped) return;
      startPolling(); // never a gap: poll while the socket is down
      retryTimer = window.setTimeout(open, socketRetryDelay(attempt++));
    };
  };

  opts.onStatus("connecting");
  void poll().then(open); // first load over REST (fast, and works even if WS is blocked)
  return () => {
    stopped = true;
    stopPolling();
    if (retryTimer !== null) window.clearTimeout(retryTimer);
    ws?.close();
  };
}
