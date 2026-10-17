
// Service Worker for Ephe PWA
//
// Strategy (SSE release, D4):
// - /api/* + non-GET  → NETWORK-ONLY: never served from cache, never cached.
//   Chat streaming (POST /api/chat/stream, SSE) and sandbox approval
//   must never be blocked by a tab that has been left standing.
// - text/event-stream → NETWORK-ONLY (detected from the SSE response header):
//   a cached event-stream aborts immediately once it is served from the cache.
// - Navigation (index.html, /) → NETWORK-FIRST, the cache only as an
//   offline fallback. A cache-first index.html + an old tab =
//   the old bundle forever (the root cause of the WS-client finding).
// - Static assets (hashed chunks, icons, manifest) → cache-first,
//   because their hashes guarantee the freshness.
// The cache key is stamped from package.json at build time
// (the Vite plugin `ephe-sw-version`): the placeholder
// __EPHE_SW_VERSION__ is rewritten to ephe-v<major.minor.patch>-sse.
// Every release thus activates a fresh SW and
// activate() discards the old caches.
const CACHE_NAME = '__EPHE_SW_VERSION__'
const ASSETS_TO_CACHE = [
  '/',
  '/index.html',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png',
  '/icon-maskable-192.png',
  '/icon-maskable-512.png',
]

const sw = self

// Install event — cache assets.
// NO skipWaiting() here: updates stay user-controlled.
// The app shows an update toast ("new version available — reload") and
// only sends the message signal 'SKIP_WAITING' when it is clicked (see below).
// That way a running chat turn is never taken over mid-stream by
// a new SW.
sw.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS_TO_CACHE))
  )
})

// Activate event — clean old caches (discards the pre-SSE bundles that still carry a WSClient)
sw.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) =>
      Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      )
    )
  )
  sw.clients.claim()
})

// Update flow: the app posts { type: 'SKIP_WAITING' } to the waiting SW
// (from the update toast, "reload"). Without that signal the currently
// active SW stays in place; the app reloads after the click.
sw.addEventListener('message', (event) => {
  if (
    event.data &&
    typeof event.data === 'object' &&
    event.data.type === 'SKIP_WAITING'
  ) {
    self.skipWaiting()
  }
})

// Fetch event — network-first with a strict API/SSE separation
sw.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)

  // API + media: always the network, never the cache (streaming + auth + approval)
  if (url.pathname.startsWith('/api/') || request.method !== 'GET') {
    event.respondWith(fetch(request))
    return
  }

  // Navigation + HTML: network-first, the cache only as the offline fallback
  const isNavigation =
    request.mode === 'navigate' || request.destination === 'document'

  if (isNavigation) {
    event.respondWith(
      fetch(request)
        .then((res) => {
          if (res.status === 200) {
            const clone = res.clone()
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone))
          }
          return res
        })
        .catch(() =>
          caches.match(request).then((cached) => cached || caches.match('/'))
        )
    )
    return
  }

  // Static assets: cache-first (hashed chunks are self-validating)
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached
      return fetch(request).then((res) => {
        // never cache an SSE response (the abort root cause)
        const ct = res.headers.get('content-type') || ''
        if (res.status === 200 && !ct.includes('text/event-stream')) {
          const clone = res.clone()
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone))
        }
        return res
      })
    })
  )
})

// Background sync (disabled until proper types are available)
// sw.addEventListener('sync', (event) => {
//   if (event.tag === 'sync-messages') {
//     event.waitUntil(Promise.resolve())
//   }
// })
