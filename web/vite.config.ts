import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API key is injected by the dev proxy so it never ships in the browser bundle.
const coreTarget = process.env.CORE_API_URL ?? "http://127.0.0.1:8000";
const apiKey = process.env.CORE_API_KEY ?? "";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/core": {
        target: coreTarget,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/core/, ""),
        headers: apiKey ? { "X-API-Key": apiKey } : {},
      },
    },
  },
});
