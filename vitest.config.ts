// P0-4: CI/root parity for `vitest run` from the repository root. This config
// mirrors the test semantics of ./app/vite.config.ts (jsdom + setup + alias +
// include) so the root run == the app run == 555. `root` points at 'app' so
// dependency resolution (jsdom, testing-library) hits app/node_modules and the
// relative include paths resolve against 'app'. Plain default export (no
// 'vitest/config' import — unresolvable through the npx cache path; defineConfig
// is only an identity helper anyway). Vite injects __dirname (as in the app
// config) so the paths stay stable relative to the repo root.
import { resolve } from 'path'
import pkg from './app/package.json'

const APP = resolve(__dirname, './app')
export default {
  // One version source, as in the app config: package.json (the UI reads __APP_VERSION__).
  define: { __APP_VERSION__: JSON.stringify(pkg.version) },
  resolve: {
    alias: { '@': resolve(APP, 'src') },
  },
  esbuild: { jsx: 'automatic', jsxImportSource: 'react' },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: [resolve(APP, 'src/test/setup.ts')],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    root: APP,
  },
}
