// Ephe — Tauri shell (R20): the tray plus the commands the PWA frontend
// (useTauriTray.ts: show/hide/quit/create-session) expects. Before this, those
// events were dead code — the tray protocol only existed inside the frontend.
// Update experience: tauri_plugin_updater + process wire the signed updater
// into the frontend (useUpdateCheck.ts).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{
    menu::{Menu, MenuItem, MenuItemKind},
    tray::TrayIconBuilder,
    Emitter, Manager,
};

use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

mod browser;
#[cfg(unix)]
mod backend;
mod instance;

/// Keep-awake (P2-B Automations): the `caffeinate` child process (macOS) that
/// `set_keep_awake(true)` starts. Held statically so the command itself stays
/// stateless and `quit_app` can clean it up.
static KEEP_AWAKE_CHILD: Mutex<Option<Child>> = Mutex::new(None);

/// Terminate the child process cleanly (kill + wait, no zombie).
fn keep_awake_stop() {
    if let Ok(mut guard) = KEEP_AWAKE_CHILD.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

/// Frontend invoke('stop_backend') — called before an in-app update relaunches
/// the shell, so the next version does not inherit this one's Python process.
#[tauri::command]
fn stop_backend() {
    backend::stop_backend();
}

/// The tour's carry-over stop: a native folder picker. The chosen folder is
/// recorded in `~/.ephe/import-source.json` with a one-time token; the surface
/// posts that token, never the path. The PWA has no path to hand to the
/// importer, so the surface declares that limit instead of faking a browser
/// directory upload.
#[tauri::command]
async fn pick_folder(app: tauri::AppHandle) -> Option<String> {
    use tauri_plugin_dialog::DialogExt;
    let chosen = app.dialog().file().blocking_pick_folder()?;
    record_import_source(&chosen.to_string())
}

/// Writes the native selection where the backend alone reads it. The token is
/// the whole HTTP-side capability: without it, `/api/import` cannot name a
/// folder, so a page on this machine cannot point the importer at one.
fn record_import_source(path: &str) -> Option<String> {
    record_import_source_in(&crate::instance::config_dir()?, path)
}

fn record_import_source_in(dir: &Path, path: &str) -> Option<String> {
    std::fs::create_dir_all(dir).ok()?;
    let created = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .ok()?
        .as_millis();
    let token = format!("{created:x}{:x}", std::process::id());
    let body = serde_json::json!({ "path": path, "token": token, "created_at": created });
    let file = dir.join("import-source.json");
    std::fs::write(&file, body.to_string()).ok()?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(&file, std::fs::Permissions::from_mode(0o600));
    }
    Some(token)
}

/// Frontend invoke('quit_app') — tray quit (useTauriTray.ts).
#[tauri::command]
fn quit_app(app: tauri::AppHandle) {
    keep_awake_stop();
    backend::stop_backend();
    app.exit(0);
}

/// Window buttons the frontend has been calling since R20 (`useTauriWindow.ts`,
/// `OnboardingWizard.tsx`) that were never registered in the shell: the buttons
/// clicked into a void, without raising an error. Five short paths onto the same
/// window.
/// R6/S4: minimum size of the main window. macOS restores the last shown frame —
/// including one below the configured `minWidth`, measured on 2026-10-07 at
/// 155×168 px although tauri.conf demands 960×640. That configuration only applies
/// to new windows; the restored frame slips past it, so the size is measured once
/// more and, if needed, pulled back up.
const MIN_WINDOW: (u32, u32) = (960, 640);

fn clamp_window_size(width: u32, height: u32) -> (u32, u32) {
    (width.max(MIN_WINDOW.0), height.max(MIN_WINDOW.1))
}

#[cfg(test)]
mod tests {
    use super::clamp_window_size;

    #[test]
    fn briefmarke_wird_auf_mindestmass_gezogen() {
        assert_eq!(clamp_window_size(155, 168), (960, 640));
    }

    #[test]
    fn normales_fenster_bleibt_unberuehrt() {
        assert_eq!(clamp_window_size(1280, 800), (1280, 800));
        assert_eq!(clamp_window_size(960, 640), (960, 640));
    }

    #[test]
    fn the_picker_records_its_selection_for_the_backend() {
        let dir = std::env::temp_dir().join(format!("ephe-import-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let token =
            super::record_import_source_in(&dir, "/tmp/old setup").expect("selection recorded");
        let body = std::fs::read_to_string(dir.join("import-source.json")).expect("file");
        let parsed: serde_json::Value = serde_json::from_str(&body).expect("json");
        assert_eq!(parsed["path"], "/tmp/old setup");
        assert_eq!(parsed["token"], token);
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mode = std::fs::metadata(dir.join("import-source.json"))
                .expect("meta")
                .permissions()
                .mode();
            assert_eq!(mode & 0o777, 0o600);
        }
        let _ = std::fs::remove_dir_all(&dir);
    }
}

fn main_window(app: &tauri::AppHandle) -> Result<tauri::WebviewWindow, String> {
    app.get_webview_window("main")
        .ok_or_else(|| "Hauptfenster nicht gefunden".to_string())
}

#[tauri::command]
fn minimize_window(app: tauri::AppHandle) -> Result<(), String> {
    main_window(&app)?
        .minimize()
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn maximize_window(app: tauri::AppHandle) -> Result<(), String> {
    let window = main_window(&app)?;
    if window.is_maximized().unwrap_or(false) {
        window.unmaximize()
    } else {
        window.maximize()
    }
    .map_err(|e| e.to_string())
}

#[tauri::command]
fn close_window(app: tauri::AppHandle) -> Result<(), String> {
    main_window(&app)?.close().map_err(|e| e.to_string())
}

#[tauri::command]
fn show_window(app: tauri::AppHandle) -> Result<(), String> {
    let window = main_window(&app)?;
    window.show().map_err(|e| e.to_string())?;
    window.set_focus().map_err(|e| e.to_string())
}

#[tauri::command]
fn hide_window(app: tauri::AppHandle) -> Result<(), String> {
    main_window(&app)?.hide().map_err(|e| e.to_string())
}

/// Frontend invoke('set_keep_awake', { enabled }) — keeps the machine awake
/// while a chat is running (useKeepAwake.ts). macOS: `caffeinate -dimsu`
/// (suppresses Display, idle-sleep, System-sleep and User assertions);
/// other platforms report `Ok(false)` honestly (no silent no-op — the frontend
/// then disables the toggle and says why).
#[tauri::command]
fn set_keep_awake(enabled: bool) -> Result<bool, String> {
    if !cfg!(target_os = "macos") {
        return Ok(false);
    }
    let mut guard = KEEP_AWAKE_CHILD.lock().map_err(|e| e.to_string())?;
    if enabled {
        // Idempotent: already running → do nothing.
        if guard.is_some() {
            return Ok(true);
        }
        let child = Command::new("caffeinate")
            .args(["-dimsu"])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| format!("caffeinate konnte nicht gestartet werden: {e}"))?;
        *guard = Some(child);
        Ok(true)
    } else {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        Ok(true)
    }
}

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
    let _ = app.emit("show", ());
}

fn hide_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.hide();
    }
    let _ = app.emit("hide", ());
}

fn shell_home() -> Result<std::path::PathBuf, String> {
    std::env::var_os("HOME")
        .map(std::path::PathBuf::from)
        .ok_or_else(|| "no home directory for this process".to_string())
}

/// Frontend invoke('save_engine_key', { value }): store the access token the next desktop
/// start spawns its backend with. The settings field used to be a one-session promise — the
/// value landed in the env of the running server and died with it, so a keyed engine chosen
/// inside the app stopped answering after the next start (measured 2026-10-11).
#[tauri::command]
fn save_engine_key(value: String) -> Result<(), String> {
    #[cfg(unix)]
    {
        backend::store_key(&shell_home()?, &value)
    }
    #[cfg(not(unix))]
    {
        let _ = value;
        Err("this platform reads the engine token from EPHE_OPENAI_COMPAT_API_KEY only".into())
    }
}

/// Frontend invoke('engine_key_state'): whether a token is stored. Existence only — the
/// value never crosses into the webview, where a devtools panel could read it back.
#[tauri::command]
fn engine_key_state() -> Result<bool, String> {
    #[cfg(unix)]
    {
        Ok(backend::key_is_stored(&shell_home()?))
    }
    #[cfg(not(unix))]
    {
        Ok(false)
    }
}

/// Frontend invoke('clear_engine_key'): remove the stored token, so deleting a key in the
/// surface is the end of it.
#[tauri::command]
fn clear_engine_key() -> Result<(), String> {
    #[cfg(unix)]
    {
        backend::clear_key(&shell_home()?)
    }
    #[cfg(not(unix))]
    {
        Ok(())
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // R4/W5: one instance. A second launch brings the running window to the
    // front and exits itself — two programs on one index was the failure that
    // was actually observed.
    #[cfg(unix)]
    let held = match instance::claim() {
        instance::Claim::Held(held) => Some(held),
        instance::Claim::OtherInstance => std::process::exit(0),
        instance::Claim::Unknown => None,
    };
    let app = tauri::Builder::default()
        // Single-instance must be the first plugin. `instance::claim` above
        // covers Unix and exits a second launch before the builder runs; on
        // Windows that guard does not compile, and on the Unix run where
        // `claim` returns `Claim::Unknown` (no HOME) it stands down as well.
        // This plugin is the backstop for both — one process on one store.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            show_main_window(app);
        }))
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_dialog::init())
        .on_menu_event(|app, event| {
            if event.id.as_ref() == "check-updates" {
                show_main_window(app);
                let _ = app.emit("update:check", ());
            }
        })
        .invoke_handler(tauri::generate_handler![
            quit_app,
            stop_backend,
            pick_folder,
            set_keep_awake,
            save_engine_key,
            engine_key_state,
            clear_engine_key,
            minimize_window,
            maximize_window,
            close_window,
            show_window,
            hide_window,
            browser::browser_open,
            browser::browser_bounds,
            browser::browser_visible,
            browser::browser_history,
            browser::browser_close,
            browser::browser_open_external
        ])
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // R7: the app icon alone has to be enough. Without this follow-up
            // check the window opens against a missing backend and reports
            // "Disconnected" — measured 2026-10-08 on the installed app.
            {
                let home = std::env::var_os("HOME").map(std::path::PathBuf::from);
                if let Some(home) = home {
                    std::thread::spawn(move || {
                        let _ = backend::sicherstellen(&home, backend::PORT);
                    });
                }
            }

            // Tray menu: Show / Hide / New Session / Quit — the IDs emit the
            // same events useTauriTray.ts already consumes.
            let show = MenuItem::with_id(app, "show", "Show Ephe", true, None::<&str>)?;
            let hide = MenuItem::with_id(app, "hide", "Hide", true, None::<&str>)?;
            let new_session = MenuItem::with_id(app, "create-session", "New Session", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let check_updates_tray =
                MenuItem::with_id(app, "check-updates", "Check for Updates…", true, None::<&str>)?;
            let menu = Menu::with_items(
                app,
                &[&show, &hide, &new_session, &check_updates_tray, &quit],
            )?;

            // R6/S4: the restored frame can sit below the minimum size; measure
            // once and pull it up so the surface never starts as a stamp.
            if let Ok(win) = main_window(app.handle()) {
                let _ = win.set_min_size(Some(tauri::Size::Logical(tauri::LogicalSize::new(
                    MIN_WINDOW.0 as f64,
                    MIN_WINDOW.1 as f64,
                ))));
                if let Ok(size) = win.outer_size() {
                    let (w, h) = clamp_window_size(size.width, size.height);
                    if w != size.width || h != size.height {
                        let _ = win.set_size(tauri::Size::Physical(
                            tauri::PhysicalSize::new(w, h),
                        ));
                    }
                }
                // macOS only restores the frame after `setup` returns — the
                // one-off clamp ran into an empty window (measured live:
                // 134×143 despite the clamp). So keep re-checking briefly until
                // the frame is in place; afterwards `set_min_size` and the
                // resize branch hold it.
                let nachsetzen = app.handle().clone();
                std::thread::spawn(move || {
                    for pause_ms in [250_u64, 750, 1500, 3000] {
                        std::thread::sleep(std::time::Duration::from_millis(pause_ms));
                        let Some(fenster) = nachsetzen.get_webview_window("main") else {
                            return;
                        };
                        let Ok(size) = fenster.outer_size() else { return };
                        let (w, h) = clamp_window_size(size.width, size.height);
                        if w == size.width && h == size.height {
                            return; // frame is within bounds — done
                        }
                        let _ = fenster
                            .set_size(tauri::Size::Physical(tauri::PhysicalSize::new(w, h)));
                    }
                });
            }

            // Programmatic fallback for the native macOS depth blur
            // (NSVisualEffectView). tauri.conf.json already asks for
            // `windowEffects.underWindowBackground`; re-applying it here guarantees
            // the effect survives the config path being ignored on a given runtime.
            #[cfg(target_os = "macos")]
            if let Some(win) = app.get_webview_window("main") {
                use tauri::window::{Effect, EffectState, EffectsBuilder};
                let _ = win.set_effects(
                    EffectsBuilder::new()
                        .effect(Effect::UnderWindowBackground)
                        .state(EffectState::FollowsWindowActiveState)
                        .build(),
                );
            }

            // R2-U: "Check for Updates…" belongs in the menu next to the Apple
            // logo — that is where macOS looks for exactly such an entry. The
            // item fires the same event as the surface's header button, so both
            // show one state instead of two half-truths.
            #[cfg(target_os = "macos")]
            {
                if let Ok(app_menu) = Menu::default(app.handle()) {
                    let check = MenuItem::with_id(
                        app.handle(),
                        "check-updates",
                        "Check for Updates…",
                        true,
                        None::<&str>,
                    )?;
                    if let Ok(items) = app_menu.items() {
                        if let Some(MenuItemKind::Submenu(sub)) = items.first() {
                            let _ = sub.append(&check);
                        }
                    }
                    let _ = app.set_menu(app_menu);
                }
            }

            TrayIconBuilder::with_id("ephe-tray")
                .icon(app.default_window_icon().expect("app icon").clone())
                .tooltip("Ephe — local & private")
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => show_main_window(app),
                    "hide" => hide_main_window(app),
                    "quit" => {
                        // R3 finding: this path left keep_awake_stop() out — the
                        // caffeinate child process survived the quit.
                        keep_awake_stop();
                        let _ = app.emit("quit", ());
                        app.exit(0);
                    }
                    "create-session" => {
                        show_main_window(app);
                        let _ = app.emit("create-session", ());
                    }
                    "check-updates" => {
                        show_main_window(app);
                        let _ = app.emit("update:check", ());
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    // Click on the tray icon: hide or reveal the window
                    if let tauri::tray::TrayIconEvent::Click {
                        button: tauri::tray::MouseButton::Left,
                        button_state: tauri::tray::MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            if window.is_visible().unwrap_or(false) {
                                hide_main_window(app);
                            } else {
                                show_main_window(app);
                            }
                        }
                    }
                })
                .build(app)?;

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    // A second launch reports itself here; it wakes the window that already
    // exists instead of becoming a second program.
    #[cfg(unix)]
    if let Some(held) = held {
        let handle = app.handle().clone();
        instance::wake_on_request(held, move || show_main_window(&handle));
    }

    // macOS decides for itself on a Dock click: `Reopen`, not a new process.
    // Without a handler here, a window hidden from the tray never comes back.
    app.run(|app_handle, event| {
        if matches!(&event, tauri::RunEvent::Exit) {
            backend::stop_backend();
        }
        // R6/S4, second look: the clamp inside setup alone was not enough — live
        // measurement still saw the window come back at 134×143. macOS restores
        // the frame after setup. So set the minimum size (then nobody can drag
        // below it) and clamp again on every resize.
        if let tauri::RunEvent::WindowEvent {
            ref label,
            event: tauri::WindowEvent::Resized(size),
            ..
        } = event
        {
            let (w, h) = clamp_window_size(size.width, size.height);
            if w != size.width || h != size.height {
                if let Some(win) = app_handle.get_webview_window(&label) {
                    let _ = win.set_size(tauri::Size::Physical(tauri::PhysicalSize::new(w, h)));
                }
            }
        }
        #[cfg(target_os = "macos")]
        if let tauri::RunEvent::Reopen {
            has_visible_windows, ..
        } = event
        {
            if !has_visible_windows {
                show_main_window(app_handle);
            }
        }
        #[cfg(not(target_os = "macos"))]
        let _ = app_handle;
    });
}
