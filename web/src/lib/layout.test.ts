import { describe, expect, it } from "vitest";

import { LAPTOP_MIN, TABLET_MIN, layoutFor } from "./layout";

describe("layoutFor", () => {
  it("phone below 768", () => {
    expect(layoutFor(320)).toBe("phone");
    expect(layoutFor(390)).toBe("phone");
    expect(layoutFor(TABLET_MIN - 1)).toBe("phone");
  });
  it("tablet from 768 to 1023", () => {
    expect(layoutFor(TABLET_MIN)).toBe("tablet");
    expect(layoutFor(LAPTOP_MIN - 1)).toBe("tablet");
  });
  it("laptop from 1024", () => {
    expect(layoutFor(LAPTOP_MIN)).toBe("laptop");
    expect(layoutFor(1440)).toBe("laptop");
  });
});
