/// <reference types="vite/client" />

/** Build constant from vite.config.ts (source: package.json). */
declare const __APP_VERSION__: string
/** Commit the bundle was built from (vite.config.ts); `unknown` outside a checkout. */
declare const __EPHE_BUILD_SHA__: string

interface ImportMetaEnv {
  readonly VITE_API_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

// ── Service Worker Types ──────────────────────────────────────────────────

interface ServiceWorkerGlobalScope extends Omit<
  ServiceWorkerGlobalScope,
  'skipWaiting' | 'clients'
> {
  skipWaiting(): void
  clients: Clients
}

interface ExtendableEvent extends Event {
  waitUntil(fn: Promise<void>): void
}

interface FetchEvent extends Event {
  request: Request
  respondWith(resp: Response | PromiseLike<Response>): void
}

interface SyncEvent extends Event {
  tag: string
  lastChance: boolean
  waitUntil(fn: Promise<void>): void
}

/**
 * The desktop shell's IPC bridge, absent in a browser — which is why every call
 * site guards on it. `useTauriWindow` and `ChatInput` read it straight off
 * `window`; the rest of the bridge is cast at the point of use.
 */
interface Window {
  __TAURI__?: {
    core: { invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown> }
  }
}
