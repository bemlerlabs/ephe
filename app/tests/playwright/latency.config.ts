import { defineConfig } from '@playwright/test'

// Wave 3's own lane (docs/UI_4X_PROGRAM_2026-10-11.md §3.3). The spec used to run under
// playwright.config.ts, whose lifecycle belongs to the visual-baseline lane: that merged a
// timing lane into a screenshot lane, and a timing figure taken next to another lane's
// screenshots is not comparable to anything.
//
// Two consequences this file owns:
// - No webServer. The shared lane starts `python3 -m http.server 9199 --directory dist`;
//   the latency probe never uses it, because r5-perceived-latency.spec.ts brings its own
//   fixture on an OS-assigned free port (never :8765, which belongs to the visual lane).
// - workers: 1 and fullyParallel: false are the config, not a habit. A wall-clock ceiling
//   measured while another worker is busy measures the machine, the defect
//   tests/test_wall_clock_budgets.py describes for the Python side.
//
// Run: pnpm exec playwright test -c tests/playwright/latency.config.ts
// EPHE_LATENCY_LANE is how the spec recognises its own lane; under the shared config it
// skips with this command in the reason.
process.env.EPHE_LATENCY_LANE = '1'

export default defineConfig({
  testDir: '.',
  // r5 is wave 3's; u6-keyboard and u6-focus are U6 (#70). All three need the same
  // conditions: one worker, no webServer of another lane, and the same injected engine.
  testMatch: ['r5-perceived-latency.spec.ts', 'u6-keyboard.spec.ts', 'u6-focus.spec.ts'],
  timeout: 240_000,
  retries: 0,
  workers: 1,
  fullyParallel: false,
  // Inside the ignored `test-results/` (`.gitignore:102`) rather than beside it: a sibling
  // directory shows up in every other lane's `git status` in this shared worktree.
  outputDir: './test-results/latency',
  reporter: [['list']],
  use: {
    headless: true,
    viewport: { width: 1280, height: 800 },
    // No baseURL: the fixture origin is printed by the run and nothing here may reach the
    // product port or the static dist server by accident.
    trace: 'off',
    screenshot: 'off',
  },
})
