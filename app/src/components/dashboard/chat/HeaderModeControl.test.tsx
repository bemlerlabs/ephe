/**
 * 2026-11-10 — the response mode is chosen in the header.
 *
 * The owner asked for the mode at the top of the app (the reference client's
 * place) and the access rights in the composer. This file holds the header half:
 * one control that names the active mode, a menu that shows all four modes with
 * their icon and their sentence, keyboard operation from the trigger (ArrowDown
 * opens, arrows move, Enter picks, Escape leaves) and a session that carries the
 * pick. The composer keeps no mode chip — `ChatInput.p3.test.tsx` holds that.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('react-i18next', async () => {
  const bundle = (await import('@/locales/en.json')).default as Record<string, unknown>
  const read = (key: string): string | undefined => {
    let node: unknown = bundle
    for (const part of key.split('.')) {
      if (typeof node !== 'object' || node === null) return undefined
      node = (node as Record<string, unknown>)[part]
    }
    return typeof node === 'string' ? node : undefined
  }
  return {
    initReactI18next: { type: '3rdParty', init: () => undefined },
    useTranslation: () => ({
      i18n: { language: 'en' },
      t: (key: string, opts?: { defaultValue?: string }) => read(key) ?? opts?.defaultValue ?? key,
    }),
  }
})

import HeaderModeControl from './HeaderModeControl'
import { useChatStore } from '@/store/chatStore'

const sessionMode = (): string | undefined =>
  useChatStore.getState().sessions.find((x) => x.id === useChatStore.getState().activeSessionId)
    ?.mode

beforeEach(() => {
  useChatStore.setState({ sessions: [], activeSessionId: null, currentSession: null } as never)
  useChatStore.getState().createSession('Mode')
})

describe('the header mode control', () => {
  it('names the active mode and opens a menu with all four, each with icon and sentence', () => {
    useChatStore.getState().setSessionMode(useChatStore.getState().activeSessionId!, 'operator')
    render(<HeaderModeControl />)
    const trigger = screen.getByTestId('header-mode-control')
    expect(trigger.textContent).toContain('Operator')
    expect(trigger.getAttribute('aria-haspopup')).toBe('menu')
    expect(trigger.getAttribute('aria-expanded')).toBe('false')

    fireEvent.click(trigger)
    expect(trigger.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByTestId('mode-menu')).toBeTruthy()
    for (const key of ['analyst', 'architect', 'operator', 'creator']) {
      const row = screen.getByTestId(`mode-option-${key}`)
      expect(row.getAttribute('role')).toBe('menuitemradio')
      expect(row.getAttribute('aria-checked')).toBe(key === 'operator' ? 'true' : 'false')
      expect(row.querySelector(`[data-testid="mode-icon-${key}"]`)?.tagName).toBe('svg')
      // The sentence stands in the row as text: no hover teaches what a mode does.
      expect(
        screen.getByTestId(`mode-option-${key}-meaning`).textContent?.length ?? 0,
      ).toBeGreaterThan(10)
    }
    expect(screen.getByTestId('mode-menu-note').textContent).toContain('ceiling')
  })

  it('writes the pick into the session and closes', () => {
    render(<HeaderModeControl />)
    fireEvent.click(screen.getByTestId('header-mode-control'))
    fireEvent.click(screen.getByTestId('mode-option-architect'))

    expect(sessionMode()).toBe('architect')
    expect(screen.getByTestId('header-mode-control').textContent).toContain('Architect')
    expect(screen.queryByTestId('mode-menu')).toBeNull()
  })

  it('is keyboard-operated from the trigger: ArrowDown opens, arrows move, Enter picks', async () => {
    useChatStore.getState().setSessionMode(useChatStore.getState().activeSessionId!, 'analyst')
    render(<HeaderModeControl />)
    const trigger = screen.getByTestId('header-mode-control')

    fireEvent.keyDown(trigger, { key: 'ArrowDown' })
    const list = await screen.findByTestId('mode-list')
    // The ring starts on the active mode, and AT follows it through the name.
    expect(list.getAttribute('aria-activedescendant')).toBe('mode-opt-analyst')
    expect(document.getElementById('mode-opt-analyst')).not.toBeNull()

    fireEvent.keyDown(list, { key: 'ArrowDown' })
    expect(list.getAttribute('aria-activedescendant')).toBe('mode-opt-architect')
    fireEvent.keyDown(list, { key: 'Enter' })

    await waitFor(() => expect(sessionMode()).toBe('architect'))
    expect(screen.queryByTestId('mode-menu')).toBeNull()
    // Enter hands the keyboard back to the control that opened the menu.
    expect(document.activeElement).toBe(trigger)
  })

  it('Escape closes without touching the session mode', async () => {
    useChatStore.getState().setSessionMode(useChatStore.getState().activeSessionId!, 'operator')
    render(<HeaderModeControl />)
    fireEvent.click(screen.getByTestId('header-mode-control'))
    const list = await screen.findByTestId('mode-list')
    fireEvent.keyDown(list, { key: 'Escape' })
    expect(screen.queryByTestId('mode-menu')).toBeNull()
    expect(sessionMode()).toBe('operator')
  })

  it('names itself for a screen reader', () => {
    render(<HeaderModeControl />)
    const trigger = screen.getByTestId('header-mode-control')
    expect(trigger.getAttribute('aria-label')).toBe('Response mode: Operator')
  })
})

describe('the header mode control — the thumb target', () => {
  it('reaches 44 x 44 on a coarse pointer without losing its desktop floor', () => {
    render(<HeaderModeControl />)
    const tokens = screen.getByTestId('header-mode-control').className.split(/\s+/)
    expect(tokens, 'desktop 24 px floor').toContain('min-h-6')
    expect(tokens, 'touch height').toContain('pointer-coarse:min-h-11')
    expect(tokens, 'touch width').toContain('pointer-coarse:min-w-11')
    expect(tokens, 'glyph and label stay centred in the square').toContain('justify-center')
  })
})
