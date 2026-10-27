# Native desktop plan (N0–N10)

Date: 2026-10-26. Order: S25 §3 and §6. Scope: the AppKit islands a WebView
cannot provide. The React surface stays the interior; these islands sit at the
edges and return JSON or a file path (S25 §3.1).

## N0 — the contract

| Layer | Owns | Must never do |
|---|---|---|
| Shell/Rust (`app/src-tauri`) | window, menu, tray, window effects, updater, native permissions, capability gates | render product UI, hold engine logic |
| React (`app/src`) | UI, tokens, sheets, composer, tool cards, panels | call AppKit directly, read arbitrary paths |
| Sidecar/plugin | Quick Look, pasteboard, Vision OCR, Share, Dock, Finder | import product Python, spawn a shell, decide policy |

**No AppKit in Python.** `core/` and `server/` import no `pyobjc`, no `AppKit`;
today neither appears in `pyproject.toml` (checked). A native capability arrives
as a Tauri command or a signed sidecar and returns JSON or a path; the N0 code
slice adds a boundary test that greps the two packages for those imports.

**Capability model.** One capability file today, `app/src-tauri/capabilities/default.json`,
scoped to window `main`, with `core:default`, `updater:default`,
`process:allow-restart`, `notification:default`, `dialog:default`,
`window-state:default` and the two global-shortcut permissions. Every new
command gets its own permission and an entry there; a command without a
capability does not ship. No arbitrary path or process access from the WebView:
paths pass `core/path_guard` and the workspace root, and a native API receives
only URLs the app itself wrote.

**Signing and TCC.** Bundle id stays `com.ephe.ephe` (read from the installed
`Info.plist`). The installed app is ad-hoc today: `codesign -dv` answers
`Identifier=app-145d7b5368b17e38`, `Signature=adhoc`, `TeamIdentifier=not set`,
which is why a rebuild can lose TCC grants. N1 replaces this with a stable
identity; entitlements and `Info.plist` purpose strings become files in the
tree, not settings on one machine. `tccutil reset` is a documented diagnostic
step, never the product's repair path.

**Icon and design.** React uses Lucide; native islands use `NSImage` and
`NSStatusItem` template images; SF Symbols appear only inside a native island.
The app icon comes from the 1024-pixel source through `tauri icon`. No generated
product image enters the tree (AGENTS.md).

## Inventory, measured 2026-10-26

| Capability | State | Evidence |
|---|---|---|
| Tray | present | `tauri` feature `tray-icon`, tray menu in `lib.rs` |
| Window depth blur | present | `set_effects(UnderWindowBackground)` in `lib.rs`; `transparent: true` in `tauri.conf.json` |
| Updater | present | `tauri-plugin-updater`, `latest.json` feed 0.1.8 |
| Dialog | present | `tauri-plugin-dialog`, attachment picker |
| Notification | present | `tauri-plugin-notification` |
| Global shortcut | present | `tauri-plugin-global-shortcut` |
| Full menu bar | present | `build_menu_bar` in `lib.rs` — Ephe, File, Edit, View, Window, Help; the bar and its accelerators were read off the built bundle on 2026-10-27 |
| Typed pasteboard | missing | no `NSPasteboard` call in the tree |
| Finder integration | missing | no `NSWorkspace` icon or reveal |
| Quick Look | missing | no `QLPreviewPanel` |
| Share | missing | no `NSSharingServicePicker` |
| Vision OCR | missing | no `VNRecognizeTextRequest` |
| Dock badge and progress | missing | no `dock` call |
| TCC diagnostics | missing | no purpose strings, no entitlements file |

## The slices

| Slice | Content | Version | Gate |
|---|---|---|---|
| N1 | stable signing identity, entitlements and purpose strings as files, TCC diagnostic path | 0.1.9 | rebuild twice, TCC grant survives, `codesign -dv` names one identity |
| N2 | full menu bar: App/File/Edit/View/Window/Help with standard shortcuts and Check for Updates | 0.1.11 | every menu item fires, ⌘W/⌘,/Esc/⏎ behave |
| N3 | typed clipboard through a capability-gated command; copy image, file, RTF; paste from Finder; web fallback | 0.2.0-alpha.2 | paste an image from Finder into the composer |
| N4 | Finder: `NSWorkspace` icon, reveal, open with default, drag an artifact to Finder | 0.2.0-alpha.2 | reveal and icon in a screenshot; drag produces a file |
| N5 | Quick Look for artifacts, spacebar and ⌘Y, web fallback | 0.2.0-beta.2 | spacebar opens the panel on a PDF and a PNG |
| N6 | Share through `NSSharingServicePicker` | 0.2.0-beta.2 | one share target receives a file |
| N7 | Vision OCR sidecar, `read_text_from_image` and `describe_image` split | 0.2.0-beta.1 | OCR text without a vision model; `describe_image` names a missing capability |
| N8 | Dock badge and progress, notification actions, tray states | 0.2.0-beta.2 | badge follows a run, a notification action returns to the run |
| N9 | VoiceOver labels, menu focus, reduced transparency, system accent and contrast | 0.2.1 | axe plus a VoiceOver pass on the native surfaces |
| N10 | Spotlight, Apple Events, Windows/Linux equivalents, haptics | 0.3.x | per slice |

## Sidecar contract (N5–N7)

One executable per concern, signed with the app, under `Contents/Resources`,
versioned in its filename. The shell starts it with `Command::new` and no shell,
writes one JSON object per line on stdin and reads one per line on stdout.
Every request carries `id`, `op`, `args`; every answer carries `id`, `ok`,
`result` or `error{code,detail}`. A request with an absolute path outside the
workspace root is refused with `path_outside_workspace`. Timeouts are per op
(OCR 10 s, Quick Look open 5 s) and a timeout kills the child. Exit codes: 0 on
clean shutdown, 64 on a refused request, 70 on an internal error. The sidecar
holds no policy: it executes one op and returns data.

Vision OCR is a Swift sidecar: `VNRecognizeTextRequest` is Swift-first, the
process boundary isolates a crash, and the JSON contract above already fits. The
small in-process calls (pasteboard, Finder icons) stay in Rust through `objc2`,
where an extra process would cost more than it isolates.

## Risks

1. **Two products.** Every island must keep a web fallback; an island that
   becomes the only path breaks the PWA surface.
2. **TCC churn.** Ad-hoc signing makes every rebuild a new identity; N1 must
   land before any island that needs a grant.
3. **Policy creep into the sidecar.** A sidecar that decides which path is
   allowed duplicates `core/path_guard`; the shell decides, the sidecar executes.

## Red team

1. **"This is a Swift rewrite by another name."** The line is capability, not
   language: five islands with a JSON contract and a fallback each, while React
   keeps every pixel of product UI.
2. **"Ad-hoc signing is fine for source builds."** It is fine for a developer's
   own machine and wrong for anyone who grants a permission once; N1 is the
   cheapest fix that stops the grant from disappearing.
3. **"Quick Look and Share are polish."** They are the difference between an app
   that has files and an app that can hand a file to another program; N5 and N6
   are scheduled after the update contract, in the beta.
