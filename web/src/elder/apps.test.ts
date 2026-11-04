import { describe, expect, it } from "vitest";
import { appLinks, isAndroid, isAppId } from "./apps";
import { planAction } from "./media";

describe("phone apps", () => {
  it("builds an intent for the app package and a web page, from its own table", () => {
    const l = appLinks("spotify", "लता मंगेशकर");
    expect(l.web).toBe(`https://open.spotify.com/search/${encodeURIComponent("लता मंगेशकर")}`);
    expect(l.intent).toMatch(/^intent:\/\/open\.spotify\.com\/search\/.+#Intent;scheme=https;package=com\.spotify\.music;end$/);
    expect(l.intent).not.toContain("browser_fallback_url");
  });
  it("knows only its own ids", () => {
    expect(isAppId("google_maps")).toBe(true);
    expect(isAppId("https://evil.example")).toBe(false);
  });
  it("plans an app action as one tap; an unknown id does nothing", () => {
    const plan = planAction({ turn: 2, type: "open", kind: "app", value: "jiosaavn", title: "जिओसावन", query: "भजन" }, [], "https://x.test");
    expect(plan.do).toBe("app");
    if (plan.do === "app") {
      expect(plan.web).toContain("jiosaavn.com/search/");
      expect(plan.title).toBe("जिओसावन");
    }
    expect(planAction({ turn: 3, type: "open", kind: "app", value: "evil" }, [], "https://x.test").do).toBe("none");
  });
  it("detects Android", () => {
    expect(isAndroid("Mozilla/5.0 (Linux; Android 14)")).toBe(true);
    expect(isAndroid("Mozilla/5.0 (Windows NT 10.0)")).toBe(false);
  });
});
