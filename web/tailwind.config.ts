import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

// Every colour is a CSS variable from src/styles/ui-tokens.css (the single source). No hex in here.
// Tailwind's own `/60` opacity suffix does not work on var() colours: use the *-muted tokens instead.
const config: Config = {
  // Only the new UI layer is scanned, so no Tailwind utility can leak into the screens still on ghar.css.
  content: ["./src/components/**/*.{ts,tsx}", "./src/preview/**/*.{ts,tsx}", "./src/screens/**/*.{ts,tsx}", "./src/elder/RecorderBar.tsx"],
  // Preflight (Tailwind's global reset) is off until the old ghar.css screens are retired; `.ui-root` carries a
  // scoped reset instead (see ui-tokens.css).
  corePlugins: { preflight: false },
  theme: {
    // phone < 768, tablet 768-1023, laptop >= 1024
    screens: { md: "768px", lg: "1024px" },
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        muted: { DEFAULT: "var(--muted)", foreground: "var(--muted-foreground)" },
        card: { DEFAULT: "var(--card)", foreground: "var(--card-foreground)" },
        popover: { DEFAULT: "var(--popover)", foreground: "var(--popover-foreground)" },
        primary: { DEFAULT: "var(--primary)", foreground: "var(--primary-foreground)" },
        secondary: { DEFAULT: "var(--secondary)", foreground: "var(--secondary-foreground)" },
        accent: { DEFAULT: "var(--accent)", foreground: "var(--accent-foreground)" },
        border: "var(--border)",
        input: "var(--input)",
        ring: "var(--ring)",
        emergency: { DEFAULT: "var(--emergency)", foreground: "var(--emergency-foreground)" },
      },
      borderRadius: { lg: "var(--radius)", md: "calc(var(--radius) - 4px)", sm: "calc(var(--radius) - 8px)" },
      fontFamily: { sans: ["var(--font-ui)"] },
      minHeight: { touch: "var(--touch-min)" },
      minWidth: { touch: "var(--touch-min)" },
      boxShadow: { card: "var(--shadow-card)", glow: "var(--shadow-orb-glow)" },
    },
  },
  plugins: [animate],
};

export default config;
