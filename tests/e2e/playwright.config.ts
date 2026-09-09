import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:15173";
export default defineConfig({
  testDir: "./specs",
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 8_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { outputFolder: "artifacts/report", open: "never" }]],
  outputDir: "artifacts/results",
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 8_000,
    navigationTimeout: 15_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
