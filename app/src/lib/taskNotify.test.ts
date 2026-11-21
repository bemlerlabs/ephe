/**
 * Ephe — Wave 3 (Finding 4): native Task-Completion-Notification.
 *
 * GIVEN a hidden tab state (user elsewhere) and granted permission
 * WHEN  the turn ends (notifyTaskDone)
 * THEN  exactly one notification appears, with tag 'ephe-task-done'.
 * GIVEN a visible tab OR missing permission
 * THEN  no popup — in the foreground every notification annoys.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { notifyTaskDone, requestTaskNotifyPermission, notificationsSupported } from './taskNotify'

type NotifCtor = new (title: string, opts?: { body?: string; tag?: string }) => unknown

describe('taskNotify (Wave 3, Finding 4)', () => {
  let ctor: ReturnType<typeof vi.fn>

  beforeEach(() => {
    ctor = vi.fn()
    vi.stubGlobal('Notification', ctor as unknown as NotifCtor)
    Object.defineProperty(ctor, 'permission', { value: 'granted', configurable: true })
    Object.defineProperty(ctor, 'requestPermission', {
      value: vi.fn(async () => 'granted'),
      configurable: true,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('shows a notification on a hidden tab with permission', () => {
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
    notifyTaskDone('Ephe — task finished', 'Aufgabe: Einkaufsliste')
    expect(ctor).toHaveBeenCalledTimes(1)
    const [, opts] = ctor.mock.calls[0] as [string, { tag?: string; body?: string }]
    expect(opts.tag).toBe('ephe-task-done')
    expect(opts.body).toContain('Einkaufsliste')
  })

  it('no notification on a visible tab', () => {
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
    notifyTaskDone('Ephe — task finished', 'x')
    expect(ctor).not.toHaveBeenCalled()
  })

  it('no notification without a granted permission', () => {
    Object.defineProperty(ctor, 'permission', { value: 'denied', configurable: true })
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
    notifyTaskDone('Ephe — task finished', 'x')
    expect(ctor).not.toHaveBeenCalled()
  })

  it('the permission request fires only in the default state', () => {
    Object.defineProperty(ctor, 'permission', { value: 'default', configurable: true })
    const req = (ctor as unknown as { requestPermission: ReturnType<typeof vi.fn> })
      .requestPermission
    requestTaskNotifyPermission()
    expect(req).toHaveBeenCalledTimes(1)
    Object.defineProperty(ctor, 'permission', { value: 'granted', configurable: true })
    requestTaskNotifyPermission()
    expect(req).toHaveBeenCalledTimes(1) // no second request
  })

  it('without the notification API everything is a no-op', () => {
    vi.unstubAllGlobals()
    expect(notificationsSupported()).toBe(false)
    expect(() => notifyTaskDone('t', 'b')).not.toThrow()
    expect(() => requestTaskNotifyPermission()).not.toThrow()
  })
})
