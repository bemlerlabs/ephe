/**
 * Persona 05 — "change ONE setting" (the approval profile that decides whether
 * tools run without asking).
 *
 * This spec runs against the LIVE product server (built `app/dist` on
 * http://127.0.0.1:8765) with the REAL backend. Like the sibling walkthroughs it
 * mocks NOTHING — no `page.route`, no fixtures standing in for the API. Every
 * boolean it reports is read off the live DOM or off the live HTTP responses.
 *
 * The questions this run answers with evidence:
 *  (a) how many clicks does the path from the chat to the control take, and is
 *      the tab findable by its name alone?
 *  (b) does the command palette (Ctrl/Cmd+K) reach that CONTROL, only the TAB,
 *      or neither — and does its settings list match the real navigation?
 *  (c) after arriving on the tab, is the control merely visible or actually
 *      pointed at (scroll target, focus, highlight)?
 *  (d) can the user change it, save it, and see that it took effect?
 *
 * Every step is photographed full-page into the walkthrough capture dir
 * (walkthrough-out.ts); the dated set is
 * docs/media/user-walkthrough-2026-10-12/persona-05-einstellungen-suchen/.
 * The run appends its observed-facts block plus findings.json into that same
 * directory; the hand-written framing in notes.md is preserved.
 *
 * Selector policy: `data-testid` / ARIA role only — never a CSS class and never a
 * copy string, except where the copy itself is the subject (the nav search and
 * the palette search are driven by the rendered names, in both languages).
 */

import { test, expect, type APIRequestContext, type Locator, type Page } from '@playwright/test'
import path from 'node:path'
import fs from 'node:fs'
import { walkthroughOutDir } from './walkthrough-out.ts'

/** The live product server (built app/dist) — not the Vite dev server of playwright.config.ts. */
const BASE = (process.env.EPHE_WALKTHROUGH_BASE ?? 'http://127.0.0.1:8765').replace(/\/$/, '')
const CHAT = `${BASE}/#/chat`
const SECURITY_API = `${BASE}/api/settings/security`

const OUT_DIR = walkthroughOutDir('persona-05-einstellungen-suchen')
const NOTES = path.join(OUT_DIR, 'notes.md')
const FINDINGS = path.join(OUT_DIR, 'findings.json')
const RUNTIME_BEGIN = '<!-- RUNTIME:persona-05 BEGIN -->'
const RUNTIME_END = '<!-- RUNTIME:persona-05 END -->'

type Severity = 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO'

// ---- testids, straight out of app/src ----------------------------------------------
// Sidebar entry: dashboard/Sidebar.tsx:1507 (the ONLY settings entry in the shell).
const SIDEBAR_SETTINGS = '[data-testid="sidebar-settings-btn"]'
const SIDEBAR = '[data-testid="chat-sidebar"]'
// Settings page: dashboard/settings/index.tsx
const SETTINGS_PAGE = '[data-testid="settings-page"]'
const SETTINGS_BACK = '[data-testid="settings-back"]'
const SETTINGS_SEARCH = '[data-testid="settings-search"]'
const SETTINGS_ROW_HIT = '[data-testid^="settings-search-row-"]'
const SETTINGS_TAB_HIT = '[data-testid^="settings-search-tab-"]'
const SETTINGS_HITS_TABS = '[data-testid="settings-search-tabs-count"]'
const SETTINGS_HITS_FIELDS = '[data-testid="settings-search-fields-count"]'
const SETTINGS_EMPTY = '[data-testid="settings-search-empty"]'
const NAV_PRIVACY = '[data-testid="settings-nav-privacy"]'
/** Every real tab row. The nav group captions carry `settings-nav-group-*` and are not tabs. */
const NAV_TAB = '[data-testid^="settings-nav-"]:not([data-testid^="settings-nav-group-"])'
// The control itself: dashboard/settings/model/sections-misc.tsx:139,153
const PROFILE_ROW = '[data-testid="privacy-profile"]'
const PROFILE_STRICT = '[data-testid="security-profile-strict"]'
const PROFILE_SESSION = '[data-testid="security-profile-session"]'
// Footer save surface (index.tsx:406-425) — expected ABSENT on the privacy tab
const SAVE_BUTTON = '[data-testid="settings-save"]'
// The chat side: dashboard/chat/ComposerModeChip.tsx:41, ChatInput.tsx:525
const MODE_SELECTOR = '[data-testid="composer-mode-selector"]'
const PERMISSION_BADGE = '[data-testid="composer-permission-badge"]'
// The palette: components/ui/CommandPalette.tsx:126,139
const PALETTE_INPUT = 'input[role="combobox"][aria-controls="cmd-palette-listbox"]'
const PALETTE_LISTBOX = '#cmd-palette-listbox'

type Lang = 'en' | 'de'

/**
 * Rendered names as the app really prints them (locales/*.json). Only used to TYPE
 * into the two search fields and to check absence — the copy is the subject here,
 * so it is data, not decoration.
 */
const NAMES = {
  tabPrivacy: { en: 'Privacy', de: 'Datenschutz' },
  control: { en: 'Approval profile', de: 'Freigabe-Profil' },
  settingsSection: { en: 'Settings', de: 'Einstellungen' },
  /** The seven tools tabs the palette's key list does not carry (settings/model.tsx NAV). */
  missingFromPaletteKeys: [
    { en: 'Appearance', de: 'Erscheinung' },
    { en: 'Behaviour', de: 'Verhalten' },
    { en: 'Ephemerality', de: 'Ephemerität' },
    { en: 'Hooks', de: 'Hooks' },
    { en: 'Code execution', de: 'Code-Ausführung' },
    { en: 'Keyboard shortcuts', de: 'Tastatur-Kürzel' },
    { en: 'Network', de: 'Netzwerk' },
  ],
  /** The palette key 'deep' has NO translation in either locale (settings.deep is absent). */
  phantomKey: 'settings.deep',
} as const

// ---- per-run bookkeeping -------------------------------------------------------------
let shotIndex = 0
let stepTitle = ''
let stepLines: string[] = []
const perStep = new Map<string, string[]>()
const consoleEvents: { type: string; text: string }[] = []
const pageErrors: string[] = []
const requestFailures: string[] = []
const shots: string[] = []
/** Pointer clicks, counted for the whole file (a keyboard shortcut is not a click). */
let clicks = 0
const report: Record<string, unknown> = {}

function record(text: string, severity: Severity = 'INFO'): void {
  stepLines.push(severity === 'INFO' ? `- ${text}` : `- **[${severity}]** ${text}`)
  console.log(`[persona-05] ${severity} ${text}`)
}

function put(key: string, value: unknown): void {
  report[key] = value
}

/** A sub-object of the report that is never undefined (Playwright may re-import the
 *  file in a second worker after a failing step, so nothing may assume a sibling
 *  step already created its bag). */
function bag(key: string): Record<string, unknown> {
  const cur = report[key]
  if (cur && typeof cur === 'object') return cur as Record<string, unknown>
  const fresh: Record<string, unknown> = {}
  report[key] = fresh
  return fresh
}

/**
 * Deterministic shot numbers, so the documented arc keeps its names even when a
 * failing step makes Playwright restart the worker (a worker restart resets every
 * module-level counter in this file).
 */
const SHOT_BASE: Record<number, number> = { 1: 1, 2: 2, 3: 5, 4: 7, 5: 11 }

function setShot(n: number): void {
  shotIndex = n - 1
}

async function shoot(page: Page, name: string, at?: number): Promise<string> {
  if (at !== undefined) setShot(at)
  shotIndex += 1
  const file = path.join(OUT_DIR, `${String(shotIndex).padStart(2, '0')}-${name}.png`)
  await page.screenshot({ path: file, fullPage: true })
  shots.push(path.basename(file))
  record(`Screenshot ${path.basename(file)}`)
  return file
}

async function innerText(loc: Locator): Promise<string> {
  try {
    // Explicit timeout: with actionTimeout unset, locator.innerText() waits for the
    // whole test budget when the element is absent (each counter badge is only
    // rendered once it has something to count).
    return (await loc.first().innerText({ timeout: 2500 })).replace(/\s+/g, ' ').trim()
  } catch {
    return ''
  }
}

async function isVisible(loc: Locator): Promise<boolean> {
  try {
    return await loc.first().isVisible()
  } catch {
    return false
  }
}

/** One pointer click, counted and logged. The counted unit is the user's click. */
async function pointerClick(loc: Locator, what: string): Promise<boolean> {
  try {
    await loc.first().click({ timeout: 15_000 })
    clicks += 1
    record(`click #${clicks} — ${what}`)
    return true
  } catch {
    record(`click FAILED — ${what} (locator not actionable)`, 'HIGH')
    return false
  }
}

function resetClicks(): void {
  clicks = 0
}

// ---- per-step persistence -------------------------------------------------------------
// A failing step makes Playwright restart the worker, which wipes every module-level
// counter above (that is how the first run lost steps 1-4 from findings.json). Each
// step therefore snapshots its own findings to disk, and a following step seeds itself
// from the parts the earlier steps of the same run wrote.

const PARTS_DIR = path.join(OUT_DIR, 'parts')

interface Part {
  step: number
  title: string
  lines: string[]
  shots: string[]
  report: Record<string, unknown>
  console: { type: string; text: string }[]
  pageErrors: string[]
  failedRequests: string[]
}

let stepIndex = 0
let consoleStart = 0
let pageErrorStart = 0
let requestFailureStart = 0
/** High-water marks of the last flush — events after these arrived post-flush. */
let flushedConsole = 0
let flushedPageErrors = 0
let flushedRequests = 0

function readParts(): Part[] {
  let names: string[] = []
  try {
    names = fs.readdirSync(PARTS_DIR)
  } catch {
    return []
  }
  const out: Part[] = []
  for (const n of names.sort()) {
    if (!/^step-\d+\.json$/.test(n)) continue
    try {
      out.push(JSON.parse(fs.readFileSync(path.join(PARTS_DIR, n), 'utf8')) as Part)
    } catch {
      /* a half-written part is not worth failing the run over */
    }
  }
  return out.sort((a, b) => a.step - b.step)
}

/** Take over everything the earlier steps of this run measured. */
function seedFromParts(step: number): void {
  for (const p of readParts()) {
    if (p.step >= step) continue
    Object.assign(report, p.report)
  }
}

function flushPart(): void {
  if (!stepIndex) return
  const part: Part = {
    step: stepIndex,
    title: stepTitle,
    lines: stepLines.slice(),
    shots: shots.slice(),
    report: { ...report },
    console: consoleEvents.slice(consoleStart),
    pageErrors: pageErrors.slice(pageErrorStart),
    failedRequests: requestFailures.slice(requestFailureStart),
  }
  fs.mkdirSync(PARTS_DIR, { recursive: true })
  fs.writeFileSync(
    path.join(PARTS_DIR, `step-${part.step}.json`),
    `${JSON.stringify(part, null, 2)}\n`,
    'utf8',
  )
  flushedConsole = consoleEvents.length
  flushedPageErrors = pageErrors.length
  flushedRequests = requestFailures.length
}

// ---- live-navigation helpers ---------------------------------------------------------

async function gotoChat(page: Page): Promise<void> {
  try {
    await page.goto(CHAT, { waitUntil: 'domcontentloaded', timeout: 30_000 })
  } catch {
    throw new Error(
      `Live server at ${BASE} is not reachable. Build and serve app/dist on ${BASE} ` +
        'before running this walkthrough; do not mock it.',
    )
  }
  await expect(page.locator(SIDEBAR)).toBeVisible({ timeout: 30_000 })
}

/**
 * The language the running app really uses: the settings back button carries
 * `← Back to the task` / `← Zurück zur Aufgabe`, so the text decides it.
 */
async function detectLang(page: Page): Promise<Lang> {
  const back = await innerText(page.locator(SETTINGS_BACK))
  const lang: Lang = back.includes('Zurück') ? 'de' : 'en'
  record(`Live UI language: ${lang} (back button reads "${back || '(empty)'}")`)
  return lang
}

async function openSettingsFromSidebar(page: Page): Promise<boolean> {
  const btn = page.locator(SIDEBAR_SETTINGS)
  if (!(await isVisible(btn))) {
    record('The sidebar has no visible settings entry at this viewport.', 'HIGH')
    return false
  }
  record(`Sidebar settings entry reads "${await innerText(btn)}"`)
  const ok = await pointerClick(
    btn,
    'sidebar "settings & profile" (the shell\'s only settings entry)',
  )
  try {
    await page.locator(SETTINGS_PAGE).waitFor({ state: 'visible', timeout: 20_000 })
  } catch {
    record('Settings page did not open after the click.', 'HIGH')
    return false
  }
  return ok
}

/** Active tab as the page presents it: the H1, the highlighted nav row, and how many
 *  tab rows the nav currently shows (typing in the settings search replaces the whole
 *  nav list with the hits, so both the rows and the highlight can be gone). */
async function activeTab(
  page: Page,
): Promise<{ title: string; activeNav: string | null; navRows: number; searchQuery: string }> {
  return page.evaluate(() => {
    const h1 = document.querySelector('[data-testid="settings-title-h1"]')
    const navs = Array.from(
      document.querySelectorAll(
        '[data-testid^="settings-nav-"]:not([data-testid^="settings-nav-group-"])',
      ),
    )
    const active = navs.find((n) => (n as HTMLElement).className.includes('text-brand'))
    return {
      title: (h1?.textContent ?? '').trim(),
      activeNav: active ? active.getAttribute('data-testid') : null,
      navRows: navs.length,
      searchQuery:
        (document.querySelector('[data-testid="settings-search"]') as HTMLInputElement | null)
          ?.value ?? '',
    }
  })
}

interface ProfileState {
  rowPresent: boolean
  strictChecked: string | null
  sessionChecked: string | null
  strictText: string
  sessionText: string
  title: string
  saveButtonPresent: boolean
  savedIndicatorPresent: boolean
}

async function readProfileState(page: Page): Promise<ProfileState> {
  return page.evaluate(() => {
    const q = (sel: string) => document.querySelector(sel) as HTMLElement | null
    const attr = (sel: string, name: string) => q(sel)?.getAttribute(name) ?? null
    return {
      rowPresent: !!q('[data-testid="privacy-profile"]'),
      strictChecked: attr('[data-testid="security-profile-strict"]', 'aria-checked'),
      sessionChecked: attr('[data-testid="security-profile-session"]', 'aria-checked'),
      strictText: (q('[data-testid="security-profile-strict"]')?.innerText ?? '').trim(),
      sessionText: (q('[data-testid="security-profile-session"]')?.innerText ?? '').trim(),
      title: (q('[data-testid="settings-title-h1"]')?.innerText ?? '').trim(),
      saveButtonPresent: !!q('[data-testid="settings-save"]'),
      savedIndicatorPresent: !!q('[data-testid="settings-saved"]'),
    }
  })
}

/** Question (c): is the control merely visible, or actually pointed at? */
async function readPointing(page: Page): Promise<Record<string, unknown>> {
  return page.evaluate(() => {
    const row = document.querySelector('[data-testid="privacy-profile"]') as HTMLElement | null
    const group = (row?.parentElement?.closest('[data-testid]') ?? null) as HTMLElement | null
    const panel = document.querySelector('[data-testid="settings-panel"]') as HTMLElement | null
    const nav = document.querySelector('[data-testid="settings-nav-privacy"]') as HTMLElement | null
    const active = document.activeElement as HTMLElement | null
    const rect = row?.getBoundingClientRect()
    const cs = row ? getComputedStyle(row) : null
    return {
      rowPresent: !!row,
      rowTestId: row?.getAttribute('data-testid') ?? null,
      rowInViewport: rect ? rect.top >= 0 && rect.bottom <= window.innerHeight : false,
      rowTopPx: rect ? Math.round(rect.top) : null,
      rowHeightPx: rect ? Math.round(rect.height) : null,
      viewportHeightPx: window.innerHeight,
      panelScrollTop: panel ? Math.round(panel.scrollTop) : null,
      rowOrChildHasFocus: !!row && (row === active || row.contains(active)),
      focusedElement: active
        ? `${active.tagName.toLowerCase()}${
            active.getAttribute('data-testid') ? `[${active.getAttribute('data-testid')}]` : ''
          }`
        : null,
      rowOutline:
        cs && cs.outlineStyle !== 'none' ? `${cs.outlineStyle} ${cs.outlineWidth}` : 'none',
      rowBoxShadow: cs?.boxShadow ?? null,
      rowAriaCurrent: row?.getAttribute('aria-current') ?? null,
      rowClassesWithRing: row
        ? ['ring-1', 'ring-2', 'outline', 'ring-brand'].filter((c) => row.className.includes(c))
        : [],
      navRowHighlighted: nav ? nav.className.includes('text-brand') : null,
      nearestGroupTestId: group?.getAttribute('data-testid') ?? null,
      deepSectionAnchorsPresent: document.querySelectorAll('[data-testid^="deep-section-"]').length,
    }
  })
}

// ---- live ground truth (the real endpoint, not the UI) --------------------------------

async function apiGetProfile(
  request: APIRequestContext,
): Promise<{ reachable: boolean; status: number; profile: string | null; raw: string }> {
  try {
    const res = await request.get(SECURITY_API, { timeout: 15_000 })
    const raw = await res.text()
    let profile: string | null = null
    try {
      profile = (JSON.parse(raw) as { approval_profile?: string }).approval_profile ?? null
    } catch {
      profile = null
    }
    return { reachable: true, status: res.status(), profile, raw }
  } catch {
    return { reachable: false, status: 0, profile: null, raw: '' }
  }
}

// ---- palette helpers ------------------------------------------------------------------

interface PaletteGroup {
  heading: string
  items: string[]
}

async function paletteOpen(page: Page): Promise<boolean> {
  if (await isVisible(page.locator(PALETTE_LISTBOX))) return true
  // Ctrl+K first (the hook accepts ctrlKey or metaKey); Meta+K as a fallback.
  for (const key of ['Control+k', 'Meta+k']) {
    await page.keyboard.press(key)
    try {
      await page.locator(PALETTE_LISTBOX).waitFor({ state: 'visible', timeout: 4000 })
      record(`Palette opened with ${key}`)
      return true
    } catch {
      /* try the next chord */
    }
  }
  record('The command palette did not open (Ctrl+K and Cmd+K both failed).', 'HIGH')
  return false
}

async function readPalette(page: Page): Promise<PaletteGroup[]> {
  return page.evaluate(() => {
    const box = document.querySelector('#cmd-palette-listbox')
    if (!box) return []
    const out: { heading: string; items: string[] }[] = []
    for (const group of Array.from(box.children)) {
      const heading = (group.querySelector('p')?.textContent ?? '').trim()
      const items = Array.from(group.querySelectorAll('ul li button')).map(
        (b) => ((b as HTMLElement).innerText ?? '').split('\n')[0]?.trim() ?? '',
      )
      if (items.length) out.push({ heading, items })
    }
    return out
  })
}

/** The palette section that carries the settings tabs = the group holding the tab's own name. */
function settingsGroupOf(groups: PaletteGroup[], tabName: string): PaletteGroup | null {
  return groups.find((g) => g.items.some((i) => i.toLowerCase() === tabName.toLowerCase())) ?? null
}

function labelPresent(items: string[], variants: { en: string; de: string }): boolean {
  const low = items.map((i) => i.toLowerCase())
  return low.includes(variants.en.toLowerCase()) || low.includes(variants.de.toLowerCase())
}

// ======================================================================================

test.describe('persona-05 — change one setting (approval profile)', () => {
  test.use({ viewport: { width: 1440, height: 900 } })
  test.setTimeout(180_000)

  test.beforeAll(() => {
    fs.mkdirSync(OUT_DIR, { recursive: true })
    put('target', BASE)
    put('startedAt', new Date().toISOString())
    put('viewport', '1440x900')
  })

  test.beforeEach(async ({ page }) => {
    stepTitle = test.info().title
    stepLines = []
    perStep.set(stepTitle, stepLines)

    const parsed = /^step\s+(\d+)/i.exec(stepTitle)
    stepIndex = parsed?.[1] ? Number(parsed[1]) : stepIndex + 1
    seedFromParts(stepIndex)
    setShot(SHOT_BASE[stepIndex] ?? shotIndex + 1)
    consoleStart = consoleEvents.length
    pageErrorStart = pageErrors.length
    requestFailureStart = requestFailures.length

    page.on('console', (msg) => {
      if (msg.type() === 'error' || msg.type() === 'warning') {
        consoleEvents.push({ type: msg.type(), text: msg.text() })
      }
    })
    page.on('pageerror', (err) => pageErrors.push(err.message))
    page.on('requestfailed', (req) => {
      requestFailures.push(
        `${req.method()} ${req.url()} — ${req.failure()?.errorText ?? 'unknown'}`,
      )
    })
  })

  test.afterEach(() => {
    flushPart()
  })

  // ---- STEP 1 ------------------------------------------------------------------------
  test('step 1 — the chat, and what the user already sees about approvals', async ({ page }) => {
    await gotoChat(page)

    // What does the user find in the chat about "tools running without asking"?
    const badge = page.locator(PERMISSION_BADGE)
    const hasBadge = await isVisible(badge)
    record(
      hasBadge
        ? `The composer shows an approval badge: "${await innerText(badge)}" (role=status — a readout, not a control)`
        : 'No approval badge in the composer.',
      hasBadge ? 'INFO' : 'MEDIUM',
    )
    put('a', {
      chatApprovalBadgeVisible: hasBadge,
      chatApprovalBadgeText: hasBadge ? await innerText(badge) : '',
    })

    const modeChip = page.locator(MODE_SELECTOR)
    const hasMode = await isVisible(modeChip)
    const modeText = hasMode ? await innerText(modeChip) : ''
    record(
      hasMode
        ? `A second, interactive control in the chat: the composer mode selector reads "${modeText}" (a per-task response mode, not the saved approval profile)`
        : 'No composer mode selector in the chat.',
      'INFO',
    )
    bag('a').chatModeSelectorText = modeText
    bag('a').chatModeSelectorVisible = hasMode

    // Is the sidebar settings entry (the only one in the shell) on screen?
    const entry = page.locator(SIDEBAR_SETTINGS)
    const entryVisible = await isVisible(entry)
    record(
      entryVisible
        ? `Settings entry in the shell: "${await innerText(entry)}" [data-testid=sidebar-settings-btn]`
        : 'The shell shows no settings entry at 1440x900.',
      entryVisible ? 'INFO' : 'HIGH',
    )
    bag('a').settingsEntryVisible = entryVisible

    await shoot(page, 'chat-start')
    expect(entryVisible).toBe(true)
  })

  // ---- STEP 2 ------------------------------------------------------------------------
  test('step 2 — path from the chat: sidebar → tab by name (clicks counted)', async ({ page }) => {
    await gotoChat(page)
    resetClicks()

    await openSettingsFromSidebar(page)
    const lang = await detectLang(page)
    put('locale', lang)

    const landing = await activeTab(page)
    record(
      `Settings opens on tab "${landing.title}" (active nav row: ${landing.activeNav ?? 'none highlighted'})`,
      landing.activeNav ? 'INFO' : 'MEDIUM',
    )

    const navCount = await page
      .locator(NAV_TAB)
      .count()
      .catch(() => 0)
    const navLabels = (await page.locator(NAV_TAB).allInnerTexts())
      .map((s) => s.replace(/\s+/g, ' ').trim())
      .filter(Boolean)
    record(`The settings navigation really offers ${navCount} tabs: ${navLabels.join(' | ')}`)
    put('navTabCount', navCount)
    put('navTabLabels', navLabels)
    await shoot(page, 'settings-open-landing-tab')

    // (a) Is the tab findable by its NAME alone inside the settings search?
    const search = page.locator(SETTINGS_SEARCH)
    const searchVisible = await isVisible(search)
    record(
      searchVisible
        ? `The nav carries its own search field [data-testid=settings-search] ("${await innerText(
            search,
          )}")`
        : 'No search field inside the settings navigation.',
      searchVisible ? 'INFO' : 'HIGH',
    )

    const tabName = NAMES.tabPrivacy[lang]
    let tabByName = false
    if (searchVisible) {
      await pointerClick(search, 'the settings search field')
      await search.fill(tabName)
      await page.waitForTimeout(400)
      const tabHits = await page.locator(SETTINGS_TAB_HIT).count()
      const tabsCount = await innerText(page.locator(SETTINGS_HITS_TABS))
      tabByName = tabHits > 0
      record(
        `Typing the tab's own name ("${tabName}") → ${tabHits} tab hit(s)` +
          (tabsCount ? ` (counter reads ${tabsCount})` : '') +
          `; empty state shown: ${await isVisible(page.locator(SETTINGS_EMPTY))}`,
        tabByName ? 'INFO' : 'HIGH',
      )
      await shoot(page, 'search-tab-by-name')

      const hit = page.locator(SETTINGS_TAB_HIT).first()
      const hitLabel = await innerText(hit)
      if (await pointerClick(hit, `the tab hit "${hitLabel}"`)) {
        await page.waitForTimeout(500)
      }
      const after = await activeTab(page)
      record(
        `After the jump the page shows "${after.title}" (nav: ${after.activeNav ?? 'none'}; ` +
          `${after.navRows} tab row(s) listed, the search field still holds "${after.searchQuery}")`,
      )
      put('a_navRowsAfterJump', after.navRows)
      await shoot(page, 'tab-reached-by-name')
    }

    const pathNavClicks = clicks
    record(
      `Measured pointer clicks for the direct path (settings entry + tab row) = ${pathNavClicks}`,
    )
    put('a_pathSearchNameClicks', pathNavClicks)
    put('a_tabFindableByName', tabByName)
    bag('a').settingsLandingTab = landing.title
    bag('a').settingsSearchVisible = searchVisible
  })

  // ---- STEP 3 ------------------------------------------------------------------------
  test('step 3 — the CONTROL by its own name, and what "arrived" looks like', async ({ page }) => {
    await gotoChat(page)
    resetClicks()
    await openSettingsFromSidebar(page)
    const lang = (report.locale as Lang) ?? (await detectLang(page))

    const controlName = NAMES.control[lang]
    const search = page.locator(SETTINGS_SEARCH)
    await pointerClick(search, 'the settings search field')
    await search.fill(controlName)
    await page.waitForTimeout(400)

    const rowHits = await page.locator(SETTINGS_ROW_HIT).count()
    const tabsCount = await innerText(page.locator(SETTINGS_HITS_TABS))
    const fieldsCount = await innerText(page.locator(SETTINGS_HITS_FIELDS))
    const rowLabels = (await page.locator(SETTINGS_ROW_HIT).allInnerTexts())
      .map((s) => s.replace(/\s+/g, ' ').trim())
      .filter(Boolean)
    record(
      `Typing the CONTROL's own name ("${controlName}") in the settings search → ` +
        `${rowHits} setting row(s): ${rowLabels.join(' | ') || '(none)'}; ` +
        `tab hits: ${tabsCount || '-'} (${await page.locator(SETTINGS_TAB_HIT).count()}), ` +
        `field hits (counter): ${fieldsCount || '-'}`,
      rowHits > 0 ? 'INFO' : 'HIGH',
    )
    put('a_controlNameRowHits', rowHits)
    put('a_controlNameRowLabels', rowLabels)
    put('a_controlNameTabHits', await page.locator(SETTINGS_TAB_HIT).count())
    const tabsBadgePresent = (await page.locator(SETTINGS_HITS_TABS).count()) > 0
    record(
      tabsBadgePresent
        ? `Both counter badges are rendered (tabs "${tabsCount}", fields "${fieldsCount}").`
        : 'The tabs counter badge [data-testid=settings-search-tabs-count] is not in the DOM when ' +
            'the query has no tab hit, while the fields counter always is. The absent element — not ' +
            'a rendered zero — is what stalled the first run of this spec: with actionTimeout unset, ' +
            'locator.innerText() waits for the whole test budget.',
      tabsBadgePresent ? 'INFO' : 'LOW',
    )
    put('a_controlNameTabsCounterRendered', tabsBadgePresent)
    await shoot(page, 'search-control-by-name')

    // Click the row hit for the approval profile itself.
    const controlRow = page.locator(SETTINGS_ROW_HIT).filter({ hasText: controlName }).first()
    const clickedRow = await pointerClick(controlRow, `the row hit named like the control`)
    await page.waitForTimeout(600)

    const arrived = await activeTab(page)
    record(
      `After clicking the row hit the page shows "${arrived.title}" (nav: ${
        arrived.activeNav ?? 'none'
      }; ${arrived.navRows} tab row(s) listed, the search field still holds "${
        arrived.searchQuery
      }"); the control row present: ${await isVisible(page.locator(PROFILE_ROW))}`,
    )
    if (
      arrived.title.toLowerCase().includes(NAMES.tabPrivacy[lang].toLowerCase()) &&
      arrived.activeNav === null
    ) {
      record(
        'The jump arrives on the right tab, but with no tab context: the settings search keeps its ' +
          'query, so the nav shows the hit list instead of the tab rows and no row is highlighted. ' +
          'Nothing marks the control either (see the pointing evidence below).',
        'MEDIUM',
      )
    }
    put('a_navRowsAfterArrival', arrived.navRows)
    put('a_activeNavAfterArrival', arrived.activeNav)
    await shoot(page, 'privacy-tab-arrived')

    // (c) visible — or pointed at?
    const pointing = await readPointing(page)
    record(`Pointing evidence: ${JSON.stringify(pointing)}`)
    put('c_pointing', pointing)
    const pointedAt =
      Boolean(pointing.rowOrChildHasFocus) ||
      (pointing.rowClassesWithRing as string[]).length > 0 ||
      pointing.rowOutline !== 'none' ||
      !pointing.rowInViewport
    record(
      pointedAt
        ? 'The control is not merely visible: focus/highlight/scroll identifies it.'
        : 'VERDICT (c): the control is only VISIBLE. No focus, no highlight, no anchor — the jump ' +
            'scrolls the content column to its top and names nothing.',
      pointedAt ? 'INFO' : 'MEDIUM',
    )
    put('c_pointedAtControl', pointedAt)
    put('c_rowInViewport', pointing.rowInViewport)

    if (clickedRow) {
      put('a_pathSearchControlClicks', clicks)
      record(`Measured pointer clicks for the search path (entry + field + row hit) = ${clicks}`)
    }
  })

  // ---- STEP 4 ------------------------------------------------------------------------
  test('step 4 — change it, save it, see that it took effect', async ({ page, request }) => {
    await gotoChat(page)
    resetClicks()
    await openSettingsFromSidebar(page)
    const lang = (report.locale as Lang) ?? (await detectLang(page))

    // Walk to the tab by name (the honest user path measured in step 2).
    const search = page.locator(SETTINGS_SEARCH)
    await search.fill(NAMES.tabPrivacy[lang])
    await page.waitForTimeout(400)
    const tabHit = page.locator(SETTINGS_TAB_HIT).first()
    if (await isVisible(tabHit)) await pointerClick(tabHit, 'the privacy tab hit')
    else if (await isVisible(page.locator(NAV_PRIVACY)))
      await pointerClick(page.locator(NAV_PRIVACY), 'the privacy nav row')
    await page.locator(PROFILE_ROW).waitFor({ state: 'visible', timeout: 20_000 })

    const before = await readProfileState(page)
    const saveVisible = await isVisible(page.locator(SAVE_BUTTON))
    const serverBefore = await apiGetProfile(request)
    record(
      `Radios before: strict="${before.strictChecked}" (${before.strictText}) · ` +
        `session="${before.sessionChecked}" (${before.sessionText})`,
    )
    record(
      serverBefore.reachable
        ? `Live GET /api/settings/security → ${serverBefore.status} ${serverBefore.raw}`
        : 'GET /api/settings/security unreachable — the panel state is the only read.',
      serverBefore.reachable ? 'INFO' : 'HIGH',
    )
    record(
      saveVisible || before.saveButtonPresent
        ? 'A footer save button IS present on this tab.'
        : 'No footer save button on this tab — the control has to write itself on click ' +
            '(READONLY_TABS carries privacy, settings/types.ts:64).',
      saveVisible ? 'MEDIUM' : 'INFO',
    )
    put('d_saveButtonVisible', saveVisible)
    await shoot(page, 'profile-before')

    const current = serverBefore.profile ?? (before.strictChecked === 'true' ? 'strict' : 'session')
    const target = current === 'strict' ? 'session' : 'strict'
    const targetRadio = page.locator(target === 'strict' ? PROFILE_STRICT : PROFILE_SESSION)

    const putResponse = page
      .waitForResponse(
        (r) => r.url().includes('/api/settings/security') && r.request().method() === 'PUT',
        { timeout: 15_000 },
      )
      .catch(() => null)

    await pointerClick(targetRadio, `the "${target}" profile radio`)
    const res = await putResponse
    // The write reaches the server first; the React state follows a paint later. A read
    // taken the instant the PUT resolves can still show the old radio (measured <=200 ms
    // behind on the live app), so let one beat pass and keep both reads as evidence.
    const uiRightAtResponse = await readProfileState(page)
    await page.waitForTimeout(400)
    const uiAfterClick = await readProfileState(page)
    const serverAfter = await apiGetProfile(request)

    if (res) {
      const body = await res.text().catch(() => '')
      record(
        `PUT /api/settings/security → ${res.status()}; payload ` +
          `${res.request().postData() ?? '(none)'}; answer ${body}`,
        res.status() < 400 ? 'INFO' : 'HIGH',
      )
      put('d_putStatus', res.status())
      put('d_putAnswer', body)
    } else {
      record('No PUT /api/settings/security response arrived within 15 s.', 'HIGH')
      put('d_putStatus', null)
    }
    record(
      `UI after the click: strict="${uiAfterClick.strictChecked}" session="${uiAfterClick.sessionChecked}" ` +
        `(read 0.4 s after the PUT response; the same read taken right at the response still showed ` +
        `strict="${uiRightAtResponse.strictChecked}" session="${uiRightAtResponse.sessionChecked}" — ` +
        'the local radio state follows the write a paint later, so this is render latency, not a lost change)',
    )
    put(
      'd_uiRightAtResponse',
      uiRightAtResponse[target === 'strict' ? 'strictChecked' : 'sessionChecked'],
    )
    record(
      `Live GET after the click → ${serverAfter.status} ${serverAfter.raw}`,
      serverAfter.profile === target ? 'INFO' : 'HIGH',
    )
    await shoot(page, 'profile-after-change')

    put('d_initialProfile', current)
    put('d_clickedProfile', target)
    put(
      'd_uiShowsChange',
      uiAfterClick[target === 'strict' ? 'strictChecked' : 'sessionChecked'] === 'true',
    )
    put('d_serverShowsChange', serverAfter.profile === target)
    put('d_saveButtonPresent', before.saveButtonPresent)
    bag('d').toastsAfterClick = await page
      .locator('[role="status"]')
      .allInnerTexts()
      .catch(() => [])

    expect.soft(serverAfter.profile, 'the live profile must equal the clicked one').toBe(target)

    // Does it survive a reload? (The strongest "saved" evidence the app can give.)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('chat-sidebar')).toBeVisible({ timeout: 30_000 })
    await openSettingsFromSidebar(page)
    const search2 = page.locator(SETTINGS_SEARCH)
    await search2.fill(NAMES.tabPrivacy[lang])
    await page.waitForTimeout(400)
    const tabHit2 = page.locator(SETTINGS_TAB_HIT).first()
    if (await isVisible(tabHit2)) await pointerClick(tabHit2, 'the privacy tab hit (after reload)')
    await page.locator(PROFILE_ROW).waitFor({ state: 'visible', timeout: 20_000 })
    const afterReload = await readProfileState(page)
    const persisted =
      afterReload[target === 'strict' ? 'strictChecked' : 'sessionChecked'] === 'true'
    record(
      `After a full reload the tab still shows ${target}: ${persisted} ` +
        `(strict="${afterReload.strictChecked}" session="${afterReload.sessionChecked}")`,
      persisted ? 'INFO' : 'HIGH',
    )
    put('d_persistedAfterReload', persisted)
    await shoot(page, 'profile-after-reload')

    // Leave the machine as it was found: put the original profile back.
    const restoreRadio = page.locator(current === 'strict' ? PROFILE_STRICT : PROFILE_SESSION)
    const restoreResponse = page
      .waitForResponse(
        (r) => r.url().includes('/api/settings/security') && r.request().method() === 'PUT',
        { timeout: 15_000 },
      )
      .catch(() => null)
    await pointerClick(restoreRadio, `the original "${current}" profile radio (restore)`)
    await restoreResponse
    const serverRestored = await apiGetProfile(request)
    record(
      `Restore: live GET → ${serverRestored.status} ${serverRestored.raw} ` +
        `(expected ${current})`,
      serverRestored.profile === current ? 'INFO' : 'HIGH',
    )
    put('d_restoredToInitial', serverRestored.profile === current)
    await shoot(page, 'profile-restored')

    expect
      .soft(serverRestored.profile, 'the walkthrough must not leave a changed profile')
      .toBe(current)
  })

  // ---- STEP 5 ------------------------------------------------------------------------
  test('step 5 — the command palette: control, tab, or neither?', async ({ page }) => {
    await gotoChat(page)
    const lang = (report.locale as Lang) ?? 'en'
    const tabName = NAMES.tabPrivacy[lang]
    const controlName = NAMES.control[lang]

    if (!(await paletteOpen(page))) return
    await page.waitForTimeout(400)
    await shoot(page, 'palette-open')

    const groups = await readPalette(page)
    const total = groups.reduce((n, g) => n + g.items.length, 0)
    const settingsGroup = settingsGroupOf(groups, tabName)
    const settingsItems = settingsGroup?.items ?? []
    const navCount = (report.navTabCount as number) ?? 0
    record(
      `Palette lists ${total} entries in ${groups.length} sections. Its settings section ` +
        `("${settingsGroup?.heading ?? 'not found'}") carries ${settingsItems.length} entries: ` +
        `${settingsItems.join(' | ') || '(none)'}`,
    )
    record(
      `The real settings navigation has ${navCount} tabs — the palette offers ` +
        `${settingsItems.length} (${navCount - settingsItems.length} tabs unreachable through it).`,
      settingsItems.length === navCount ? 'INFO' : 'HIGH',
    )

    const missing = NAMES.missingFromPaletteKeys.filter((k) => !labelPresent(settingsItems, k))
    const phantom = settingsItems.filter((i) => i === NAMES.phantomKey)
    record(
      `Not reachable through the palette: ${missing.map((k) => k.en).join(', ') || '(none)'}`,
      missing.length ? 'HIGH' : 'INFO',
    )
    record(
      phantom.length
        ? `The palette carries "${NAMES.phantomKey}" — a raw i18n key with no tab behind it ` +
            '(settings/model.tsx NAV has no such key; locales/*.json has no such string).'
        : 'No phantom entry in the palette settings list.',
      phantom.length ? 'HIGH' : 'INFO',
    )
    put('b_paletteSettingsCount', settingsItems.length)
    put('b_paletteSettingsLabels', settingsItems)
    put('b_paletteTotalEntries', total)
    put(
      'b_missingTabs',
      missing.map((k) => k.en),
    )
    put('b_phantomEntries', phantom)

    // (b) Does the palette reach the CONTROL by name?
    const input = page.locator(PALETTE_INPUT)
    await input.fill(controlName)
    await page.waitForTimeout(500)
    const controlGroups = await readPalette(page)
    const controlHits = controlGroups.flatMap((g) => g.items)
    record(
      `Palette with the control's own name ("${controlName}") → ${controlHits.length} hit(s): ` +
        `${controlHits.join(' | ') || '(nothing)'}`,
    )
    const hitsTheControl = controlHits.some((h) =>
      h.toLowerCase().includes(controlName.toLowerCase()),
    )
    record(
      hitsTheControl
        ? 'The palette DOES offer an entry named like the control.'
        : 'VERDICT (b): the palette cannot reach the CONTROL. Its settings entries are tab names ' +
            'only (SETTINGS_NAV_KEYS in hooks/paletteExtraItems.ts:9), so a name search finds nothing.',
      hitsTheControl ? 'INFO' : 'MEDIUM',
    )
    put('b_controlReachableByName', hitsTheControl)
    put('b_controlQueryHits', controlHits)
    await shoot(page, 'palette-control-name-query')

    // Does it at least reach the TAB?
    await input.fill(tabName)
    await page.waitForTimeout(500)
    const tabGroups = await readPalette(page)
    const tabHit = page.locator(`${PALETTE_LISTBOX} li button`).filter({ hasText: tabName }).first()
    const tabEntryPresent = await isVisible(tabHit)
    record(
      `Palette with the tab's own name ("${tabName}") → hits: ` +
        `${tabGroups.flatMap((g) => g.items).join(' | ') || '(nothing)'}`,
      tabEntryPresent ? 'INFO' : 'HIGH',
    )
    put('b_tabReachableByName', tabEntryPresent)
    await shoot(page, 'palette-tab-name-query')

    if (tabEntryPresent) {
      await pointerClick(tabHit, `the palette entry "${tabName}"`)
      try {
        await page.locator(SETTINGS_PAGE).waitFor({ state: 'visible', timeout: 20_000 })
      } catch {
        record('The palette entry did not open settings at all.', 'HIGH')
      }
      await page.waitForTimeout(700)
      const landed = await activeTab(page)
      const rowPresent = await isVisible(page.locator(PROFILE_ROW))
      record(
        `The palette entry opened settings on "${landed.title}" (nav: ${landed.activeNav ?? 'none'}); ` +
          `the wanted control is on screen: ${rowPresent}`,
        rowPresent ? 'INFO' : 'HIGH',
      )
      await shoot(page, 'palette-tab-landing')
      put('b_paletteLandingTab', landed.title)
      put('b_paletteLandsOnControl', rowPresent)
      put('b_paletteEntryClicks', 1)
      // The code reason if the landing tab is not the one that was asked for:
      // useSettingsCore.ts:73-79 resets activeTab to initialTab ?? 'engine' whenever
      // `isOpen` flips, and the palette dispatches both events in one synchronous
      // handler (useCommandPalette.ts:292-296) — the reset can win.
      put('b_paletteTabJumpComment', 'measure only — compare b_paletteLandingTab with the tab name')
    }

    // Can the palette be used at all while the settings overlay stands?
    // Dismiss the palette by its backdrop if it is still up (Escape would reach the
    // overlay's own window listener too and close the settings page underneath).
    if (await isVisible(page.locator(PALETTE_LISTBOX))) {
      await page.mouse.click(16, 16)
      await page.waitForTimeout(300)
      record('Palette dismissed by clicking its backdrop (not part of any counted path).')
    }
    let settingsOpen = await isVisible(page.locator(SETTINGS_PAGE))
    if (!settingsOpen) {
      // The palette entry did not open the overlay — open it through the shell entry so
      // the "palette over the overlay" question is still answered.
      settingsOpen = await openSettingsFromSidebar(page)
      record(
        'The overlay had to be opened through the sidebar entry for this check ' +
          '(the palette entry above did not open it).',
        'MEDIUM',
      )
    }
    if (settingsOpen) {
      const openedAgain = await paletteOpen(page)
      const state = await page.evaluate(() => {
        const list = document.querySelector('#cmd-palette-listbox')
        if (!list) return null
        let node: HTMLElement | null = list as HTMLElement
        let inertAncestor: string | null = null
        while (node) {
          if (node.hasAttribute('inert')) inertAncestor = node.getAttribute('class') ?? 'inert'
          node = node.parentElement
        }
        return { inertAncestor }
      })
      record(
        `While the settings overlay stands: palette opens = ${openedAgain}; ` +
          `inert on its ancestor chain = ${state?.inertAncestor ?? 'none'}`,
        openedAgain ? 'INFO' : 'MEDIUM',
      )
      put('b_paletteOpenWhileSettings', openedAgain)
      await shoot(page, 'palette-over-settings')
    } else {
      put('b_paletteOpenWhileSettings', 'settings overlay was not open')
    }

    // Contrast trial: is the landed-on-Engine jump specific to the "Privacy" entry, or does no
    // palette tab entry reach its tab? Close the overlay first — with the panel already open the
    // reset effect (useSettingsCore.ts:71-76) does not re-run, so only a closed overlay is the
    // honest case.
    await pointerClick(page.locator(SETTINGS_BACK), 'the settings back button (close the overlay)')
    await page.waitForTimeout(400)
    const overlayClosed = !(await isVisible(page.locator(SETTINGS_PAGE)))
    if (overlayClosed && (await paletteOpen(page))) {
      const contrastInput = page.locator(PALETTE_INPUT)
      await contrastInput.fill('Audio')
      await page.waitForTimeout(400)
      const contrastHit = page
        .locator(`${PALETTE_LISTBOX} li button`)
        .filter({ hasText: 'Audio' })
        .first()
      if (await isVisible(contrastHit)) {
        await pointerClick(contrastHit, 'the palette entry "Audio" (contrast trial)')
        await page.waitForTimeout(900)
        const contrast = await activeTab(page)
        const reachesItsTab = contrast.activeNav === 'settings-nav-voice'
        record(
          `Contrast trial — the palette entry "Audio" with the overlay closed opened settings on ` +
            `"${contrast.title}" (nav: ${contrast.activeNav ?? 'none'}): ` +
            (reachesItsTab
              ? 'that entry does reach its tab, so the Privacy landing above is entry-specific.'
              : 'the dropped tab jump is not specific to "Privacy" — with the overlay closed no ' +
                'palette tab entry reaches its tab.'),
          reachesItsTab ? 'INFO' : 'HIGH',
        )
        put('b_paletteContrastEntry', 'Audio')
        put('b_paletteContrastLandingTab', contrast.title)
        put('b_paletteContrastActiveNav', contrast.activeNav)
        await shoot(page, 'palette-contrast-tab-entry', 17)
      } else {
        record('Contrast trial skipped: the palette offered no "Audio" entry.', 'LOW')
      }
    } else {
      record(
        `Contrast trial skipped: the settings overlay could not be closed (closed=${overlayClosed}).`,
        'LOW',
      )
    }

    // Final state, at the fixed number 16 so the documented shot arc stays valid even if
    // one of the conditional shots above is skipped.
    if (await isVisible(page.locator(PALETTE_LISTBOX))) {
      await page.mouse.click(16, 16)
      await page.waitForTimeout(300)
    }
    await shoot(page, 'end-state', 16)
  })

  // ---- runtime notes + machine-readable findings ---------------------------------------
  test.afterAll(() => {
    // Every step snapshots itself into parts/; merge them so the run keeps the numbers
    // of the steps that ran before a worker restart.
    const parts = readParts()
    const merged: Record<string, unknown> = {}
    const mergedConsole: { type: string; text: string }[] = []
    const mergedPageErrors: string[] = []
    const mergedFailures: string[] = []
    const mergedShots = new Set<string>()
    const mergedLines: string[] = []
    const seen = new Set<string>()

    for (const p of parts) {
      Object.assign(merged, p.report)
      mergedConsole.push(...p.console)
      mergedPageErrors.push(...p.pageErrors)
      mergedFailures.push(...p.failedRequests)
      for (const s of p.shots) mergedShots.add(s)
      if (!seen.has(p.title)) {
        seen.add(p.title)
        mergedLines.push(
          '',
          `### ${p.title}`,
          p.lines.length ? p.lines.join('\n') : '- (no observations recorded)',
        )
      }
    }
    // This worker's own state wins for the steps it actually ran.
    Object.assign(merged, report)
    for (const [title, body] of perStep) {
      if (seen.has(title)) continue
      seen.add(title)
      mergedLines.push(
        '',
        `### ${title}`,
        body.length ? body.join('\n') : '- (no observations recorded)',
      )
    }
    // Console/page/request events that arrived after the last flush.
    mergedConsole.push(...consoleEvents.slice(flushedConsole))
    mergedPageErrors.push(...pageErrors.slice(flushedPageErrors))
    mergedFailures.push(...requestFailures.slice(flushedRequests))

    merged.clicks = {
      directNavPath: merged.a_pathSearchNameClicks ?? null,
      searchPath: merged.a_pathSearchControlClicks ?? null,
      palettePath: (merged.b_paletteEntryClicks as number) ?? null,
      note: 'Pointer clicks only; typing and the Ctrl+K chord are not clicks.',
    }
    merged.consoleErrors = mergedConsole.filter((e) => e.type === 'error').length
    merged.consoleWarnings = mergedConsole.filter((e) => e.type === 'warning').length
    merged.pageErrors = mergedPageErrors.length
    merged.failedRequests = mergedFailures.length
    merged.shots = Array.from(mergedShots).sort()
    merged.finishedAt = new Date().toISOString()

    fs.mkdirSync(OUT_DIR, { recursive: true })
    fs.writeFileSync(FINDINGS, `${JSON.stringify(merged, null, 2)}\n`, 'utf8')

    const lines: string[] = []
    lines.push(RUNTIME_BEGIN)
    lines.push('')
    lines.push(`## Runtime observations (generated ${new Date().toISOString()} by the spec)`)
    lines.push('')
    lines.push(`- Target: \`${BASE}\` (live product server, real backend, no mocking)`)
    lines.push(`- Machine-readable results: \`findings.json\` in this directory`)
    lines.push(`- Screenshots: ${mergedShots.size} (full page)`)
    lines.push(...mergedLines)
    lines.push('')
    lines.push(`## Console errors / warnings (${mergedConsole.length})`)
    lines.push(
      mergedConsole.length
        ? mergedConsole.map((e) => `- [${e.type}] ${e.text}`).join('\n')
        : '- none',
    )
    lines.push('')
    lines.push(`## Page errors (${mergedPageErrors.length})`)
    lines.push(
      mergedPageErrors.length ? mergedPageErrors.map((e) => `- ${e}`).join('\n') : '- none',
    )
    lines.push('')
    lines.push(`## Failed network requests (${mergedFailures.length})`)
    lines.push(mergedFailures.length ? mergedFailures.map((e) => `- ${e}`).join('\n') : '- none')
    lines.push('')
    lines.push(RUNTIME_END)
    lines.push('')

    const block = lines.join('\n')
    let existing = ''
    try {
      existing = fs.readFileSync(NOTES, 'utf8')
    } catch {
      existing = '# Persona 05 — “change one setting” walkthrough\n'
    }
    const begin = existing.indexOf(RUNTIME_BEGIN)
    const end = existing.indexOf(RUNTIME_END)
    const head = begin >= 0 ? existing.slice(0, begin).trimEnd() : existing.trimEnd()
    const tail = end >= 0 ? existing.slice(end + RUNTIME_END.length).replace(/^\s*\n/, '') : ''
    fs.writeFileSync(NOTES, `${head}\n\n${block}${tail ? `\n${tail}` : ''}`)
    console.log(`[persona-05] wrote runtime notes to ${NOTES} and ${FINDINGS}`)
  })
})
