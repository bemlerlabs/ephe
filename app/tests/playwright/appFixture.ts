import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http'
import { readFile } from 'node:fs/promises'
import { dirname, extname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * The app fixture the timing lanes share: the current `app/dist` served from an
 * OS-assigned free port, with the engine leg injected as a known constant.
 *
 * One port per lane, never :8765 (the product server, owned by another lane tonight) and
 * never the static dist server on :9199 that `playwright.config.ts` reuses — a figure or a
 * frame taken from a server this lane did not start describes somebody else's bundle.
 *
 * The engine leg is why the split is a statement: the upstream wait is a value this file
 * sets and measures on its own clock, so whatever else the wait contains belongs to the
 * surface. No claim about a real engine's rate comes out of here; the live TTFT budget
 * stays in `docs/LATENCY_BUDGETS.md` and `tests/test_r25_latency_budgets.py`.
 */

const HERE = dirname(fileURLToPath(import.meta.url))
export const DIST_ROOT = resolve(HERE, '../../dist')

const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.webp': 'image/webp',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ico': 'image/x-icon',
  '.map': 'application/json',
  '.webmanifest': 'application/manifest+json',
}

export type FixtureKind = 'chat' | 'first-run'

export type FixtureRequest = { method: string; path: string; atMs: number }

export type AppFixture = {
  server: Server
  origin: string
  port: number
  pid: number
  kind: FixtureKind
  close(): Promise<void>
}

type Route = (req: IncomingMessage, res: ServerResponse) => boolean

export type FixtureOptions = {
  kind: FixtureKind
  /** The upstream leg this fixture injects, in ms. */
  engineMs: number
  /** Collects the gap from first write to first content chunk, on the server clock. */
  gaps?: number[]
  marks?: string[]
  /** Every request the bundle made, in arrival order — how a flow names its own routes. */
  requests?: FixtureRequest[]
  /** Answered before the generic `/api/` stub; return false to fall through. */
  routes?: Route[]
  /**
   * Answered before this file's own `/api/setup/status`, `/api/health` and `/api/chat/stream`,
   * so a lane can paint an engine that is there but refusing: an unreachable engine is a
   * product state (`lib/engineState.ts`) and the built-in health answer would hide it.
   */
  preRoutes?: Route[]
  /**
   * Frames of the streamed answer. A string is a text chunk; an object is emitted as it
   * stands, so a lane can stream a tool card (`{type:'tool_start', ...}`) and walk the tab
   * order over the rows it inserts.
   */
  chunks?: (string | Record<string, unknown>)[]
  /**
   * Gap between chunks. r5 keeps the default 30 ms: its question is the wait for the FIRST
   * token. A lane that prices how long the answer keeps moving needs a stream that actually
   * streams, so it sets this and passes more chunks.
   */
  chunkGapMs?: number
}

function sse(event: unknown): string {
  return `data: ${JSON.stringify(event)}\n\n`
}

export function startAppFixture(options: FixtureOptions): Promise<AppFixture> {
  const {
    kind,
    engineMs,
    gaps = [],
    marks = [],
    requests = [],
    routes = [],
    preRoutes = [],
  } = options
  const chunks = options.chunks ?? ['first ', 'second ', 'third.']
  const chunkGap = options.chunkGapMs ?? 30

  return new Promise((listening, reject) => {
    const server = createServer(async (req, res) => {
      const path = new URL(req.url ?? '/', 'http://127.0.0.1').pathname
      requests.push({ method: req.method ?? 'GET', path, atMs: Math.round(performance.now()) })

      for (const route of preRoutes) {
        if (route(req, res)) return
      }

      if (path === '/api/setup/status') {
        // App.tsx:33 reads this and only opens the chat when the engine is configured.
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        res.end(
          JSON.stringify({
            configured: kind === 'chat',
            skipped: false,
            provider: 'openai_compatible',
            model: kind === 'chat' ? 'fixture-model' : null,
            url: null,
          }),
        )
        return
      }

      if (path === '/api/health') {
        // The shape the product's own online gate reads, with no hostname and no credential.
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        res.end(
          JSON.stringify({
            status: 'ok',
            version: 'fixture',
            models: ['fixture-model'],
            active_model: 'fixture-model',
            active_provider: 'openai_compatible',
            engine_online: true,
            engine_state: 'ok',
            model_installed: true,
            detail: 'app fixture',
          }),
        )
        return
      }

      if (path === '/api/chat/stream' && req.method === 'POST') {
        req.resume() // the body is not needed; draining keeps the socket honest
        res.writeHead(200, {
          'Content-Type': 'text/event-stream; charset=utf-8',
          'Cache-Control': 'no-cache',
        })
        const base = performance.now()
        // A comment frame first: the app's parser drops it (stream.ts:180) and it gives the
        // probe a first-byte instant separate from the first-token instant.
        res.write(': ready\n\n')
        marks.push(`accept+${(performance.now() - base).toFixed(1)}`)
        const timers = chunks.map((text, index) =>
          setTimeout(
            () => {
              res.write(sse(typeof text === 'string' ? { type: 'chunk', data: text } : text))
              if (index === 0) {
                gaps.push(Number((performance.now() - base).toFixed(1)))
              }
              marks.push(`chunk${index + 1}+${(performance.now() - base).toFixed(1)}`)
              if (index === chunks.length - 1) {
                res.end()
                marks.push(`end+${(performance.now() - base).toFixed(1)}`)
              }
            },
            engineMs + index * chunkGap,
          ),
        )
        req.on('aborted', () => timers.forEach(clearTimeout))
        // Cleanup watches the response: req emits 'close' as soon as the small JSON body is
        // drained, and clearing the timers there leaves the page with the comment frame and
        // no token.
        res.on('close', () => {
          if (!res.writableEnded) {
            timers.forEach(clearTimeout)
            marks.push(`client-gone+${(performance.now() - base).toFixed(1)}`)
          }
        })
        return
      }

      for (const route of routes) {
        if (route(req, res)) return
      }

      if (path.startsWith('/api/')) {
        // Everything else the bundle asks for on boot answers empty rather than 404, so a
        // figure here never describes a missing route.
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
        res.end(req.method === 'GET' ? '{}' : '{"ok":true}')
        return
      }

      const relative = path === '/' ? 'index.html' : path.replace(/^\/+/, '')
      const file = join(DIST_ROOT, relative)
      if (!file.startsWith(`${DIST_ROOT}/`)) {
        res.writeHead(403)
        res.end('outside the bundle')
        return
      }
      try {
        const body = await readFile(file)
        res.writeHead(200, { 'Content-Type': MIME[extname(file)] ?? 'application/octet-stream' })
        res.end(body)
      } catch {
        const index = await readFile(join(DIST_ROOT, 'index.html'))
        res.writeHead(200, { 'Content-Type': MIME['.html'] })
        res.end(index)
      }
    })

    server.on('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      if (address === null || typeof address === 'string') {
        reject(new Error('the fixture did not get a port'))
        return
      }
      listening({
        server,
        port: address.port,
        origin: `http://127.0.0.1:${address.port}`,
        pid: process.pid,
        kind,
        close: () =>
          new Promise<void>((done) => {
            server.closeAllConnections?.()
            server.close(() => done())
          }),
      })
    })
  })
}
