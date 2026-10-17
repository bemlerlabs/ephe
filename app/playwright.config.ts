import { defineConfig, devices } from '@playwright/test'

/**
 * Ephe PWA — Playwright E2E config (PWA-Chat-UX-Plan, phase E1)
 *
 * Base: the Vite dev server on 127.0.0.1:5174 (it proxies /api/* → 8765).
 * Backend prerequisite: the ephe server on 127.0.0.1:8765 (live tests are
 * skipped when that backend is unreachable — the approval tests run
 * deterministically via network interception, without a backend).
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 120_000, // local model streaming turns can run past 30s
  expect: { timeout: 30_000 },
  fullyParallel: false, // keep the chat state (IndexedDB) isolated per browser profile
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5174',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npx vite --port 5174 --strictPort',
    url: 'http://127.0.0.1:5174',
    reuseExistingServer: true,
    timeout: 60_000,
  },
})
