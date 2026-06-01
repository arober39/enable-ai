import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for Enable AI's UI smoke tests.
 *
 * Boots both the FastAPI backend (uvicorn on :8000) and the Next.js dev
 * server (next dev on :3000) before running the suite. Set
 * `reuseExistingServer: true` so iterating locally doesn't restart
 * servers between runs.
 *
 * Demo mode (`ENABLE_AI_DEMO_MODE=true`) is forced on the backend so the
 * smoke tests never hit a live LLM.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      // FastAPI backend. Run from repo root (../..) so uvicorn can import
      // `ui.api.server`. Demo mode is forced — the smoke tests never spend
      // money on LLM calls.
      command:
        "cd ../.. && .venv/bin/uvicorn ui.api.server:app --port 8000",
      port: 8000,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
      env: {
        ENABLE_AI_DEMO_MODE: "true",
      },
    },
    {
      command: "npm run dev",
      port: 3000,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
