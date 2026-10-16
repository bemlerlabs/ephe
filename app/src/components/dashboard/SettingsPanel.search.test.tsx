// I7-5: the section search finds every row — including the ones outside the
// open tab. In the test the key string is the title (identity-t), so the search
// runs over it, which in the real interface would have gone via the language.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const api = vi.hoisted(() => ({}))

vi.mock('@/lib/api', async (importOriginal) => ({
  ...((await importOriginal()) as Record<string, unknown>),
  ...api,
}))

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: Record<string, unknown>) => (opts && opts.returnObjects ? [] : k),
      i18n: { language: 'de', changeLanguage: vi.fn() },
    }),
  }
})

import SettingsPanel from './SettingsPanel'

beforeEach(() => {
  localStorage.clear()
  Object.assign(api, {
    getSettings: vi.fn(async () => ({ provider: { type: 'local_ollama', model: 'gemma4:12b' } })),
    updateSettings: vi.fn(async () => ({})),
    getDeepSettings: vi.fn(async () => ({ sections: [] })),
    putDeepSettings: vi.fn(async () => ({ sections: [] })),
  })
})

async function openAndSearch(query: string) {
  render(<SettingsPanel isOpen onClose={vi.fn()} initialTab="about" />)
  const box = (await screen.findByTestId('settings-search')) as HTMLInputElement
  fireEvent.change(box, { target: { value: query } })
}

describe('Bereichs-Suche findet Zeilen ausserhalb des Registers (I7-5)', () => {
  it('einen Ton-Regler, der kein Registerfeld ist', async () => {
    await openAndSearch('sttModel')
    const hit = await screen.findByTestId('settings-search-row-voice-settings.sttModel')
    expect(hit.textContent).toContain('settings.voice')
    fireEvent.click(hit)
    expect(screen.getByTestId('settings-title-h1').textContent).toBe('settings.voice')
  })

  it('eine Netzwerk-Zeile', async () => {
    await openAndSearch('networkBind')
    expect(
      await screen.findByTestId('settings-search-row-network-settings.networkBind'),
    ).toBeTruthy()
  })

  it('ein Kurzbefehl aus dem anderen Sprachraum', async () => {
    await openAndSearch('shortcuts.send')
    expect(await screen.findByTestId('settings-search-row-shortcuts-shortcuts.send')).toBeTruthy()
  })

  it('sagt leer, wenn nichts passt', async () => {
    await openAndSearch('dieses-wort-gibt-es-nirgends')
    expect(await screen.findByTestId('settings-search-empty')).toBeTruthy()
  })
})
