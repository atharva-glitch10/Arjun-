import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { ORB_STATES } from "@/components/orbState";
import tailwind from "../../tailwind.config";

const here = (...p: string[]) => join(__dirname, ...p);
const tokensCss = readFileSync(here("ui-tokens.css"), "utf8");
const uiCss = readFileSync(here("ui.css"), "utf8");

/** Value of a custom property declared in :root, following one level of var(--other). */
function token(name: string): string {
  const m = new RegExp(`--${name}:\\s*([^;]+);`).exec(tokensCss);
  if (!m?.[1]) throw new Error(`token --${name} is missing`);
  const v = m[1].trim();
  const ref = /^var\(--([a-z0-9-]+)\)$/.exec(v);
  return ref?.[1] ? token(ref[1]) : v;
}

function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => {
    const s = (c ?? 0) / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

describe("palette", () => {
  it("is the approved subtle palette", () => {
    expect(token("ui-white")).toBe("#ffffff");
    expect(token("ui-cream")).toBe("#fbf4e6");
    expect(token("ui-cream-border")).toBe("#f0e2c4");
    expect(token("ui-navy")).toBe("#1c2541");
    expect(token("ui-amber-light")).toBe("#f9c877");
    expect(token("ui-amber")).toBe("#f2a246");
    expect(token("ui-amber-deep")).toBe("#e98b35");
  });

  it("maps shadcn: primary = amber, card = cream, foreground = navy, background = white", () => {
    expect(token("primary")).toBe(token("ui-amber"));
    expect(token("card")).toBe(token("ui-cream"));
    expect(token("foreground")).toBe(token("ui-navy"));
    expect(token("background")).toBe(token("ui-white"));
    expect(token("border")).toBe(token("ui-cream-border"));
    expect(token("emergency")).toBe(token("ui-red"));
  });

  it("muted text is navy at about 70% (60% measured below AA on white)", () => {
    const navy = parseInt(token("ui-navy").slice(1), 16);
    const muted = parseInt(token("ui-navy-muted").slice(1), 16);
    for (const shift of [16, 8, 0]) {
      const n = (navy >> shift) & 255;
      const expected = Math.round(n * 0.7 + 255 * 0.3);
      expect(Math.abs(((muted >> shift) & 255) - expected)).toBeLessThanOrEqual(2);
    }
  });
});

describe("contrast (WCAG)", () => {
  const cases: Array<[string, string, string, number]> = [
    ["foreground", "background", "navy text on white", 4.5],
    ["card-foreground", "card", "navy text on cream", 4.5],
    ["primary-foreground", "primary", "navy text on amber", 4.5],
    ["muted-foreground", "background", "muted text on white", 4.5],
    ["muted-foreground", "card", "muted text on cream", 4.5],
    ["emergency-foreground", "emergency", "white text on emergency red", 4.5],
    ["input", "background", "field border on white (non-text, 3:1)", 3],
    ["ring", "background", "focus ring on white (non-text, 3:1)", 3],
  ];
  it.each(cases)("%s on %s: %s", (fg, bg, _what, min) => {
    expect(contrast(token(fg), token(bg))).toBeGreaterThanOrEqual(min);
  });
});

describe("tailwind theme", () => {
  const colors = (tailwind.theme?.extend?.colors ?? {}) as Record<string, unknown>;
  const flat = JSON.stringify(colors);

  it("reads colours only from CSS variables", () => {
    expect(flat).not.toMatch(/#[0-9a-f]{3,8}/i);
    for (const key of ["background", "foreground", "primary", "card", "border", "ring", "emergency"]) {
      expect(flat).toContain(`var(--${key})`);
    }
  });

  it("has phone < 768 / tablet / laptop >= 1024 breakpoints", () => {
    expect(tailwind.theme?.screens).toEqual({ md: "768px", lg: "1024px" });
  });

  it("every colour variable it references exists in ui-tokens.css", () => {
    for (const [, name] of flat.matchAll(/var\(--([a-z0-9-]+)\)/g)) {
      expect(tokensCss, `--${name}`).toMatch(new RegExp(`--${name}:`));
    }
  });
});

describe("single source: no hardcoded hex in components", () => {
  const roots = [here("..", "components"), here("..", "preview"), here("..", "..", "tailwind.config.ts")];
  const files: string[] = [];
  const walk = (p: string) => {
    if (statSync(p).isDirectory()) readdirSync(p).forEach((f) => walk(join(p, f)));
    else if (/\.(ts|tsx)$/.test(p) && !/\.test\./.test(p)) files.push(p);
  };
  roots.forEach(walk);

  it("scans real files", () => expect(files.length).toBeGreaterThan(10));
  it.each(files)("%s", (f) => {
    expect(readFileSync(f, "utf8")).not.toMatch(/#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b(?![\w-])/);
  });
});

describe("orb css", () => {
  it("styles every orb state", () => {
    for (const s of ORB_STATES.filter((x) => x !== "idle")) expect(uiCss).toContain(`.orb[data-state="${s}"]`);
    expect(uiCss).toContain('.orb[data-state="idle"]');
  });

  it("uses the amber gradient tokens", () => {
    expect(uiCss).toMatch(/radial-gradient\([^)]*var\(--orb-1\)[^)]*var\(--orb-2\)[^)]*var\(--orb-3\)/);
  });

  it("stops moving under prefers-reduced-motion and the family no-motion switch", () => {
    expect(uiCss).toMatch(/@media \(prefers-reduced-motion: reduce\)\s*{\s*\.orb\s*{\s*animation: none;/);
    expect(uiCss).toContain(".no-motion .orb");
  });

  it("scopes its reset instead of enabling Tailwind preflight", () => {
    expect(tailwind.corePlugins).toEqual({ preflight: false });
    expect(uiCss).toContain(":where(.ui-root *)");
  });
});

describe("elder type scale", () => {
  it("body >= 20px, headings >= 28px, touch targets >= 56px", () => {
    expect(parseInt(token("text-body"))).toBeGreaterThanOrEqual(20);
    expect(parseInt(token("text-heading"))).toBeGreaterThanOrEqual(28);
    expect(parseInt(token("touch-min"))).toBeGreaterThanOrEqual(56);
  });
});
