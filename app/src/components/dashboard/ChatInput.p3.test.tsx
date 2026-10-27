/**
 * P3 wave 2026-10-05 — composer inputs (ChatInput).
 *
 * Each block holds one of the findings measured during the user review walk:
 *  1 escape order  2 plus menu  3 @ mention keyboard  4 model menu
 *  5 raw content / type separation  6 thinking chip  7 mode menu  8 microcopy
 *
 * jsdom cannot measure layout — what gets checked are classes, roles and
 * behaviour, never pixels.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const DE: Record<string, string> = {
  'chat.placeholder': 'Womit kann ich dir helfen?',
  'chat.attachFile': 'Datei anhängen',
  'chat.attachImage': 'Bild anhängen',
  'chat.modeHint.ask': 'Fragen — Ephe antwortet nur, keine Werkzeuge laufen',
  'chat.modeHint.edit-auto': 'Bearbeiten — Ephe nutzt Werkzeuge und editiert Dateien im Workspace',
  'chat.modeHint.plan': 'Planen — Ephe entwirft erst einen Plan; nichts läuft ohne Bestätigung',
  'chat.modeHint.full-access': 'Vollzugriff — Ephe arbeitet autonom mit allen Werkzeugen',
  'chat.modeSelectorAria': 'Antwort-Modus des Composers',
  'chat.thinkingChipAria': 'Denk-Modus',
  'chat.thinkingOn': 'An',
  'chat.thinkingOff': 'Aus',
  'chat.perm.strict': 'Manuell',
  'chat.offlineCapableLocal': 'Offline-fähig (lokal)',
  'chat.offlineCapableRemote': 'Remote',
  'chat.mentionTitle': 'Dateien im Workspace',
  'chat.modelChipAria': 'Modell-Provider umschalten',
  'chat.setupEngineChip': 'Engine einrichten',
  // WS7-45: German values mirrored from de.json so the German surface is asserted
  // against the shipped translation; each line carries the gate pragma.
  'chat.modelUnconfiguredHint': 'nicht konfiguriert', // language-gate: ignore
  'chat.modelGroupOther': 'Andere Typen (Sprache, Bild)', // language-gate: ignore
  'chat.modelGroupUnconfigured': 'Ohne Endpunkt — nicht konfigurierbar', // language-gate: ignore
  // language-gate: ignore
  'chat.thinkingChipHint':
    'Gezeigt, ob Ephe in dieser Aufgabe bereits mitgedacht hat — reiner Status, nicht schaltbar',
  'chat.modeSection.none': 'Ohne Werkzeuge', // language-gate: ignore
  'chat.modeSection.read': 'Nur lesend', // language-gate: ignore
  'chat.modeSection.write': 'Mit Schreibzugriff', // language-gate: ignore
}

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string, opts?: unknown) => {
      const o = opts as Record<string, unknown> | undefined
      // Like the real i18next: {{placeholders}} are filled from the options.
      // Without this, "Position {{pos}} von {{total}}" would be a green test even
      // with broken interpolation — exactly the class this wave fixes.
      const raw = DE[key] ?? (o && typeof o.defaultValue === 'string' ? o.defaultValue : key)
      return String(raw).replace(/\{\{(\w+)\}\}/g, (_m, name: string) =>
        o && o[name] !== undefined ? String(o[name]) : `{{${name}}}`,
      )
    },
  }),
}))

const scanEnv = vi.hoisted(() =>
  vi.fn(async (_opts?: unknown): Promise<unknown> => ({
    tools: [],
    summary: { installed: 0, with_models: [] },
  })),
)
vi.mock('@/lib/api/environment', () => ({ scanEnvironment: (...a: unknown[]) => scanEnv(...a) }))

const setModelProvider = vi.hoisted(() => vi.fn(async () => ({ active: { model: 'm1' } })))
vi.mock('@/lib/api', () => ({
  getModelProviders: vi.fn(async () => ({
    active: { provider: 'local_ollama', model: 'gemma4:12b', offline_capable: true },
    providers: [
      { provider: 'local_ollama', model: 'gemma4:12b', label: 'Local Ollama' },
      { provider: 'openai_compatible', model: 'm', label: 'OpenAI-compatible API' },
    ],
    local_models: [],
    local_model_options: [],
  })),
  transcribeAudio: vi.fn(async () => ''),
  listFs: vi.fn(async () => ({
    path: '/tmp/ws',
    parent: null,
    home: '/tmp',
    workspace: '/tmp/ws',
    entries: [
      { name: 'README.md', type: 'file', size: 1 },
      { name: 'reading-list.md', type: 'file', size: 1 },
      { name: 'app', type: 'dir', size: 0 },
      { name: 'server', type: 'dir', size: 0 },
    ],
  })),
  getSettings: vi.fn(async () => ({ workspace_dir: '/tmp/ws', approval_profile: 'strict' })),
  setModelProvider,
  getSetupStatus: vi.fn(async () => ({ configured: true, provider: 'local_ollama' })),
}))

import ChatInput from './ChatInput'
import { useChatStore } from '@/store/chatStore'
import {
  groupModelEntries,
  isUnconfiguredEntry,
  buildScanEntries,
} from './chat/composerModelEntries'
import { detectMentionToken, filterMentionEntries, topmostPopup } from './chat/composerPopups'
import { modeShortLabel, COMPOSER_MODES } from './chat/ComposerModeMenu'
import {
  hasUnfilledTemplate,
  isJunkModel,
  isLoopbackEndpoint,
  isPrivateEndpoint,
  modelKind,
} from '@/lib/modelFilter'

const ta = () => screen.getByTestId('chat-input') as HTMLTextAreaElement

beforeEach(() => {
  localStorage.clear()
  setModelProvider.mockClear()
  useChatStore.setState({ sessions: [], activeSessionId: null, currentSession: null } as never)
})

// ── 1 · Escape order ───────────────────────────────────────────────────────
describe('P3-1 Escape schließt zuerst das oberste Popup', () => {
  const esc = () => fireEvent.keyDown(window, { key: 'Escape', bubbles: true })

  it('Plus-Menü: Escape schließt es (vorher ignoriert) und stoppt NICHT', () => {
    const onStop = vi.fn()
    render(<ChatInput onSend={vi.fn()} streaming onStop={onStop} />)
    fireEvent.click(screen.getByTestId('composer-attach-plus'))
    expect(screen.getByTestId('composer-attach-menu')).toBeTruthy()
    esc()
    expect(screen.queryByTestId('composer-attach-menu')).toBeNull()
    expect(onStop).not.toHaveBeenCalled()
  })

  it('Modell-Menü hat Vorrang vor der Slash-Liste (Palette > Modell > …)', () => {
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.change(ta(), { target: { value: '/' } })
    expect(screen.getByTestId('slash-menu')).toBeTruthy()
    fireEvent.click(screen.getByTestId('model-chip'))
    expect(screen.getByTestId('model-chip-menu')).toBeTruthy()
    esc()
    expect(screen.queryByTestId('model-chip-menu')).toBeNull()
    // the lower popup stays open — one step per keypress
    expect(screen.getByTestId('slash-menu')).toBeTruthy()
  })

  it('nichts offen → Escape stoppt die Generierung', () => {
    const onStop = vi.fn()
    render(<ChatInput onSend={vi.fn()} streaming onStop={onStop} />)
    esc()
    expect(onStop).toHaveBeenCalledTimes(1)
  })

  it('offene Palette/Dialog: Composer fasst nichts an und stoppt nicht', () => {
    const onStop = vi.fn()
    render(<ChatInput onSend={vi.fn()} streaming onStop={onStop} />)
    const dialog = document.createElement('div')
    dialog.setAttribute('role', 'dialog')
    dialog.setAttribute('aria-modal', 'true')
    document.body.appendChild(dialog)
    esc()
    expect(onStop).not.toHaveBeenCalled()
    dialog.remove()
  })

  it('Reihenfolge der Kette: Modell > Modus > Plus > @ > Slash', () => {
    expect(
      topmostPopup({ model: false, mode: false, attach: true, mention: true, slash: true }),
    ).toBe('attach')
    expect(topmostPopup({ model: false, mode: false, attach: false, mention: true })).toBe(
      'mention',
    )
    expect(topmostPopup({ slash: true })).toBe('slash')
    expect(topmostPopup({ model: true, mode: true, attach: true })).toBe('model')
    expect(topmostPopup({})).toBeNull()
  })
})

// ── 2 · Plus menu ──────────────────────────────────────────────────────────
describe('P3-2 Plus-Menü ohne Fenster-Scrim, portaliert, alle Punkte sichtbar', () => {
  it('kein fixed-inset-Overlay mehr über dem Fenster', () => {
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.click(screen.getByTestId('composer-attach-plus'))
    expect(document.querySelector('div.fixed.inset-0.z-overlay')).toBeNull()
  })

  it('Menü hängt am body und ist höhenbegrenzt + scrollbar', () => {
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.click(screen.getByTestId('composer-attach-plus'))
    const menu = screen.getByTestId('composer-attach-menu')
    expect(menu.parentElement).toBe(document.body)
    expect(menu.className).toContain('fixed')
    expect(menu.className).toContain('max-h-')
    expect(menu.className).toContain('overflow-y-auto')
    // all four items (screenshot is absent without getDisplayMedia)
    expect(screen.getByTestId('composer-attach-file')).toBeTruthy()
    expect(screen.getByTestId('composer-attach-image')).toBeTruthy()
    expect(screen.getByTestId('composer-wide-research')).toBeTruthy()
  })

  it('Außenklick schließt, Klick ins Menü nicht', () => {
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.click(screen.getByTestId('composer-attach-plus'))
    fireEvent.mouseDown(screen.getByTestId('composer-attach-file'))
    expect(screen.getByTestId('composer-attach-menu')).toBeTruthy()
    fireEvent.mouseDown(document.body)
    expect(screen.queryByTestId('composer-attach-menu')).toBeNull()
  })

  it('Seitenleiste bleibt klickbar: der Außenklick schließt nur das Menü', () => {
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.click(screen.getByTestId('composer-attach-plus'))
    const outside = document.createElement('button')
    document.body.appendChild(outside)
    fireEvent.mouseDown(outside)
    expect(screen.queryByTestId('composer-attach-menu')).toBeNull()
    outside.remove()
  })
})

// ── 3 · @ mentions ─────────────────────────────────────────────────────────
describe('P3-3 @-Mentions sind tastaturbedienbar', () => {
  const openMention = async (text: string) => {
    render(<ChatInput onSend={vi.fn()} onSlashCommand={vi.fn()} />)
    fireEvent.change(ta(), { target: { value: text, selectionStart: text.length } })
    await screen.findByTestId('mention-popup')
  }

  it('Erkennung: „@" als erstes Zeichen zählt wie „@" nach Text', () => {
    expect(detectMentionToken('@read', 5)).toEqual({ query: 'read', start: 0 })
    expect(detectMentionToken('lies @read', 10)?.start).toBe(5)
    expect(detectMentionToken('mail@x', 6)).toBeNull()
  })

  it('Treffer filtern nach dem getippten Abschnitt, Präfix zuerst', () => {
    const entries = [{ name: 'README.md' }, { name: 'reading-list.md' }, { name: 'app' }]
    expect(filterMentionEntries(entries, 'rea').map((e) => e.name)).toEqual([
      'README.md',
      'reading-list.md',
    ])
  })

  it('Roving-Highlight ab Zeile 1, ArrowDown wandert', async () => {
    await openMention('@')
    const marked = () =>
      [...screen.getAllByRole('option')].findIndex(
        (el) => el.getAttribute('aria-selected') === 'true',
      )
    expect(marked()).toBe(0)
    fireEvent.keyDown(ta(), { key: 'ArrowDown' })
    expect(marked()).toBe(1)
  })

  it('Enter fügt die Datei ein und sendet NICHT', async () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    // The workspace path comes from getSettings() — without this await the test
    // types before the path is known, and the inserted line would be the bare
    // name instead of the path.
    await screen.findByTestId('chat-input')
    fireEvent.change(ta(), { target: { value: '@rea', selectionStart: 4 } })
    await screen.findByTestId('mention-popup')
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSend).not.toHaveBeenCalled()
    expect(ta().value).toBe('/tmp/ws/README.md ')
    expect(screen.queryByTestId('mention-popup')).toBeNull()
  })

  it('Escape schließt das Popup und lässt den Text unangetastet', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.change(ta(), { target: { value: '@rea', selectionStart: 4 } })
    await screen.findByTestId('mention-popup')
    fireEvent.keyDown(ta(), { key: 'Escape' })
    expect(screen.queryByTestId('mention-popup')).toBeNull()
    expect(ta().value).toBe('@rea')
  })

  it('Listbox-Rollen + aria-activedescendant am Textfeld', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.change(ta(), { target: { value: '@', selectionStart: 1 } })
    await screen.findByTestId('mention-popup')
    expect(screen.getByRole('listbox', { name: /Dateien im Workspace/i })).toBeTruthy()
    expect(ta().getAttribute('aria-controls')).toBe('mention-listbox')
    expect(ta().getAttribute('aria-activedescendant')).toBe('mention-opt-0')
  })
})

// ── 4 · Model menu ─────────────────────────────────────────────────────────
const SCAN_TOOLS = [
  {
    tool: 'sample',
    installed: true,
    config_path: '~/.example-tool/config.yaml',
    providers: ['http://127.0.0.1:11434/v1'],
    models: ['claude-fable-5', 'whisper-1', 'qwen3.8-flash-next'],
    auth_present: true,
    model_endpoints: {
      'claude-fable-5': 'https://${SNOWFLAKE_ACCOUNT}.snowflakecomputing.com/api/v2/cortex/v1',
      'qwen3.8-flash-next': 'https://api.vultrinference.com/v1',
    },
  },
  {
    tool: 'claude',
    installed: true,
    config_path: '~/.claude/settings.json',
    providers: ['http://host-one.example.ts.net:8000'],
    models: ['deepseek-v4-flash'],
    auth_present: true,
  },
]

async function openModelMenu() {
  scanEnv.mockResolvedValueOnce({ tools: SCAN_TOOLS, summary: { installed: 2, with_models: [] } })
  render(<ChatInput onSend={vi.fn()} />)
  await waitFor(() => expect(screen.getByTestId('model-chip').textContent).toContain('gemma4'))
  fireEvent.click(screen.getByTestId('model-chip'))
  await screen.findByTestId('model-chip-menu')
}

describe('P3-4 Modell-Menü: Höhe, Scrollen, Suche, Markierung, Tastatur', () => {
  it('Liste ist höhenbegrenzt und scrollbar (kein Überhang über den Rand)', async () => {
    await openModelMenu()
    const list = screen.getByTestId('model-chip-list')
    expect(list.className).toContain('max-h-')
    expect(list.className).toContain('overflow-y-auto')
    expect(screen.getByTestId('model-chip-menu').className).toContain('max-h-')
  })

  it('Suchfeld ab dem ersten Zeichen — es bleiben nur die Treffer stehen', async () => {
    await openModelMenu()
    const search = screen.getByTestId('model-chip-search')
    expect(search).toBeTruthy()
    fireEvent.change(search, { target: { value: 'whisper' } })
    expect(
      screen
        .getAllByRole('option')
        .map((el) => el.textContent)
        .join('|'),
    ).toContain('whisper-1')
    expect(screen.queryByTestId('model-chip-option-local_ollama')).toBeNull()
    // 'gemma' would be a hit (gemma4:12b sits in the list) — the empty case needs
    // an input that by definition cannot find anything.
    fireEvent.change(search, { target: { value: 'zzz-nicht-vorhanden' } })
    expect(screen.getByTestId('model-chip-empty')).toBeTruthy()
  })

  it('aktuelle Position ist markiert und benannt', async () => {
    await openModelMenu()
    const active = screen.getByTestId('model-chip-option-local_ollama')
    expect(active.getAttribute('aria-selected')).toBe('true')
    expect(active.getAttribute('aria-current')).toBe('true')
  })

  it('Pfeiltasten + Enter schalten das Modell (setModelProvider)', async () => {
    await openModelMenu()
    const marked = () =>
      document.querySelector('[data-testid="model-chip-menu"] [aria-current="true"]')
    expect(marked()).toBeTruthy()
    fireEvent.keyDown(screen.getByTestId('model-chip-search'), { key: 'ArrowDown' })
    fireEvent.keyDown(screen.getByTestId('model-chip-search'), { key: 'Enter' })
    await waitFor(() => expect(setModelProvider).toHaveBeenCalled())
    expect(screen.queryByTestId('model-chip-menu')).toBeNull()
  })

  it('Escape schließt das Menü, ohne etwas zu ändern', async () => {
    await openModelMenu()
    fireEvent.keyDown(screen.getByTestId('model-chip-search'), { key: 'Escape' })
    expect(screen.queryByTestId('model-chip-menu')).toBeNull()
    expect(setModelProvider).not.toHaveBeenCalled()
  })
})

// ── 5 · Raw content / type separation ──────────────────────────────────────
describe('P3-5 Modell-Liste: Vorlagen deaktiviert, Typen getrennt', () => {
  it('Filter-Klassifikation', () => {
    expect(isJunkModel('nomic-embed-text')).toBe(true)
    expect(isJunkModel('test')).toBe(true)
    expect(isJunkModel('gemma4:12b')).toBe(false)
    expect(modelKind('whisper-1')).toBe('speech')
    expect(modelKind('base')).toBe('speech')
    expect(modelKind('tts-1')).toBe('speech')
    expect(modelKind('dall-e-3')).toBe('image')
    expect(modelKind('gemma4:12b')).toBe('chat')
    expect(modelKind('database')).toBe('chat')
    expect(hasUnfilledTemplate('https://${SNOWFLAKE_ACCOUNT}.x.com/v1')).toBe(true)
    expect(hasUnfilledTemplate('https://api.openai.com/v1')).toBe(false)
    expect(isLoopbackEndpoint('http://127.0.0.1:11434')).toBe(true)
    expect(isPrivateEndpoint('http://host-one.example.ts.net:8000')).toBe(true)
    expect(isPrivateEndpoint('https://api.vultrinference.com/v1')).toBe(false)
  })

  it('ungefüllte Vorlage: eigene Sektion, nicht anwählbar', async () => {
    await openModelMenu()
    const row = screen.getByTestId('model-chip-option-sample:claude-fable-5')
    expect(row.getAttribute('aria-disabled')).toBe('true')
    expect(row.textContent).toContain('nicht konfiguriert')
    fireEvent.click(row)
    expect(setModelProvider).not.toHaveBeenCalled()
    expect(screen.getByTestId('model-group-unconfigured')).toBeTruthy()
  })

  it('Sprachmodell steht in der Typ-Sektion, nicht zwischen den Chat-Modellen', async () => {
    await openModelMenu()
    const groups = screen.getByTestId('model-chip-list').textContent ?? ''
    expect(screen.getByTestId('model-group-other').textContent).toContain('Andere Typen')
    expect(groups.indexOf('Andere Typen')).toBeLessThan(groups.indexOf('Ohne Endpunkt'))
    const chat = screen.getByTestId('model-group-chat').parentElement
    expect(chat?.textContent).toContain('qwen3.8-flash-next')
    expect(screen.getByTestId('model-group-other').textContent).toContain('whisper-1')
  })

  it('Tailnet- und Loopback-Endpunkte stehen nicht als rohe URL in der Zeile', () => {
    const entries = buildScanEntries(SCAN_TOOLS as never)
    const priv = entries.find((e) => e.id === 'claude:deepseek-v4-flash')
    expect(priv?.endpoint).toContain('ts.net')
    expect(priv?.label).not.toContain('ts.net')
    expect(priv?.endpointKind).toBe('private')
  })

  it('gruppieren trennt nach Typ und Vorlage', () => {
    const g = groupModelEntries([
      { label: 'A', model: 'gemma4:12b' },
      { label: 'B', model: 'whisper-1' },
      { label: 'C', model: 'x', endpoint: 'https://${V}.example.com', unconfigured: true },
    ])
    expect(g.chat.map((e) => e.label)).toEqual(['A'])
    expect(g.other.map((e) => e.label)).toEqual(['B'])
    expect(g.unconfigured.map((e) => e.label)).toEqual(['C'])
    expect(isUnconfiguredEntry({ label: 'C', endpoint: 'https://real.example.com' })).toBe(false)
  })
})

// ── 6 · Thinking chip ──────────────────────────────────────────────────────
describe('P3-6 Denk-Chip ist reiner Status ohne Schalter-Optik', () => {
  it('kein Button, keine Rand-/Flächen-Optik, aber vollständiger Name + Titel', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    const chip = await screen.findByTestId('composer-thinking-chip')
    expect(chip.tagName).toBe('SPAN')
    expect(chip.getAttribute('role')).toBe('status')
    expect(chip.className).not.toContain('border-hairline')
    expect(chip.className).not.toContain('bg-surface')
    expect(chip.getAttribute('aria-label')).toBe('Denk-Modus: Aus')
    expect(chip.getAttribute('title')).toContain('nicht schaltbar')
  })
})

// ── 7 · Mode menu ──────────────────────────────────────────────────────────
describe('P3-7 Modus-Menü: deutsch, Sektionen, Tastatur', () => {
  it('Kurz-Titel aus der Übersetzung, Notname ohne Auflösung', () => {
    const ask = COMPOSER_MODES.find((m) => m.key === 'ask')!
    expect(modeShortLabel(ask, 'Fragen — Ephe antwortet nur')).toBe('Fragen')
    expect(modeShortLabel(ask, 'chat.modeHint.ask')).toBe('Ask')
    expect(modeShortLabel(ask, '')).toBe('Ask')
    expect(modeShortLabel(ask, 'Ganz langer Satz ohne Trenner, der alles verdeckt')).toBe('Ask')
  })

  it('Chip und Zeilen tragen die deutschen Kurz-Titel', async () => {
    useChatStore.getState().createSession('S')
    render(<ChatInput onSend={vi.fn()} />)
    expect(screen.getByTestId('composer-mode-selector').textContent).toContain('Vollzugriff')
    fireEvent.click(screen.getByTestId('composer-mode-selector'))
    const menu = await screen.findByTestId('composer-mode-menu')
    expect(menu.textContent).toContain('Fragen')
    expect(menu.textContent).toContain('Bearbeiten')
    expect(menu.textContent).not.toContain('Ask —')
  })

  it('Sektionen nach Ausführungsrecht', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.click(screen.getByTestId('composer-mode-selector'))
    await screen.findByTestId('composer-mode-menu')
    expect(screen.getByTestId('composer-mode-section-none').textContent).toContain('Ohne Werkzeuge')
    expect(screen.getByTestId('composer-mode-section-read').textContent).toContain('Nur lesend')
    expect(screen.getByTestId('composer-mode-section-write').textContent).toContain(
      'Mit Schreibzugriff',
    )
    expect(
      document.querySelectorAll('[data-testid="composer-mode-menu"] [role="group"]').length,
    ).toBe(3)
  })

  it('Tastatur: Highlight ab Zeile 1, Enter wählt', async () => {
    useChatStore.getState().createSession('S')
    const st = useChatStore.getState()
    useChatStore.getState().setSessionMode(st.activeSessionId!, 'ask')
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.click(screen.getByTestId('composer-mode-selector'))
    await screen.findByTestId('composer-mode-menu')
    const marked = () =>
      [
        ...document.querySelectorAll('[data-testid="composer-mode-menu"] [role="menuitemradio"]'),
      ].findIndex((el) => el.getAttribute('aria-current') === 'true')
    expect(marked()).toBe(0)
    fireEvent.keyDown(screen.getByTestId('composer-mode-list'), { key: 'ArrowDown' })
    expect(marked()).toBe(1)
    fireEvent.keyDown(screen.getByTestId('composer-mode-list'), { key: 'Enter' })
    await waitFor(() =>
      expect(
        useChatStore
          .getState()
          .sessions.find((x) => x.id === useChatStore.getState().activeSessionId)?.mode,
      ).toBe('plan'),
    )
    expect(screen.queryByTestId('composer-mode-menu')).toBeNull()
  })
})

// ── 8 · Microcopy ──────────────────────────────────────────────────────────
describe('P3-8 Microcopy: Zähler nur mit Leser, Badge-Namen', () => {
  it('„↑/↓ 0/1" erscheint nicht mehr im Ruhezustand, aber beim Blättern — mit Erklärung', () => {
    render(<ChatInput onSend={vi.fn()} />)
    fireEvent.change(ta(), { target: { value: 'erste nachricht' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(screen.queryByTestId('composer-recall-counter')).toBeNull()
    fireEvent.keyDown(ta(), { key: 'ArrowUp' })
    const counter = screen.getByTestId('composer-recall-counter')
    expect(counter.textContent).toContain('1/1')
    expect(counter.getAttribute('title')).toContain('scrolls through your sent messages')
    expect(counter.getAttribute('aria-label')).toContain('History: position 1 of 1')
  })

  it('Status-Punkt und Berechtigungs-Badge haben einen zugaenglichen Namen', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    const dot = await screen.findByTestId('composer-status-dot')
    expect(dot.getAttribute('role')).toBe('img')
    expect(dot.getAttribute('aria-label')).toBeTruthy()
    const badge = screen.getByTestId('composer-permission-badge')
    expect(badge.getAttribute('aria-label')).toContain('Manuell')
  })
})

// ── 2 · typed dashes survive the shell ─────────────────────────────────────
describe('QD-008 the composer does not rewrite typed dashes', () => {
  it('turns off the substitutions WKWebView applies to a text field', () => {
    render(<ChatInput onSend={vi.fn()} />)
    const input = ta()
    expect(input.getAttribute('autocorrect')).toBe('off')
    expect(input.getAttribute('autocapitalize')).toBe('off')
    expect(input.getAttribute('spellcheck')).toBe('false')
  })
})
