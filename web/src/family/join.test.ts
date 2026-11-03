import { describe, expect, it } from "vitest";

import { joinProblem, joinTokenFrom, statusFromError } from "./join";

describe("family join link", () => {
  it("reads the signed token from the query string", () => {
    expect(joinTokenFrom("?view=join&t=12.345.abc")).toBe("12.345.abc");
  });

  it("has no token when the link is missing one", () => {
    expect(joinTokenFrom("?view=join")).toBe("");
    expect(joinTokenFrom("")).toBe("");
  });

  it("trims stray whitespace around the token", () => {
    expect(joinTokenFrom("?t=%20abc%20")).toBe("abc");
  });

  it("reads the HTTP status out of an api error", () => {
    expect(statusFromError(new Error("403: join link is invalid or expired"))).toBe(403);
    expect(statusFromError(new Error("boom"))).toBe(0);
    expect(statusFromError("not an error")).toBe(0);
  });

  it("explains an expired link and an absent elder in Marathi", () => {
    expect(joinProblem(403)).toContain("कालबुध्द");
    expect(joinProblem(409)).toBe("आई सध्या ॲपवर नाहीत");
    expect(joinProblem(503)).toContain("उपलब्ध नाही");
    expect(joinProblem(500)).toContain("पुन्हा प्रयत्न करा");
  });
});
