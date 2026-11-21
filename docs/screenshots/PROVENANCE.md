# Screenshot provenance

The three captures are the README's product surface. Every pixel of them is painted by the built
PWA (`app/dist`, built with Node v22.23.5 and pnpm 11.11.0) served by the product server on
`127.0.0.1:8784`, captured with Playwright's Chromium on 2026-11-20. The build is the tree this
repository ships: `/api/health` answered `git_sha` from the very build the camera ran against, and
these captures add nothing to that tree but the four files they are. Nothing was composited, retouched or rendered from mock HTML: one
screenshot call per file, the only edit a rectangular crop, named below where it was used. Three
consecutive runs of the harness produced byte-identical files; the published bytes are one of them.

The engine was a local stub on `127.0.0.1:11434` that answers `/api/tags`, `/api/chat`,
`/api/generate`, `/api/version` and the `/v1` compatibility routes: the streamed answer is this
repository's own mock Ollama fixture (`tests/conftest.py::mock_ollama_chunks`), and the two
models it advertises are real, pullable tags of the public Ollama library — a 12B-class and a
3B-class tag at the 8.2 GB and 2.0 GB sizes the registry reports on `ollama.com`, with the model
layers and architectures their GGUF headers name. No quantisation is claimed,
because the stub cannot verify one, and no turn was asked of it: its audit log holds 99 requests
across the runs that produced these frames — 73 `GET /v1/models`, 26 `GET /api/tags` and no
`POST /api/chat` at all — every one of them `auth=none`, with never an `Authorization` value, a
`Bearer` string or an `sk-` prefix in it.
The server was started with a temporary `HOME` and `EPHE_CONFIG_DIR`, with `EPHE_LANGUAGE=en`,
and with the persisted `engine.json` naming `openai_compatible` at `http://127.0.0.1:11434/v1`.
Loopback needs no credential (`core/model_provider.py::_endpoint_requires_api_key`), none was put
in the environment, and none reached the stub. No paid model was called and the real user
configuration directory was never opened.

One instrument is shared by the three frames, and it is the one the visual specs use:
`app/tests/playwright/visual.spec.ts` freezes the browser clock, here to
`2026-11-20T13:05:00+01:00`, so the greeting says "Good afternoon" as it did in the previous
captures instead of depending on the hour the camera ran. Each frame got a fresh context at
`deviceScaleFactor: 1`, `reducedMotion: reduce`, `locale: en-US`, `timezoneId: Europe/Berlin`
and `serviceWorkers: block`. The only interactions are real clicks on the product's own
controls — the first-run skip (`intro-skip`), the embedding-model decline
(`embedding-model-dismiss`) and the task-list expand (`header-sidebar-toggle`) — and the toasts
are waited out until `[data-testid="toaster-rail"]` detaches, never hidden with CSS.

## `readme-chat-1280.png`

- **File**: `docs/screenshots/readme-chat-1280.png` — 1280x730 PNG, 85950 bytes,
  sha256 `4cc7e7a2314a55386b0945e50fe877a4328db0414068d913cf3187de75e21bed`.
- **Surface**: `README.md` hero — the first product image a stranger meets.
- **Decision it is evidence for**: the landing page shows the real Ephe workspace: the task list
  on the left (fresh and empty, "No tasks yet"), the agent's empty chat with the greeting, the
  three starting suggestions, the workspace switcher, and the composer whose model chip names
  the active model, `gemma3:12b`. The header carries the mode control, reading "Operator", and
  the engine state, reading "Engine reachable".
- **The crop**: rendered at 1280x793 and clipped to 1280x730, which is the only crop in these
  three files. Two measured bounds make it a crop above the Settings & Profile control rather
  than a cut through it: `[data-testid="sidebar-settings-btn"]` top = 732, below the crop line,
  and the composer card `.composer-dock` bottom = 728, above it. The crop line therefore runs
  through the gap between the two: the composer is inside the frame whole, and neither the
  control nor the version number it carries is in the image.
- **Re-shoot when**: the workspace chrome, the header mode control or the mark changes.

## `readme-chat-390.png`

- **File**: `docs/screenshots/readme-chat-390.png` — 390x844 PNG, 60614 bytes,
  sha256 `56633a96eafa41f02f1b381d99a7d7845c0d7a7f7154a62a97ba177ff875e4cf`.
- **Surface**: `README.md`, "Work in a phone-sized window".
- **Decision it is evidence for**: the same workspace at the phone-width floor the app supports.
  No crop: the frame is the viewport. `scrollingElement.scrollWidth` = 390 against
  `clientWidth` = 390, so nothing overflows horizontally. The composer card sits at y 629-751
  and the mobile tab bar at 799-844, both inside 844. At this width the header engine pill is
  `hidden lg:inline-flex` by the product's own layout, so the engine state in the frame is the
  composer's model chip — where the product's own squeeze (`truncate max-lg:max-w-28` inside a
  flex row) renders the active tag `gemma3:12b` as `gem…`, the span measuring 46 px against a
  79 px demand — and the status strip, which reads "Connected" and "100% free".
- **Re-shoot when**: the phone chrome, the composer row or the status strip changes.

## `readme-settings-1280.png`

- **File**: `docs/screenshots/readme-settings-1280.png` — 1280x420 PNG, 56953 bytes,
  sha256 `d4b74dcf1546d3127488bdcf73acb489925eec912ed1e79d2b1ee7ee6f184a8a`.
- **Surface**: `README.md`, "Choose the engine that fits your machine".
- **Decision it is evidence for**: the real Engine settings page. `[data-testid="settings-active-engine"]`
  spans y 131-220 and names the active engine, "OpenAI-compatible engine", reachable at
  `http://127.0.0.1:11434/v1`; `[data-testid="engine-group-model"]` spans 236-383 and is the
  model picker listing the two models the engine reported — `gemma3:12b` marked "in use" and,
  below it, `llama3.2:3b`, whose row the 420 line cuts. No crop: the frame is the viewport, and
  the page is top-anchored, so the same rows appear at any taller render.
- **The crop line**: the endpoint input `#settings-endpoint` begins at y 438 and the API-key
  field `#settings-api-key` at 508, both below the 420 line, so the image carries no
  credential-shaped value. The endpoint appears once, as the loopback address in the active-engine
  card, which is what the README sentence above the image promises.
- **Whose numbers these are**: the model tags, byte sizes and digests are the stub's, and they are
  the Ollama registry's own values for those two tags — so a reader can pull both. What the row
  adds is the product's: `≈ 8.1 GB` and `fits · 51%` are computed in `app/src/lib/modelMatrix.ts`
  from the identifier's parameter count and quantisation suffix, divided by the memory total
  `/api/system/metrics` reported for the machine the camera ran on (16 GB). It is the same estimate
  a user sees for their own models, not a figure typed into the stub.
- **Re-shoot when**: the Engine page, its section order or the model row's metadata changes.
