/**
 * The restart gate. A relaunch ends the process the user is working in, so a
 * turn that is still running and a message the user has not sent both hold it
 * back. The shell call itself has to work through the global the plugin
 * defines and through the core channel the app uses everywhere.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { relaunchApp, restartGuardNow, setComposerDraft } from '@/lib/restartGuard'
import { useChatStore } from '@/store/chatStore'

const bridge = () => window as unknown as { __TAURI__?: unknown }

describe('U-4 — the restart gate reads live state', () => {
  beforeEach(() => {
    setComposerDraft('')
    useChatStore.setState({ isTyping: false })
  })
  afterEach(() => {
    setComposerDraft('')
    useChatStore.setState({ isTyping: false })
  })

  it('a running turn holds the restart', () => {
    useChatStore.setState({ isTyping: true })
    expect(restartGuardNow()).toEqual({ blocked: true, reason: 'running' })
  })

  it('an unsent draft holds the restart', () => {
    setComposerDraft('half a sentence')
    expect(restartGuardNow()).toEqual({ blocked: true, reason: 'draft' })
  })

  it('whitespace alone holds nothing', () => {
    setComposerDraft('   \n  ')
    expect(restartGuardNow()).toEqual({ blocked: false, reason: null })
  })

  it('a cleared composer and an idle store let the restart through', () => {
    setComposerDraft('')
    expect(restartGuardNow()).toEqual({ blocked: false, reason: null })
  })

  it('a running turn outranks a draft in the reason it reports', () => {
    useChatStore.setState({ isTyping: true })
    setComposerDraft('still typing')
    expect(restartGuardNow().reason).toBe('running')
  })
})

describe('U-4 — relaunchApp reaches the shell', () => {
  afterEach(() => {
    delete bridge().__TAURI__
  })

  it('calls the process global the plugin defines', async () => {
    const relaunch = vi.fn(async () => {})
    bridge().__TAURI__ = { process: { relaunch } }
    await expect(relaunchApp()).resolves.toBe(true)
    expect(relaunch).toHaveBeenCalledTimes(1)
  })

  it('falls back to the core channel with the plugin command', async () => {
    const invoke = vi.fn(async () => null)
    bridge().__TAURI__ = { core: { invoke } }
    await expect(relaunchApp()).resolves.toBe(true)
    expect(invoke).toHaveBeenCalledWith('plugin:process|restart')
  })

  it('answers false where no shell listens', async () => {
    await expect(relaunchApp()).resolves.toBe(false)
  })
})
