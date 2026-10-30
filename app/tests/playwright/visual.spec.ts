import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test, type Page } from '@playwright/test'
import { ensureOnboarded, gotoHash } from './helpers'

// `deep_view()` shape at defaults, generated 2026-10-19 from the register with a
// fresh EPHE_CONFIG_DIR. Display text is the English half so a German sentence
// does not enter a test fixture.
const SETTINGS_DEEP = JSON.parse(
  readFileSync(fileURLToPath(new URL('./fixtures/settingsDeep.json', import.meta.url)), 'utf8'),
)
const MARKET_INDEX = JSON.parse(
  readFileSync(fileURLToPath(new URL('../../../marketplace/index.json', import.meta.url)), 'utf8'),
)
const MARKET_HOME = {
  sources: [
    {
      id: 'bundled',
      title: 'Ephe bundled',
      kind: 'bundled',
      url: '',
      trust: 'bundled',
      removable: false,
    },
  ],
  last_read: {},
  last_error: {},
}

// A worker answers its own fetch() outside the page, so page.route never sees an
// /api request the moment the app's freshly registered worker claims the client.
// Blocking workers is the only way the fixture table below is the sole answer.
test.use({ serviceWorkers: 'block' })

/**
 * UI 4x wave 6 — visual regression over the states the inventory certifies.
 *
 * `docs/UI_STATE_INVENTORY_2026-10-11.md` names 25 states and gives each a verdict. This spec
 * baselines 12 of them, the twelve it could certify as they look today: the two workbench
 * views and ten register sections. The refused rows stay refused — a baseline over a defect
 * turns the defect into the reference. Six more rows are refused on the forest ground over the
 * 4.43:1 pair this file's wave-1 gate left unpinned; U3 moved that veil and the pair now reads
 * 4.85:1, so those six verdicts are the inventory's to re-run.
 *
 * Three decisions make a shot repeatable, and each is the instrument's own claim:
 *
 * 1. Every read is answered from the fixture table below, so a baseline is over a named
 *    payload and not over this machine's 39 artifacts or 66 facts. Service workers are
 *    blocked for this file (`serviceWorkers: 'block'`): a worker answers its own fetch()
 *    outside the page, so the moment the app's freshly registered worker claims the client,
 *    `page.route` never sees an /api request. The old unregister-and-reload recipe was undone
 *    by the re-registration on the next boot, which is why every register shot used to
 *    photograph an empty API body.
 * 2. The clock is frozen with `setFixedTime`, which fakes `Date` and leaves timers alone.
 *    Relative stamps (`artifact-stamp-*`, the memory ages) are the only other per-run pixels
 *    in these frames, and freezing the clock retires them without masking the row that
 *    carries them.
 * 3. Every shot runs under `reducedMotion: 'reduce'`, set on the projects in
 *    `playwright.config.ts`, and every shot proves it moved nothing: the seven CSS loops at
 *    rest (`globals.css:617,700,705,774,989,1182,1185`) stop under reduce
 *    (`:658-666,851-860,995,1200-1213`, the precedent being `r33-a11y.spec.ts:113-121`), and
 *    the guard below checks that no animation inside the shot's own root is advancing.
 *    Reduce does not reach framer-motion: the chat shell behind the register keeps 8
 *    entrance animations attached, which is a wave 2 fact, not a reason to skip a shot.
 *
 * No mask is configured, and that is a finding rather than an omission: none of these twelve
 * frames contains the status bar. The register is `fixed inset-0`
 * (`app/src/components/dashboard/settings/index.tsx:137`) and the workbench is its own root
 * space, so TTFT and tokens-per-second are outside every shot here. The first state that
 * frames the status bar has to mask `[data-testid="statusbar-tok-per-sec"]`,
 * `[data-testid="statusbar-cache"]` and the popover's TTFT line, and `mask` below is where it
 * goes.
 *
 * The mutation run: `EPHE_VISUAL_MUTATION=1` adds one `pt-px` to `#root` before the shot. It
 * is the proof that a green baseline means the instrument looked.
 *
 * Runner: `pnpm exec playwright test -c tests/playwright/playwright.config.ts visual --workers=1`.
 * Baselines belong to a pinned environment — Playwright's own note on fonts, OS and headless
 * mode — so the project is opt-in until a runner is named.
 */

const FROZEN_TIME = new Date('2026-10-11T09:00:00Z')
const MUTATION = process.env.EPHE_VISUAL_MUTATION === '1'

/** One payload per read, so a baseline says what data it was taken over. */
const FIXTURES: Array<[RegExp, () => unknown]> = [
  [/\/api\/market$/, () => MARKET_HOME],
  [
    /\/api\/market\/index$/,
    () => ({ status: 'ok', source: MARKET_HOME.sources[0], index: MARKET_INDEX, error: '' }),
  ],
  [/\/api\/market\/installed$/, () => ({ plugins: [] })],
  [/\/api\/market\/updates$/, () => ({ updates: [], errors: [] })],
  [/\/api\/setup\/status/, () => ({ configured: true, skipped: false })],
  [
    /\/api\/health/,
    () => ({
      status: 'ok',
      version: '0.0.1',
      ollama: true,
      models: ['gemma4:12b'],
      active_tier: 'local',
      active_model: 'gemma4:12b',
      dgx_online: false,
      active_provider: 'ollama',
      offline_capable: true,
      requires_internet: false,
      engine_online: true,
      engine_state: 'ok',
    }),
  ],
  // Anchored: the generic body used to match /api/settings/hooks as well, so the
  // hooks section was answered by the main settings payload.
  [
    /\/api\/settings(?:\?|$)/,
    () => ({ language: 'en', memory_enabled: true, deep: SETTINGS_DEEP }),
  ],
  [
    /\/api\/model\/providers/,
    () => ({ active: {}, providers: [], local_models: [], local_model_options: [] }),
  ],
  [
    /\/api\/memory\/stats/,
    () => ({
      total: 66,
      scope: 'ephe_memory_visual',
      provider: 'kepta',
      vector_leg: true,
      lexical_leg: true,
      deleted: 2,
    }),
  ],
  [/\/api\/skills\/pack-index/, () => ({ version: 1, packs: [] })],
  [
    /\/api\/skills/,
    () => ({
      skills: [
        {
          name: 'visual-alpha',
          trigger: 'alpha',
          description: 'First fixture skill row.',
          is_builtin: true,
          version: '1.0.0',
        },
        {
          name: 'visual-beta',
          trigger: 'beta',
          description: 'Second fixture skill row.',
          is_builtin: false,
          version: '0.2.0',
        },
      ],
      total: 2,
    }),
  ],
  [
    /\/api\/tasks/,
    () => [
      { id: 't1', title: 'Baseline the workbench', status: 'done', project: 'visual' },
      { id: 't2', title: 'Baseline the register', status: 'open', project: 'visual' },
      { id: 't3', title: 'Report the mutation catch', status: 'open', project: 'visual' },
    ],
  ],
  [
    /\/api\/settings\/hooks/,
    () => ({
      enabled: true,
      path: '~/.ephe/hooks.json',
      exists: true,
      events: [{ name: 'on_turn_end', matched: 3 }],
      recent: [{ event: 'on_turn_end', ok: true, at: '2026-10-11T08:59:00Z' }],
    }),
  ],
  [/\/api\/artifacts\/expiry/, () => ({ due: [], count: 0, bytes: 0, days: 30 })],
  [
    /\/api\/artifacts\/stats/,
    () => ({
      count: 2,
      bytes: 4096,
      by_kind: [],
      expiring_count: 0,
      expiring_bytes: 0,
      next_expiry: null,
    }),
  ],
  // Anchored collection read: the old \b form also answered the detail route
  // (/api/artifacts/va1), so the preview received the list body and crashed.
  [
    /\/api\/artifacts(?:\?|$)/,
    () => ({
      artifacts: [
        {
          id: 'va1',
          root_id: 'va1',
          version: 1,
          session_id: 'sess-visual',
          name: 'wave-six-alpha.txt',
          path: '/home/visual/.ephe/artifacts/sess-visual/wave-six-alpha.txt',
          kind: 'text',
          size: 2048,
          topic: '',
          created_at: '2026-10-11T08:00:00+00:00',
          favorite: false,
          tags: [],
          origin_path: '/home/visual/.ephe/artifacts/sess-visual/wave-six-alpha.txt',
          adopted_path: '',
          content_hash: 'sha256:visual-a',
          viewed_at: null,
          turn_id: 'visualturn01',
          call_id: 'visualtu-0',
          expires_at: null,
          keep: false,
        },
        {
          id: 'va2',
          root_id: 'va2',
          version: 1,
          session_id: 'sess-visual',
          name: 'wave-six-beta.txt',
          path: '/home/visual/.ephe/artifacts/sess-visual/wave-six-beta.txt',
          kind: 'text',
          size: 2048,
          topic: '',
          created_at: '2026-10-11T08:30:00+00:00',
          favorite: true,
          tags: [],
          origin_path: '/home/visual/.ephe/artifacts/sess-visual/wave-six-beta.txt',
          adopted_path: '/home/visual/Desktop/wave-six-beta.txt',
          content_hash: 'sha256:visual-b',
          viewed_at: null,
          turn_id: 'visualturn02',
          call_id: 'visualtu-1',
          expires_at: null,
          keep: false,
        },
      ],
      total: 2,
    }),
  ],
  [/\/api\/artifacts\/[^/]+\/versions/, () => ({ versions: [] })],
  [/\/api\/artifacts\/[^/]+\/preview/, () => ({ mode: 'none', reason: 'no-text-preview' })],
  [
    /\/api\/artifacts\/[^/]+\/provenance/,
    () => ({ known: false, turn_id: '', call_id: '', args_hash: '', session_id: '', calls: [] }),
  ],
  [
    /\/api\/artifacts\/va2(?:\?|$)/,
    () => ({
      id: 'va2',
      root_id: 'va2',
      version: 1,
      session_id: 'sess-visual',
      name: 'wave-six-beta.txt',
      path: '/home/visual/.ephe/artifacts/sess-visual/wave-six-beta.txt',
      kind: 'text',
      size: 2048,
      topic: '',
      created_at: '2026-10-11T08:30:00+00:00',
      favorite: true,
      tags: [],
      origin_path: '/home/visual/.ephe/artifacts/sess-visual/wave-six-beta.txt',
      adopted_path: '/home/visual/Desktop/wave-six-beta.txt',
      content_hash: 'sha256:visual-b',
      viewed_at: null,
      turn_id: 'visualturn02',
      call_id: 'visualtu-1',
      expires_at: null,
      keep: false,
      adopted_state: 'current',
    }),
  ],
  [
    /\/api\/artifacts\/va1(?:\?|$)/,
    () => ({
      id: 'va1',
      root_id: 'va1',
      version: 1,
      session_id: 'sess-visual',
      name: 'wave-six-alpha.txt',
      path: '/home/visual/.ephe/artifacts/sess-visual/wave-six-alpha.txt',
      kind: 'text',
      size: 2048,
      topic: '',
      created_at: '2026-10-11T08:00:00+00:00',
      favorite: false,
      tags: [],
      origin_path: '/home/visual/.ephe/artifacts/sess-visual/wave-six-alpha.txt',
      adopted_path: '',
      content_hash: 'sha256:visual-a',
      viewed_at: null,
      turn_id: 'visualturn01',
      call_id: 'visualtu-0',
      expires_at: null,
      keep: false,
      adopted_state: 'none',
    }),
  ],
  [/\/api\/sessions\/restore/, () => ({ sessions: [] })],
  [
    /\/api\/context\/budget/,
    () => ({
      message_count: 0,
      char_count: 0,
      estimated_tokens: 0,
      window_tokens: 8192,
      window_source: 'legacy',
      percent: 0,
      compaction_threshold: 28,
      compaction_active: false,
    }),
  ],
  [/\/api\/cell/, () => ({ cell: {} })],
  [/\/api\/ephemeris/, () => ({ days: [] })],
]

async function stubReads(page: Page) {
  await page.route('**/api/**', (route) => {
    const url = route.request().url()
    if (/\/api\/artifacts\/[^/]+\/file/.test(url)) {
      return route.fulfill({
        status: 200,
        contentType: 'text/plain',
        body: 'Fixture artifact content.\n',
      })
    }
    const hit = FIXTURES.find(([re]) => re.test(url))
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(hit ? hit[1]() : {}),
    })
  })
}

/**
 * The tap that says which section opened. `settings-title-h1` and the chip render the same
 * key, so comparing them proves the click landed where it was aimed in either language —
 * the lesson from 2026-10-10, where a control that looked reachable was disproved only by
 * performing the gesture.
 */
async function openSection(page: Page, tab: string) {
  const chip = page.getByTestId(`settings-nav-${tab}`)
  const label = ((await chip.textContent()) ?? '').trim()
  await chip.click()
  await expect(page.getByTestId('settings-title-h1')).toHaveText(label)
}

async function openRegister(page: Page, tab: string) {
  await page.getByTestId('sidebar-settings-btn').first().click()
  await expect(page.getByTestId('settings-page')).toBeVisible()
  await openSection(page, tab)
}

/** The drawer path is the only way to the register at phone width. */
async function openRegisterPhone(page: Page, tab: string) {
  await page.locator('button:has(svg.lucide-menu)').first().click()
  await expect(page.getByTestId('chat-sidebar')).toBeVisible()
  await openRegister(page, tab)
}

type Shot = {
  name: string
  phone: boolean
  lang: 'en' | 'de'
  anchor: string
  reach: (page: Page) => Promise<void>
  decision: string
}

const DESKTOP: Shot[] = [
  {
    name: 'workbench-shelf',
    phone: false,
    lang: 'en',
    anchor: '[data-testid="artifacts-page"]',
    reach: (p) => gotoHash(p, '/artifacts', '[data-testid="artifacts-page"]'),
    decision:
      'certifies the shelf over two fixture cards: the D8 no-match sentence is absent because the list answers, the F8 hairline stands on the unselected view tab, and the detail pane is open on the first card.',
  },
  {
    name: 'workbench-adopted',
    phone: false,
    lang: 'en',
    anchor: '[data-testid="artifacts-ablage-hint"]',
    reach: async (p) => {
      await gotoHash(p, '/artifacts', '[data-testid="artifacts-page"]')
      await p.locator('a[href="#/artifacts/ablage"]').first().click()
      await expect(p.getByTestId('artifacts-ablage-hint')).toBeVisible()
    },
    decision:
      'certifies the adopted view: one of the two fixture cards carries an adopted_path, so the count on the tab and the copy in the detail pane are the state being watched.',
  },
  {
    name: 'register-appearance',
    phone: false,
    lang: 'en',
    anchor: '[data-testid="settings-page"]',
    reach: async (p) => {
      await gotoHash(p, '/chat', '[data-testid="chat-sidebar"]')
      await openRegister(p, 'appearance')
    },
    decision:
      'certifies the appearance section on the one ground: its header, the rows the truthful ' +
      'deep fixture feeds it (including chat font scale and reading width), its Save footer, ' +
      'and no Dark/Light control.',
  },
  {
    name: 'register-extensions',
    phone: false,
    lang: 'en',
    anchor: '[data-testid="discover-page"]',
    reach: async (p) => {
      await gotoHash(p, '/chat', '[data-testid="chat-sidebar"]')
      await p.getByTestId('sidebar-action-marketplace').click()
      await expect(p.getByTestId('discover-page')).toBeVisible()
    },
    decision:
      'certifies the curated Extension Center: the Plugin label, first-party provenance, the measured/no line and no install action on bundled entries.',
  },
  {
    name: 'register-behaviour',
    phone: false,
    lang: 'en',
    anchor: '[data-testid="settings-page"]',
    reach: async (p) => {
      await gotoHash(p, '/chat', '[data-testid="chat-sidebar"]')
      await openRegister(p, 'behaviour')
    },
    decision:
      'certifies the behaviour rows and their hint lines from the truthful deep fixture, which is where a renamed key would show as a raw string.',
  },
  {
    name: 'register-code-exec',
    phone: false,
    lang: 'en',
    anchor: '[data-testid="settings-page"]',
    reach: async (p) => {
      await gotoHash(p, '/chat', '[data-testid="chat-sidebar"]')
      await openRegister(p, 'code-exec')
    },
    decision:
      'certifies the measured cell caps as rendered numbers, stable per checkout and unchanged by the fixture.',
  },
  {
    name: 'register-ephemera',
    phone: false,
    lang: 'en',
    anchor: '[data-testid="settings-page"]',
    reach: async (p) => {
      await gotoHash(p, '/chat', '[data-testid="chat-sidebar"]')
      await openRegister(p, 'ephemera')
    },
    decision:
      'certifies the deep-field renderer for the ephemera prefix from the truthful fixture, the block that shows only what the store really writes.',
  },
  {
    name: 'register-generation',
    phone: false,
    lang: 'en',
    anchor: '[data-testid="settings-page"]',
    reach: async (p) => {
      await gotoHash(p, '/chat', '[data-testid="chat-sidebar"]')
      await openRegister(p, 'generation')
    },
    decision:
      'certifies the generation rows at their default values, including the fields the audit found that no engine reads.',
  },
  {
    name: 'register-hooks',
    phone: false,
    lang: 'en',
    anchor: '[data-testid="settings-page"]',
    reach: async (p) => {
      await gotoHash(p, '/chat', '[data-testid="chat-sidebar"]')
      await openRegister(p, 'hooks')
    },
    decision:
      'certifies the hooks read page over a fixture view of one event and one run, which is the layout a device with hooks.json shows.',
  },
  {
    name: 'register-memory',
    phone: false,
    lang: 'en',
    anchor: '[data-testid="settings-page"]',
    reach: async (p) => {
      await gotoHash(p, '/chat', '[data-testid="chat-sidebar"]')
      await openRegister(p, 'memory')
    },
    decision:
      'certifies the knowledge rows over a fixed stats payload of 66 facts and 2 deleted, so the numbers in the frame are the fixture and not the machine.',
  },
  {
    name: 'register-shortcuts',
    phone: false,
    lang: 'en',
    anchor: '[data-testid="settings-page"]',
    reach: async (p) => {
      await gotoHash(p, '/chat', '[data-testid="chat-sidebar"]')
      await openRegister(p, 'shortcuts')
    },
    decision:
      'certifies the shortcut table at its 12 rows; wave 4 takes this to 48, so this baseline is expected to move and is named for that.',
  },
  {
    name: 'register-skills',
    phone: false,
    lang: 'en',
    anchor: '[data-testid="settings-page"]',
    reach: async (p) => {
      await gotoHash(p, '/chat', '[data-testid="chat-sidebar"]')
      await openRegister(p, 'skills')
    },
    decision:
      'certifies the skill rows with their descriptions resolved through the D4 key path, over two fixture skills.',
  },
  {
    name: 'register-tasks',
    phone: false,
    lang: 'en',
    anchor: '[data-testid="settings-page"]',
    reach: async (p) => {
      await gotoHash(p, '/chat', '[data-testid="chat-sidebar"]')
      await openRegister(p, 'tasks')
    },
    decision:
      'certifies the steps list over three fixture tasks in two states, which is the shape the row renderer has to keep.',
  },
]

const PHONE: Shot[] = [
  {
    name: 'workbench-shelf',
    phone: true,
    lang: 'de',
    anchor: '[data-testid="artifacts-page"]',
    reach: (p) => gotoHash(p, '/artifacts', '[data-testid="artifacts-page"]'),
    decision:
      'certifies the same shelf at 390 px in the language with the longer strings: the D8 and F4 branches, the F8 hairline on both view tabs, and the wrapped control row.',
  },
  {
    name: 'register-appearance',
    phone: true,
    lang: 'de',
    anchor: '[data-testid="settings-page"]',
    reach: async (p) => {
      await gotoHash(p, '/chat', '[data-testid="chat-sidebar"]')
      await openRegisterPhone(p, 'appearance')
    },
    decision:
      'certifies the phone register: the drawer opened it, the section strip scrolls to the tapped chip, and the save footer clears the bottom band.',
  },
  {
    name: 'register-extensions',
    phone: true,
    lang: 'de',
    anchor: '[data-testid="discover-page"]',
    reach: async (p) => {
      await gotoHash(p, '/chat', '[data-testid="chat-sidebar"]')
      await p.getByTestId('sidebar-action-marketplace').click()
      await expect(p.getByTestId('discover-page')).toBeVisible()
    },
    decision:
      'certifies the Extension Center at 390 px in German: the quality label, provenance and measured/no line fit the phone register.',
  },
  {
    name: 'register-memory',
    phone: true,
    lang: 'de',
    anchor: '[data-testid="settings-page"]',
    reach: async (p) => {
      await gotoHash(p, '/chat', '[data-testid="chat-sidebar"]')
      await openRegisterPhone(p, 'memory')
    },
    decision:
      'certifies the knowledge rows in German at phone width, the surface where the audit found a number that disagreed with the interface language.',
  },
  {
    name: 'register-skills',
    phone: true,
    lang: 'de',
    anchor: '[data-testid="settings-page"]',
    reach: async (p) => {
      await gotoHash(p, '/chat', '[data-testid="chat-sidebar"]')
      await openRegisterPhone(p, 'skills')
    },
    decision:
      'certifies the skill list in German at phone width, where the D4 description key path is the only thing keeping the row free of untranslated text.',
  },
]

// The shared 15 s is a per-file budget the boot-plus-drawer path does not fit in; the
// config stays untouched so the other 17 specs keep theirs.
test.describe.configure({ timeout: 60_000 })

function pinLanguage(page: Page, lang: 'en' | 'de') {
  return page.addInitScript((l) => {
    localStorage.setItem('i18nextLng', l)
    localStorage.setItem('ephe_onboarded', '1')
  }, lang)
}

async function shoot(page: Page, shot: Shot) {
  await page.clock.setFixedTime(FROZEN_TIME)
  await stubReads(page)
  await shot.reach(page)
  await page.waitForSelector(shot.anchor, { timeout: 15000 })
  // A toast is a transient element over a stable one, and this check needed two repairs
  // on 2026-10-16, both measured: it asked for `[role="status"].glass-float`, where
  // `glass-float` is a token prefix and not a class any element carries, so it matched
  // nothing and never fired; and it ran BEFORE the settle wait, while the boot restore
  // raises its toast asynchronously afterwards. Three baselines had the restore banner
  // frozen into them as a result. The toast's own hook is `data-float` (Toaster.tsx), and
  // the assertion waits for the region to clear instead of sampling it once.
  await page.waitForTimeout(700)
  await expect.poll(() => page.locator('[data-float]').count(), { timeout: 8000 }).toBe(0)
  // The reduce rule, measured where it has to hold: inside the surface being shot. The
  // instrument is motion itself — an animation whose currentTime advances over a 250 ms
  // window — and it is polled rather than sampled once, because the section container's
  // 150 ms entrance starts when the register's own read resolves, not when the chip is
  // tapped. A fixed wait would shoot in the middle of it; `expect.poll` settles and still
  // fails if something never stops.
  //
  // A count of `playState === 'running'` is not this measurement: framer-motion keeps the
  // entrance animation attached and reporting running after it has reached its end value,
  // and the chat shell behind the register holds 8 of them (measured on the skills
  // section). Reduce stops the seven CSS loops, not those.
  const movingInside = (root: string) =>
    page.evaluate(
      async ([sel, gap]) => {
        const box = document.querySelector(sel)
        const inside = () =>
          document.getAnimations().filter((a) => {
            const t = a.effect ? a.effect.target : null
            return (
              a.playState === 'running' && t instanceof Element && box !== null && box.contains(t)
            )
          })
        const before = inside().map((a) => [a, a.currentTime])
        await new Promise((r) => setTimeout(r, gap))
        const after = new Map(inside().map((a) => [a, a.currentTime]))
        return before
          .filter(([a, t]) => after.has(a) && after.get(a) !== t)
          .map(([a]) => {
            const t = a.effect ? a.effect.target : null
            const el = t instanceof Element ? t : null
            return `${a.animationName || a.constructor.name}@${el ? `${el.tagName}.${String(el.className).slice(0, 40)}` : 'none'}`
          })
      },
      [root, 250],
    )

  /**
   * The preconditions a committed baseline rests on, asserted before the comparison.
   *
   * Playwright's own note is that a snapshot belongs to a browser, an OS, a font set and
   * a headless mode. When one of those drifts the lane does not say so: it reports a
   * whole-page pixel storm that reads exactly like a layout regression, and the natural
   * response is to refresh the baseline and bury a real one. These four assertions name
   * the instrument instead, so a red shot can only mean the product's pixels moved.
   *
   * Measured 2026-10-16 on the machine that wrote these baselines: the fonts settle before
   * the shot (Playwright's own call log prints `waiting for fonts to load... fonts loaded`),
   * the heading rasterises as the self-hosted `Inter SemiBold` rather than a fallback (CDP
   * `CSS.getPlatformFontsForNode`), 22 `@font-face` rules reach the document, the ratio is
   * 1, and six installed Chromium builds produce the same diff to the pixel. None of the
   * four is where a red shot comes from today; they are asserted because the next runner
   * is the one that will supply the difference.
   */
  /**
   * A baseline belongs to a tree as well as to a machine, and nothing in a failing run
   * said so: on 2026-10-16 all sixteen shots failed with a diff that read like a layout
   * regression, and the cause turned out to be a reference set written four hundred
   * commits earlier. Dating one string in the diff is what settled it. This constant is
   * that dating done in advance — bump it in the same commit that regenerates a baseline,
   * so the report always answers `is this reference current` before anyone reads pixels.
   */
  const BASELINE_COMMIT = 'c0b742ac'
  // The package is `type: module`, so `__dirname` is undefined in this file: with it the
  // probe threw into its own catch, `apart` was always empty, and the provenance line
  // printed the constant while never answering `is this reference current against HEAD`.
  const here = path.dirname(fileURLToPath(import.meta.url))
  const head = (() => {
    try {
      return execFileSync('git', ['rev-parse', '--short', 'HEAD'], {
        cwd: path.resolve(here, '..', '..', '..'),
        encoding: 'utf8',
      }).trim()
    } catch {
      return null
    }
  })()
  // The constant names the commit that last REGENERATED the baselines, so HEAD differing
  // from it is the normal state after any later change — a drift claim here would cry wolf
  // on every run. It is printed as provenance, and a failure message carries it too.
  const apart = head ? `, HEAD ${head}` : ''

  // Printed once per worker at import, not in a hook: this file nests its describes in
  // loops, and a hook registered in that scope is not one Playwright accepts.
  console.log(
    `baselines last regenerated at ${BASELINE_COMMIT}${apart}. Regenerate them in the same` +
      ' commit that changes a screen they cover.',
  )

  async function assertComparableEnvironment(p: Page, s: Shot) {
    const env = await p.evaluate(async () => {
      await document.fonts.ready
      // Whether a face is *registered* says nothing: `@fontsource` declares Space Grotesk
      // and Instrument Serif for screens this lane never photographs, and the browser
      // leaves an unused face `unloaded`, so `document.fonts.check('16px "Space Grotesk"')`
      // answers false on a perfectly healthy page. Measure instead: the same string under
      // the app's real stack and under the generic fallback. Equal widths mean the shot
      // would photograph a system face where the baseline has a self-hosted one.
      const widthOf = (stack: string) => {
        const probe = document.createElement('span')
        probe.style.cssText = `position:absolute;visibility:hidden;white-space:nowrap;font:16px ${stack}`
        probe.textContent = 'Handgloves — Ephe 0123'
        document.body.appendChild(probe)
        const w = probe.getBoundingClientRect().width
        probe.remove()
        return w
      }
      const selfHosted = widthOf('"Inter", sans-serif')
      const fallback = widthOf('sans-serif')
      return {
        status: document.fonts.status,
        faces: document.fonts.size,
        dpr: window.devicePixelRatio,
        zoom: window.visualViewport ? window.visualViewport.scale : 1,
        selfHosted,
        fallback,
      }
    })
    const where = `${s.name}-${s.lang}-${s.phone ? '390' : '1280'}`
    expect(env.status, `${where}: the shot was taken before the webfonts settled${apart}`).toBe(
      'loaded',
    )
    expect(env.faces, `${where}: no @font-face reached the document`).toBeGreaterThan(0)
    expect(
      Math.abs(env.selfHosted - env.fallback) > 0.5,
      `${where}: Inter measures ${env.selfHosted}px against the fallback's ${env.fallback}px — the body face is not the self-hosted one`,
    ).toBe(true)
    expect(
      env.dpr,
      `${where}: this baseline was written at a device pixel ratio of 1${apart}`,
    ).toBe(1)
    expect(
      env.zoom,
      `${where}: the page is zoomed, so every edge lands on a different subpixel`,
    ).toBe(1)
  }

  await expect
    .poll(() => movingInside(shot.anchor), {
      timeout: 8000,
      message: 'something never stopped moving inside the shot',
    })
    .toEqual([])
  await assertComparableEnvironment(page, shot)
  if (MUTATION) {
    // The one injected pixel. `pt-px` as a class would do nothing here: Tailwind v4 emits
    // only the utilities the source uses, and `.pt-px` is absent from the built stylesheet
    // (grep over app/dist/assets/*.css: 0), so the mutation declares the same rule.
    await page.addStyleTag({ content: '#root { padding-top: 1px }' })
    await page.waitForTimeout(150)
  }
  await expect(page).toHaveScreenshot(
    `${shot.name}-${shot.lang}-${shot.phone ? '390' : '1280'}.png`,
    {
      fullPage: true,
      // The tolerance is written out rather than inherited. A guard whose sensitivity is
      // whatever the runner's defaults happen to be cannot say what it looked at, and the
      // redesign's own contract asks for this line explicitly. 0 pixels of budget with the
      // 0.2 default per-pixel colour distance: any pixel past a fifth of the colour
      // distance fails the shot, and the sum of them may not buy a single one.
      animations: 'disabled',
      caret: 'hide',
      threshold: 0.2,
      maxDiffPixels: 0,
      maxDiffPixelRatio: 0,
      // The option is `mask`; this was `masks`, which Playwright ignores, so "no mask is
      // configured" was true by accident. It is meant: none of these twelve frames
      // contains the status bar (see the header note), so nothing is masked.
      mask: [],
    },
  )
}

test.describe('visual desktop 1280x800 en', () => {
  test.use({ viewport: { width: 1280, height: 800 } })
  for (const shot of DESKTOP) {
    test(shot.name, async ({ page }) => {
      ensureOnboarded(page)
      await pinLanguage(page, shot.lang)
      await shoot(page, shot)
    })
  }
})

test.describe('visual phone 390x844 de', () => {
  test.use({ viewport: { width: 390, height: 844 } })
  for (const shot of PHONE) {
    test(shot.name, async ({ page }) => {
      ensureOnboarded(page)
      await pinLanguage(page, shot.lang)
      await shoot(page, shot)
    })
  }
})
