import { useEffect, useState } from "react";

/** phone < 768, tablet 768-1023, laptop >= 1024 (the same cut-offs as tailwind.config.ts `screens`). */
export type Layout = "phone" | "tablet" | "laptop";

export const TABLET_MIN = 768;
export const LAPTOP_MIN = 1024;

export function layoutFor(width: number): Layout {
  if (width >= LAPTOP_MIN) return "laptop";
  if (width >= TABLET_MIN) return "tablet";
  return "phone";
}

/** The current layout, updated when the window is resized or rotated. */
export function useLayout(): Layout {
  const [layout, setLayout] = useState<Layout>(() => layoutFor(window.innerWidth));
  useEffect(() => {
    const update = () => setLayout(layoutFor(window.innerWidth));
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);
  return layout;
}
