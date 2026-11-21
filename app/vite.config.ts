import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { execFileSync } from 'node:child_process'
import { resolve } from 'path'
import pkg from './package.json'

/**
 * The commit this bundle was built from. The backend answers with its own
 * (`/api/health.git_sha`, twelve characters as well), so a window whose `dist`
 * is older than the tree serving it can say so instead of pretending the new
 * behaviour is simply absent. A source tarball has no `.git`: `unknown` keeps
 * the comparison silent rather than inventing a mismatch.
 */
function buildSha(): string {
  try {
    return execFileSync('git', ['rev-parse', '--short=12', 'HEAD'], {
      cwd: __dirname,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim()
  } catch {
    return 'unknown'
  }
}

// The Radix overlay stack: the `@radix-ui/*` packages plus the dependency tail they
// drag in (`@floating-ui/*`, `react-remove-scroll*`, `react-style-singleton`,
// `use-sidecar`, `use-callback-ref`, `get-nonce`, `aria-hidden`) — 45 vendor modules
// that used to sit in the entry chunk next to the app shell.
// One target for the dev proxy. The backend now rejects a foreign Origin on
// mutations and WebSocket handshakes; the proxy rewrites both to the app's own
// origin so the Vite page keeps working without a second allowlist entry.
const API_TARGET = process.env.EPHE_API_TARGET || 'http://127.0.0.1:8765'

// The UI primitives the first paint itself renders. The rest of
// `src/components/ui` is opened by a lazy route; the old rule named the whole
// directory, so every primitive a route imported became a static dependency of
// the shell (the dialog primitive alone held the 35.8 kB Radix overlay stack on
// the first load).
const SHELL_UI = [
  '/src/components/ui/ErrorBoundary',
  '/src/components/ui/Skeleton',
  '/src/components/ui/Toaster',
  '/src/components/ui/iconScale',
] as const

const RADIX_VENDOR = [
  '@radix-ui/',
  '@floating-ui/',
  'react-remove-scroll',
  'react-style-singleton',
  'use-sidecar/',
  'use-callback-ref',
  'get-nonce',
  'aria-hidden',
] as const

// The service-worker cache version is stamped by scripts/stamp-sw-version.mjs
// after the build (the package.json build script): Vite copies public/ into
// dist/ after closeBundle(), so a build hook would run too early.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // One version source: package.json (the UI reads __APP_VERSION__).
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
    __EPHE_BUILD_SHA__: JSON.stringify(buildSha()),
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    // The picker's wall-clock ceiling runs in `vitest.perf.config.ts`, one worker and a
    // median. Collecting it here put a host measurement back into the parallel suite.
    exclude: ['**/*.perf.test.{ts,tsx}'],
    // Pin the fork-worker startup under parallel load: removes the transient
    // 'Failed to start forks worker' failure in the CI.
    pool: 'forks',
    // Vitest 4 moved worker settings to the top level and IGNORES `poolOptions` (it
    // prints a DEPRECATED warning for it), so the four-worker ceiling that keeps
    // 'Failed to start forks worker' away from CI lives here now. Written as
    // `poolOptions.forks.maxWorkers` it was a no-op that looked like a fix.
    maxWorkers: 4,
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    host: true,
    // Dev proxy: API + media from the Vite port (same-origin) to the backend (8765).
    // That lets the PWA run in dev without a hard-coded API URL (as in prod,
    // where the server serves the PWA itself). VITE_API_URL
    // still overrides it for external setups.
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        headers: { Origin: API_TARGET },
        ws: true, // P1-5: /api/shell/term WebSocket (PTY) + /api/proxy HMR tunnel
      },
      '/audio': API_TARGET,
      '/images': API_TARGET,
    },
  },
  build: {
    // WD-33: `src/i18n.ts` awaits its own catalog before the app renders (the readiness
    // gate that replaced the two static locale imports), so the bundles are built for a
    // target that has top-level await: Chrome/Edge 89+, Firefox 89+, Safari 15+.
    target: 'es2022',
    outDir: 'dist',
    sourcemap: true,
    chunkSizeWarningLimit: 500,
    rollupOptions: {
      // The `@/components/ui` barrel is imported through its index, so Vite
      // keeps every module it re-exports unless told otherwise — the app has no
      // `sideEffects` field, and Rollup then assumes each primitive may run
      // something at import time. They are pure component modules; marking them
      // side-effect-free lets the barrel keep its shape while only the
      // primitives a surface imports reach that surface's chunk.
      treeshake: {
        moduleSideEffects: (id: string) => !id.includes('/src/components/ui/'),
      },
      output: {
        manualChunks(id: string) {
          // Route bundles are already split via React.lazy; split heavy vendors.
          if (id.includes('node_modules')) {
            // The highlighter's own chunking is left to Rollup. Grouping its
            // modules here made one chunk statically import every grammar, which
            // put the whole set back on the first paint (measured in Chromium:
            // 59 JS requests against 25).
            // `hast-util-to-html` is the exception: it is the highlighter's HTML
            // writer, nothing on the markdown path asks for it, and the `hast`
            // clause below charged the chat route 8.4 kB gzip for it.
            if (id.includes('hast-util-to-html')) {
              return 'highlighter'
            }
            // Markdown ecosystem: self-contained so the lazy markdown route
            // doesn't pull unrelated vendor code into the initial load.
            if (
              id.includes('react-markdown') ||
              id.includes('remark-gfm') ||
              id.includes('marked') ||
              id.includes('dompurify') ||
              id.includes('unified') ||
              id.includes('micromark') ||
              id.includes('remark') ||
              id.includes('rehype') ||
              id.includes('mdast') ||
              id.includes('hast') ||
              id.includes('vfile') ||
              id.includes('decode-named') ||
              id.includes('highlight') ||
              id.includes('lowlight')
            ) {
              return 'markdown'
            }
            // framer-motion + its runtime on their own. App.tsx imports
            // `MotionConfig`, the reduced-motion provider, and nothing else
            // from the library, so this chunk is on the first
            // paint for a 1.4 kB module. Measured: splitting the provider (and
            // its static closure: motion-dom's `isMotionValue` + frameloop +
            // value system, ~17 kB) into a chunk of its own was tried and does
            // not converge — each split just exposes the next binding the shell
            // borrows from the feature chunk, and the hand-written module list
            // that would be needed rots with every framer-motion upgrade. The
            // honest lever on these bytes is the feature set, not the chunk
            // boundary: see the `m` + `LazyMotion features={domAnimation}`
            // conversion in App.tsx and the animated surfaces.
            if (
              id.includes('framer-motion') ||
              id.includes('motion-dom') ||
              id.includes('motion-utils')
            ) {
              return 'motion'
            }
            if (
              id.includes('lucide-react') ||
              id.includes('react-i18next') ||
              id.includes('i18next')
            ) {
              return 'ui-vendor'
            }
            // Radix + its tail on their own: the overlay stack is one dependency
            // island, and it left the entry chunk with the app shell.
            if (RADIX_VENDOR.some((vendor) => id.includes(vendor))) {
              return 'radix'
            }
            // date-fns in two chunks. The `dates` chunk (locales, relative time)
            // is what the app shell reads through `src/lib/dateLocale.ts`; the
            // `dates-format` chunk is the sidebar's `format()` and the formatter
            // tables it drags in (`_lib/format/*`). They were one chunk until now,
            // which is why the entry carried `format.js` + `formatters.js` —
            // 45.9 kB of formatting tables only the dated session list reads.
            // `formatDistance*` does not touch `_lib/format/` (checked against the
            // package: only `format`, `lightFormat`, `parse` and `cdn` import it),
            // so the split moves the tables to the surface that uses them and
            // leaves the first paint with what it renders.
            if (id.includes('date-fns')) {
              if (
                /date-fns\/(format|lightFormat|parse)\.js$/.test(id) ||
                id.includes('date-fns/_lib/format/')
              ) {
                return 'dates-format'
              }
              return 'dates'
            }
            // React 19 runtime (react/react-dom/scheduler) re-exports shared internals
            // across packages — it MUST stay together in the main chunk. Splitting it
            // into its own chunk creates a circular chunk (react-core <-> vendor).
            // Split only the genuinely independent UI/state libs instead.
            if (
              id.includes('react-router') ||
              id.includes('@tanstack') ||
              id.includes('zustand') ||
              id.includes('idb-keyval') ||
              id.includes('clsx') ||
              id.includes('class-variance-authority')
            ) {
              return 'app-vendor'
            }
          }
          // The shell's own primitive layer, and only that: a module another
          // route needs is split with that route.
          if (SHELL_UI.some((module) => id.includes(module))) {
            return 'ui'
          }
        },
      },
    },
  },
})
