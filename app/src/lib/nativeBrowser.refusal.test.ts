/**
 * SEC-A: what the pane reports when it will not take an address.
 *
 * The refusal is decided in the shell (`src-tauri/src/browser.rs`, at both doors:
 * the `browser_open` argument and every navigation a loaded page asks for) and
 * arrives here as an event, because a cancelled navigation that says nothing is a
 * dead link as far as the user is concerned. These are the frontend half: the
 * channel is subscribed, the payload is turned into a state, and the codes are the
 * two the shell sends.
 *
 * The bridge is simulated (`window.__TAURI__`); the rest is the real module.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  hasNativeBrowser,
  listenNativeBrowser,
  refusalReason,
  usesNativeBrowser,
  type BrowserEvent,
} from './nativeBrowser'

type Handler = (e: { payload: unknown }) => void

let subscribed: string[] = []
let handlers: Record<string, Handler> = {}

function simulateShell() {
  subscribed = []
  handlers = {}
  ;(window as unknown as { __TAURI__: unknown }).__TAURI__ = {
    core: { invoke: vi.fn(async () => null) },
    event: {
      listen: (name: string, handler: Handler) => {
        subscribed.push(name)
        handlers[name] = handler
        return Promise.resolve(() => {
          delete handlers[name]
        })
      },
    },
  }
}

const emit = (name: string, payload: unknown) => handlers[name]?.({ payload })

/** Subscribe, and hand back what the surface saw plus the cleanup. */
function watch() {
  const events: BrowserEvent[] = []
  const stop = listenNativeBrowser((event) => events.push(event))
  return { events, stop }
}

describe('the browser pane reports the address it refused', () => {
  beforeEach(() => {
    simulateShell()
  })

  afterEach(() => {
    delete (window as unknown as { __TAURI__?: unknown }).__TAURI__
  })

  it('subscribes to the refusal channel beside the four it already had', () => {
    const { stop } = watch()
    expect(subscribed.sort()).toEqual(
      [
        'browser:load',
        'browser:navigation',
        'browser:new-window',
        'browser:refused',
        'browser:title',
      ].sort(),
    )
    stop()
  })

  /** GIVEN a shell that refused an address THEN the surface gets address, scheme and code. */
  it('turns a refusal into a state with the address, the scheme and the code', () => {
    const { events, stop } = watch()
    emit('browser:refused', {
      url: 'file:///etc/hosts',
      scheme: 'file',
      reason: 'scheme-not-allowed',
    })

    expect(events).toEqual([
      { kind: 'refused', url: 'file:///etc/hosts', scheme: 'file', reason: 'scheme-not-allowed' },
    ])
    stop()
  })

  // The codes are `browser.rs`'s `Refusal::code()`. A rename there without one here
  // would land an unknown value on the surface, which is why the pair is fixed and
  // the fallback is named rather than empty.
  it('knows exactly the two codes the shell sends', () => {
    const { events, stop } = watch()
    emit('browser:refused', {
      url: 'http://ipc.localhost/x',
      scheme: 'http',
      reason: 'app-own-origin',
    })
    emit('browser:refused', { url: 'file:///x', scheme: 'file', reason: 'not-a-code-yet' })

    expect(events.map((event) => (event.kind === 'refused' ? event.reason : event.kind))).toEqual([
      'app-own-origin',
      'scheme-not-allowed',
    ])
    expect(refusalReason(undefined)).toBe('scheme-not-allowed')
    stop()
  })

  /** A refusal does not replace the load events; the pane simply stays where it was. */
  it('keeps the channel of the page it did allow', () => {
    const { events, stop } = watch()
    emit('browser:navigation', { url: 'https://example.com/' })
    emit('browser:load', { phase: 'finished', url: 'https://example.com/' })

    expect(events.map((event) => event.kind)).toEqual(['navigation', 'load'])
    stop()
  })

  /**
   * The surface still hands the shell only what it may show: an external site goes
   * native, this machine's own servers and a `file:` address do not — they never
   * reach `browser_open`, and the shell would refuse the `file:` one anyway.
   */
  it('routes only external http(s) to the native pane', () => {
    expect(usesNativeBrowser('https://example.com/a')).toBe(true)
    expect(usesNativeBrowser('http://example.com')).toBe(true)
    expect(usesNativeBrowser('http://127.0.0.1:8765/api/x')).toBe(false)
    expect(usesNativeBrowser('http://localhost:5173/#/chat')).toBe(false)
    expect(usesNativeBrowser('file:///etc/hosts')).toBe(false)
    expect(usesNativeBrowser('/api/file?path=x')).toBe(false)
  })

  it('says there is no native pane at all without the shell', () => {
    delete (window as unknown as { __TAURI__?: unknown }).__TAURI__
    expect(hasNativeBrowser()).toBe(false)
    expect(usesNativeBrowser('https://example.com/')).toBe(false)
  })
})
