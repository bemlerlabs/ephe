import { defineConfig } from '@playwright/test'

/**
 * The #92 live leg. It owns the origin the plan turn needs: a running product server behind
 * the built bundle or the dev server, both of which answer /api. Nothing here starts that
 * server — the leg is opt-in by flag (plan-live.spec.ts) precisely because it spends an
 * engine turn, so the port is declared and documented rather than assumed.
 */
export default defineConfig({
  testDir: '.',
  testMatch: /plan-live\.spec\.ts/,
  timeout: 900_000,
  retries: 0,
  workers: 1,
  fullyParallel: false,
  reporter: [['line']],
  outputDir: './test-results-plan-live',
  use: {
    headless: true,
    baseURL: process.env.EPHE_PLAN_BASE || 'http://localhost:5173',
    viewport: { width: 1280, height: 900 },
    ignoreHTTPSErrors: true,
    screenshot: 'off',
  },
})
