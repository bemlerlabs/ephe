import { defineConfig } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// ESM: `__dirname`/`require` are not available in a "type":"module" package.
const __dirname = path.dirname(fileURLToPath(import.meta.url))

/**
 * E2E against the REAL Ephe server (FastAPI) — no mock, no stub.
 *
 * - webServer: app/tests/e2e_server.py starts the production-equivalent
 *   FastAPI server (uvicorn) on 127.0.0.1:8765 with an isolated, empty
 *   config dir (fresh: engine.json missing → the first-run setup flow).
 * - Frontend: the REAL build from app/dist (requires `npm run build` beforehand).
 * - Test engine: the REAL DGX Spark (OpenAI-compatible, SGLang) — the probe
 *   and the chat run against the actual on-network engine, not Ollama.
 *
 * Prerequisites (checked inside the test itself with clear errors):
 *   1. app/dist/ exists             → `npm run build`
 *   2. the DGX is reachable         → EPHE_EPHE_E2E_DGX_URL (default: the Spark tailnet)
 *   3. a Python venv with FastAPI/uvicorn/httpx
 *
 * No mock: the test flow is the real end-user flow:
 *   /  (unconfigured) → setup page → endpoint input → probe → model picker
 *   → apply → chat → a message to the REAL DGX → assistant answer.
 */
// The venv Python (the system python3 has no FastAPI/uvicorn). Override via EPHE_EPHE_PYTHON.
// Config dir: <repo>/app/tests/playwright → the repo root is 3 levels up.
const python = process.env.EPHE_EPHE_PYTHON || path.resolve(__dirname, '../../../.venv/bin/python')

export default defineConfig({
  testDir: './setup-e2e',
  timeout: 60000, // DGX inference: generous (a 27B model, the first tokens can take a while)
  expect: { timeout: 20000 },
  retries: 0,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  outputDir: './test-results-real',
  use: {
    headless: true,
    baseURL: 'http://127.0.0.1:8765',
    viewport: { width: 1280, height: 800 },
    ignoreHTTPSErrors: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `${python} tests/e2e_server.py`,
    cwd: '../..',
    url: 'http://127.0.0.1:8765/api/health',
    timeout: 120000,
    reuseExistingServer: false,
    stdout: 'pipe',
    stderr: 'pipe',
  },
})
