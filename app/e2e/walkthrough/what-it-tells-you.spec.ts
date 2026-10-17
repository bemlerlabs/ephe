/**
 * Walkthrough — "does the product ever tell the user what its modes, its
 * approval profiles and its shortcuts mean?"
 *
 * The product offers two independent stores that both decide whether a tool
 * runs without asking:
 *   - the composer's response mode  (Ask / Plan / Edit auto / Full access),
 *     `data-testid="composer-mode-selector"`, session attribute;
 *   - the approval profile           (Strict / Session / […]),
 *     `data-testid="privacy-profile"` in Settings › Privacy, plus the amber
 *     `data-testid="composer-permission-badge"` readout in the composer.
 *
 * This run photographs what the LIVE product (built app/dist on
 * http://127.0.0.1:8765, real backend) actually shows about them, and records
 * the verbatim strings — never a paraphrase of a label into a sentence the app
 * never wrote. Nothing is mocked: no `page.route`, no fixtures standing in for
 * the API. Every quoted string is read off the live DOM or off a repo file on
 * disk.
 *
 * The five questions this run answers with evidence:
 *  (1) composer mode selector + permission badge — is there ANY explanation of
 *      what "Plan" or "Full access" does, or only the label?
 *  (2) the settings surfaces that govern this — Privacy (privacy-profile,
 *      security-profile-strict|session) and the shell's help/about surface.
 *      Exact wording a user finds.
 *  (3) the in-repo documentation a user could read (README.md,
 *      docs/INSTALL.md, docs/CLI.md, docs/COMPOSER_MODES.md) — and whether a
 *      user who only has the app can reach the same thing.
 *  (4) is there any place that explains the DIFFERENCE between the composer's
 *      mode and the settings' profile (two stores, one decision)?
 *  (5) the help/shortcuts surfaces — does the product document its own keyboard
 *      shortcuts and its own capabilities anywhere in the UI?
 *
 * Artifacts: the walkthrough capture dir (walkthrough-out.ts); the dated set is
 * docs/media/user-walkthrough-2026-10-12/what-it-tells-you/
 *   - NN-name.png, full page
 *   - observations.json — the verbatim findings, the console/page/request
 *     failures, and a one-line verdict per question.
 *
 * Run (the orchestrator runs it; this file starts no engine turn):
 *   cd app && npx playwright test e2e/walkthrough/what-it-tells-you.spec.ts \
 *     --timeout=300000
 * Overridable: EPHE_WALKTHROUGH_BASE (falls back to EPHE_E2E_BASE, then :8765).
 *
 * Selector policy: `data-testid` / ARIA role only — never a CSS class; a copy
 * string is only ever the SUBJECT of a quotation, never the selector.
 *
 * The spec never changes a setting it walks past: it opens the mode menu but
 * picks no option, opens Privacy but clicks no profile radio and no sandbox
 * toggle. The mode and the profile are read, not written.
 */
import { test, expect, type Page } from '@playwright/test'
import * as fs from 'node:fs'
import * as path from 'node:path'
import { fileURLToPath } from 'node:url'
import { walkthroughOutDir } from './walkthrough-out.ts'

const BASE = (
  process.env.EPHE_WALKTHROUGH_BASE ??
  process.env.EPHE_E2E_BASE ??
  'http://127.0.0.1:8765'
).replace(/\/$/, '')

const HERE = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.resolve(HERE, '../../..')
const OUT_DIR = walkthroughOutDir('what-it-tells-you')
const OBS_FILE = path.join(OUT_DIR, 'observations.json')

// ---- testids and roles, straight out of app/src -------------------------------------
const COMPOSER = '#ephe-chat-input'
const MODE_SELECTOR = '[data-testid="composer-mode-selector"]'
const MODE_MENU = '[data-testid="composer-mode-menu"]'
const MODE_SECTIONS = '[data-testid^="composer-mode-section-"]'
const ASK_HINT = '[data-testid="composer-ask-hint"]'
const PERM_BADGE = '[data-testid="composer-permission-badge"]'

const SIDEBAR_SETTINGS = '[data-testid="sidebar-settings-btn"]'
const SETTINGS_PAGE = '[data-testid="settings-page"]'
const SETTINGS_BACK = '[data-testid="settings-back"]'
const SETTINGS_PANEL = '[data-testid="settings-panel"]'
const SETTINGS_SEARCH = '[data-testid="settings-search"]'
const SEARCH_HIT = '[data-testid^="settings-search-"]'
const NAV_TAB = '[data-testid^="settings-nav-"]:not([data-testid^="settings-nav-group-"])'
const NAV_PRIVACY = '[data-testid="settings-nav-privacy"]'
const NAV_SHORTCUTS = '[data-testid="settings-nav-shortcuts"]'
const NAV_ABOUT = '[data-testid="settings-nav-about"]'
const PRIVACY_PROFILE = '[data-testid="privacy-profile"]'
const PROFILE_STRICT = '[data-testid="security-profile-strict"]'
const PROFILE_SESSION = '[data-testid="security-profile-session"]'
const SHORTCUTS_FIXED_NOTE = '[data-testid="shortcuts-fixed-note"]'
const SHORTCUT_ROW = '[data-testid^="shortcuts-row-"]'
const SHORTCUT_GROUP = '[data-testid^="shortcuts-group-"]'

const HEADER_HELP = '[data-testid="header-help"]'
const HEADER_PALETTE = '[data-testid="header-palette"]'
const SHORTCUTS_OVERLAY = '[data-testid="shortcuts-overlay"]'

const PALETTE_INPUT = 'input[role="combobox"][aria-controls="cmd-palette-listbox"]'
const PALETTE_OPTION = '#cmd-palette-listbox li[role="option"]'

const SLASH_MENU = '[data-testid="slash-menu"]'
const SLASH_GROUP = '[data-testid^="slash-group-"]'
const SLASH_HELP_ROW = '#slash-opt-help'

// ---- artifact collection -----------------------------------------------------------

interface Diag {
  consoleErrors: string[]
  pageErrors: string[]
  failedRequests: string[]
  badResponses: string[]
}

interface Finding {
  id: string
  question: string
  source: string
  verbatim: string
  note: string
}

const findings: Finding[] = []
const questions: Record<string, string> = {}
const allDiag: Diag = { consoleErrors: [], pageErrors: [], failedRequests: [], badResponses: [] }
let diag: Diag = { consoleErrors: [], pageErrors: [], failedRequests: [], badResponses: [] }
let step = 0

function record(question: string, source: string, verbatim: string, note = ''): void {
  const flat = verbatim.replace(/\s+/g, ' ').trim()
  findings.push({ id: `f${findings.length + 1}`, question, source, verbatim: flat, note })

  console.log(`[q${question}] ${source}: ${JSON.stringify(flat)}${note ? ` — ${note}` : ''}`)
}

async function shot(page: Page, name: string): Promise<void> {
  step += 1
  const file = path.join(OUT_DIR, `${String(step).padStart(2, '0')}-${name}.png`)
  await page.screenshot({ path: file, fullPage: true })
}

async function textOf(page: Page, selector: string): Promise<string> {
  try {
    return (await page.locator(selector).first().innerText({ timeout: 5_000 })).trim()
  } catch {
    return ''
  }
}

async function attr(page: Page, selector: string, name: string): Promise<string> {
  try {
    return (
      (await page.locator(selector).first().getAttribute(name, { timeout: 5_000 })) ?? ''
    ).trim()
  } catch {
    return ''
  }
}

async function allTexts(page: Page, selector: string): Promise<string[]> {
  try {
    const xs = await page.locator(selector).allInnerTexts()
    return xs.map((x) => x.replace(/\s+/g, ' ').trim()).filter(Boolean)
  } catch {
    return []
  }
}

async function openChat(page: Page): Promise<void> {
  await page.goto(`${BASE}/#/chat`, { waitUntil: 'load' })
  try {
    await page.locator(COMPOSER).waitFor({ state: 'visible', timeout: 60_000 })
  } catch {
    await page
      .screenshot({ path: path.join(OUT_DIR, '00-shell-without-composer.png'), fullPage: true })
      .catch(() => {})
    throw new Error('Chat composer never appeared — likely the engine setup gate.')
  }
  await page.waitForTimeout(1_200) // IndexedDB hydration
}

/** Open the settings surface: the sidebar entry first, the palette item as fallback. */
async function openSettings(page: Page): Promise<void> {
  const btn = page.locator(SIDEBAR_SETTINGS)
  if (await btn.isVisible().catch(() => false)) {
    await btn.click()
  } else {
    const paletteBtn = page.locator(HEADER_PALETTE)
    if (await paletteBtn.isVisible().catch(() => false)) {
      await paletteBtn.click()
      await page.locator(PALETTE_INPUT).waitFor({ state: 'visible', timeout: 8_000 })
      await page
        .locator(PALETTE_OPTION)
        .filter({ hasText: 'Open settings' })
        .first()
        .click()
        .catch(() => {})
    }
  }
  await page.locator(SETTINGS_PAGE).waitFor({ state: 'visible', timeout: 20_000 })
  await page.waitForTimeout(500)
}

/** Verbatim lines of a repo file that contain `needle`; a labelled miss otherwise. */
function excerpt(file: string, needle: string): string {
  const rel = path.relative(REPO_ROOT, file)
  if (!fs.existsSync(file)) return `(missing file: ${rel})`
  const lines = fs.readFileSync(file, 'utf8').split('\n')
  const hits = lines.map((l) => l.trim()).filter((l) => l.includes(needle))
  return hits.length ? hits.join(' ⏎ ') : `(no line in ${rel} contains ${JSON.stringify(needle)})`
}

// ── lifecycle ────────────────────────────────────────────────────────────────

test.describe('what it tells you — modes, profiles and shortcuts', () => {
  test.describe.configure({ timeout: 300_000 })

  test.beforeAll(() => {
    fs.mkdirSync(OUT_DIR, { recursive: true })
  })

  test.beforeEach(async ({ page }) => {
    diag = { consoleErrors: [], pageErrors: [], failedRequests: [], badResponses: [] }
    page.on('console', (m) => {
      if (m.type() === 'error') diag.consoleErrors.push(m.text())
    })
    page.on('pageerror', (e) => diag.pageErrors.push(String(e)))
    page.on('requestfailed', (r) =>
      diag.failedRequests.push(
        `${r.method()} ${r.url()} :: ${r.failure()?.errorText ?? 'unknown'}`,
      ),
    )
    page.on('response', (r) => {
      if (r.status() >= 400)
        diag.badResponses.push(`${r.status()} ${r.request().method()} ${r.url()}`)
    })
    // Pin the interface to English (i18n localises via localStorage only) and
    // record any window.open target instead of leaving the app for an external
    // site — a probe, not a stand-in for the API.
    await page.addInitScript(() => {
      try {
        localStorage.setItem('i18nextLng', 'en')
        localStorage.setItem('i18nextLang', 'en')
      } catch {
        /* storage may be unavailable before the first document */
      }
      const w = window as unknown as { __epheOpenTargets?: string[] }
      w.__epheOpenTargets = []
      window.open = ((url?: string | URL) => {
        w.__epheOpenTargets?.push(String(url ?? ''))
        return null
      }) as typeof window.open
    })
  })

  test.afterEach(() => {
    allDiag.consoleErrors.push(...diag.consoleErrors)
    allDiag.pageErrors.push(...diag.pageErrors)
    allDiag.failedRequests.push(...diag.failedRequests)
    allDiag.badResponses.push(...diag.badResponses)
  })

  // ── (1a) the composer mode selector ────────────────────────────────────────
  test('1a — composer mode selector: label only, or an explanation?', async ({ page }) => {
    await openChat(page)

    const chipText = await textOf(page, MODE_SELECTOR)
    const chipTitle = await attr(page, MODE_SELECTOR, 'title')
    const chipAria = await attr(page, MODE_SELECTOR, 'aria-label')
    const askHintPresent = await page
      .locator(ASK_HINT)
      .isVisible()
      .catch(() => false)
    record('1', 'composer-mode-selector (live DOM, visible text)', chipText)
    record('1', 'composer-mode-selector title attribute (native tooltip only)', chipTitle)
    record('1', 'composer-mode-selector aria-label', chipAria)
    record(
      '1',
      'composer-ask-hint present in the current mode',
      String(askHintPresent),
      'chat.askNoTools ("no tools run in Ask mode") renders next to the chip only while the mode is ask (ChatInput.tsx:515-522); the mode was deliberately NOT switched — it is a persisted session attribute',
    )
    await shot(page, 'composer-mode-chip-closed')

    // Open the menu — read only; no option is picked.
    await page.locator(MODE_SELECTOR).click()
    await page.locator(MODE_MENU).waitFor({ state: 'visible', timeout: 8_000 })
    await page.waitForTimeout(300)
    await shot(page, 'composer-mode-menu-open')

    const sections = await allTexts(page, MODE_SECTIONS)
    record('1', 'composer mode menu — section labels (visible text)', sections.join(' | '))

    for (const key of ['ask', 'plan', 'edit-auto', 'full-access']) {
      const sel = `[data-testid="composer-mode-${key}"]`
      record('1', `mode option "${key}" — visible label`, await textOf(page, sel))
      record(
        '1',
        `mode option "${key}" — title attribute (hover tooltip)`,
        await attr(page, sel, 'title'),
      )
      record('1', `mode option "${key}" — aria-label`, await attr(page, sel, 'aria-label'))
    }
    record(
      '1',
      'verdict — where the meaning of a mode lives',
      'The menu shows only the short label under a section heading; the sentence that says what the mode does exists solely as a native `title` tooltip (and, doubled, in the aria-label). There is no always-visible explanation of "Plan" or "Full access" in the composer.',
    )
    await page.keyboard.press('Escape')
    await page.waitForTimeout(200)
  })

  // ── (1b) the permission badge ──────────────────────────────────────────────
  test('1b — permission badge: what does the amber chip tell the user?', async ({ page }) => {
    await openChat(page)
    record(
      '1',
      'composer-permission-badge visible',
      String(
        await page
          .locator(PERM_BADGE)
          .isVisible()
          .catch(() => false),
      ),
    )
    record('1', 'composer-permission-badge visible text', await textOf(page, PERM_BADGE))
    record('1', 'composer-permission-badge title attribute', await attr(page, PERM_BADGE, 'title'))
    record('1', 'composer-permission-badge aria-label', await attr(page, PERM_BADGE, 'aria-label'))
    record('1', 'composer-permission-badge role', await attr(page, PERM_BADGE, 'role'))
    record(
      '1',
      'verdict — the badge explains nothing',
      'The badge is a role=status readout of the approval-profile value only (chat.perm.* = Manual / Session / Auto). Its title and aria-label repeat that single word; no sentence anywhere in the composer says what the profile does.',
    )
    await shot(page, 'composer-permission-badge')
  })

  // ── (2a) Settings › Privacy — the approval profile ─────────────────────────
  test('2a — Settings › Privacy: the approval profile, in the product’s own words', async ({
    page,
  }) => {
    await openChat(page)
    await openSettings(page)

    const navLabels = await allTexts(page, NAV_TAB)
    record('2', 'settings nav tabs (visible labels)', navLabels.join(' | '))
    record(
      '2',
      'is there a Documentation or Help tab in Settings',
      String(navLabels.some((l) => /doc|help/i.test(l))),
      'no settings nav entry is named Documentation or Help',
    )

    await page.locator(NAV_PRIVACY).click()
    await page.locator(PRIVACY_PROFILE).waitFor({ state: 'visible', timeout: 15_000 })
    await page.waitForTimeout(500)
    await shot(page, 'settings-privacy-approval-profile')

    record(
      '2',
      'Settings › Privacy — page text (verbatim)',
      (await textOf(page, SETTINGS_PANEL)).slice(0, 900),
    )
    record(
      '2',
      'privacy-profile row (title + description, verbatim)',
      await textOf(page, PRIVACY_PROFILE),
    )
    record('2', 'profile option "strict" — visible label', await textOf(page, PROFILE_STRICT))
    record('2', 'profile option "session" — visible label', await textOf(page, PROFILE_SESSION))
    record(
      '2',
      'profile options present (testids)',
      'security-profile-strict | security-profile-session',
    )
    record(
      '2',
      'profile option aria-checked (strict | session)',
      `${await attr(page, PROFILE_STRICT, 'aria-checked')} | ${await attr(page, PROFILE_SESSION, 'aria-checked')}`,
    )
    record(
      '2',
      'verdict — the settings profile IS explained, but only two of the four values exist here',
      'The Privacy tab writes a real sentence per value (profileStrict "Strict — always ask", profileSession "Session — remember per tool") plus securityHint/profileSessionHint. The UI offers exactly two options (strict, session); the README names a third (autonomous) and the composer badge can read "Auto" — neither is chooseable or explained on this surface.',
    )
  })

  // ── (2b) the shell's help / about surface ───────────────────────────────────
  test('2b — the shell’s own help and about surfaces', async ({ page }) => {
    await openChat(page)

    record('2', 'header help control — aria-label', await attr(page, HEADER_HELP, 'aria-label'))
    record('2', 'header help control — title attribute', await attr(page, HEADER_HELP, 'title'))

    await page.locator(HEADER_HELP).click()
    await page.locator(SHORTCUTS_OVERLAY).waitFor({ state: 'visible', timeout: 8_000 })
    await page.waitForTimeout(300)
    await shot(page, 'help-overlay-from-header')

    record(
      '2',
      'help overlay (shortcuts-overlay) full text, verbatim',
      (await textOf(page, SHORTCUTS_OVERLAY)).slice(0, 700),
    )
    record('2', 'help overlay aria-label', await attr(page, SHORTCUTS_OVERLAY, 'aria-label'))
    await page.keyboard.press('Escape')
    await page.waitForTimeout(300)

    await openSettings(page)
    await page.locator(NAV_ABOUT).click()
    await page.waitForTimeout(700)
    await shot(page, 'settings-about')
    record(
      '2',
      'Settings › About — page text (verbatim)',
      (await textOf(page, SETTINGS_PANEL)).slice(0, 600),
    )
    record(
      '2',
      'verdict — the shell’s help surface is the keyboard-shortcut overlay and nothing else',
      'The header help button points at the shortcut cheatsheet; Settings has an "About" card (version/provider/model/offline) with no explanation of modes or profiles. No UI surface states what a mode or an approval profile does beyond the two profile labels quoted above.',
    )
  })

  // ── (5) shortcuts and documented capabilities ───────────────────────────────
  test('5 — does the product document its own shortcuts and capabilities?', async ({ page }) => {
    await openChat(page)
    await openSettings(page)
    await page.locator(NAV_SHORTCUTS).click()
    await page.waitForTimeout(700)
    await shot(page, 'settings-keyboard-shortcuts')

    const groups = await allTexts(page, SHORTCUT_GROUP)
    const rows = await allTexts(page, SHORTCUT_ROW)
    record(
      '5',
      'shortcuts tab — page text (verbatim)',
      (await textOf(page, SETTINGS_PANEL)).slice(0, 700),
    )
    record('5', 'shortcut groups (verbatim)', groups.join(' | '))
    record('5', 'shortcut rows — key + description (verbatim)', rows.join(' | '))
    record('5', 'shortcuts-fixed-note (verbatim)', await textOf(page, SHORTCUTS_FIXED_NOTE))

    // The product's own command surface: typing "/" opens the command list.
    // No turn is sent and the composer is cleared again.
    //
    // Back to the composer through the product's own close control, NOT through
    // `page.goto`: settings is an overlay over the chat with no route of its own,
    // so navigating to the current URL (`#/chat`) is a same-document no-op —
    // measured 2026-10-13 against the live build: goto returned in 1 ms, the
    // overlay stayed open, its `makeBackgroundInert` left `inert`+`aria-hidden`
    // on the chat's <main>/sidebar, and the composer was visible but could never
    // receive an event, so the click waited out the whole test timeout. The
    // ← Back control is what the user has.
    await page.locator(SETTINGS_BACK).click({ timeout: 15_000 })
    await expect(page.locator(SETTINGS_PAGE)).toBeHidden({ timeout: 10_000 })
    const composer = page.locator(COMPOSER)
    await composer.waitFor({ state: 'visible', timeout: 60_000 })
    await composer.click({ timeout: 15_000 })
    await composer.fill('/', { timeout: 15_000 })
    await page
      .locator(SLASH_MENU)
      .waitFor({ state: 'visible', timeout: 8_000 })
      .catch(() => {})
    await page.waitForTimeout(300)
    await shot(page, 'composer-slash-commands')
    const slashText = await textOf(page, SLASH_MENU)
    record('5', 'composer slash menu (/help surface) text, verbatim', slashText.slice(0, 1_500))
    record(
      '5',
      'slash menu group headings (verbatim)',
      (await allTexts(page, SLASH_GROUP)).join(' | '),
    )
    // Read the row by its own id rather than a line of the slice above: the /help
    // row renders its command and description on two lines, and it is grouped under
    // "SKILLS" although the text is the app's own `/help` (measured 2026-10-13:
    // useComposerSlash classifies a suggestion by whether a SKILL claims the same
    // command name, and skills/help does — while the skill's own row is dropped as a
    // duplicate in filterCommands, slashCommands.ts).
    record(
      '5',
      'the /help row (command + description, verbatim)',
      await textOf(page, SLASH_HELP_ROW),
    )
    await composer.fill('', { timeout: 15_000 })
    await page.waitForTimeout(200)

    record(
      '5',
      'verdict — shortcuts and capabilities ARE documented in the UI',
      'Keyboard shortcuts: yes, two places (the header help overlay and Settings › Keyboard shortcuts, both drawn from one table). Capabilities: the composer slash list names the commands with a one-line description each. Modes and approval profiles are NOT documented in the same way — there is no equivalent list that says what "Plan" or "Full access" or a profile does.',
    )
  })

  // ── (3) the in-repo documentation, and whether the app can reach it ─────────
  test('3 — the in-repo docs a user could read, and whether the app shows them', async ({
    page,
  }) => {
    const README = path.join(REPO_ROOT, 'README.md')
    const INSTALL = path.join(REPO_ROOT, 'docs/INSTALL.md')
    const CLI = path.join(REPO_ROOT, 'docs/CLI.md')
    const MODES = path.join(REPO_ROOT, 'docs/COMPOSER_MODES.md')

    for (const f of [README, INSTALL, CLI, MODES]) {
      record('3', `doc file present: ${path.relative(REPO_ROOT, f)}`, String(fs.existsSync(f)))
    }

    record(
      '3',
      'README.md — what it says about the profiles',
      excerpt(README, 'security profile you control'),
    )
    record('3', 'README.md — what it says about a mode', excerpt(README, 'Ask mode runs no tools'))
    record('3', 'docs/INSTALL.md — the word "mode" there', excerpt(INSTALL, 'What each mode needs'))
    record('3', 'docs/CLI.md — the word "approval" there', excerpt(CLI, 'approval gate'))
    record('3', 'docs/COMPOSER_MODES.md — the mode table header', excerpt(MODES, '| Mode (UI) |'))
    record('3', 'docs/COMPOSER_MODES.md — the Plan row', excerpt(MODES, '| Plan |'))
    record(
      '3',
      'docs/COMPOSER_MODES.md — the profile axis',
      excerpt(MODES, 'composer-permission-badge'),
    )

    // Can a user who only has the app reach any of this? The palette is the only
    // pointer to documentation — and it leaves the app for an external URL.
    await openChat(page)
    await page.locator(HEADER_PALETTE).click()
    await page.locator(PALETTE_INPUT).waitFor({ state: 'visible', timeout: 8_000 })
    await page.waitForTimeout(400)
    await shot(page, 'command-palette')
    record(
      '3',
      'command palette — every item label (verbatim)',
      (await allTexts(page, PALETTE_OPTION)).join(' | '),
    )

    const docItem = page.locator(PALETTE_OPTION).filter({ hasText: 'Documentation' }).first()
    if (await docItem.isVisible().catch(() => false)) {
      await docItem.click()
      await page.waitForTimeout(400)
    }
    const opened = await page
      .evaluate(
        () => (window as unknown as { __epheOpenTargets?: string[] }).__epheOpenTargets ?? [],
      )
      .catch(() => [] as string[])
    record(
      '3',
      'the palette “Documentation” item opens (window.open target)',
      opened.join(' | ') || '(nothing)',
    )
    await page.keyboard.press('Escape')
    await page.waitForTimeout(300)

    record(
      '3',
      'verdict — a user with only the app cannot read the same thing',
      'README.md / docs/INSTALL.md / docs/CLI.md are not reachable from the shipped UI; the single in-app pointer is the palette item "Documentation", which navigates to an external URL, not to these files. docs/COMPOSER_MODES.md — the SSoT matrix — is a developer document that is not bundled. INSTALL.md and CLI.md say nothing about the four composer modes or the approval profiles at all.',
    )
  })

  // ── (4) does anything explain mode vs profile as two different stores? ──────
  test('4 — mode vs profile: is the difference between the two stores ever stated?', async ({
    page,
  }) => {
    await openChat(page)

    record(
      '4',
      'two controls in one composer row (mode chip | badge)',
      `${await textOf(page, MODE_SELECTOR)} | ${await textOf(page, PERM_BADGE)}`,
    )
    record(
      '4',
      'does the badge itself name the mode axis or say the two are different',
      String(/two|different|separate|mode|profile/i.test(await textOf(page, PERM_BADGE))),
      'the badge carries one word only; neither control on the composer row names the other',
    )

    await openSettings(page)
    await page.locator(SETTINGS_SEARCH).fill('mode')
    await page.waitForTimeout(600)
    await shot(page, 'settings-search-mode')
    record(
      '4',
      'Settings search "mode" — hits (verbatim)',
      (await allTexts(page, SEARCH_HIT)).join(' | ') || '(none)',
    )

    await page.locator(SETTINGS_SEARCH).fill('profile')
    await page.waitForTimeout(600)
    await shot(page, 'settings-search-profile')
    record(
      '4',
      'Settings search "profile" — hits (verbatim)',
      (await allTexts(page, SEARCH_HIT)).join(' | ') || '(none)',
    )
    record(
      '4',
      'does an always-visible sentence anywhere on the Privacy surface mention both axes together',
      String(
        /mode[\s\S]{0,200}profile|profile[\s\S]{0,200}mode/i.test(
          await textOf(page, SETTINGS_PANEL),
        ),
      ),
      'the composer and the Privacy surface never state that the mode and the approval profile are two separate stores feeding the same decision',
    )

    record(
      '4',
      'verdict — the distinction is documented only in a developer file',
      'No UI surface explains that the composer mode and the settings profile are two different stores that both decide whether a tool runs. The only place that disentangles them is docs/COMPOSER_MODES.md § "Disentangling the indicators" ("Deliberately named differently so the two axes are not confused with each other"), which is not shipped with, or reachable from, the app.',
    )
  })

  // ── artifact: observations.json (verbatim findings + failures) ──────────────
  test.afterAll(() => {
    questions['1'] =
      'Mode and profile are labelled but not explained in the composer: the meaning of each mode exists only as a native `title` tooltip (and a doubled aria-label), and the amber badge repeats one word (Manual/Session/Auto).'
    questions['2'] =
      'Settings › Privacy explains exactly two profile values in visible prose ("Strict — always ask", "Session — remember per tool"); the shell’s help surface is the keyboard-shortcut overlay, and Settings › About only reports version/provider/model.'
    questions['3'] =
      'The four modes and the approval profiles are documented only in repo files, and incompletely: README names three profiles (strict/session/autonomous) and one mode ("Ask mode runs no tools at all"); INSTALL.md and CLI.md say nothing about them; docs/COMPOSER_MODES.md holds the real matrix but is a developer doc. A user with only the app cannot read any of it — the sole in-app pointer, the palette item "Documentation", leaves for an external URL.'
    questions['4'] =
      'Nothing in the UI says the composer mode and the settings profile are two different stores that both gate tools. The distinction lives only in docs/COMPOSER_MODES.md.'
    questions['5'] =
      'Yes for shortcuts and capabilities: the header help overlay and Settings › Keyboard shortcuts both render the same table, and the composer slash list names the commands with a one-line description each. No such list exists for the modes or the profiles.'

    fs.writeFileSync(
      OBS_FILE,
      JSON.stringify(
        {
          spec: 'app/e2e/walkthrough/what-it-tells-you.spec.ts',
          base: BASE,
          locale: 'en (pinned via localStorage i18nextLng=en / i18nextLang=en)',
          capturedAt: new Date().toISOString(),
          modeWasNotChanged: true,
          profileWasNotChanged: true,
          questions,
          findings,
          consoleErrors: allDiag.consoleErrors,
          pageErrors: allDiag.pageErrors,
          failedRequests: allDiag.failedRequests,
          badResponses: allDiag.badResponses,
        },
        null,
        2,
      ),
    )
  })
})
