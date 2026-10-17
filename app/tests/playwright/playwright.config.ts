import { execFileSync } from 'node:child_process'
import { defineConfig } from '@playwright/test'

// The static dist leg owns the server it tests.
//
// It used to pin :9199 and set `reuseExistingServer: true`: any server already holding
// that port — a stray left by an earlier run, or the developer's own — answered the leg
// instead of the command below, and the leg then reported green or red about a bundle it
// never served (tests/test_playwright_port_hygiene.py reproduced the shape: the command
// never ran, `1 passed`, and the page was the stranger's). The port is picked at run time
// now and the leg is exclusive, so it only ever tests a server it started; a port somehow
// taken before the command binds is a refusal, not a silent reuse. The hygiene guard holds
// it: the leg declares no fixed port (`test_the_leg_ports_are_measured_not_assumed`) and
// reuses none (the empty `REUSED_SERVER_PORTS` register).
//
// Resolved once and shared through `process.env`, so the command, the probe and every
// worker's baseURL agree on one number: the first evaluation binds :0 and keeps what the
// OS hands back, and the child processes inherit it. Set `EPHE_E2E_STATIC_PORT` to pin the
// port (CI debugging); nothing else may.
function ownedPort(): number {
  const pinned = process.env.EPHE_E2E_STATIC_PORT
  if (pinned) return Number(pinned)
  const chosen = execFileSync(
    process.execPath,
    [
      '-e',
      "const s=require('node:net').createServer();" +
        "s.listen(0,'127.0.0.1',()=>{console.log(s.address().port);s.close()})",
    ],
    { encoding: 'utf8' },
  ).trim()
  process.env.EPHE_E2E_STATIC_PORT = chosen
  return Number(chosen)
}

const STATIC_PORT = ownedPort()
const STATIC_ORIGIN = `http://127.0.0.1:${STATIC_PORT}`

export default defineConfig({
  testDir: '.',
  // First-run E2E boots its own real backend + DGX engine; it is owned by
  // playwright.real.config.ts and must not run against the static dist server.
  // dogfood.spec targets the vite dev server + live backend (it is owned by
  // dogfood.config.ts); setup-e2e boots its own real stack via playwright.real.config.ts.
  // u6-focus is U6 (#70) and self-skips outside latency.config.ts's lane, but it still
  // collects here and names :5173 — the same cross-leg shape the guard in
  // tests/test_playwright_port_hygiene.py refuses (a spec bound to an origin its leg
  // does not start). Its lane is latency.config.ts; the file does not belong to this one.
  testIgnore: [
    '**/setup-e2e/**',
    '**/dogfood.spec.ts',
    '**/artifact-export.spec.ts',
    '**/u6-focus.spec.ts',
  ],
  timeout: 15000,
  retries: 0,
  use: {
    headless: true,
    baseURL: STATIC_ORIGIN,
    viewport: { width: 1280, height: 800 },
    // A committed baseline belongs to one device pixel ratio. Playwright's own note
    // is that snapshots vary by browser, OS, fonts and headless mode; the ratio sits
    // in the same list and is the one a developer's Retina laptop supplies for free.
    // At 2 every glyph edge lands on a different subpixel and every shot in the lane
    // fails at once; pinned here so the ratio is a stated contract, not a property of
    // whoever happened to run the lane last. The spec asserts it per shot.
    deviceScaleFactor: 1,
    ignoreHTTPSErrors: true,
  },
  webServer: {
    command: `python3 -m http.server ${STATIC_PORT} --directory dist`,
    port: STATIC_PORT,
    cwd: '../../',
    // Exclusive: this leg starts its own server or refuses. It never answers from a
    // server it did not start — see the note at the top of this file.
    reuseExistingServer: false,
  },
  // Two entries, and the shape matters for the next one. `chromium` is the default leg and
  // keeps today's collection exactly: every spec but the visual one, on the shared `use`
  // above. A second entry without a `testMatch` would run all 20 specs again, so a new leg
  // adds a third entry that names its own file and leaves `chromium` alone — the
  // perceived-latency leg included, whose spec is collected by `chromium` as it stands.
  // The visual leg is opt-in because a committed baseline belongs to one environment —
  // Playwright's own note on fonts, OS and headless mode — and no runner is pinned yet.
  // `EPHE_VISUAL=1` adds it; without the flag no project matches visual.spec.ts, so
  // `npm run test:e2e` is unchanged.
  projects: [
    {
      name: 'chromium',
      testIgnore: ['**/visual.spec.ts', '**/composer-width.spec.ts', '**/r4-motion-paint.spec.ts'],
    },
    // The serial segment this repo's rule demands for a budget that only fails under load — the
    // guard in tests/test_timing_assertion_guard.py holds that line for pytest, and the browser
    // side had no equivalent until now. Measured 2026-10-14 on the CI box: composer-width lost the
    // resize-handle race with ten workers at 1100 px *and* at 1280 px, the viewport that passes,
    // and r4-motion-paint counts long frames inside a 1200 ms idle window. Both pass with one
    // worker at every viewport. The budget is not widened; the contention is removed.
    {
      name: 'load-sensitive',
      testMatch: [/composer-width\.spec\.ts/, /r4-motion-paint\.spec\.ts/],
      workers: 1,
    },
    ...(process.env.EPHE_VISUAL === '1'
      ? [
          {
            name: 'visual',
            testMatch: /visual\.spec\.ts/,
            // Wave 6's first rule, and the reason the entry sets it rather than each test:
            // reduce stops the seven CSS loops at rest. It does not reach framer-motion,
            // which keeps entrance animations reporting `running` after their end value —
            // the per-shot guard in visual.spec.ts measures advancing currentTime instead.
            use: { reducedMotion: 'reduce' },
          },
        ]
      : []),
  ],
})
