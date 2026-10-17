// I3-V5: nav search finds the range and the single setting, and knows where to jump.
import { describe, it, expect } from 'vitest'
import i18next from 'i18next'

import de from '@/locales/de.json'
import en from '@/locales/en.json'
import { matchFields, matchRows, matchTabs } from './settingsSearch'
import { ROW_INDEX } from './rowIndex'
import type { DeepSection } from '@/types'

const sections = [
  {
    key: 'appearance',
    fields: [
      {
        key: 'appearance.font_scale',
        type: 'number',
        label: 'Schriftgröße (%)',
        labelEn: 'Font scale (%)',
        default: 100,
        value: 100,
        hint: 'Setzt die Schriftgröße der Oberfläche.',
        hintEn: 'Sets the interface text size.',
      },
    ],
  },
  {
    key: 'chat',
    fields: [
      {
        key: 'chat.show_reasoning',
        type: 'bool',
        label: 'Denkprozess anzeigen',
        labelEn: 'Show reasoning',
        default: true,
        value: true,
      },
    ],
  },
  {
    key: 'advanced',
    fields: [
      {
        key: 'advanced.api_timeout',
        type: 'number',
        label: 'API-Zeitüberschreitung (s)',
        labelEn: 'API timeout (s)',
        default: 120,
        value: 120,
      },
    ],
  },
] as unknown as DeepSection[]

const NAV = [{ key: 'engine' }, { key: 'appearance' }, { key: 'plugins' }]

describe('matchTabs', () => {
  it('leert bei leerer Eingabe nichts weg', () => {
    expect(matchTabs(NAV, () => '', '')).toEqual([])
  })

  it('findet den Bereich ueber seinen Titel', () => {
    const hits = matchTabs(NAV, (n) => `settings.${n.key}`, 'plugins')
    expect(hits.map((h) => h.key)).toEqual(['plugins'])
  })
})

describe('matchFields', () => {
  it('findet ueber den deutschen Titel', () => {
    expect(matchFields(sections, 'Schriftgröße', true).map((h) => h.secKey)).toEqual(['appearance'])
  })

  it('findet ueber die Beschreibung', () => {
    expect(matchFields(sections, 'oberfläche', true).map((h) => h.secKey)).toEqual(['appearance'])
  })

  it('springt zur Karte, wo das Feld liegt', () => {
    const hits = matchFields(sections, 'zeitüberschreitung', true)
    expect(hits).toEqual([
      { secKey: 'advanced', label: 'API-Zeitüberschreitung (s)', tab: 'engine' },
    ])
  })

  it('nutzt den englischen Titel, wenn die Sprache en ist', () => {
    const hits = matchFields(sections, 'reasoning', false)
    // I6-3: the chat section lives in the behaviour range, not in appearance.
    expect(hits[0]).toMatchObject({ secKey: 'chat', label: 'Show reasoning', tab: 'behaviour' })
  })

  it('ohne Register keine Treffer, kein Fehler', () => {
    expect(matchFields(null, 'schrift', true)).toEqual([])
  })

  it('ein Bereich ohne Karte wird nicht angeboten', () => {
    // I7-5: the old fallback threw the user to appearance, where the field
    // never sits. No target means: no hit.
    const foreign = [{ key: 'irgendwas', fields: [{ key: 'x.y', label: 'Ziellos' }] }]
    expect(matchFields(foreign as unknown as DeepSection[], 'ziellos', true)).toEqual([])
  })

  it('die Gedächtnis-Felder springen ins Gedächtnis', () => {
    const mem = [
      { key: 'memory', fields: [{ key: 'memory.inject_max_entries', label: 'Einträge' }] },
    ]
    const hits = matchFields(mem as unknown as DeepSection[], 'einträge', true)
    expect(hits.map((h) => h.tab)).toEqual(['memory'])
  })
})

describe('matchRows (I7-5)', () => {
  const texts: Record<string, Record<'de' | 'en', string>> = {
    'settings.sttModel': { de: 'Erkennungsmodell', en: 'Recognition model' },
    'settings.mcpServers': { de: 'Verbundene Server', en: 'Connected servers' },
  }
  const translate = (key: string, opts?: Record<string, unknown>) => {
    const row = texts[key]
    if (!row) return ''
    const lng = opts?.lng === 'en' ? 'en' : opts?.lng === 'de' ? 'de' : 'de'
    return row[lng]
  }

  it('findet eine Zeile aus dem deutschen Titel', () => {
    const hits = matchRows(translate, 'erkennung')
    expect(hits).toEqual([{ tab: 'voice', label: 'Erkennungsmodell' }])
  })

  it('findet dieselbe Zeile im englischen Wort', () => {
    // The user knows the term from the docs, the interface is German.
    expect(matchRows(translate, 'connected').map((h) => h.tab)).toEqual(['mcp'])
  })

  it('leere Suche trifft nichts', () => {
    expect(matchRows(translate, '   ')).toEqual([])
  })
})

describe('der Zeilen-Index ist gedeckt', () => {
  const inst = (lng: 'de' | 'en') => {
    const i = i18next.createInstance()
    void i.init({
      resources: { de: { translation: de }, en: { translation: en } },
      lng,
      fallbackLng: lng,
      supportedLngs: [lng],
      interpolation: { escapeValue: false },
    })
    return i
  }
  const deInst = inst('de')
  const enInst = inst('en')

  it('jeder Index-Schluessel existiert in beiden Sprachen', () => {
    const missing = ROW_INDEX.filter((e) => !deInst.exists(e.key) || !enInst.exists(e.key)).map(
      (e) => `${e.tab}:${e.key}`,
    )
    expect(missing).toEqual([])
  })

  it('der Index deckt jeden Bereich ausser dem Register ab', () => {
    // Ranges without their own rows (register fields only) are allowed: behaviour.
    const covered = new Set(ROW_INDEX.map((e) => e.tab))
    for (const tab of [
      'engine',
      'voice',
      'mcp',
      'plugins',
      'hooks',
      'shortcuts',
      'network',
    ] as const) {
      expect(covered.has(tab), tab).toBe(true)
    }
  })
})
