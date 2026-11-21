/**
 * #88 — the watched page shows the state it is in.
 *
 * `browserWatch.test.ts` proves the client computes the phases; this proves the surface
 * renders them, in the reader's words rather than the server's, and that a picture only
 * appears when there is one. The three states a reader can act on are the point: live,
 * still, and refused.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen, act } from '@testing-library/react'
import { BrowserWatch } from './BrowserWatch'
import type { WatchSnapshot } from '@/lib/browserWatch'

const { listeners } = vi.hoisted(() => ({
  listeners: new Set<(snapshot: WatchSnapshot) => void>(),
}))

/**
 * `vi.hoisted` because `vi.mock` is hoisted above every declaration in this file: a factory
 * that reached for a plain const would read it before it exists, which is the error a test
 * of this shape usually starts with.
 */
vi.mock('@/lib/browserWatch', () => ({
  watchBrowserSession: (_session: string, listener: (snapshot: WatchSnapshot) => void) => {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
}))

function emit(snapshot: WatchSnapshot): void {
  for (const listener of listeners) listener(snapshot)
}

/** app/src, found from the run's cwd (vitest runs at the app or the repo root). */
function findSrc(): string {
  for (const base of [process.cwd(), resolve(process.cwd(), 'app')]) {
    const candidate = resolve(base, 'src')
    if (existsSync(resolve(candidate, 'locales/en.json'))) return candidate
  }
  throw new Error(`app/src not found below ${process.cwd()}`)
}
const BUNDLE = JSON.parse(readFileSync(resolve(findSrc(), 'locales/en.json'), 'utf8')) as {
  chat: Record<string, string>
  serverError: Record<string, string>
}

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const [space, leaf] = key.split('.')
      const table = space === 'chat' ? BUNDLE.chat : BUNDLE.serverError
      const template =
        (leaf !== undefined && table[leaf]) || (options?.defaultValue as string) || key
      return template.replace(/\{\{(\w+)\}\}/g, (_match: string, name: string) =>
        String(options?.[name] ?? ''),
      )
    },
  }),
}))

const FRAME = {
  jpeg: 'aGVsbG8=',
  viewportWidth: 1280,
  viewportHeight: 800,
  castWidth: 800,
  castHeight: 500,
  scroll: 0,
  scale: 1,
  pageTop: 0,
  audit: null,
}

beforeEach(() => {
  listeners.clear()
})

function renderWatch(session = 'run-4') {
  const view = render(<BrowserWatch session={session} />)
  return {
    ...view,
    to: (snapshot: Partial<WatchSnapshot>) => {
      act(() => {
        emit({ phase: 'connecting', frame: null, ageS: 0, refusal: null, ...snapshot })
      })
    },
  }
}

describe('the browser watch surface', () => {
  it('says it is opening before anything arrived', () => {
    renderWatch()
    expect(screen.getByTestId('browser-watch').dataset.phase).toBe('connecting')
    expect(screen.getByTestId('browser-watch-state').textContent).toBe('Opening the view…')
    expect(screen.queryByTestId('browser-watch-frame')).toBeNull()
  })

  it('draws the frame at the page aspect ratio and names both spaces it was given', () => {
    const { to } = renderWatch()
    to({ phase: 'casting', frame: FRAME })

    const image = screen.getByTestId('browser-watch-frame') as HTMLImageElement
    expect(image.src).toContain('data:image/jpeg;base64,aGVsbG8=')
    expect(image.dataset.viewport).toBe('1280x800')
    expect(image.dataset.cast).toBe('800x500')
    expect(image.style.aspectRatio).toBe('1280 / 800')
  })

  /** The state line is the difference between a run that is thinking and one that is stuck. */
  it('reads a still page as still and keeps the last picture on screen', () => {
    const { to } = renderWatch()
    to({ phase: 'unchanged', frame: FRAME, ageS: 12 })

    expect(screen.getByTestId('browser-watch').dataset.phase).toBe('unchanged')
    expect(screen.getByTestId('browser-watch-state').textContent).toContain('12')
    expect(screen.getByTestId('browser-watch-frame')).toBeTruthy()
  })

  it('answers a refusal with the bundle sentence the code names', () => {
    const { to } = renderWatch('ghost')
    to({
      phase: 'refused',
      refusal: {
        code: 'browser_session_unknown',
        message: "the server said something in English about 'ghost'",
        params: { session: 'ghost' },
      },
    })

    const state = screen.getByTestId('browser-watch-state').textContent ?? ''
    expect(state).toContain('ghost')
    // The reader's words win; the server's English is only the fallback under the key.
    expect(state).not.toContain('the server said something')
  })

  it('says a session that ran out instead of spinning at a black picture', () => {
    const { to } = renderWatch()
    to({ phase: 'ended', frame: null })

    expect(screen.getByTestId('browser-watch').dataset.phase).toBe('ended')
    expect(screen.getByTestId('browser-watch-state').textContent).toBe(
      'This browser session is no longer running.',
    )
  })

  it('stops listening when the card it sits in goes away', () => {
    const view = renderWatch()
    expect(listeners.size).toBe(1)
    view.unmount()
    expect(listeners.size).toBe(0)
  })

  it('reads a frame with no audit row as unproven', () => {
    const { to } = renderWatch()
    to({ phase: 'casting', frame: { ...FRAME, audit: null } })
    expect(screen.getByTestId('browser-watch-proof').dataset.audit).toBe('missing')
    expect(screen.getByTestId('browser-watch-proof').textContent).toBe(
      'This frame has no audit row.',
    )
  })

  it('names the audit row beside a frame that has one', () => {
    const { to } = renderWatch()
    to({
      phase: 'casting',
      frame: {
        ...FRAME,
        audit: {
          kind: 'tool_exec',
          ts: '2026-11-07T12:00:00.000Z',
          tool: 'browser_go',
          verdict: 'observed',
          delta: { url_changed: 1 },
        },
      },
    })
    const proof = screen.getByTestId('browser-watch-proof')
    expect(proof.dataset.audit).toBe('bound')
    expect(proof.dataset.kind).toBe('tool_exec')
    expect(proof.dataset.verdict).toBe('observed')
    expect(proof.textContent).toContain('browser_go')
  })

  it('leaves the refusal with no picture to misread', () => {
    const { to } = renderWatch()
    to({ phase: 'refused', frame: null, refusal: { code: 'x', message: 'no', params: {} } })
    expect(screen.queryByTestId('browser-watch-frame')).toBeNull()
  })
})
