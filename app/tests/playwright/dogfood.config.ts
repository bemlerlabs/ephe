import { defineConfig } from '@playwright/test'

// Dogfood: runs against the VITE DEV server (5173) which proxies /api -> 8765 (the live backend).
// No webServer (dev runs externally), the DE locale is set via addInitScript inside the spec.
export default defineConfig({
  testDir: '.',
  // setup-e2e belongs to playwright.real.config (webServer uvicorn+dist+DGX probe→setup flow→chat);
  // in the dev-dogfood context (dev server 5173, already-onboarded) it runs into a void and pollutes
  // the daily green/red signal with setup-context noise instead of real product findings.
  testIgnore: '**/setup-e2e/**',
  timeout: 60000,
  retries: 0,
  workers: 1,
  reporter: 'line',
  use: {
    headless: true,
    baseURL: 'http://localhost:5173',
    viewport: { width: 1280, height: 800 },
    ignoreHTTPSErrors: true,
    screenshot: 'off',
  },
})
