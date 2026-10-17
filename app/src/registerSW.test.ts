import { describe, it, expect, vi } from 'vitest'
import {
  registerServiceWorker,
  setupInstallPrompt,
  initPwa,
  type BeforeInstallPromptEvent,
  type ServiceWorkerLike,
} from '@/registerSW'
import { toastBus, type ToastItem } from '@/lib'

class FakeWorker {
  state: ServiceWorkerState = 'installing'
  messages: unknown[] = []
  private handlers = new Map<string, Set<() => void>>()

  addEventListener(type: string, cb: () => void): void {
    const set = this.handlers.get(type) ?? new Set<() => void>()
    set.add(cb)
    this.handlers.set(type, set)
  }
  postMessage(message: unknown): void {
    this.messages.push(message)
  }
  emit(type: string): void {
    this.handlers.get(type)?.forEach((cb) => cb())
  }
  listenerCount(type: string): number {
    return this.handlers.get(type)?.size ?? 0
  }
}

class FakeRegistration {
  installing: FakeWorker | null = null
  waiting: FakeWorker | null = null
  private handlers = new Map<string, Set<() => void>>()

  addEventListener(type: string, cb: () => void): void {
    const set = this.handlers.get(type) ?? new Set<() => void>()
    set.add(cb)
    this.handlers.set(type, set)
  }
  emit(type: string): void {
    this.handlers.get(type)?.forEach((cb) => cb())
  }
  listenerCount(type: string): number {
    return this.handlers.get(type)?.size ?? 0
  }
}

function asRegistration(reg: FakeRegistration): ServiceWorkerRegistration {
  return reg as unknown as ServiceWorkerRegistration
}

function makeContainer(reg: FakeRegistration, controller: ServiceWorker | null): ServiceWorkerLike {
  return {
    controller,
    register: vi.fn(async (_url: string) => asRegistration(reg)),
    getRegistrations: vi.fn(async () => [] as readonly ServiceWorkerRegistration[]),
  }
}

function installEvent(outcome: 'accepted' | 'dismissed'): {
  evt: BeforeInstallPromptEvent
  prompt: ReturnType<typeof vi.fn>
} {
  const prompt = vi.fn(async () => {})
  const evt = new Event('beforeinstallprompt', { cancelable: true })
  Object.assign(evt, { prompt, userChoice: Promise.resolve({ outcome, platform: 'web' }) })
  return { evt: evt as BeforeInstallPromptEvent, prompt }
}

describe('registerServiceWorker', () => {
  it('dev: deregisters any production worker left on the origin', async () => {
    const unregister = vi.fn(async () => true)
    const container: ServiceWorkerLike = {
      controller: null,
      register: vi.fn(async () => ({}) as ServiceWorkerRegistration),
      getRegistrations: vi.fn(async () => [{ unregister } as unknown as ServiceWorkerRegistration]),
    }
    registerServiceWorker({ dev: true, serviceWorker: container })
    await vi.waitFor(() => expect(unregister).toHaveBeenCalledTimes(1))
    expect(container.register).not.toHaveBeenCalled()
  })

  it('prod: registers /service-worker.js and offers an update once installed with a controller', async () => {
    const reg = new FakeRegistration()
    const container = makeContainer(reg, {} as ServiceWorker)
    const onUpdate = vi.fn()
    const reload = vi.fn()
    registerServiceWorker({ dev: false, serviceWorker: container, onUpdate, reload })

    await vi.waitFor(() => expect(reg.listenerCount('updatefound')).toBe(1))
    expect(container.register).toHaveBeenCalledWith('/service-worker.js')

    const worker = new FakeWorker()
    reg.installing = worker
    reg.emit('updatefound')
    worker.state = 'installed'
    worker.emit('statechange')

    expect(onUpdate).toHaveBeenCalledTimes(1)
    const activate = onUpdate.mock.calls[0]?.[0] as () => void
    activate()
    expect(worker.messages).toEqual([{ type: 'SKIP_WAITING' }])
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('first install (no controller) never shows the update banner', async () => {
    const reg = new FakeRegistration()
    const container = makeContainer(reg, null)
    const onUpdate = vi.fn()
    registerServiceWorker({ dev: false, serviceWorker: container, onUpdate })

    await vi.waitFor(() => expect(reg.listenerCount('updatefound')).toBe(1))
    const worker = new FakeWorker()
    reg.installing = worker
    reg.emit('updatefound')
    worker.state = 'installed'
    worker.emit('statechange')

    expect(onUpdate).not.toHaveBeenCalled()
  })

  it('a worker waiting from an earlier session is offered right away', async () => {
    const reg = new FakeRegistration()
    reg.waiting = new FakeWorker()
    const container = makeContainer(reg, {} as ServiceWorker)
    const onUpdate = vi.fn()
    registerServiceWorker({ dev: false, serviceWorker: container, onUpdate, reload: vi.fn() })
    await vi.waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1))
  })
})

describe('setupInstallPrompt', () => {
  it('captures beforeinstallprompt, suppresses the mini-infobar and prompts once', async () => {
    const target = new EventTarget()
    const onAvailable = vi.fn()
    const teardown = setupInstallPrompt({ target, onAvailable })

    const { evt, prompt } = installEvent('accepted')
    const notPrevented = target.dispatchEvent(evt)
    expect(notPrevented).toBe(false)
    expect(onAvailable).toHaveBeenCalledTimes(1)

    const install = onAvailable.mock.calls[0]?.[0]
    await expect(install.prompt()).resolves.toBe('accepted')
    expect(prompt).toHaveBeenCalledTimes(1)
    // the deferred event is spent — a second prompt has nothing to show
    await expect(install.prompt()).resolves.toBe('dismissed')
    teardown()
  })

  it('teardown removes both listeners', () => {
    const target = new EventTarget()
    const onAvailable = vi.fn()
    const onInstalled = vi.fn()
    const teardown = setupInstallPrompt({ target, onAvailable, onInstalled })
    teardown()

    target.dispatchEvent(installEvent('accepted').evt)
    target.dispatchEvent(new Event('appinstalled'))
    expect(onAvailable).not.toHaveBeenCalled()
    expect(onInstalled).not.toHaveBeenCalled()
  })

  it('reports the install via appinstalled', () => {
    const target = new EventTarget()
    const onInstalled = vi.fn()
    setupInstallPrompt({ target, onInstalled })
    target.dispatchEvent(new Event('appinstalled'))
    expect(onInstalled).toHaveBeenCalledTimes(1)
  })
})

describe('initPwa', () => {
  it('raises an install banner with a working action on beforeinstallprompt', async () => {
    const items: ToastItem[] = []
    const unsub = toastBus.subscribe((t) => items.push(t))
    initPwa({ dev: true })

    const { evt, prompt } = installEvent('accepted')
    window.dispatchEvent(evt)

    expect(items).toHaveLength(1)
    const action = items[0]?.action
    expect(action?.label).toBeTruthy()
    action?.onClick()
    await vi.waitFor(() => expect(prompt).toHaveBeenCalledTimes(1))
    unsub()
  })
})
