/**
 * PWA wiring: service-worker registration, the update banner and the install
 * prompt. Kept free of React so both flows can be exercised directly; `initPwa`
 * is the one entry point that touches the app's toast and i18n surface.
 */
import { toastBus } from '@/lib'
import i18n from '@/i18n'

/** The navigator.serviceWorker subset the registration flow uses. */
export interface ServiceWorkerLike {
  controller: ServiceWorker | null
  register(scriptURL: string): Promise<ServiceWorkerRegistration>
  getRegistrations(): Promise<readonly ServiceWorkerRegistration[]>
}

export interface RegisterOptions {
  /** True in the Vite dev server: deregister a leftover production worker. */
  dev: boolean
  /** Fired once a new worker has installed while an older one controls the page. */
  onUpdate?: (activate: () => void) => void
  /** Injectable container; the browser default is used otherwise. */
  serviceWorker?: ServiceWorkerLike
  /** Injectable reload, so the activate step is observable in tests. */
  reload?: () => void
}

function defaultReload(): void {
  if (typeof location !== 'undefined') location.reload()
}

export function registerServiceWorker({
  dev,
  onUpdate,
  serviceWorker,
  reload = defaultReload,
}: RegisterOptions): void {
  const sw =
    serviceWorker ?? (typeof navigator !== 'undefined' ? navigator.serviceWorker : undefined)
  if (!sw) return

  if (dev) {
    // A production worker left on the same origin (for example from an earlier
    // `vite preview`) serves the old bundle and buffers SSE. Drop it in dev.
    void sw.getRegistrations().then((regs) => regs.forEach((r) => void r.unregister()))
    return
  }

  const start = () => {
    void sw
      .register('/service-worker.js')
      .then((reg) => {
        // The new worker stays waiting until the banner's action posts
        // SKIP_WAITING, so a running chat turn is never taken over mid-stream.
        const offerUpdate = (waiting: ServiceWorker) => {
          onUpdate?.(() => {
            waiting.postMessage({ type: 'SKIP_WAITING' })
            reload()
          })
        }
        reg.addEventListener('updatefound', () => {
          const installing = reg.installing
          if (!installing) return
          installing.addEventListener('statechange', () => {
            if (installing.state === 'installed' && sw.controller) offerUpdate(installing)
          })
        })
        // An update from an earlier session may already be waiting.
        if (reg.waiting && sw.controller) offerUpdate(reg.waiting)
      })
      .catch((err: unknown) => console.error('Service worker registration failed:', err))
  }

  // An injected container means the caller (a test) wants the flow now.
  if (serviceWorker) start()
  else if (typeof document === 'undefined' || document.readyState === 'complete') start()
  else window.addEventListener('load', start, { once: true })
}

/** Chrome/Edge `beforeinstallprompt`. Not in lib.dom, so declared here. */
export interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>
}

export interface InstallPrompt {
  /** Shows the browser's install dialog; resolves with the user's choice. */
  prompt(): Promise<'accepted' | 'dismissed'>
}

export interface InstallOptions {
  /** Fired when the browser reports the app is installable. */
  onAvailable?: (install: InstallPrompt) => void
  /** Fired when the app is added to the home screen or installed. */
  onInstalled?: () => void
  /** Defaults to `window`; tests pass their own target. */
  target?: EventTarget
}

/** Returns a teardown that removes both listeners. */
export function setupInstallPrompt(options: InstallOptions = {}): () => void {
  const target = options.target ?? (typeof window !== 'undefined' ? window : undefined)
  if (!target) return () => {}

  let deferred: BeforeInstallPromptEvent | null = null

  const onBeforeInstall = (event: Event) => {
    // Suppress the browser mini-infobar: the app offers its own affordance.
    event.preventDefault()
    const promptEvent = event as BeforeInstallPromptEvent
    deferred = promptEvent
    options.onAvailable?.({
      prompt: async () => {
        if (!deferred) return 'dismissed'
        const current = deferred
        // One prompt per event: a second call has nothing left to show.
        deferred = null
        await current.prompt()
        const { outcome } = await current.userChoice
        return outcome
      },
    })
  }

  const onInstalled = () => {
    deferred = null
    options.onInstalled?.()
  }

  target.addEventListener('beforeinstallprompt', onBeforeInstall)
  target.addEventListener('appinstalled', onInstalled)

  return () => {
    target.removeEventListener('beforeinstallprompt', onBeforeInstall)
    target.removeEventListener('appinstalled', onInstalled)
  }
}

export interface PwaEnv {
  /** `import.meta.env.DEV`: true in the Vite dev server, false in a build. */
  dev: boolean
}

/** Mounts the PWA surfaces: update banner via the SW, install banner via the prompt. */
export function initPwa(env: PwaEnv): void {
  registerServiceWorker({
    dev: env.dev,
    onUpdate: (activate) => {
      toastBus.info(i18n.t('sw.updateAvailable'), i18n.t('sw.updateHint'), {
        label: i18n.t('sw.reload'),
        onClick: activate,
      })
    },
  })
  setupInstallPrompt({
    onAvailable: (install) => {
      toastBus.info(i18n.t('sw.installAvailable'), i18n.t('sw.installHint'), {
        label: i18n.t('sw.install'),
        onClick: () => void install.prompt(),
      })
    },
    onInstalled: () => toastBus.success(i18n.t('sw.installed')),
  })
}
