import { describe, expect, it } from "vitest";

import { AUTH_KEYS, AUTH_LANGS, at, authErrorKey } from "./authText";

describe("family auth screens: mr / hi / en", () => {
  it("every string exists in Marathi, Hindi and English", () => {
    for (const [lang] of AUTH_LANGS) {
      for (const key of AUTH_KEYS) expect(at(key, lang).trim().length, `${key}/${lang}`).toBeGreaterThan(0);
    }
  });

  it("Marathi and Hindi are really translated, not English copies", () => {
    for (const key of ["login", "create", "err_wrong", "err_many", "err_code", "logout", "signup_code"] as const) {
      expect(at(key, "mr")).not.toBe(at(key, "en"));
      expect(at(key, "hi")).not.toBe(at(key, "en"));
    }
  });

  it("a 429 says to wait a minute, in each language", () => {
    expect(at("err_many", "en")).toBe("Too many attempts, wait a minute.");
    expect(at("err_many", "mr")).toContain("एक मिनिट");
    expect(at("err_many", "hi")).toContain("एक मिनट");
  });

  it("maps each failed response to the right line", () => {
    expect(authErrorKey("429: invalid email or password", "login")).toBe("err_many"); // not "wrong password"
    expect(authErrorKey("401: invalid email or password", "login")).toBe("err_wrong");
    expect(authErrorKey("429: too many sign-up attempts", "signup")).toBe("err_many");
    expect(authErrorKey("403: sign-up code required", "signup")).toBe("err_code");
    expect(authErrorKey("403: sign-up is closed", "signup")).toBe("err_closed");
    expect(authErrorKey("409: email unavailable", "signup")).toBe("err_exists");
    expect(authErrorKey("422: ...", "signup")).toBe("err_check");
    expect(authErrorKey("Failed to fetch", "login")).toBe("err_net");
  });
});
