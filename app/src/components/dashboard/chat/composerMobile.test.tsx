/**
 * Composer mobile layout contract (WD-29).
 *
 * jsdom measures no layout, so what is held here is the class contract the
 * breakpoints encode — the same contract the pixel runs measure
 * (`tests/playwright/composer-width.spec.ts`, `mobile-viewport.spec.ts`).
 *
 * Rule: below lg (1024px) every interactive composer control reaches the 44px
 * touch floor (`max-lg:min-h-11`, square icon buttons also `max-lg:min-w-11`),
 * the action row reflows (`flex-wrap`), the command-palette button drops below
 * sm, and every composer menu row reaches the same floor.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { useRef } from 'react'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string, opts?: unknown) => {
      const o = opts as Record<string, unknown> | undefined
      return String(o && typeof o.defaultValue === 'string' ? o.defaultValue : key)
    },
  }),
}))

vi.mock('@/lib/api', () => ({
  getModelProviders: vi.fn(async () => ({
    active: { provider: 'local_ollama', model: 'gemma4:12b', offline_capable: true },
    providers: [{ provider: 'local_ollama', model: 'gemma4:12b', label: 'Local Ollama' }],
    local_models: [],
    local_model_options: [],
  })),
  transcribeAudio: vi.fn(async () => ''),
  listFs: vi.fn(async () => ({
    path: '/tmp/ws',
    parent: null,
    home: '/tmp',
    workspace: '/tmp/ws',
    entries: [],
  })),
  getSettings: vi.fn(async () => ({ workspace_dir: '/tmp/ws', approval_profile: 'strict' })),
  setModelProvider: vi.fn(async () => ({ active: { model: 'm1' } })),
  getSetupStatus: vi.fn(async () => ({ configured: true, provider: 'local_ollama' })),
}))

import ChatInput from '@/components/dashboard/ChatInput'
import ComposerMicButton from './ComposerMicButton'
import ComposerAttachMenu from './ComposerAttachMenu'
import { useChatStore } from '@/store/chatStore'

const cls = (testid: string) => screen.getByTestId(testid).className

beforeEach(() => {
  localStorage.clear()
  useChatStore.setState({ sessions: [], activeSessionId: null, currentSession: null } as never)
})

describe('composer mobile layout — the 44px touch floor below lg', () => {
  it('every interactive control in the action row carries the mobile floor', () => {
    render(<ChatInput onSend={vi.fn()} />)
    for (const id of [
      'composer-attach-plus',
      'model-chip',
      'composer-mode-selector',
      'send-btn',
      'composer-permission-badge',
    ]) {
      expect(cls(id), `${id} mobile touch floor`).toContain('max-lg:min-h-11')
    }
    // square icon controls keep the 44px width too
    expect(cls('composer-attach-plus')).toContain('max-lg:min-w-11')
    expect(cls('model-chip')).toContain('max-lg:min-w-11')
    expect(cls('send-btn')).toContain('max-lg:min-w-11')
    // the send button grows its padding below lg instead of the desktop min-h-9
    expect(cls('send-btn')).toContain('max-lg:p-3')
    // the thinking chip stays a status, but keeps the same row height
    expect(cls('composer-thinking-chip')).toContain('max-lg:min-h-11')
  })

  it('the action row reflows and keeps thumb separation when it does', () => {
    render(<ChatInput onSend={vi.fn()} />)
    const row = screen.getByTestId('composer-actions-row')
    expect(row.className).toContain('flex-wrap')
    // The column gap is narrow so the controls keep one line; the wider gap sits
    // on the rows, which is where a wrapped rail needs the thumb separation.
    const left = row.querySelector('.gap-x-1.gap-y-2')
    expect(left, 'left sub-group: narrow columns, wide rows').not.toBeNull()
  })

  it('the empty field is one line, and the touch floor holds it below sm and on touch', () => {
    render(<ChatInput onSend={vi.fn()} />)
    const field = screen.getByTestId('chat-input')
    // No height is written before the draft is measured, so the class list owns
    // the floor: one line of the ramp plus py-1, raised to 44px where a thumb works.
    for (const token of ['py-1', 'max-sm:min-h-11', 'pointer-coarse:min-h-11', 'max-h-32']) {
      expect(cls('chat-input'), `field keeps ${token}`).toContain(token)
    }
    expect(field.className).not.toContain('min-h-[48px]')
  })

  it('the command-palette button drops below sm so the row stays narrow', () => {
    render(<ChatInput onSend={vi.fn()} />)
    const palette = screen.getByLabelText('chat.openPalette')
    expect(palette.className).toContain('max-sm:hidden')
    expect(palette.className).toContain('max-lg:min-h-11')
  })

  it('the ask-mode hint only appears from md up', () => {
    useChatStore.setState({
      sessions: [{ id: 's1', mode: 'analyst' }],
      activeSessionId: 's1',
      currentSession: null,
    } as never)
    render(<ChatInput onSend={vi.fn()} />)
    const hint = screen.getByTestId('composer-ask-hint')
    expect(hint.className).toContain('hidden')
    expect(hint.className).toContain('md:inline')
  })

  it('the model chip and the permission badge clamp their width on mobile', () => {
    render(<ChatInput onSend={vi.fn()} />)
    // the label span clamps narrower below lg so the chip cannot push the row
    expect(screen.getByTestId('model-chip').querySelector('.max-lg\\:max-w-28')).not.toBeNull()
    expect(cls('composer-permission-badge')).toContain('max-lg:max-w-20')
  })
})

describe('extracted composer controls — the same floor without the store', () => {
  it('the mic button keeps the 44px floor', () => {
    const levels = { current: new Float32Array(4) }
    render(
      <ComposerMicButton
        recording={false}
        transcribing={false}
        micFrame={0}
        micLevelsRef={levels}
        onPointerDown={vi.fn()}
        onPointerUp={vi.fn()}
      />,
    )
    const btn = screen.getByRole('button')
    expect(btn.className).toContain('max-lg:min-h-11')
    expect(btn.className).toContain('max-lg:min-w-11')
  })

  it('every plus-menu row reaches the 44px floor', () => {
    function Host() {
      const anchorRef = useRef<HTMLButtonElement>(null)
      return (
        <ComposerAttachMenu
          pos={{ left: 40, bottom: 80 }}
          anchorRef={anchorRef}
          onClose={vi.fn()}
          onAttachFile={vi.fn()}
          onAttachImage={vi.fn()}
          onCaptureScreen={vi.fn()}
          onWideResearch={vi.fn()}
        />
      )
    }
    render(<Host />)
    const rows = screen.getAllByRole('menuitem')
    expect(rows.length).toBeGreaterThanOrEqual(2)
    for (const row of rows) expect(row.className).toContain('max-lg:min-h-11')
  })
})
