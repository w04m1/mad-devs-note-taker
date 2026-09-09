import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const proxyTarget = process.env.VITE_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": { target: proxyTarget, changeOrigin: true },
      "/ws": { target: proxyTarget, ws: true },
    },
  },
  test: { environment: "jsdom", setupFiles: "./src/test/setup.ts" },
});
