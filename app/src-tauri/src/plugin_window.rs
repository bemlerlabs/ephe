//! Ephe — the native plugin window (W1-3)
//!
//! A plugin surface gets a window with its own label. Tauri binds capabilities to
//! window **labels**, so the label is the boundary: every `ephe-plugin-<id>` window
//! answers to `capabilities/plugin-window.json`, which hands it no command at all,
//! while `main` keeps the app capability in `default.json`. Ids are manifest slugs
//! over `[a-z0-9-]`, which is what keeps a label free of glob characters.
//! The decisions themselves — label, caller rule, bounds, URL, descriptor mapping —
//! are in `plugin_window_options.rs`, where a test can read them.
//!
//! Two doors, and both read the label of the calling **webview**, never of its
//! window. [`guard_before_dispatch`] wraps the whole `generate_handler!` list in
//! `lib.rs` and refuses the three surface names before a body runs; each command
//! then asks the same question of the same label itself ([`guard`]). The names
//! are the list in `plugin_window_options::SURFACE_COMMANDS`. A test walks the
//! registered list and fails when a name with that prefix is missing from it.
//! Reading the webview rather than the window is what
//! makes either of them mean anything — `browser.rs:70` attaches `ephe-browser` as a
//! child webview of `main`, so a window-label read hands any page that pane shows
//! the workbench's own authority. The allow-list is `main` alone; the pane is
//! refused, and so is every label this file has never heard of.
//!
//! What neither door covers, written here because the alternative is a reader who
//! assumes otherwise:
//!   * **the event channel.** `guard` sees commands. A webview with `core:event`
//!     authority can `listen`, `emit` and `emit-to` app-wide, and no command guard
//!     is on that path — the shell itself broadcasts `global-shortcut` from
//!     `reveal_main_window` and `show` from `show_main_window` (`lib.rs`). The
//!     surface capability grants no core permission at all, so this window has no
//!     event authority to misuse; the capability description says the same, and a
//!     future `remote` grant there reopens this.
//!   * **a command outside the three surface names.** The app manifest lists every
//!     registered command. `capabilities/workbench-commands.json` grants that set
//!     to the webview labelled `main`. A surface window takes
//!     `capabilities/plugin-window.json`, whose permission list is empty, so the
//!     access-control layer refuses the set there. The browser pane is the webview
//!     `ephe-browser` on the main window, and the grant names the webview, so the
//!     pane is outside it. `default.json` still binds its plugin permissions to the
//!     main window, which covers every webview of that window. The door below still
//!     refuses the three names from any caller except `main`.
//!
//! The document a surface window loads is the route #42 serves at
//! `http://127.0.0.1:8765/api/plugins/ui/<id>/<nonce>/`. That page carries
//! `sandbox allow-scripts allow-popups` with no `allow-same-origin`, so its origin
//! is opaque, its nonce comes from an authenticated fetch only the main window can
//! make, and the global bridge is deleted from it before its own script runs. A
//! plugin webview cannot mint a credential and has no reason to call any command
//! here — which is why this window's capability can be empty.
//!
//! Isolation, stated where the claim lives: the sandbox of the **shipped** engine
//! is unmeasured. #42 measured Chromium 151 and WebKit 26.5 in Playwright's own
//! builds. The engine inside the built app is the system WKWebView, and no channel
//! in this tree can read back what it enforces for a window like this one until the
//! bridge task #23 gives a surface a legitimate write path. No line below claims
//! that observation happened.

use std::sync::Mutex;

use tauri::{AppHandle, Emitter, Manager, Url, WebviewUrl, WebviewWindowBuilder};

use crate::plugin_window_options::{
    caller_is_allowed, clamp_dimension, default_ui_size, is_surface_url, plan, refusal_for_bad_url,
    refusal_for_build_failure, refusal_for_close_failure, refusal_for_geometry_failure,
    refusal_for_navigation_failure, refusal_for_surface_call, refusal_for_type,
    refusal_for_unknown_handle, refusal_from_a_surface, surface_type_is_native,
    surface_url_for_plugin, window_label, SurfaceDescriptor, WindowPlan, PLUGIN_LABEL_PREFIX,
    WORKBENCH_LABEL,
};
use crate::runlog;

/// The bridge the app hands every webview globally (`withGlobalTauri`). A plugin
/// document is code nobody here wrote, so it goes: the same loop `browser.rs:75`
/// runs for the browser pane. The bridge task #23 replaces this with a scoped
/// channel in place of the global object.
const STRIP_GLOBAL_BRIDGE: &str = "for (const k of ['__TAURI__','__TAURI_INTERNALS__','__TAURI_METADATA__']) { try { delete window[k] } catch (e) { try { window[k] = undefined } catch (e2) {} } }";

/// What the shell reports back, so the surface can say what it actually got.
#[derive(Debug, Clone, serde::Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct SurfaceInfo {
    pub label: String,
    pub width: u32,
    pub height: u32,
    pub transparent: bool,
    pub decorations: bool,
    pub always_on_top: bool,
    /// False when this call found the window already open and only revealed it.
    pub created: bool,
    pub note: String,
}

/// Geometry of an already-open surface, in logical pixels.
#[derive(Debug, Clone, Copy, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SurfaceBounds {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

/// A caller the shell does not own asked for the surface layer: say so in the run
/// log, and hand the caller the curated rule and nothing else.
fn refuse(caller: &str) -> String {
    runlog::note_here("plugin_window_refused");
    log::warn!("webview {caller} tried to drive the surface layer");
    refusal_from_a_surface().to_string()
}

/// The second door. The calling webview's own label, read in Rust, so a page cannot
/// talk past it by naming another label — and cannot borrow the workbench's label
/// either, because the label is not part of the invoke payload but of the webview
/// that sent it.
fn guard(webview: &tauri::Webview) -> Result<(), String> {
    if caller_is_allowed(webview.label()) {
        return Ok(());
    }
    Err(refuse(webview.label()))
}

/// The first door. It wraps the command handler the app registers, so an invoke
/// of one of the three surface names is refused before its command wrapper runs.
/// The names are [`crate::plugin_window_options::SURFACE_COMMANDS`]. A command
/// that only shares their prefix is outside that list, and this door leaves it
/// to the access-control layer.
///
/// The manifest is on. `build.rs` hands `AppManifest` every registered name, with
/// the three surface names first. The workbench webview is the only label that
/// receives the set. The surface capability receives none of it. What this door
/// still leaves to other layers: the event channel, which never passes through a
/// command handler, and any command whose name is outside the three. Those other
/// commands are the workbench set, granted to the webview `main` and withheld
/// from a surface window by the empty permission list.
pub fn guard_before_dispatch<H, R>(
    registered: H,
) -> impl Fn(tauri::ipc::Invoke<R>) -> bool + Send + Sync + 'static
where
    R: tauri::Runtime,
    H: Fn(tauri::ipc::Invoke<R>) -> bool + Send + Sync + 'static,
{
    move |invoke| {
        let command = invoke.message.command().to_string();
        let caller = invoke.message.webview_ref().label().to_string();
        if refusal_for_surface_call(&command, &caller).is_some() {
            invoke.resolver.reject(refuse(&caller));
            return true;
        }
        registered(invoke)
    }
}

/// Labels the shell opened this run. The window map of the app is the authority on
/// what exists, so a second open finds the real window; this ledger only carries
/// the count into the quit report.
static OPEN_LABELS: Mutex<Vec<String>> = Mutex::new(Vec::new());

fn remember(label: &str) {
    if let Ok(mut open) = OPEN_LABELS.lock() {
        if !open.iter().any(|l| l == label) {
            open.push(label.to_string());
        }
    }
}

fn forget(label: &str) {
    if let Ok(mut open) = OPEN_LABELS.lock() {
        open.retain(|l| l != label);
    }
}

fn info_from(built_plan: &WindowPlan, created: bool) -> SurfaceInfo {
    SurfaceInfo {
        label: built_plan.label.clone(),
        width: built_plan.width,
        height: built_plan.height,
        transparent: built_plan.transparent,
        decorations: built_plan.decorations,
        always_on_top: built_plan.always_on_top,
        created,
        note: built_plan.note.clone(),
    }
}

fn measured(info: &mut SurfaceInfo, size: tauri::PhysicalSize<u32>) {
    info.width = size.width;
    info.height = size.height;
}

fn report(app: &AppHandle, info: &SurfaceInfo) {
    let _ = app.emit_to(WORKBENCH_LABEL, "plugin-window:opened", info.clone());
}

/// Opens the surface window, or reveals and re-points the one that already exists.
#[tauri::command]
pub async fn plugin_window_open(
    app: AppHandle,
    webview: tauri::Webview,
    plugin_id: String,
    url: String,
    descriptor: SurfaceDescriptor,
) -> Result<SurfaceInfo, String> {
    guard(&webview)?;
    if !surface_type_is_native(&descriptor) {
        return Err(refusal_for_type().to_string());
    }
    let label = window_label(&plugin_id)?;
    let parsed: Url = url.parse().map_err(|_| refusal_for_bad_url().to_string())?;
    if !surface_url_for_plugin(&parsed, &plugin_id) {
        return Err(refusal_for_bad_url().to_string());
    }

    let built_plan = plan(label.clone(), &descriptor);

    if let Some(existing) = app.get_webview_window(&label) {
        existing.navigate(parsed).map_err(|error| {
            log::warn!("plugin surface {label} would not re-point: {error}");
            refusal_for_navigation_failure().to_string()
        })?;
        existing
            .set_size(tauri::LogicalSize::new(
                f64::from(built_plan.width),
                f64::from(built_plan.height),
            ))
            .map_err(|error| {
                log::warn!("plugin surface {label} refused its size: {error}");
                refusal_for_geometry_failure().to_string()
            })?;
        let _ = existing.show();
        let _ = existing.unminimize();
        let _ = existing.set_focus();
        let mut info = info_from(&built_plan, false);
        if let Ok(size) = existing.outer_size() {
            measured(&mut info, size);
        }
        report(&app, &info);
        return Ok(info);
    }

    let mut builder = WebviewWindowBuilder::new(&app, &label, WebviewUrl::External(parsed))
        .title(built_plan.title.clone())
        .inner_size(f64::from(built_plan.width), f64::from(built_plan.height))
        .resizable(true)
        .decorations(built_plan.decorations)
        .transparent(built_plan.transparent)
        .always_on_top(built_plan.always_on_top)
        .visible_on_all_workspaces(true)
        .focused(true)
        .initialization_script_for_all_frames(STRIP_GLOBAL_BRIDGE)
        // A plugin page that opens a window would get a webview the shell never
        // built and never matched against a capability: refused at the door.
        .on_new_window(|_url, _features| tauri::webview::NewWindowResponse::Deny)
        .on_navigation(is_surface_url);

    // `devtools` is never set here. `browser.rs:128` turns it on for the app's own
    // pane, and `engine_key_state` (lib.rs:674) says why a value must not sit where
    // a devtools panel could read it back: this document is untrusted code.
    if built_plan.transparent && cfg!(debug_assertions) {
        builder = builder.background_color(tauri::window::Color(0, 0, 0, 0));
    }

    let built = builder.build().map_err(|error| {
        log::warn!("plugin surface {label} could not be built: {error}");
        refusal_for_build_failure().to_string()
    })?;
    let mut info = info_from(&built_plan, true);
    if let Ok(size) = built.outer_size() {
        measured(&mut info, size);
    }
    remember(&label);
    if !built_plan.note.is_empty() {
        log::warn!("plugin surface {}: {}", label, built_plan.note);
    }
    report(&app, &info);
    Ok(info)
}

/// Closes one surface window. The handle has to name a surface label, so a call
/// can never reach `main` or the browser pane.
#[tauri::command]
pub async fn plugin_window_close(
    app: AppHandle,
    webview: tauri::Webview,
    handle: String,
) -> Result<bool, String> {
    guard(&webview)?;
    if !handle.starts_with(PLUGIN_LABEL_PREFIX) {
        return Err(refusal_for_unknown_handle().to_string());
    }
    let Some(surface) = app.get_webview_window(&handle) else {
        forget(&handle);
        return Err(refusal_for_unknown_handle().to_string());
    };
    surface.close().map_err(|error| {
        log::warn!("plugin surface {handle} would not close: {error}");
        refusal_for_close_failure().to_string()
    })?;
    forget(&handle);
    let _ = app.emit_to(WORKBENCH_LABEL, "plugin-window:closed", handle);
    Ok(true)
}

/// Moves and sizes one surface window. The frontend owns the geometry; the shell
/// keeps the size inside the ceiling the descriptor contract states.
#[tauri::command]
pub async fn plugin_window_bounds(
    app: AppHandle,
    webview: tauri::Webview,
    handle: String,
    bounds: SurfaceBounds,
) -> Result<(), String> {
    guard(&webview)?;
    if !handle.starts_with(PLUGIN_LABEL_PREFIX) {
        return Err(refusal_for_unknown_handle().to_string());
    }
    let surface = app
        .get_webview_window(&handle)
        .ok_or_else(|| refusal_for_unknown_handle().to_string())?;
    let (default_width, default_height) = default_ui_size();
    let width = clamp_dimension(bounds.width.max(0.0) as u32, default_width);
    let height = clamp_dimension(bounds.height.max(0.0) as u32, default_height);
    surface
        .set_size(tauri::LogicalSize::new(f64::from(width), f64::from(height)))
        .map_err(|error| {
            log::warn!("plugin surface {handle} refused its size: {error}");
            refusal_for_geometry_failure().to_string()
        })?;
    surface
        .set_position(tauri::LogicalPosition::new(bounds.x, bounds.y))
        .map_err(|error| {
            log::warn!("plugin surface {handle} refused its position: {error}");
            refusal_for_geometry_failure().to_string()
        })
}

/// Every surface window goes with the app: both quit paths in `lib.rs` reach
/// `app.exit(0)`, which ends the event loop and destroys each window with it. The
/// count is written so a run log can tell a quit that carried surfaces.
pub fn note_quit() {
    if let Ok(open) = OPEN_LABELS.lock() {
        if !open.is_empty() {
            log::info!("closing {} plugin surface(s) with the app", open.len());
        }
    }
}
