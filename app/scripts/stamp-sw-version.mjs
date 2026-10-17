/**
 * Stamps the service-worker cache version into dist/service-worker.js
 * from the package.json version (runs as part of `npm run build`).
 *
 * The placeholder __EPHE_SW_VERSION__ in public/service-worker.js
 * is rewritten to ephe-v<major.minor.patch>-sse. Every
 * release thus automatically gets a new cache key — the new SW's activate()
 * drops the old caches. No manual bump.
 *
 * Standalone rather than a Vite plugin, because Vite only copies the public/ files
 * into dist AFTER closeBundle() — a build hook would run too early.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const appRoot = dirname(dirname(fileURLToPath(import.meta.url)))
const PLACEHOLDER = '__EPHE_SW_VERSION__'
const swPath = join(appRoot, 'dist', 'service-worker.js')

if (!existsSync(swPath)) {
  console.warn('[sw-version] dist/service-worker.js fehlt — Stamping übersprungen')
  process.exit(0)
}
const src = readFileSync(swPath, 'utf-8')
if (!src.includes(PLACEHOLDER)) {
  // Already stamped (e.g. a repeated build) — nothing to do.
  process.exit(0)
}
const pkg = JSON.parse(readFileSync(join(appRoot, 'package.json'), 'utf-8'))
// Build stamp as a cache-key extension: every build gets a new
// key so that activate() (SW-Z.48ff) drops the old caches — otherwise a plain
// Cmd+R after a rebuild still serves the old bundle (cache-first SW).
const stamp = Math.floor(Date.now() / 1000)
writeFileSync(
  swPath,
  src.replaceAll(PLACEHOLDER, `ephe-v${pkg.version}-sse-${stamp}`),
)
console.log(`[sw-version] dist/service-worker.js → ephe-v${pkg.version}-sse-${stamp}`)
