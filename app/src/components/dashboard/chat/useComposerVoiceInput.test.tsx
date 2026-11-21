/**
 * QD-008 M1/M2 — the recording state machine and the recorder's MIME choice.
 *
 * The owner's 1-minute TCC check on the installed app found both defects at the
 * microphone: a first click started the recording and a second click could not
 * end it (the latch was only cleared on pointerup, and a latched recorder made
 * every later press a no-op), and nothing was transcribed on this machine
 * because the recorder asked for `audio/webm`, which WKWebView does not record.
 *
 * These tests drive the hook the way the button drives it: press, release, and
 * the browser's own stop callback. jsdom has neither getUserMedia nor
 * MediaRecorder, so both arrive as stand-ins that record what the hook asked
 * them for.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

const transcribeAudio = vi.hoisted(() => vi.fn(async (_blob: Blob) => 'voice note'))
vi.mock('@/lib/api', () => ({ transcribeAudio }))

const toastError = vi.hoisted(() => vi.fn())
vi.mock('@/lib/toast', () => ({ toastBus: { error: toastError, info: vi.fn(), success: vi.fn() } }))

import { useComposerVoiceInput } from './useComposerVoiceInput'

class FakeRecorder {
  static isTypeSupported = (_type: string) => true
  static instances: FakeRecorder[] = []
  ondataavailable: ((e: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null
  state = 'inactive'
  mimeType: string
  constructor(_stream: unknown, opts?: { mimeType?: string }) {
    this.mimeType = opts?.mimeType ?? ''
    FakeRecorder.instances.push(this)
  }
  start() {
    this.state = 'recording'
  }
  stop() {
    this.state = 'inactive'
    this.ondataavailable?.({ data: new Blob(['pcm'], { type: this.mimeType || 'audio/webm' }) })
    this.onstop?.()
  }
}

const trackStop = vi.fn()
const getUserMedia = vi.fn(async () => ({ getTracks: () => [{ stop: trackStop }] }))

function mount() {
  const setMessage = vi.fn()
  const textareaRef = { current: null } as unknown as { current: HTMLTextAreaElement | null }
  const view = renderHook(() => useComposerVoiceInput({ setMessage, textareaRef }))
  return { ...view, setMessage }
}

const tick = () => act(async () => { await Promise.resolve() })

beforeEach(() => {
  FakeRecorder.instances = []
  FakeRecorder.isTypeSupported = () => true
  getUserMedia.mockClear()
  trackStop.mockClear()
  transcribeAudio.mockClear()
  transcribeAudio.mockImplementation(async () => 'voice note')
  toastError.mockClear()
  ;(globalThis as unknown as { MediaRecorder: unknown }).MediaRecorder = FakeRecorder
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia },
  })
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-27T20:00:00Z'))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('QD-008 M1 — tap to stop a latched recording', () => {
  it('a second click stops the recording and hands the audio to transcription', async () => {
    const { result, setMessage } = mount()

    act(() => result.current.onMicPointerDown())
    act(() => result.current.onMicPointerUp())
    await tick()
    expect(result.current.recording).toBe(true)

    act(() => {
      vi.setSystemTime(new Date('2026-10-27T20:00:05Z'))
      result.current.onMicPointerDown()
    })
    act(() => result.current.onMicPointerUp())
    await tick()

    expect(result.current.recording).toBe(false)
    expect(trackStop).toHaveBeenCalled()
    expect(transcribeAudio).toHaveBeenCalledTimes(1)
    expect(setMessage).toHaveBeenCalled()
    const applied = setMessage.mock.calls[0]![0] as (prev: string) => string
    expect(applied('')).toBe('voice note')
  })

  it('a short tap still latches when the microphone permission resolves late', async () => {
    let grant: ((stream: unknown) => void) | null = null
    getUserMedia.mockImplementationOnce(
      () => new Promise((resolve) => { grant = resolve as (s: unknown) => void }) as never,
    )
    const { result } = mount()

    act(() => result.current.onMicPointerDown())
    act(() => result.current.onMicPointerUp()) // ends before the grant arrives
    await act(async () => {
      grant?.({ getTracks: () => [{ stop: trackStop }] })
      await Promise.resolve()
    })

    expect(result.current.recording).toBe(true)
    expect(FakeRecorder.instances).toHaveLength(1)
  })

  it('holding past the threshold stops on release instead of latching', async () => {
    const { result } = mount()

    act(() => result.current.onMicPointerDown())
    await tick()
    expect(result.current.recording).toBe(true)

    act(() => {
      vi.setSystemTime(new Date('2026-10-27T20:00:02Z'))
      result.current.onMicPointerUp()
    })
    await tick()

    expect(result.current.recording).toBe(false)
    expect(transcribeAudio).toHaveBeenCalledTimes(1)
  })

  it('Escape cancels a running recording without transcribing it', async () => {
    const { result, setMessage } = mount()

    act(() => result.current.onMicPointerDown())
    act(() => result.current.onMicPointerUp())
    await tick()
    expect(result.current.recording).toBe(true)

    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    })
    await tick()

    expect(result.current.recording).toBe(false)
    expect(trackStop).toHaveBeenCalled()
    expect(transcribeAudio).not.toHaveBeenCalled()
    expect(setMessage).not.toHaveBeenCalled()
  })
})

describe('QD-008 M2 — the recorder asks for a format it can record', () => {
  it('prefers webm/opus where the engine supports it', async () => {
    FakeRecorder.isTypeSupported = () => true
    const { result } = mount()

    act(() => result.current.onMicPointerDown())
    await tick()

    expect(FakeRecorder.instances[0]!.mimeType).toBe('audio/webm;codecs=opus')
  })

  it('falls back to audio/mp4 when the shell records only MP4', async () => {
    FakeRecorder.isTypeSupported = (type: string) => type.startsWith('audio/mp4')
    const { result } = mount()

    act(() => result.current.onMicPointerDown())
    await tick()
    act(() => {
      vi.setSystemTime(new Date('2026-10-27T20:00:02Z'))
      result.current.onMicPointerUp()
    })
    await tick()

    expect(FakeRecorder.instances[0]!.mimeType).toBe('audio/mp4')
    expect(transcribeAudio).toHaveBeenCalledTimes(1)
    const blob = transcribeAudio.mock.calls[0]![0] as unknown as Blob
    expect(blob.type).toBe('audio/mp4')
  })

  it('constructs the recorder without options when nothing is advertised', async () => {
    ;(FakeRecorder as unknown as { isTypeSupported?: unknown }).isTypeSupported = undefined
    const { result } = mount()

    act(() => result.current.onMicPointerDown())
    await tick()

    expect(FakeRecorder.instances).toHaveLength(1)
    expect(FakeRecorder.instances[0]!.mimeType).toBe('')
  })
})

describe('QD-008 M2 — a failed start releases the microphone', () => {
  it('stops the stream tracks when the recorder cannot be built', async () => {
    class BrokenRecorder extends FakeRecorder {
      constructor(stream: unknown, opts?: { mimeType?: string }) {
        super(stream, opts)
        throw new Error('recorder unsupported')
      }
    }
    ;(globalThis as unknown as { MediaRecorder: unknown }).MediaRecorder = BrokenRecorder
    const { result } = mount()

    act(() => result.current.onMicPointerDown())
    await tick()

    expect(result.current.recording).toBe(false)
    expect(trackStop).toHaveBeenCalled()
    expect(toastError).toHaveBeenCalled()
  })

  it('reports a denied microphone instead of going quiet', async () => {
    getUserMedia.mockRejectedValueOnce(new DOMException('denied', 'NotAllowedError'))
    const { result } = mount()

    act(() => result.current.onMicPointerDown())
    await tick()

    expect(result.current.recording).toBe(false)
    expect(toastError).toHaveBeenCalledWith('chat.micDenied')
  })
})
