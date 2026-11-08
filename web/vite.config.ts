import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { createAccess } from "./server/access";

// The API key is injected by the dev proxy so it never ships in the browser bundle. Through a tunnel it is injected
// ONLY for a request that carries a valid access cookie (see server/access.ts); this laptop is always trusted.
const coreTarget = process.env.CORE_API_URL ?? "http://127.0.0.1:8000";
const apiKey = process.env.CORE_API_KEY ?? "";
const access = createAccess({ code: (process.env.ARJUN_ACCESS_CODE ?? "").trim(), apiKey });

export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  plugins: [
    react(),
    {
      name: "arjun-access-lock",
      // Registered before Vite's own middlewares, so it sees every request first.
      configureServer(server) {
        server.middlewares.use(access.middleware);
      },
    },
  ],
  server: {
    allowedHosts: [".trycloudflare.com", ".ts.net"],
    proxy: {
      "/core": {
        target: coreTarget,
        changeOrigin: true,
        ws: true, // the family feed WebSocket (/core/ws/...): checked again in proxyReqWs
        rewrite: (p) => p.replace(/^\/core/, ""),
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq, req) => access.onProxyReq(proxyReq, req));
          proxy.on("proxyReqWs", (proxyReq, req, socket) => access.onProxyReqWs(proxyReq, req, socket));
        },
      },
    },
  },
});
