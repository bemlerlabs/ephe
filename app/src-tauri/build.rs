fn main() {
    // The three surface commands lead the list. A surface capability that copied
    // the grant would take them first, and the surface file is kept empty so it
    // never receives the set. Every name the shell registers is here: turning
    // the manifest on refuses a command that has no allow entry.
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "plugin_window_open",
            "plugin_window_close",
            "plugin_window_bounds",
            "quit_app",
            "stop_backend",
            "backend_parity",
            "backend_readiness",
            "write_rich_clipboard",
            "reveal_file_in_finder",
            "open_file_in_default_app",
            "quick_look_file",
            "extract_image_text",
            "set_dock_badge",
            "set_dock_progress",
            "pick_attachment",
            "pick_folder",
            "set_keep_awake",
            "save_engine_key",
            "engine_key_state",
            "clear_engine_key",
            "minimize_window",
            "maximize_window",
            "close_window",
            "show_window",
            "hide_window",
            "browser_open",
            "browser_bounds",
            "browser_visible",
            "browser_history",
            "browser_close",
            "browser_open_external",
            "set_global_shortcut",
        ]),
    ))
    .expect("failed to run tauri-build");
}
