/**
 * Tunnel access lock for the Vite dev server (the only thing a Cloudflare quick tunnel exposes).
 *
 * The /core proxy adds the CORE_API_KEY, so without a lock anyone who learns the tunnel URL holds the whole API.
 * Rules:
 *   - A request from THIS laptop (loopback socket, a localhost Host header, no tunnel/proxy headers) is trusted.
 *   - Anything else needs an HttpOnly cookie. The cookie is handed out by /auth?k=<ARJUN_ACCESS_CODE> (or by opening
 *     the phone link `/?user=1&k=<code>`, which does the same and then removes `k` from the address bar).
 *   - The cookie carries a ROLE (elder | family). Each role may call only the core-api routes its page uses.
 *   - The signed Telegram join link stays public: GET /core/family/join and the page /?view=join (the token is
 *     checked by core-api). Nothing else is.
 *   - The API key is injected into the proxied request ONLY when the request passed this check. Otherwise core-api
 *     sees no key and answers 401 as well.
 *   - A key in a WebSocket URL (?key=) is refused outright.
 * No code configured (or shorter than 6 characters) = every remote request is refused.
 */

import { createHash, createHmac, timingSafeEqual } from "node:crypto";
import type { IncomingMessage, ServerResponse } from "node:http";

export type Role = "elder" | "family";

export const COOKIE_NAME = "arjun_access";
export const COOKIE_MAX_AGE_S = 12 * 60 * 60;
export const MIN_CODE_LENGTH = 6;
export const BAD_LINK_TEXT = "हा दुवा चालत नाही. घरच्यांना नवीन दुवा मागा.";

const ID = "\\d+";
interface Route {
  method: string;
  path: RegExp;
}
const route = (method: string, path: string): Route => ({ method, path: new RegExp(`^${path}$`) });

/** What the elder page calls (web/src/elder/*, voice/*): read her day, answer a dose, ack a delivery, join voice. */
export const ELDER_ROUTES: Route[] = [
  route("GET", `/users/${ID}/(?:deliveries/open|day|reminders|appointments/next|contacts|medicines/due)`),
  route("POST", `/users/${ID}/medicine-doses/${ID}/(?:taken|snooze)`),
  route("POST", `/users/${ID}/deliveries/${ID}/ack`),
  route("POST", "/livekit/token"),
];

/** What the family dashboard calls (web/src/family/*, api.ts) including the live feed REST fallback and WebSocket. */
export const FAMILY_ROUTES: Route[] = [
  route("POST", "/users"),
  route("GET", `/users/${ID}`),
  route("PATCH", `/users/${ID}`),
  route("GET", `/users/${ID}/(?:reminders|appointments|contacts|app-links|medicines)`),
  route("POST", `/users/${ID}/(?:reminders|appointments|contacts|app-links|medicines)`),
  route("DELETE", `/users/${ID}/(?:reminders|app-links|medicines)/${ID}`),
  route("PATCH", `/users/${ID}/medicines/${ID}`),
  route("GET", `/users/${ID}/appointments/next`),
  route("GET", "/media/status"),
  route(
    "GET",
    `/users/${ID}/(?:memory-book|caregiver-requests|notifications|activity|wellbeing/today|bp-readings|watch-samples/latest|medicine-doses|checkins/card|deliveries|feed)`,
  ),
  route("GET", `/ws/users/${ID}/feed`),
];

/** Public on purpose: the join token is signed and checked by core-api. */
export const PUBLIC_ROUTES: Route[] = [route("GET", "/family/join")];

export const routeAllowed = (routes: Route[], method: string, path: string): boolean =>
  routes.some((r) => r.method === method.toUpperCase() && r.path.test(path));

// ---- cookie ---------------------------------------------------------------------------------------------------

const b64url = (buf: Buffer): string => buf.toString("base64url");

export function accessSecret(code: string, apiKey: string): Buffer {
  return createHash("sha256").update(`arjun-access-v1|${code}|${apiKey}`).digest();
}

export function signCookie(role: Role, expiresAtS: number, secret: Buffer): string {
  const payload = `${role}.${expiresAtS}`;
  return `${payload}.${b64url(createHmac("sha256", secret).update(payload).digest())}`;
}

export function verifyCookie(value: string | undefined, secret: Buffer, nowS: number): Role | null {
  const parts = (value ?? "").split(".");
  if (parts.length !== 3) return null;
  const [role, exp, sig] = parts as [string, string, string];
  if ((role !== "elder" && role !== "family") || !/^\d+$/.test(exp)) return null;
  const want = Buffer.from(b64url(createHmac("sha256", secret).update(`${role}.${exp}`).digest()));
  const got = Buffer.from(sig);
  if (want.length !== got.length || !timingSafeEqual(want, got)) return null;
  return Number(exp) > nowS ? role : null;
}

export function parseCookies(header: string | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  for (const piece of (header ?? "").split(";")) {
    const i = piece.indexOf("=");
    if (i > 0) out[piece.slice(0, i).trim()] = piece.slice(i + 1).trim();
  }
  return out;
}

function sameText(a: string, b: string): boolean {
  const ha = createHash("sha256").update(a).digest();
  const hb = createHash("sha256").update(b).digest();
  return timingSafeEqual(ha, hb);
}

// ---- who is asking --------------------------------------------------------------------------------------------

type Headers = IncomingMessage["headers"];
const header = (h: Headers, name: string): string => {
  const v = h[name];
  return (Array.isArray(v) ? v[0] : v) ?? "";
};

const LOOPBACK = new Set(["127.0.0.1", "::1", "::ffff:127.0.0.1"]);
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);
const PROXY_HEADERS = ["cf-connecting-ip", "cf-ray", "cf-visitor", "x-forwarded-for", "x-forwarded-host", "forwarded"];

/** True only for a browser on this laptop. The tunnel agent connects from loopback too, but it adds proxy headers and
 * keeps the public Host, so loopback alone is not enough. */
export function isLocalRequest(req: Pick<IncomingMessage, "socket" | "headers">): boolean {
  if (!LOOPBACK.has(req.socket?.remoteAddress ?? "")) return false;
  if (PROXY_HEADERS.some((name) => header(req.headers, name) !== "")) return false;
  const host = header(req.headers, "host").toLowerCase().replace(/:\d+$/, "");
  return LOCAL_HOSTS.has(host);
}

const isHttps = (h: Headers): boolean =>
  header(h, "x-forwarded-proto").includes("https") || header(h, "cf-visitor").includes("https");

// ---- the gate -------------------------------------------------------------------------------------------------

export interface AccessOptions {
  /** ARJUN_ACCESS_CODE */
  code: string;
  /** CORE_API_KEY, injected into allowed proxied requests */
  apiKey: string;
  /** seconds since epoch (tests) */
  now?: () => number;
}

export type Verdict =
  | { ok: true; role: Role | "local" | "public" }
  | { ok: false; status: number; detail: string };

/** `/core/users/1/day?x=1` or the already-rewritten `/users/1/day?x=1` -> path + query. */
export function corePath(url: string): { path: string; query: URLSearchParams } {
  const u = new URL(url, "http://local");
  const path = u.pathname.startsWith("/core/") ? u.pathname.slice("/core".length) : u.pathname;
  return { path, query: u.searchParams };
}

export function createAccess(opts: AccessOptions) {
  const nowS = opts.now ?? (() => Math.floor(Date.now() / 1000));
  const enabled = opts.code.length >= MIN_CODE_LENGTH;
  const secret = accessSecret(opts.code, opts.apiKey);
  const failures: number[] = []; // times of recent wrong codes (a brute-force brake)

  const roleOf = (h: Headers): Role | null =>
    enabled ? verifyCookie(parseCookies(header(h, "cookie"))[COOKIE_NAME], secret, nowS()) : null;

  const tooManyFailures = (): boolean => {
    const cutoff = nowS() - 60;
    while (failures.length && (failures[0] ?? 0) <= cutoff) failures.shift();
    return failures.length >= 10;
  };

  const codeIsRight = (given: string | null): boolean => {
    if (!enabled || !given) return false;
    const ok = sameText(given, opts.code);
    if (!ok) failures.push(nowS());
    return ok;
  };

  /** Decide a request for the /core proxy (HTTP or WebSocket upgrade). */
  function decideCore(req: Pick<IncomingMessage, "socket" | "headers" | "method" | "url">): Verdict {
    const { path, query } = corePath(req.url ?? "/");
    const method = (req.method ?? "GET").toUpperCase();
    if (path.startsWith("/ws/") && query.has("key")) {
      return { ok: false, status: 400, detail: "the API key must not be sent in the URL" };
    }
    if (routeAllowed(PUBLIC_ROUTES, method, path)) return { ok: true, role: "public" };
    if (isLocalRequest(req)) return { ok: true, role: "local" };
    const role = roleOf(req.headers);
    if (role === null) return { ok: false, status: 401, detail: "access link required" };
    const routes = role === "elder" ? ELDER_ROUTES : FAMILY_ROUTES;
    if (!routeAllowed(routes, method, path)) return { ok: false, status: 403, detail: "not allowed for this link" };
    return { ok: true, role };
  }

  function setCookieHeader(role: Role, h: Headers): string {
    const value = signCookie(role, nowS() + COOKIE_MAX_AGE_S, secret);
    const secure = isHttps(h) ? "; Secure" : "";
    return `${COOKIE_NAME}=${value}; HttpOnly; SameSite=Lax; Path=/; Max-Age=${COOKIE_MAX_AGE_S}${secure}`;
  }

  const badLinkPage = (res: ServerResponse, status: number): void => {
    res.statusCode = status;
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    res.setHeader("Cache-Control", "no-store");
    res.end(
      `<!doctype html><html lang="mr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">` +
        `<title>Arjun</title></head><body style="font-family:sans-serif;font-size:28px;line-height:1.5;padding:32px;background:#FBF1DE;color:#2b2118">` +
        `<p>${BAD_LINK_TEXT}</p></body></html>`,
    );
  };

  const denyJson = (res: ServerResponse, status: number, detail: string): void => {
    res.statusCode = status;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ detail }));
  };

  /** Redirect target: same-site path only (no open redirect), `k` removed. */
  const cleanTarget = (to: string, drop: string[]): string => {
    if (!to.startsWith("/") || to.startsWith("//")) return "/";
    const u = new URL(to, "http://local");
    for (const name of drop) u.searchParams.delete(name);
    return u.pathname + (u.search || "");
  };

  /** Shared by /auth and by the phone link: check the code, set the cookie, send her to the clean URL. */
  function authenticate(req: IncomingMessage, res: ServerResponse, code: string | null, role: Role, to: string): void {
    if (tooManyFailures()) return badLinkPage(res, 429);
    if (!codeIsRight(code)) return badLinkPage(res, 403);
    res.statusCode = 302;
    res.setHeader("Set-Cookie", setCookieHeader(role, req.headers));
    res.setHeader("Location", cleanTarget(to, ["k"]));
    res.setHeader("Cache-Control", "no-store");
    res.end();
  }

  /** Connect middleware: runs before Vite's own proxy and static handling. */
  function middleware(req: IncomingMessage, res: ServerResponse, next: () => void): void {
    const url = req.url ?? "/";
    const u = new URL(url, "http://local");

    if (u.pathname === "/auth") {
      const role: Role = u.searchParams.get("view") === "family" ? "family" : "elder";
      return authenticate(req, res, u.searchParams.get("k"), role, u.searchParams.get("to") ?? "/");
    }

    if (u.pathname.startsWith("/core/")) {
      const v = decideCore(req);
      if (!v.ok) return denyJson(res, v.status, v.detail);
      return next();
    }

    if (u.pathname === "/" || u.pathname === "/index.html") {
      const view = u.searchParams.get("view");
      if (view === "join") return next(); // the signed Telegram link: core-api checks the token
      if (u.searchParams.has("k")) {
        // the phone link: /?user=1&k=<code> (elder) or /?view=family&user=1&k=<code> (family)
        const role: Role = view === "family" ? "family" : "elder";
        return authenticate(req, res, u.searchParams.get("k"), role, u.pathname + u.search);
      }
      if (isLocalRequest(req) || roleOf(req.headers) !== null) return next();
      return badLinkPage(res, 401);
    }
    return next();
  }

  /** http-proxy `proxyReq`: add the API key only to a request that passes, and never forward the cookie. */
  function onProxyReq(proxyReq: { setHeader(n: string, v: string): void; removeHeader(n: string): void }, req: IncomingMessage): void {
    proxyReq.removeHeader("cookie");
    proxyReq.removeHeader("x-api-key"); // whatever the browser sent is not ours
    if (decideCore(req).ok && opts.apiKey) proxyReq.setHeader("X-API-Key", opts.apiKey);
  }

  /** http-proxy `proxyReqWs`: the WebSocket upgrade never passes through the connect middleware, so check here. */
  function onProxyReqWs(
    proxyReq: { setHeader(n: string, v: string): void; removeHeader(n: string): void; destroy(): void },
    req: IncomingMessage,
    socket: { write(s: string): unknown; destroy(): void },
  ): void {
    const v = decideCore(req);
    if (!v.ok) {
      try {
        socket.write(`HTTP/1.1 ${v.status} ${v.status === 401 ? "Unauthorized" : "Forbidden"}\r\nConnection: close\r\n\r\n`);
      } finally {
        socket.destroy();
        proxyReq.destroy();
      }
      return;
    }
    onProxyReq(proxyReq, req);
  }

  return { enabled, decideCore, middleware, onProxyReq, onProxyReqWs, roleOf, setCookieHeader };
}
