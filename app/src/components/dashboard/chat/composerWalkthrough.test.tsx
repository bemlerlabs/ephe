/**
 * W3-50 — the composer as ONE walkthrough: attachments, @-mentions, slash, voice.
 *
 * The four input affordances of the composer had tests one feature at a time
 * (mentions in ChatInput.p3, slash in ChatInput.test, attachments in the drop
 * suite, voice only as an isolated button contract), but nothing walked them in
 * one pass over the same live composer. This file holds the interaction story:
 *
 *   attach, mention, slash, voice, send — in that order
 *
 * and it pins the seam the walkthrough exposed: an open @-popup is only valid for
 * the exact text its token was detected in. Every draft change that does NOT come
 * from a keystroke (a voice transcript, a slash pick, the wide-research template,
 * a recalled message) used to leave the popup live with stale offsets — the next
 * Enter then inserted a path at the wrong span and swallowed the send. The fix
 * lives in chat/useComposerMentions (detectedInRef + a close effect); these tests
 * lock it.
 *
 * jsdom measures no layout — this asserts roles, text and behaviour, never pixels.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string, opts?: unknown) => {
      const o = opts as Record<string, unknown> | undefined
      // The wide-research row writes a template into the draft — a fixed sentinel
      // stands in for the long real string so the assertion stays readable.
      if (key === 'chat.wideResearchTemplate') return 'WR_TEMPLATE'
      return String(o && typeof o.defaultValue === 'string' ? o.defaultValue : key)
    },
  }),
}))

const transcribeAudio = vi.hoisted(() => vi.fn(async () => 'voice note'))
vi.mock('@/lib/api', () => ({
  getModelProviders: vi.fn(async () => ({
    active: { provider: 'local_ollama', model: 'gemma4:12b', offline_capable: true },
    providers: [{ provider: 'local_ollama', model: 'gemma4:12b', label: 'Local Ollama' }],
    local_models: [],
    local_model_options: [],
  })),
  transcribeAudio,
  listFs: vi.fn(async () => ({
    path: '/tmp/ws',
    parent: null,
    home: '/tmp',
    workspace: '/tmp/ws',
    // P3-3 order: prefix hit first so «@rea» picks README.md deterministically.
    entries: [
      { name: 'README.md', type: 'file', size: 1 },
      { name: 'reading-list.md', type: 'file', size: 1 },
      { name: 'app', type: 'dir', size: 0 },
    ],
  })),
  getSettings: vi.fn(async () => ({ workspace_dir: '/tmp/ws', approval_profile: 'strict' })),
  setModelProvider: vi.fn(async () => ({ active: { model: 'm1' } })),
  getSetupStatus: vi.fn(async () => ({ configured: true, provider: 'local_ollama' })),
}))

import ChatInput from '@/components/dashboard/ChatInput'
import { useChatStore } from '@/store/chatStore'

const ta = () => screen.getByTestId('chat-input') as HTMLTextAreaElement

// voice harness
// jsdom ships no MediaRecorder; the component only needs start()/stop() and the
// onstop callback, so a recorder that records its instances and lets the test
// fire the browser's stop signal stands in. MediaRecorder.stop() is what a real
// hold-to-talk release triggers — calling it here is the same event, and like
// the real one it hands the buffered audio over before onstop runs.
class FakeRecorder {
  ondataavailable: ((e: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null
  constructor(_stream: unknown, _opts?: unknown) {
    recs.push(this)
  }
  start() {}
  stop() {
    this.ondataavailable?.({ data: new Blob(['pcm'], { type: 'audio/webm' }) })
    this.onstop?.()
  }
}
let recs: FakeRecorder[] = []

const fileDt = (files: File[]) =>
  ({
    types: ['Files'],
    files,
    data: { getData: () => '', setData: () => {} },
  }) as unknown as DataTransfer

/** Press the mic, let getUserMedia resolve, then let the recorder stop. */
async function dictate(text = 'voice note') {
  transcribeAudio.mockResolvedValueOnce(text)
  fireEvent.pointerDown(screen.getByRole('button', { name: /stopRecording|voiceInput|holdToTalk/ }))
  await act(async () => {
    await Promise.resolve()
  })
  expect(recs.length).toBeGreaterThan(0)
  await act(async () => {
    recs[recs.length - 1]!.stop()
  })
}

beforeEach(() => {
  localStorage.clear()
  useChatStore.setState({ sessions: [], activeSessionId: null, currentSession: null } as never)
  recs = []
  ;(globalThis as unknown as { MediaRecorder: unknown }).MediaRecorder = FakeRecorder
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: vi.fn() }] })) },
  })
  transcribeAudio.mockReset()
  transcribeAudio.mockImplementation(async () => 'voice note')
})

describe('W3-50 composer walkthrough — attach ▶ mention ▶ slash ▶ voice ▶ send', () => {
  it('walks all four input affordances over one composer and hands the draft off once', async () => {
    const onSend = vi.fn()
    const onSlash = vi.fn()
    render(<ChatInput onSend={onSend} onSlashCommand={onSlash} />)
    await screen.findByTestId('chat-input')

    // 1. attach — a file dropped anywhere in the viewport becomes a chip.
    const file = new File(['hello'], 'walkthrough.txt', { type: 'text/plain' })
    await act(async () => {
      fireEvent.dragEnter(window, { dataTransfer: fileDt([file]) })
      fireEvent.drop(document.body, { dataTransfer: fileDt([file]) })
    })
    expect(await screen.findByText('walkthrough.txt')).toBeTruthy()

    // 2. mention — «@rea» opens the workspace list; Enter inserts the path and
    //    must NOT send. The attachment from step 1 survives the edit.
    fireEvent.change(ta(), { target: { value: '@rea', selectionStart: 4 } })
    await screen.findByTestId('mention-popup')
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSend).not.toHaveBeenCalled()
    expect(ta().value).toBe('/tmp/ws/README.md ')
    expect(screen.queryByTestId('mention-popup')).toBeNull()
    expect(screen.getByText('walkthrough.txt')).toBeTruthy()

    // 3. slash — the same composer still completes commands; the attachment stays.
    fireEvent.change(ta(), { target: { value: '' } })
    fireEvent.change(ta(), { target: { value: '/comp' } })
    await screen.findByTestId('slash-menu')
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(ta().value).toBe('/compact')
    expect(screen.getByText('walkthrough.txt')).toBeTruthy()
    // exact command + Enter routes to the parent, never to the model.
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSlash).toHaveBeenCalledWith('/compact')
    expect(onSend).not.toHaveBeenCalled()
    expect(ta().value).toBe('')
    // …and the slash command must not have discarded the attachment chip.
    expect(screen.getByText('walkthrough.txt')).toBeTruthy()

    // 4. voice — transcript lands in the draft, it does not auto-send.
    await dictate('summarize the readme')
    await waitFor(() => expect(ta().value).toBe('summarize the readme'))
    expect(onSend).not.toHaveBeenCalled()

    // 5. send — Enter hands message + the still-attached file to the parent once,
    //    then clears both the draft and the chip row.
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSend).toHaveBeenCalledTimes(1)
    expect(onSend).toHaveBeenCalledWith('summarize the readme', [
      expect.objectContaining({ name: 'walkthrough.txt' }),
    ])
    expect(ta().value).toBe('')
    expect(screen.queryByText('walkthrough.txt')).toBeNull()
  })
})

describe('W3-50 coherence — a programmatic draft change closes the stale @-popup', () => {
  it('the wide-research template replaces the draft and closes the popup (Enter is not swallowed)', async () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    await screen.findByTestId('chat-input')

    fireEvent.change(ta(), { target: { value: '@rea', selectionStart: 4 } })
    await screen.findByTestId('mention-popup')

    // Programmatic change, no keystroke: the plus menu writes the template.
    fireEvent.click(screen.getByTestId('composer-attach-plus'))
    fireEvent.click(screen.getByTestId('composer-wide-research'))
    expect(ta().value).toBe('WR_TEMPLATE')
    // The token's offsets describe text that no longer exists → popup must be gone.
    expect(screen.queryByTestId('mention-popup')).toBeNull()

    // …so Enter sends the template instead of corrupting it into a path insert.
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSend).toHaveBeenCalledWith('WR_TEMPLATE', undefined)
    expect(ta().value).toBe('')
  })

  it('a voice transcript typed after an @-token closes the popup instead of leaving it stale', async () => {
    render(<ChatInput onSend={vi.fn()} />)
    await screen.findByTestId('chat-input')

    fireEvent.change(ta(), { target: { value: '@rea', selectionStart: 4 } })
    await screen.findByTestId('mention-popup')

    await dictate('please')
    await waitFor(() => expect(ta().value).toContain('please'))
    expect(screen.queryByTestId('mention-popup')).toBeNull()
  })
})

describe('W4-28 queue flush keeps the composer chips', () => {
  // W3-50 stopped the slash path from discarding the composer's chips. The
  // queue flush in sendNextQueued carried the same defect, rarer: it cleared
  // the live attachments while sending the queued item, which brings its own.
  // A file the user dropped for the next draft vanished when the stream settled.

  it('the stream-settle auto-flush keeps the chip the user attached for the next draft', async () => {
    const onSend = vi.fn()
    const { rerender } = render(<ChatInput onSend={onSend} streaming={false} />)
    await screen.findByTestId('chat-input')

    // Turn running → Enter queues instead of starting a parallel send.
    rerender(<ChatInput onSend={onSend} streaming={true} />)
    fireEvent.change(ta(), { target: { value: 'queued task' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSend).not.toHaveBeenCalled()
    expect(screen.getByText(/queue/i)).toBeTruthy()

    // The user drops a file for the NEXT draft while the answer still runs.
    const kept = new File(['x'], 'kept.txt', { type: 'text/plain' })
    await act(async () => {
      fireEvent.dragEnter(window, { dataTransfer: fileDt([kept]) })
      fireEvent.drop(document.body, { dataTransfer: fileDt([kept]) })
    })
    expect(await screen.findByText('kept.txt')).toBeTruthy()

    // Stream settles → the queue flushes on its own…
    rerender(<ChatInput onSend={onSend} streaming={false} />)
    expect(onSend).toHaveBeenCalledWith('queued task', undefined)
    expect(screen.queryByText(/queue/i)).toBeNull()
    // …and the file attached for the next draft is still on screen.
    expect(screen.getByText('kept.txt')).toBeTruthy()
  })

  it('the empty-composer Enter that flushes the queue also keeps the chip', async () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    await screen.findByTestId('chat-input')

    // Alt+Enter puts the current draft in the queue without sending.
    fireEvent.change(ta(), { target: { value: 'queued task' } })
    fireEvent.keyDown(ta(), { key: 'Enter', altKey: true })
    expect(onSend).not.toHaveBeenCalled()

    const kept = new File(['x'], 'kept.txt', { type: 'text/plain' })
    await act(async () => {
      fireEvent.dragEnter(window, { dataTransfer: fileDt([kept]) })
      fireEvent.drop(document.body, { dataTransfer: fileDt([kept]) })
    })
    expect(await screen.findByText('kept.txt')).toBeTruthy()

    // Empty composer + non-empty queue + Enter → the queued item goes out.
    fireEvent.keyDown(ta(), { key: 'Enter' })
    expect(onSend).toHaveBeenCalledWith('queued task', undefined)
    // The chip belongs to the next draft, not to the flushed item.
    expect(screen.getByText('kept.txt')).toBeTruthy()
  })
})
