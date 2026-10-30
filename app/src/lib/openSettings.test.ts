import { describe, expect, it, beforeEach } from 'vitest'
import { requestSettingsOpen, takePendingSettingsOpen } from './openSettings'

beforeEach(() => {
  window.location.hash = ''
})

describe('settings reach', () => {
  it('opens right away on the chat route', () => {
    let fired = 0
    const onOpen = () => {
      fired += 1
    }
    window.addEventListener('ephe:open-settings', onOpen)
    window.location.hash = '#/chat'
    requestSettingsOpen()
    window.removeEventListener('ephe:open-settings', onOpen)
    expect(fired).toBe(1)
    expect(takePendingSettingsOpen()).toBe(false)
  })

  it('carries the request through the route change from another page', () => {
    window.location.hash = '#/discover'
    requestSettingsOpen()
    expect(window.location.hash).toBe('#/chat')
    expect(takePendingSettingsOpen()).toBe(true)
    // At most once: the chat shell consumes it on mount.
    expect(takePendingSettingsOpen()).toBe(false)
  })
})
