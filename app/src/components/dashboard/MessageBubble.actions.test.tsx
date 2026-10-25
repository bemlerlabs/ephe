/**
 * G1.1/G1.2 — messaging parity: the action UI inside MessageBubble
 *
 * GIVEN  a MessageBubble with onEdit / onRegenerate / onRetry callbacks
 * WHEN   a user message is hovered and edited
 * THEN   it offers Edit → the inline textarea → Save calls onEdit(id, text)
 * AND    assistant bubbles offer Regenerate (never while streaming)
 * AND    error bubbles offer Try again (onRetry)
 * AND    while streaming NONE of the actions appears
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import MessageBubble from '@/components/dashboard/MessageBubble'

vi.mock('react-markdown', () => ({
  default: ({ children }: { children: string }) => (
    <div data-testid="markdown">{String(children)}</div>
  ),
}))
vi.mock('remark-gfm', () => ({ default: () => (node: unknown) => node }))
vi.mock('rehype-highlight', () => ({ default: () => (node: unknown) => node }))
vi.mock('@/components/dashboard/CodeBlock', () => ({
  default: ({ children }: { children?: React.ReactNode }) => <pre>{children}</pre>,
}))
vi.mock('@/lib/utils', () => ({ formatTime: () => '12:00' }))
vi.mock('@/lib/api', () => ({
  synthesizeSpeech: vi.fn(() => Promise.resolve('/audio/tts_test.mp3')),
}))
vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: (() => ({ t: (key: string) => key, i18n: { language: 'de' } })) as never,
}))

import type { ChatMessage } from '@/types'

function userMsg(content: string): ChatMessage {
  return { id: 'u1', role: 'user', content, timestamp: 0 } as ChatMessage
}
function assistantMsg(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: 'a1',
    role: 'assistant',
    content: 'Antwort',
    timestamp: 0,
    ...overrides,
  } as ChatMessage
}

describe('MessageBubble Actions (G1)', () => {
  it('User-Bubble: Bearbeiten öffnet Inline-Textarea, Speichern ruft onEdit(id, text)', () => {
    const onEdit = vi.fn()
    render(<MessageBubble message={userMsg('erste Frage')} onEdit={onEdit} />)

    fireEvent.click(screen.getByRole('button', { name: 'chat.edit' }))
    const box = screen.getByRole('textbox') as HTMLTextAreaElement
    expect(box.value).toBe('erste Frage')

    fireEvent.change(box, { target: { value: 'geänderte Frage' } })
    fireEvent.click(screen.getByRole('button', { name: 'chat.save' }))
    expect(onEdit).toHaveBeenCalledWith('u1', 'geänderte Frage')
    // the editor is closed again
    expect(screen.queryByRole('textbox')).toBeNull()
  })

  it('User-Bubble: Abbrechen schließt den Editor ohne onEdit', () => {
    const onEdit = vi.fn()
    render(<MessageBubble message={userMsg('Frage')} onEdit={onEdit} />)
    fireEvent.click(screen.getByRole('button', { name: 'chat.edit' }))
    fireEvent.click(screen.getByRole('button', { name: 'chat.cancel' }))
    expect(onEdit).not.toHaveBeenCalled()
    expect(screen.queryByRole('textbox')).toBeNull()
  })

  it('User-Bubble ohne onEdit-Callback zeigt keinen Bearbeiten-Knopf', () => {
    render(<MessageBubble message={userMsg('Frage')} />)
    expect(screen.queryByRole('button', { name: 'chat.edit' })).toBeNull()
  })

  it('Assistant-Bubble: Neu generieren ruft onRegenerate (nicht beim Streaming)', () => {
    const onRegenerate = vi.fn()
    const { rerender } = render(
      <MessageBubble message={assistantMsg()} onRegenerate={onRegenerate} />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'chat.regenerate' }))
    expect(onRegenerate).toHaveBeenCalledTimes(1)

    // streaming → no Regenerate button
    rerender(
      <MessageBubble message={assistantMsg({ streaming: true })} onRegenerate={onRegenerate} />,
    )
    expect(screen.queryByRole('button', { name: 'chat.regenerate' })).toBeNull()
  })

  it('Fehler-Bubble: Erneut versuchen ruft onRetry', () => {
    const onRetry = vi.fn()
    render(
      <MessageBubble
        message={assistantMsg({ error: 'Boom', streaming: false })}
        onRetry={onRetry}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'chat.retry' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('error bubble: a failed turn offers retry, not engine setup', () => {
    render(
      <MessageBubble
        message={assistantMsg({
          error: 'Failed to connect to Ollama at http://127.0.0.1:11434',
          errorCode: 'stream_closed_before_done',
          streaming: false,
          durationMs: 1200,
        })}
        onRetry={vi.fn()}
      />,
    )
    // S19: the engine answered this turn, so its absence is not the diagnosis.
    expect(screen.queryByTestId('error-setup-engine')).toBeNull()
    // A known connection failure is rendered in the UI language, not as the
    // backend's English sentence.
    expect(screen.getByText('chat.errorEngineUnreachable')).toBeTruthy()
    expect(screen.getByText('chat.turnFailed')).toBeTruthy()
    expect(screen.queryByText(/chat.turnWorked/)).toBeNull()
  })


  it('Assistant-Bubble: Vorlesen-Knopf ruft synthesizeSpeech (G4)', async () => {
    const { synthesizeSpeech } = await import('@/lib/api')
    render(<MessageBubble message={assistantMsg()} />)
    fireEvent.click(screen.getByRole('button', { name: 'chat.speak' }))
    expect(synthesizeSpeech).toHaveBeenCalledWith('Antwort')
  })

  it('ohne Fehler kein Retry-Knopf; ohne Callbacks keine Aktionsleiste', () => {
    render(<MessageBubble message={assistantMsg()} />)
    expect(screen.queryByRole('button', { name: 'chat.retry' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'chat.regenerate' })).toBeNull()
  })
})
