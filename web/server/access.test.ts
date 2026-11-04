import type { IncomingMessage, ServerResponse } from "node:http";
import { describe, expect, it, vi } from "vitest";
import {
  BAD_LINK_TEXT,
  COOKIE_MAX_AGE_S,
  COOKIE_NAME,
  accessSecret,
  createAccess,
  isLocalRequest,
  signCookie,
  verifyCookie,
} from "./access";

const CODE = "kesar-4821";
const KEY = "test-core-key";
const NOW = 1_800_000_000;

const access = () => createAccess({ code: CODE, apiKey: KEY, now: () => NOW });

interface Opts {
  method?: string;
  url: string;
  cookie?: string;
  remote?: string;
  host?: string;
  extra?: Record<string, string>;
}
/** A request as the tunnel delivers it: loopback socket, the public Host, and Cloudflare's headers. */
const viaTunnel = (o: Opts): IncomingMessage =>
  ({
    method: o.method ?? "GET",
    url: o.url,
    socket: { remoteAddress: o.remote ?? "127.0.0.1" },
    headers: {
      host: o.host ?? "quiet-lake-1234.trycloudflare.com",
      "cf-connecting-ip": "203.0.113.9",
      "x-forwarded-proto": "https",
      ...(o.cookie ? { cookie: o.cookie } : {}),
      ...(o.extra ?? {}),
    },
  }) as unknown as IncomingMessage;

/** The laptop's own browser. */
const onLaptop = (o: Opts): IncomingMessage =>
  ({
    method: o.method ?? "GET",
    url: o.url,
    socket: { remoteAddress: "127.0.0.1" },
    headers: { host: "localhost:5173", ...(o.cookie ? { cookie: o.cookie } : {}) },
  }) as unknown as IncomingMessage;

function fakeRes() {
  const headers: Record<string, string> = {};
  const res = {
    statusCode: 200,
    body: "",
    headers,
    setHeader(n: string, v: string) {
      headers[n.toLowerCase()] = v;
    },
    end(b?: string) {
      res.body = b ?? "";
    },
  };
  return res;
}

function run(a: ReturnType<typeof access>, req: IncomingMessage) {
  const res = fakeRes();
  const next = vi.fn();
  a.middleware(req, res as unknown as ServerResponse, next);
  return { res, next };
}

const cookieFor = (role: "elder" | "family", exp = NOW + 3600) =>
  `${COOKIE_NAME}=${signCookie(role, exp, accessSecret(CODE, KEY))}`;

describe("the /core proxy", () => {
  it("rejects a tunnel request without the cookie (401) and adds no API key", () => {
    const a = access();
    const req = viaTunnel({ url: "/core/users/1/notifications" });
    const { res, next } = run(a, req);
    expect(res.statusCode).toBe(401);
    expect(next).not.toHaveBeenCalled();
    const proxyReq = { setHeader: vi.fn(), removeHeader: vi.fn() };
    a.onProxyReq(proxyReq, req);
    expect(proxyReq.setHeader).not.toHaveBeenCalled(); // core-api would answer 401 as well
  });

  it("allows a request with a valid cookie, injects the key and does not forward the cookie", () => {
    const a = access();
    const req = viaTunnel({ url: "/core/users/1/notifications", cookie: cookieFor("family") });
    const { next, res } = run(a, req);
    expect(next).toHaveBeenCalledOnce();
    expect(res.statusCode).toBe(200);
    const proxyReq = { setHeader: vi.fn(), removeHeader: vi.fn() };
    a.onProxyReq(proxyReq, req);
    expect(proxyReq.setHeader).toHaveBeenCalledWith("X-API-Key", KEY);
    expect(proxyReq.removeHeader).toHaveBeenCalledWith("cookie");
  });

  it("rejects a tampered, expired or foreign cookie", () => {
    const a = access();
    const good = cookieFor("family");
    for (const cookie of [
      good.slice(0, -2) + "xx",
      cookieFor("family", NOW - 1),
      `${COOKIE_NAME}=${signCookie("family", NOW + 99, accessSecret("another-code", KEY))}`,
      `${COOKIE_NAME}=family.${NOW + 99}.`,
    ]) {
      expect(run(a, viaTunnel({ url: "/core/users/1/notifications", cookie })).res.statusCode).toBe(401);
    }
  });

  it("an elder cookie may call the elder routes", () => {
    const a = access();
    const cookie = cookieFor("elder");
    for (const [method, url] of [
      ["GET", "/core/users/1/day"],
      ["GET", "/core/users/1/deliveries/open"],
      ["GET", "/core/users/1/reminders"],
      ["GET", "/core/users/1/appointments/next"],
      ["GET", "/core/users/1/contacts"],
      ["GET", "/core/users/1/medicines/due"],
      ["POST", "/core/users/1/medicine-doses/7/taken"],
      ["POST", "/core/users/1/medicine-doses/7/snooze"],
      ["POST", "/core/users/1/deliveries/3/ack"],
      ["POST", "/core/livekit/token"],
    ] as const) {
      expect(run(a, viaTunnel({ method, url, cookie })).next, `${method} ${url}`).toHaveBeenCalledOnce();
    }
  });

  it("an elder cookie is blocked (403) from the family-only routes", () => {
    const a = access();
    const cookie = cookieFor("elder");
    for (const [method, url] of [
      ["GET", "/core/users/1/memory-book"],
      ["GET", "/core/users/1/notifications"],
      ["GET", "/core/users/1/medicines"],
      ["POST", "/core/users/1/medicines"],
      ["DELETE", "/core/users/1/medicines/2"],
      ["PATCH", "/core/users/1"],
      ["POST", "/core/users"],
      ["GET", "/core/users/1/feed"],
      ["GET", "/core/users/1/facts"],
      ["POST", "/core/users/1/facts/forget"],
      ["GET", "/core/ws/users/1/feed"],
      ["POST", "/core/users/1/distress"],
      ["POST", "/core/internal/reminders/fire-due"],
    ] as const) {
      const { res, next } = run(a, viaTunnel({ method, url, cookie }));
      expect(res.statusCode, `${method} ${url}`).toBe(403);
      expect(next).not.toHaveBeenCalled();
    }
  });

  it("a family cookie may call the dashboard routes but not the elder-only ones or internals", () => {
    const a = access();
    const cookie = cookieFor("family");
    for (const [method, url] of [
      ["GET", "/core/users/1"],
      ["PATCH", "/core/users/1"],
      ["POST", "/core/users/1/medicines"],
      ["PATCH", "/core/users/1/medicines/2"],
      ["GET", "/core/users/1/feed?after=4"],
      ["GET", "/core/ws/users/1/feed?after=4"],
      ["GET", "/core/users/1/wellbeing/today"],
      ["GET", "/core/users/1/facts?audience=family"],
      ["DELETE", "/core/users/1/facts/3"],
    ] as const) {
      expect(run(a, viaTunnel({ method, url, cookie })).next, `${method} ${url}`).toHaveBeenCalledOnce();
    }
    for (const [method, url] of [
      ["POST", "/core/livekit/token"],
      ["POST", "/core/users/1/medicine-doses/7/taken"],
      ["POST", "/core/internal/medicines/tick"],
      ["POST", "/core/users/1/actions/propose"],
      ["GET", "/core/users/1/stories/latest"],
    ] as const) {
      expect(run(a, viaTunnel({ method, url, cookie })).res.statusCode, `${method} ${url}`).toBe(403);
    }
  });

  it("the signed family join link works without a cookie, and nothing else does", () => {
    const a = access();
    expect(run(a, viaTunnel({ url: "/core/family/join?t=1.99.sig" })).next).toHaveBeenCalledOnce();
    expect(run(a, viaTunnel({ url: "/core/livekit/token", method: "POST" })).res.statusCode).toBe(401);
    expect(run(a, viaTunnel({ url: "/core/users/1" })).res.statusCode).toBe(401);
    const page = run(a, viaTunnel({ url: "/?view=join&t=1.99.sig" }));
    expect(page.next).toHaveBeenCalledOnce();
  });

  it("this laptop is allowed without a cookie, and gets the key", () => {
    const a = access();
    const req = onLaptop({ url: "/core/users/1/memory-book" });
    expect(isLocalRequest(req)).toBe(true);
    expect(run(a, req).next).toHaveBeenCalledOnce();
    const proxyReq = { setHeader: vi.fn(), removeHeader: vi.fn() };
    a.onProxyReq(proxyReq, req);
    expect(proxyReq.setHeader).toHaveBeenCalledWith("X-API-Key", KEY);
  });

  it("tunnel traffic that reaches us from loopback is NOT mistaken for the laptop", () => {
    expect(isLocalRequest(viaTunnel({ url: "/" }))).toBe(false);
    expect(isLocalRequest(viaTunnel({ url: "/", host: "localhost:5173" }))).toBe(false); // cf-* headers present
    expect(isLocalRequest(viaTunnel({ url: "/", remote: "192.168.1.20", extra: { "cf-connecting-ip": "" } }))).toBe(false);
    const lan = { ...onLaptop({ url: "/" }), socket: { remoteAddress: "192.168.1.20" } } as unknown as IncomingMessage;
    expect(isLocalRequest(lan)).toBe(false); // another device on the Wi-Fi
  });
});

describe("the WebSocket", () => {
  it("rejects a key in the URL, even from the laptop and even with a valid cookie", () => {
    const a = access();
    for (const req of [
      onLaptop({ url: "/core/ws/users/1/feed?after=0&key=anything" }),
      viaTunnel({ url: "/core/ws/users/1/feed?key=" + KEY, cookie: cookieFor("family") }),
    ]) {
      const v = a.decideCore(req as IncomingMessage);
      expect(v).toMatchObject({ ok: false, status: 400 });
      expect(run(a, req).res.statusCode).toBe(400);
    }
  });

  it("the upgrade itself is refused without the cookie and passes with the family cookie", () => {
    const a = access();
    // after Vite's rewrite the url no longer starts with /core: both forms must be understood
    const denied = viaTunnel({ url: "/ws/users/1/feed?after=0" });
    const socket = { write: vi.fn(), destroy: vi.fn() };
    const proxyReq = { setHeader: vi.fn(), removeHeader: vi.fn(), destroy: vi.fn() };
    a.onProxyReqWs(proxyReq, denied, socket);
    expect(socket.write).toHaveBeenCalledWith(expect.stringContaining("401"));
    expect(socket.destroy).toHaveBeenCalled();
    expect(proxyReq.setHeader).not.toHaveBeenCalled();

    const okReq = viaTunnel({ url: "/ws/users/1/feed?after=0", cookie: cookieFor("family") });
    const socket2 = { write: vi.fn(), destroy: vi.fn() };
    const proxyReq2 = { setHeader: vi.fn(), removeHeader: vi.fn(), destroy: vi.fn() };
    a.onProxyReqWs(proxyReq2, okReq, socket2);
    expect(socket2.destroy).not.toHaveBeenCalled();
    expect(proxyReq2.setHeader).toHaveBeenCalledWith("X-API-Key", KEY);

    const elder = viaTunnel({ url: "/ws/users/1/feed", cookie: cookieFor("elder") });
    const socket3 = { write: vi.fn(), destroy: vi.fn() };
    a.onProxyReqWs({ setHeader: vi.fn(), removeHeader: vi.fn(), destroy: vi.fn() }, elder, socket3);
    expect(socket3.write).toHaveBeenCalledWith(expect.stringContaining("403"));
  });
});

describe("the access link", () => {
  it("/?user=1&k=<code> sets an HttpOnly elder cookie and removes k from the address", () => {
    const a = access();
    const { res } = run(a, viaTunnel({ url: `/?user=1&k=${CODE}` }));
    expect(res.statusCode).toBe(302);
    expect(res.headers["location"]).toBe("/?user=1");
    const set = res.headers["set-cookie"] ?? "";
    expect(set).toContain(`${COOKIE_NAME}=elder.`);
    expect(set).toContain("HttpOnly");
    expect(set).toContain("SameSite=Lax");
    expect(set).toContain(`Max-Age=${COOKIE_MAX_AGE_S}`);
    expect(COOKIE_MAX_AGE_S).toBe(12 * 3600);
    expect(set).toContain("Secure"); // https through the tunnel
    expect(set).not.toContain(CODE);
  });

  it("/?view=family&user=1&k=<code> sets a family cookie", () => {
    const { res } = run(access(), viaTunnel({ url: `/?view=family&user=1&k=${CODE}` }));
    expect(res.headers["set-cookie"]).toContain(`${COOKIE_NAME}=family.`);
    expect(res.headers["location"]).toBe("/?view=family&user=1");
  });

  it("/auth?k= does the same and never redirects off-site", () => {
    const a = access();
    const ok = run(a, viaTunnel({ url: `/auth?k=${CODE}&view=family&to=/%3Fview%3Dfamily%26user%3D1` }));
    expect(ok.res.statusCode).toBe(302);
    expect(ok.res.headers["location"]).toBe("/?view=family&user=1");
    const evil = run(a, viaTunnel({ url: `/auth?k=${CODE}&to=//evil.example/x` }));
    expect(evil.res.headers["location"]).toBe("/");
    const evil2 = run(a, viaTunnel({ url: `/auth?k=${CODE}&to=https://evil.example/` }));
    expect(evil2.res.headers["location"]).toBe("/");
  });

  it("a wrong or missing code shows the Marathi page and sets no cookie", () => {
    const a = access();
    for (const url of ["/?user=1&k=wrong-code", "/auth?k=nope", "/auth", "/?user=1&k="]) {
      const { res, next } = run(a, viaTunnel({ url }));
      expect(res.statusCode, url).toBe(403);
      expect(res.body).toContain(BAD_LINK_TEXT);
      expect(res.headers["set-cookie"]).toBeUndefined();
      expect(next).not.toHaveBeenCalled();
    }
    const bare = run(a, viaTunnel({ url: "/?user=1" }));
    expect(bare.res.statusCode).toBe(401);
    expect(bare.res.body).toContain("हा दुवा चालत नाही. घरच्यांना नवीन दुवा मागा.");
  });

  it("the page opens with a cookie or on the laptop, and static assets are not gated", () => {
    const a = access();
    expect(run(a, viaTunnel({ url: "/?user=1", cookie: cookieFor("elder") })).next).toHaveBeenCalledOnce();
    expect(run(a, onLaptop({ url: "/?user=1" })).next).toHaveBeenCalledOnce();
    expect(run(a, viaTunnel({ url: "/src/main.tsx" })).next).toHaveBeenCalledOnce();
  });

  it("ten wrong codes in a minute lock the door for a while (429), even for the right code", () => {
    const a = access();
    for (let i = 0; i < 10; i++) run(a, viaTunnel({ url: `/?k=bad${i}` }));
    expect(run(a, viaTunnel({ url: `/?k=${CODE}` })).res.statusCode).toBe(429);
  });

  it("with no code (or a short one) configured, every remote request is refused", () => {
    for (const code of ["", "abc"]) {
      const a = createAccess({ code, apiKey: KEY, now: () => NOW });
      expect(a.enabled).toBe(false);
      expect(run(a, viaTunnel({ url: `/?k=${code}` })).res.statusCode).toBe(403);
      expect(run(a, viaTunnel({ url: "/core/users/1", cookie: `${COOKIE_NAME}=family.${NOW + 9}.x` })).res.statusCode).toBe(401);
      expect(run(a, onLaptop({ url: "/core/users/1" })).next).toHaveBeenCalledOnce(); // the laptop still works
    }
  });
});

describe("cookie format", () => {
  it("round-trips and checks the expiry", () => {
    const secret = accessSecret(CODE, KEY);
    const value = signCookie("elder", NOW + 10, secret);
    expect(verifyCookie(value, secret, NOW)).toBe("elder");
    expect(verifyCookie(value, secret, NOW + 10)).toBeNull();
    expect(verifyCookie("elder.1.2", secret, NOW)).toBeNull();
    expect(verifyCookie(undefined, secret, NOW)).toBeNull();
  });
});
