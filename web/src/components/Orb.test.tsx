import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { orbLabel } from "@/elder/i18n";

import { Orb } from "./Orb";
import { ORB_STATES } from "./orbState";

describe("<Orb>", () => {
  it.each(ORB_STATES)("renders the %s state with its words for screen readers", (state) => {
    const html = renderToStaticMarkup(<Orb state={state} label={orbLabel("mr", state)} />);
    expect(html).toContain(`data-state="${state}"`);
    expect(html).toContain('role="img"');
    expect(html).toContain(`aria-label="${orbLabel("mr", state)}"`);
    expect(html).toContain('class="orb"');
  });

  it("sets its size through --orb-size", () => {
    const html = renderToStaticMarkup(<Orb state="idle" label="x" size="12rem" />);
    expect(html).toContain("--orb-size:12rem");
  });

  it("merges extra classes without dropping .orb", () => {
    const html = renderToStaticMarkup(<Orb state="idle" label="x" className="mx-auto" />);
    expect(html).toMatch(/class="orb mx-auto"/);
  });
});
