# Screenshot provenance

These three captures are the README's product surface. They come from the built PWA
(`app/dist`, built with Node 22.23.4) on 2026-10-23, served by a local backend with an
isolated temporary `HOME` and a local stub engine on `127.0.0.1:11434`. No paid model
was called and no key was used.

## `readme-chat-1280.png`

- **File**: `docs/screenshots/readme-chat-1280.png` — 1280x730 PNG.
- **Surface**: `README.md` hero — the first product image a stranger meets.
- **Decision it is evidence for**: the landing page shows the real Ephe workspace: the
  task list, the agent's empty chat, the workspace switcher and the composer. The image
  is cropped above the Settings & Profile control so neither that control nor an unreleased version number is shown.
- **Re-shoot when**: the workspace chrome or the mark changes.

## `readme-chat-390.png`

- **File**: `docs/screenshots/readme-chat-390.png` — 390x844 PNG.
- **Surface**: `README.md`, "Work in a phone-sized window".
- **Decision it is evidence for**: the same workspace at the phone-width floor the app
  supports; no horizontal overflow, the composer and the engine state remain visible.

## `readme-settings-1280.png`

- **File**: `docs/screenshots/readme-settings-1280.png` — 1280x420 PNG.
- **Surface**: `README.md`, "Choose the engine that fits your machine".
- **Decision it is evidence for**: the real Engine settings page (active engine, model
  picker), cropped above the API-key field so the image carries no credential-shaped
  value.

## Retired: `hero-banner.png`

The older 2560x1440 banner is no longer referenced by any README. It stays in the
repository as a historical asset and is not part of the public export.
