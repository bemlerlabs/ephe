/**
 * 2026-11-10 — the composer holds six visible controls at 1440 px, not nine.
 *
 * Measured before this pass, the action row carried the plus, the mode chip, the
 * mode hint, the approval badge, the engine dot, the mic, the palette button, the
 * model chip, the thinking chip and send. The owner's complaint was that this
 * reads as a pile. After the pass: plus · access · mic · model · details · send.
 *
 * jsdom lays nothing out, so "visible at 1440" is decided by the class contract
 * the line states: an element counts unless it hides itself at a breakpoint above
 * 1440 (a max-2xl rule hides below 1536) or carries a bare `hidden` with no
 * breakpoint that shows it again below 1440. The pixel proof is the Playwright
 * capture named in the report.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

vi.mock('@/lib/api', () => ({
  getModelProviders: vi.fn(async () => ({
    active: { provider: 'local_ollama', model: 'm', api_url: null, offline_capable: true },
    local_models: [],
    local_model_options: [],
  })),
  getSettings: vi.fn(async () => ({ workspace_dir: '/tmp/ws', approval_profile: 'strict' })),
  saveSecuritySettings: vi.fn(async () => ({ approval_profile: 'strict', sandbox_enabled: false })),
  setModelProvider: vi.fn(async () => ({})),
  getSetupStatus: vi.fn(async () => ({ configured: true, provider: 'local_ollama' })),
  listFs: vi.fn(async () => ({ path: '/tmp/ws', parent: null, entries: [] })),
  listSkills: vi.fn(async () => ({ skills: [] })),
  transcribeAudio: vi.fn(async () => ''),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => undefined },
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
  }),
}))

import ChatInput from '../ChatInput'
import { useChatStore } from '@/store/chatStore'

/**
 * Only a max-* variant whose breakpoint sits above 1440 px still hides there.
 * Built from parts so Tailwind's scanner does not ship a rule for a test string.
 */
const HIDES_AT_1440 = new RegExp(['max', '2xl'].join('-') + ':' + 'hidden')

function visibleAt1440(el: Element): boolean {
  const classes = el.className.split(/\s+/)
  if (classes.some((c) => HIDES_AT_1440.test(c))) return false
  if (!classes.includes('hidden')) return true
  // `hidden md:flex` and `hidden xl:inline` are visible at 1440; bare `hidden` is not.
  const shows = new RegExp(
    `^(${['sm', 'md', 'lg', 'xl', '2xl'].join('|')}):(${['inline', 'flex', 'block', 'grid'].join('|')})$`,
  )
  return classes.some((c) => shows.test(c))
}

beforeEach(() => {
  // A real browser has getUserMedia, so the mic renders — the row's widest shape.
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: () => Promise.resolve({ getTracks: () => [] }) },
  })
  useChatStore.setState({ sessions: [], activeSessionId: null, currentSession: null } as never)
})

describe('the composer control budget at 1440 px', () => {
  it('shows at most six controls in the action row', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('composer-access-control')).toBeTruthy())
    const row = screen.getByTestId('composer-actions-row')
    const controls = [
      ...row.querySelectorAll('button, [role="button"], [role="img"], [role="status"]'),
    ]
      .filter(visibleAt1440)
      .map((el) => el.getAttribute('data-testid') ?? el.getAttribute('aria-label') ?? el.tagName)
    expect(controls.length, `visible controls: ${controls.join(', ')}`).toBeLessThanOrEqual(6)
    // The six are the ones the pass kept, and nothing else slipped in.
    expect(new Set(controls)).toEqual(
      new Set([
        'composer-attach-plus',
        'composer-access-control',
        'chat.voiceInput',
        'model-chip',
        'composer-thinking-chip',
        'send-btn',
      ]),
    )
  })

  it('the controls that left the row are gone, not merely hidden', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    await waitFor(() => expect(screen.getByTestId('composer-access-control')).toBeTruthy())
    expect(screen.queryByTestId('composer-mode-selector')).toBeNull()
    expect(screen.queryByTestId('composer-permission-badge')).toBeNull()
    expect(screen.queryByTestId('composer-ask-hint')).toBeNull()
    // The palette keeps one home: the header run line (`workbench-command`).
    expect(screen.queryByLabelText('chat.openPalette')).toBeNull()
  })
})
