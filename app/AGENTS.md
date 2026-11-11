# App (PWA)

The React PWA: its layout, its build and the two locale bundles.

Applies on top of the root AGENTS.md.

## Stack

React 19, Vite 6 and TypeScript in strict mode, Tailwind CSS v4, React Router (HashRouter),
`date-fns`, `lucide-react`. The Tauri shell that wraps this build has its own
[`src-tauri/AGENTS.md`](src-tauri/AGENTS.md).

## Commands

```bash
pnpm exec vitest run    # unit suite
pnpm run build          # tsc -b, vite build, then the service-worker stamp
pnpm run lint           # eslint
pnpm run dev            # Vite dev server on :5173, compiles from src/ live
```

`pnpm` is the package manager, pinned by `packageManager` in `package.json`; `pnpm-lock.yaml` is the
only lockfile. The desktop docs spell the same scripts as `npm run …`; either runner reads the
committed `package.json`.

## Layout

- `src/components/` groups by feature (`dashboard/`, `shell/`, `discover/`, `ui/`); `ui/` holds the
  shared primitives (Button, Card, Input).
- `src/pages/` holds the routed screens; routes are registered in `App.tsx`.
- `src/lib/` holds the API client (`lib/api/http.ts`), utilities and the feature modules.
- `src/hooks/` and `src/store/` hold the state layer; `src/styles/globals.css` holds the
  design tokens.

Function components and hooks only; no class components, no CSS-in-JS. Tailwind utility classes and
the tokens in `globals.css` carry the styling. `@/` resolves to `src/`.

## Text

Every user-facing string goes through i18next and lives in both `src/locales/en.json` and
`src/locales/de.json`. A key in one bundle and not the other is caught by
`src/locales/completeness.test.ts`; an English leaf pasted into the German bundle is caught by
`src/locales/germanSurface.test.ts`, which requires every leaf identical to its English neighbour to
be listed as same-by-design.

## Shipping the bundle

`index.html` lives in `app/`, not in `src/`. The production build writes `dist/`, which the
product server on `:8765` serves: an edit under `src/` stays invisible until `pnpm run build` runs,
and the page needs a hard reload (Cmd+Shift+R). The dev server compiles from `src/` directly.

The build also stamps the service worker (`scripts/stamp-sw-version.mjs`) and is measured by
[`scripts/bundle_budget.py`](scripts/bundle_budget.py), which holds each first-paint chunk to its
gzip ceiling. A chunk that outgrows the small ceiling earns a row in that file, measured again; the
ceiling is not raised to clear a red.

## Tests

Vitest specs sit beside the module they cover (`*.test.ts`, `*.test.tsx`). Browser specs live in
`tests/playwright/` and run through `pnpm exec playwright test -c tests/playwright/playwright.config.ts`.
A spec that needs the server uses the fixture in `tests/playwright/`, never a real engine turn.
