import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

const proxyTarget = process.env.VITE_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  server: {
    proxy: {
      "/api": { target: proxyTarget, changeOrigin: true },
      "/ws": { target: proxyTarget, ws: true },
    },
  },
  build: {
    rolldownOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("/node_modules/")) return;
          if (id.includes("/node_modules/@fullcalendar/")) return "calendar";
          if (
            id.includes("/node_modules/react/") ||
            id.includes("/node_modules/react-dom/") ||
            id.includes("/node_modules/react-router/") ||
            id.includes("/node_modules/react-router-dom/") ||
            id.includes("/node_modules/scheduler/") ||
            id.includes("/node_modules/@tanstack/")
          )
            return "framework";
          if (
            id.includes("/node_modules/react-hook-form/") ||
            id.includes("/node_modules/@hookform/") ||
            id.includes("/node_modules/zod/")
          )
            return "forms";
          if (
            id.includes("/node_modules/@radix-ui/") ||
            id.includes("/node_modules/lucide-react/") ||
            id.includes("/node_modules/class-variance-authority/") ||
            id.includes("/node_modules/clsx/") ||
            id.includes("/node_modules/tailwind-merge/")
          )
            return "ui";
          if (id.includes("/node_modules/luxon/")) return "dates";
        },
      },
    },
  },
  test: { environment: "jsdom", setupFiles: "./src/test/setup.ts" },
});
