import { createRoot } from 'react-dom/client'
import { Suspense, lazy } from 'react'
// Side-effect import: i18n must be initialized before App renders.
import './i18n'
import { installDbAutoFlush } from '@/lib'
import { applyTheme, getStoredTheme } from '@/lib'
import { initDeepSettings } from '@/lib'
import { hasSeenFirstRunIntro, loadSetupGate, readSetupGateHint } from '@/lib'
import { initPwa } from './registerSW'
import App from './App'
import './styles/globals.css'
import './styles/highlight.css'

// The first-run scene is a chunk of its own, fetched by a browser that has not seen it and
// by no other: the entry keeps its budget, and a returning load pays nothing for a scene it
// would not show. The flag it is gated on lives in `lib/firstRun`; the read sits here rather
// than inside the scene because a component that is not rendered is a component that is
// never fetched. The fetch starts now, beside the gate's round trip, so the scene has its
// code in hand instead of after a round trip of its own.
const FirstRunIntro = lazy(() => import('./components/onboarding/FirstRunIntro'))
const introPending = !hasSeenFirstRunIntro()
if (introPending) void import('./components/onboarding/FirstRunIntro')

// Apply the theme before the first paint — otherwise Dark flashes up before
// html.light has bent the primitive tokens.
applyTheme(getStoredTheme())

// R25 (perceived latency): the setup gate's round trip starts here — with the bundle, before
// React's first commit — instead of inside a mount effect that runs after it. The answer
// then lands while the route chunk is still arriving rather than after it.
void loadSetupGate()

// A load with no remembered gate answer (a new visitor, or the first load after an update)
// is the one load that cannot decide its own route yet: the verdict arrives one round trip
// later, and for a new visitor that verdict is the engine choice. Start that chunk now so it
// is in hand when the answer is; a configured first load pays one extra chunk, once per
// browser, and every later load skips this branch.
if (readSetupGateHint() === null) void import('./pages/SetupPage')

// I3-4: apply the appearance from the deep register (font size, animations) on
// <html>. It comes from /api/settings; without a backend everything stays at the
// default, and the app does not wait for it.
void initDeepSettings()

// Self-hosted fonts (offline-first, no CDN): Inter (UI) and
// Instrument Serif (display) — the font-family fallbacks in globals.css
// stay unchanged, the @font-face definitions now come from local files.
//
// Subsets: a bare weight import pulls EVERY subset the package ships (@font-face
// for latin, latin-ext, cyrillic, cyrillic-ext, greek, greek-ext, vietnamese) —
// 53 @font-face blocks for eleven faces, 37.4 kB of the entry's CSS, and ~700 kB
// of woff2 in dist that this app can never select: SUPPORTED_LANGUAGES is
// ['en','de'], both of which live in the `latin` range (German ä/ö/ü/ß sit in
// U+00E4…, the € in the range fontsource includes in `latin`). `latin-ext` stays
// so that Latin-script content pasted from elsewhere still keeps the UI face;
// the three other scripts do not.
import '@fontsource/inter/latin-400.css'
import '@fontsource/inter/latin-500.css'
import '@fontsource/inter/latin-600.css'
import '@fontsource/inter/latin-700.css'
import '@fontsource/inter/latin-ext-400.css'
import '@fontsource/inter/latin-ext-500.css'
import '@fontsource/inter/latin-ext-600.css'
import '@fontsource/inter/latin-ext-700.css'
import '@fontsource/space-grotesk/latin-500.css'
import '@fontsource/space-grotesk/latin-600.css'
import '@fontsource/space-grotesk/latin-700.css'
import '@fontsource/space-grotesk/latin-ext-500.css'
import '@fontsource/space-grotesk/latin-ext-600.css'
import '@fontsource/space-grotesk/latin-ext-700.css'
import '@fontsource/instrument-serif/latin-400.css'
import '@fontsource/instrument-serif/latin-400-italic.css'
import '@fontsource/instrument-serif/latin-ext-400.css'
import '@fontsource/instrument-serif/latin-ext-400-italic.css'
// R17 F-17: bundle JetBrains Mono offline — .font-mono-code used to fall back to generic monospace
import '@fontsource/jetbrains-mono/latin-400.css'
import '@fontsource/jetbrains-mono/latin-700.css'
import '@fontsource/jetbrains-mono/latin-ext-400.css'
import '@fontsource/jetbrains-mono/latin-ext-700.css'

// PWA: register the service worker (production builds only — in the dev server
// the SW would intercept SSE streaming and module fetches) and mount the install
// and update banners. See src/registerSW.ts.
initPwa({ dev: import.meta.env.DEV })

// I6 P2b: flush pending persist writes (debouncedSaveSession) on tab change
// and page unload — otherwise a reload mid-stream loses the part of the
// answer so far.
installDbAutoFlush()

// Mount the app — i18n must be imported above; wrapped in Suspense for lazy init
const rootElement = document.getElementById('root')
if (!rootElement) {
  throw new Error('Root element not found')
}
const root = createRoot(rootElement)
root.render(
  <Suspense fallback={null}>
    <App />
    {/* The scene sits above the shell as a sibling, so the surface the gate
        resolved — the engine choice or the chat — is already mounted behind it and
        comes into view when the scene ends. Its own Suspense boundary keeps the
        chunk's arrival away from <App />: the app renders on the entry's schedule,
        and the scene takes over the screen when its code lands. */}
    {introPending ? (
      <Suspense fallback={null}>
        <FirstRunIntro />
      </Suspense>
    ) : null}
  </Suspense>,
)
