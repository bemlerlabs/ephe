// Ephe — Tauri shell (R20): the tray, the N2 menu bar and the commands the PWA
// frontend (useTauriTray.ts: show/hide/quit/create-session) expects. Before this,
// those events were dead code — the tray protocol only existed inside the frontend.
// Update experience: tauri_plugin_updater + process wire the signed updater
// into the frontend (useUpdateCheck.ts).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Emitter, Manager,
};

use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;

use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

mod attachment;
mod browser;
#[cfg(unix)]
mod backend;
mod desktop;
mod instance;
mod parity;

/// Keep-awake (P2-B Automations): the `caffeinate` child process (macOS) that
/// `set_keep_awake(true)` starts. Held statically so the command itself stays
/// stateless and `quit_app` can clean it up.
static KEEP_AWAKE_CHILD: Mutex<Option<Child>> = Mutex::new(None);

/// Set once a quit really started. macOS asks every window `windowShouldClose`
/// before it ends the app, and the guard that keeps ⌘W from destroying `main`
/// would otherwise veto the quit and leave a hidden window with no way back.
static QUITTING: AtomicBool = AtomicBool::new(false);

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

/// The one chord the desktop registers: Cmd+Shift+E on macOS, Ctrl+Shift+E elsewhere.
fn global_shortcut() -> Shortcut {
    #[cfg(target_os = "macos")]
    let modifiers = Modifiers::SUPER | Modifiers::SHIFT;
    #[cfg(not(target_os = "macos"))]
    let modifiers = Modifiers::CONTROL | Modifiers::SHIFT;
    Shortcut::new(Some(modifiers), Code::KeyE)
}

fn reveal_main_window(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.show();
        let _ = win.unminimize();
        let _ = win.set_focus();
        let _ = app.emit("global-shortcut", ());
    }
}

/// Opt-in registration. Disabled is the default; a conflict with another
/// application surfaces as an error and the settings surface writes the value
/// back to off instead of leaving a shortcut that never fires.
#[tauri::command]
fn set_global_shortcut(app: tauri::AppHandle, enabled: bool) -> Result<String, String> {
    let manager = app.global_shortcut();
    let shortcut = global_shortcut();
    if enabled {
        // Idempotent re-enable; only `register` decides whether the chord is free.
        let _ = manager.unregister(shortcut);
        manager
            .register(shortcut)
            .map_err(|error| error.to_string())?;
        Ok("registered".into())
    } else {
        let _ = manager.unregister(shortcut);
        Ok("unregistered".into())
    }
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

/// Opens the native picker and returns the file the user chose, read and
/// capped in the shell. The path stays here; the surface receives content.
#[cfg(desktop)]
#[tauri::command]
async fn pick_attachment(
    app: tauri::AppHandle,
    accept: Option<String>,
) -> Result<Option<attachment::Attachment>, String> {
    tauri::async_runtime::spawn_blocking(move || attachment::pick_and_read(&app, accept.as_deref()))
        .await
        .map_err(|err| err.to_string())?
}

/// What the shell and the backend reported about their versions, for the
/// surface to say out loud. The start thread runs the full check; a cached
/// "no backend" is re-asked here on a worker thread, because a synchronous
/// command body would hold the window for the length of the wait.
#[tauri::command]
async fn backend_parity() -> parity::Status {
    let status = parity::last_status();
    let Some(project) = parity::configured_project() else {
        return status;
    };
    if !parity::should_refresh(&status) {
        return status;
    }
    tauri::async_runtime::spawn_blocking(move || {
        parity::check_and_heal_with(crate::backend::PORT, &project, 8_000)
    })
    .await
    .unwrap_or(status)
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
    QUITTING.store(true, Ordering::Relaxed);
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
    fn the_global_shortcut_is_one_explicit_chord() {
        let shortcut = super::global_shortcut();
        assert_eq!(shortcut.key, tauri_plugin_global_shortcut::Code::KeyE);
        assert!(shortcut.mods.contains(tauri_plugin_global_shortcut::Modifiers::SHIFT));
        #[cfg(target_os = "macos")]
        assert!(shortcut.mods.contains(tauri_plugin_global_shortcut::Modifiers::SUPER));
        #[cfg(not(target_os = "macos"))]
        assert!(shortcut.mods.contains(tauri_plugin_global_shortcut::Modifiers::CONTROL));
    }

    #[test]
    fn a_stamp_is_pulled_up_to_the_minimum_size() {
        assert_eq!(clamp_window_size(155, 168), (960, 640));
    }

    #[test]
    fn a_normal_window_stays_untouched() {
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

    #[test]
    fn every_native_id_routes_to_one_action() {
        // The tray and the menu bar are built from these ids. An id the handler
        // does not know fires nothing, which is what N2's gate refuses.
        let routed = [
            (super::ID_SHOW, super::MenuAction::Show),
            (super::ID_HIDE, super::MenuAction::Hide),
            (
                super::ID_NEW_SESSION,
                super::MenuAction::NewSession,
            ),
            (
                super::ID_CHECK_UPDATES,
                super::MenuAction::CheckUpdates,
            ),
            (
                super::ID_OPEN_SETTINGS,
                super::MenuAction::OpenSettings,
            ),
            (super::ID_OPEN_DOCS, super::MenuAction::OpenDocs),
            (super::ID_QUIT, super::MenuAction::Quit),
        ];
        for (id, action) in routed {
            assert_eq!(super::menu_action(id), Some(action), "{id} routes wrong");
        }
        assert_eq!(super::menu_action("close-window"), None);
    }

    #[test]
    fn the_events_are_the_names_the_surface_listens_for() {
        // useTauriTray.ts and useUpdateCheck.ts subscribe by string. If the shell
        // renames an event, the menu item fires into a void.
        use super::MenuAction::*;
        assert_eq!(NewSession.event(), Some("create-session"));
        assert_eq!(CheckUpdates.event(), Some("update:check"));
        assert_eq!(OpenSettings.event(), Some("open-settings"));
        assert_eq!(OpenDocs.event(), Some("open-docs"));
        for action in [Show, Hide, Quit] {
            assert_eq!(action.event(), None, "{action:?} emits on its own");
        }
    }

    #[test]
    fn an_item_that_answers_in_the_window_wakes_it_first() {
        use super::MenuAction::*;
        for action in [Show, NewSession, CheckUpdates, OpenSettings] {
            assert!(action.reveals_window(), "{action:?} would answer a hidden window");
        }
        for action in [Hide, OpenDocs, Quit] {
            assert!(!action.reveals_window(), "{action:?} would fight the user");
        }
    }
}

fn main_window(app: &tauri::AppHandle) -> Result<tauri::WebviewWindow, String> {
    app.get_webview_window("main")
        .ok_or_else(|| "main window not found".to_string())
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
            .map_err(|e| format!("failed to start caffeinate: {e}"))?;
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

/// N2: the ids the tray menu and the macOS menu bar hand to the same handler.
/// Both surfaces are built from this list, so an entry cannot exist in one and
/// sit dead in the other — the failure the tray protocol had before R20.
const ID_SHOW: &str = "show";
const ID_HIDE: &str = "hide";
const ID_NEW_SESSION: &str = "create-session";
const ID_CHECK_UPDATES: &str = "check-updates";
const ID_OPEN_SETTINGS: &str = "open-settings";
const ID_OPEN_DOCS: &str = "open-docs";
const ID_QUIT: &str = "quit";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum MenuAction {
    Show,
    Hide,
    NewSession,
    CheckUpdates,
    OpenSettings,
    OpenDocs,
    Quit,
}

impl MenuAction {
    /// The event the surface listens for. `Show`, `Hide` and `Quit` answer none:
    /// the window helpers below already emit them, and `Quit` is answered here.
    fn event(self) -> Option<&'static str> {
        match self {
            Self::NewSession => Some("create-session"),
            Self::CheckUpdates => Some("update:check"),
            Self::OpenSettings => Some("open-settings"),
            Self::OpenDocs => Some("open-docs"),
            Self::Show | Self::Hide | Self::Quit => None,
        }
    }

    /// An entry the user reaches while the window sits hidden in the tray has to
    /// bring it back before anything can happen in it.
    fn reveals_window(self) -> bool {
        matches!(self, Self::Show | Self::NewSession | Self::CheckUpdates | Self::OpenSettings)
    }
}

fn menu_action(id: &str) -> Option<MenuAction> {
    match id {
        ID_SHOW => Some(MenuAction::Show),
        ID_HIDE => Some(MenuAction::Hide),
        ID_NEW_SESSION => Some(MenuAction::NewSession),
        ID_CHECK_UPDATES => Some(MenuAction::CheckUpdates),
        ID_OPEN_SETTINGS => Some(MenuAction::OpenSettings),
        ID_OPEN_DOCS => Some(MenuAction::OpenDocs),
        ID_QUIT => Some(MenuAction::Quit),
        _ => None,
    }
}

/// The quit path both native surfaces share. `caffeinate` survived this call
/// once already (R3), so it stays in one place instead of per caller.
fn quit_from_shell(app: &tauri::AppHandle) {
    QUITTING.store(true, Ordering::Relaxed);
    keep_awake_stop();
    let _ = app.emit("quit", ());
    app.exit(0);
}

/// N3: the page hands over both faces of a copy; the shell owns the pasteboard.
/// The cap is checked before anything is written, so a refusal leaves the old
/// clipboard contents intact.
#[tauri::command]
fn write_rich_clipboard(plain: String, html: Option<String>) -> Result<(), String> {
    desktop::clipboard_bytes(&plain, html.as_deref())?;
    desktop::write_clipboard(&plain, html.as_deref())
}

/// N4: show a file in its folder. Only files inside the roots from
/// `desktop::allowed_roots` are accepted — the page never names a path we open.
#[tauri::command]
fn reveal_file_in_finder(path: String) -> Result<(), String> {
    let file = desktop::resolve_allowed_file(&path, &desktop::default_roots())?;
    desktop::reveal(&file)
}

/// N4: the same fence, then the file's default application.
#[tauri::command]
fn open_file_in_default_app(path: String) -> Result<(), String> {
    let file = desktop::resolve_allowed_file(&path, &desktop::default_roots())?;
    desktop::open_default(&file)
}

fn handle_menu_id(app: &tauri::AppHandle, id: &str) {
    let Some(action) = menu_action(id) else {
        return;
    };
    match action {
        MenuAction::Show => show_main_window(app),
        MenuAction::Hide => hide_main_window(app),
        MenuAction::Quit => quit_from_shell(app),
        action => {
            if action.reveals_window() {
                show_main_window(app);
            }
            if let Some(event) = action.event() {
                let _ = app.emit(event, ());
            }
        }
    }
}

/// N2: the bar itself, hand-built instead of `Menu::default` — the default
/// template has no New Session, no Settings and no route into the surface, and
/// an item that does not fire is worse than one that is absent. Linux and
/// Windows render the macOS-only entries disabled, so the bar lives where every
/// entry works.
#[cfg(target_os = "macos")]
fn build_menu_bar(app: &tauri::AppHandle) -> tauri::Result<Menu<tauri::Wry>> {
    use tauri::menu::{AboutMetadata, PredefinedMenuItem, Submenu};

    let package = app.package_info();
    let name = package.name.clone();
    let about = AboutMetadata {
        name: Some(name.clone()),
        version: Some(package.version.to_string()),
        copyright: app.config().bundle.copyright.clone(),
        authors: app.config().bundle.publisher.clone().map(|publisher| vec![publisher]),
        ..Default::default()
    };
    let item = |id: &str, text: &str, accelerator: Option<&str>| {
        MenuItem::with_id(app, id, text, true, accelerator)
    };

    let ephe = Submenu::with_items(
        app,
        name.as_str(),
        true,
        &[
            &PredefinedMenuItem::about(app, None, Some(about))?,
            &PredefinedMenuItem::separator(app)?,
            &item(ID_CHECK_UPDATES, "Check for Updates…", None)?,
            &item(ID_OPEN_SETTINGS, "Settings…", Some("CmdOrCtrl+,"))?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::services(app, None)?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::hide(app, None)?,
            &PredefinedMenuItem::hide_others(app, None)?,
            &PredefinedMenuItem::show_all(app, None)?,
            &PredefinedMenuItem::separator(app)?,
            // Our own Quit, not `PredefinedMenuItem::quit`: the predefined item
            // ends the app through AppKit, which never reaches `RunEvent::Exit`
            // and leaves both the backend and `caffeinate` behind.
            &item(ID_QUIT, format!("Quit {name}").as_str(), Some("CmdOrCtrl+Q"))?,
        ],
    )?;
    let file = Submenu::with_items(
        app,
        "File",
        true,
        &[
            &item(ID_NEW_SESSION, "New Session", Some("CmdOrCtrl+N"))?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::close_window(app, None)?,
        ],
    )?;
    let edit = Submenu::with_items(
        app,
        "Edit",
        true,
        &[
            &PredefinedMenuItem::undo(app, None)?,
            &PredefinedMenuItem::redo(app, None)?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::cut(app, None)?,
            &PredefinedMenuItem::copy(app, None)?,
            &PredefinedMenuItem::paste(app, None)?,
            &PredefinedMenuItem::select_all(app, None)?,
        ],
    )?;
    let view = Submenu::with_items(
        app,
        "View",
        true,
        &[&PredefinedMenuItem::fullscreen(app, None)?],
    )?;
    let window = Submenu::with_id_and_items(
        app,
        tauri::menu::WINDOW_SUBMENU_ID,
        "Window",
        true,
        &[
            &PredefinedMenuItem::minimize(app, None)?,
            &PredefinedMenuItem::maximize(app, None)?,
            &PredefinedMenuItem::separator(app)?,
            &item(ID_SHOW, "Show Ephe", None)?,
        ],
    )?;
    let help = Submenu::with_id_and_items(
        app,
        tauri::menu::HELP_SUBMENU_ID,
        "Help",
        true,
        &[&item(ID_OPEN_DOCS, "Ephe Documentation", None)?],
    )?;

    Menu::with_items(app, &[&ephe, &file, &edit, &view, &window, &help])
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
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, shortcut, event| {
                    if event.state() == ShortcutState::Pressed && shortcut == &global_shortcut() {
                        reveal_main_window(app);
                    }
                })
                .build(),
        )
        .on_menu_event(|app, event| handle_menu_id(app, event.id.as_ref()))
        .invoke_handler(tauri::generate_handler![
            quit_app,
            stop_backend,
            backend_parity,
            write_rich_clipboard,
            reveal_file_in_finder,
            open_file_in_default_app,
            pick_attachment,
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
            browser::browser_open_external,
            set_global_shortcut
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
                    // The root is read before the window can ask for a verdict, so the
                    // surface's command never sees "not run yet" because this thread
                    // has not reached its own read.
                    let project = std::fs::read_to_string(backend::konfig_pfad(&home))
                        .ok()
                        .and_then(|text| backend::befehl_aus(&text, &home))
                        .map(|cmd| cmd.projekt);
                    if let Some(project) = project.as_deref() {
                        parity::remember_project(project);
                    }
                    std::thread::spawn(move || {
                        let _ = backend::sicherstellen(&home, backend::PORT);
                        // The updater replaces the shell and nothing else, so the
                        // backend has to be asked what version it actually runs.
                        let Some(project) = project else {
                            return;
                        };
                        let status = parity::check_and_heal(backend::PORT, &project);
                        if status.verdict != "current" {
                            log::warn!(
                                "backend parity {}: shell {}, backend {} — {}",
                                status.verdict,
                                status.shell,
                                status.backend,
                                status.note
                            );
                        }
                    });
                }
            }

            // Tray menu: Show / Hide / New Session / Quit — the IDs emit the
            // same events useTauriTray.ts already consumes.
            let show = MenuItem::with_id(app, ID_SHOW, "Show Ephe", true, None::<&str>)?;
            let hide = MenuItem::with_id(app, ID_HIDE, "Hide", true, None::<&str>)?;
            let new_session =
                MenuItem::with_id(app, ID_NEW_SESSION, "New Session", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, ID_QUIT, "Quit", true, None::<&str>)?;
            let check_updates_tray =
                MenuItem::with_id(app, ID_CHECK_UPDATES, "Check for Updates…", true, None::<&str>)?;
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
                let app_handle = app.handle().clone();
                std::thread::spawn(move || {
                    for pause_ms in [250_u64, 750, 1500, 3000] {
                        std::thread::sleep(std::time::Duration::from_millis(pause_ms));
                        let Some(win) = app_handle.get_webview_window("main") else {
                            return;
                        };
                        let Ok(size) = win.outer_size() else { return };
                        let (w, h) = clamp_window_size(size.width, size.height);
                        if w == size.width && h == size.height {
                            return; // frame is within bounds — done
                        }
                        let _ = win
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

            // N2: the menu bar. R2-U put "Check for Updates…" next to the Apple
            // logo because that is where macOS looks for such an entry; the bar
            // now carries it inside a full template that also answers ⌘N and ⌘,.
            #[cfg(target_os = "macos")]
            if let Err(error) = build_menu_bar(app.handle()).and_then(|bar| app.set_menu(bar)) {
                log::warn!("menu bar not installed: {error}");
            }

            // The menu-bar glyph is the mono cut: macOS renders it as a template,
            // so it follows both menu-bar appearances instead of keeping a coloured
            // tile. `include_image!` embeds the raw pixels at compile time, so no
            // PNG codec enters the runtime dependency tree.
            let tray_icon = tauri::include_image!("icons/tray-mono.png");
            TrayIconBuilder::with_id("ephe-tray")
                .icon(tray_icon)
                .icon_as_template(true)
                .tooltip("Ephe — local & private")
                .menu(&menu)
                .on_menu_event(|app, event| handle_menu_id(app, event.id.as_ref()))
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
            // An exit that arrives through AppKit rather than one of our quit
            // calls would otherwise leave `caffeinate` running after the shell.
            keep_awake_stop();
            backend::stop_backend();
        }
        // ⌘W and the red button both end here. Letting Tauri destroy `main` left
        // `get_webview_window("main")` empty, and no Dock reopen and no tray click
        // can bring a destroyed window back — so a close hides it instead.
        #[cfg(target_os = "macos")]
        if let tauri::RunEvent::WindowEvent {
            ref label,
            event: tauri::WindowEvent::CloseRequested { ref api, .. },
            ..
        } = event
        {
            if label == "main" && !QUITTING.load(Ordering::Relaxed) {
                api.prevent_close();
                hide_main_window(app_handle);
            }
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
                if let Some(win) = app_handle.get_webview_window(label) {
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
