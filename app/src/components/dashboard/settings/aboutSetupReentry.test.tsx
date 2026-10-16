/**
 * F5: the register's "Re-open engine setup" card has to arrive somewhere.
 *
 * Measured on both surfaces at 390x844 and 1280x800 before the fix: the click left the
 * app at `#/`, with no setup page and no register either. `/setup` only opens on a
 * stated intent (`lib/setupGate.ts`), because a surviving hash would otherwise pin a
 * configured machine into first run forever. The composer chip marks that intent and
 * this card did not — and the chip's setup row only exists while no engine is
 * configured, so on any machine that has one this card is the only way in.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { renderAbout } from './model/sections-misc'
import { SETUP_INTENT_KEY, shouldLeaveSetup } from '@/lib/setupGate'

const model = {
  about: {
    version: '0.0.1',
    active_provider: 'ollama',
    active_model: 'gemma4:12b',
    offline_capable: true,
  },
  t: (k: string) => k,
  // The card reads two fields; the rest of the model belongs to other sections.
} as never

beforeEach(() => {
  sessionStorage.clear()
  window.location.hash = ''
})

afterEach(cleanup)

describe('the onboarding re-entry card', () => {
  it('states the intent the route asks for, then navigates', () => {
    render(renderAbout(model))
    fireEvent.click(screen.getByTestId('about-restart-onboarding'))
    expect(sessionStorage.getItem(SETUP_INTENT_KEY)).toBe('1')
    expect(window.location.hash).toBe('#/setup')
  })

  it('without the mark, the guard sends a configured machine back to the chat', () => {
    const gate = { ready: true, configured: true, skipped: false }
    expect(shouldLeaveSetup(gate, false)).toBe(true)
    expect(shouldLeaveSetup(gate, true)).toBe(false)
  })

  it('stays a button with its own word, not an icon', () => {
    render(renderAbout(model))
    const card = screen.getByTestId('about-restart-onboarding')
    expect(card.tagName).toBe('BUTTON')
    expect(card.textContent).toBe('settings.aboutRestartOnboarding')
  })
})
