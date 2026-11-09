//! Ephe — what a plugin surface window is made of (W1-3, the pure half)
//!
//! `plugin_window.rs` owns the commands and the webview builder. This module holds
//! the decisions inside them: the label, the caller rule, the size bound, the URL
//! the surface may load, and the mapping from a descriptor to window options. They
//! are separate because a unit test can read a decision here, while a webview is
//! only observable in a running app.
//!
//! The two shell lifecycle decisions that a plugin window changed also live here for
//! the same reason: [`workbench_size_floor`] (which window the workbench's minimum
//! size applies to) and [`workbench_needs_reveal`] (when a Dock click has to bring
//! the workbench back). `lib.rs` asks them and holds no rule of its own.
//!
//! Every bound comes from a contract already written down. `MAX_UI_DIMENSION`,
//! the size defaults, the title bound and the slug shape are the numbers of
//! `core/plugin_ui_capabilities.py` (the descriptor #42 hands over), so the shell
//! re-decides nothing the manifest validator already decided.

use tauri::Url;

/// The label of the window the user opened Ephe for. Every decision in this module
/// that tells the shell's own UI apart from a surface starts from this one string.
pub const WORKBENCH_LABEL: &str = "main";

/// Every plugin window starts here, and every capability for one matches it.
pub const PLUGIN_LABEL_PREFIX: &str = "ephe-plugin-";

/// The surface commands, in the order the workbench permission set lists them.
/// The door matches these names. A command that only shares the prefix is
/// outside the list, so a rename has to land here before the door treats it
/// as a surface command.
pub const SURFACE_COMMANDS: [&str; 3] = [
    "plugin_window_open",
    "plugin_window_close",
    "plugin_window_bounds",
];

/// The workbench's own minimum size, R6/S4. A plugin surface is sized by its
/// descriptor, so this floor belongs to one label and to no other window.
pub const WORKBENCH_MINIMUM: (u32, u32) = (960, 640);

/// The ceiling `core/plugin_ui_capabilities.py` fixes as `MAX_UI_DIMENSION`. The
/// shell uses the same number #39 replaces with a measured one.
const MAX_UI_DIMENSION: u32 = 4096;

/// The fallbacks of the same validator, for a descriptor that names no size.
const DEFAULT_UI: (u32, u32) = (480, 320);

/// A title past this is truncated by a titlebar; the validator's own bound.
const MAX_UI_TITLE_CHARS: usize = 80;

/// The path prefix of the surface route (#42). Nothing else may load here.
const SURFACE_PATH_ROOT: &str = "/api/plugins/ui/";

/// The loopback hosts the product server binds. The port stays free: the shell
/// reads it from its own backend module, which is platform-gated.
const SURFACE_HOSTS: [&str; 2] = ["127.0.0.1", "localhost"];

/// A slug is at most this long in the manifest contract.
const MAX_SLUG_CHARS: usize = 64;

/// Each refusal says the rule a caller broke and nothing about the machinery: no
/// label scheme, no command name, no path.
pub const REFUSAL_FROM_A_SURFACE: &str = "plugin windows open from the Ephe window only";
const REFUSAL_BAD_ID: &str = "this plugin id cannot name a window";
const REFUSAL_BAD_URL: &str = "only the plugin surface route loads in a plugin window";
const REFUSAL_TYPE: &str = "this surface type has no native window yet";
const REFUSAL_UNKNOWN: &str = "no plugin window carries that handle";
/// A window-server failure does say something, but the engine's own words about it
/// are not for the workbench console: these four carry the action that failed and
/// nothing else, so a refusal cannot become a leak of what the runtime reported.
const REFUSAL_BUILD: &str = "the plugin window could not be opened";
const REFUSAL_NAVIGATE: &str = "the plugin window would not take the new address";
const REFUSAL_CLOSE: &str = "the plugin window would not close";
const REFUSAL_GEOMETRY: &str = "the plugin window would not take the size or position";

/// The one surface type with a native window today. `dock-panel` and
/// `canvas-overlay` are in the same vocabulary and land with #44.
const NATIVE_SURFACE_TYPE: &str = "floating-window";

/// What a plugin surface window is asked for. The shape is `ui_descriptor()` of
/// `core/plugin_ui_capabilities.py` as the API hands it over: already defaulted,
/// flattened, snake_case. Fields this window does not act on (`entry`,
/// `capabilities`, `grants`) are ignored here, because #23 and #38 decide those.
#[derive(Debug, Clone, Default, serde::Deserialize, PartialEq, Eq)]
pub struct SurfaceDescriptor {
    #[serde(rename = "type")]
    pub surface_type: String,
    #[serde(default)]
    pub title: String,
    #[serde(default)]
    pub width: u32,
    #[serde(default)]
    pub height: u32,
    #[serde(default)]
    pub transparent: bool,
    #[serde(default)]
    pub always_on_top: bool,
}

/// The window options a descriptor turns into.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WindowPlan {
    pub label: String,
    pub title: String,
    pub width: u32,
    pub height: u32,
    pub transparent: bool,
    pub decorations: bool,
    pub always_on_top: bool,
    pub note: String,
}

/// A name that can safely sit inside a window label: one slug, no glob character,
/// no space, no separator at either edge.
fn is_slug(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= MAX_SLUG_CHARS
        && !id.starts_with('-')
        && !id.ends_with('-')
        && id
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
}

pub fn window_label(plugin_id: &str) -> Result<String, String> {
    if !is_slug(plugin_id) {
        return Err(REFUSAL_BAD_ID.to_string());
    }
    Ok(format!("{PLUGIN_LABEL_PREFIX}{plugin_id}"))
}

/// The webview labels that may drive the surface layer. An allow-list on purpose: a
/// label nobody here has thought about yet is refused instead of getting in by
/// accident, which is the failure mode a deny-list of plugin prefixes has.
///
/// Read against the **calling webview's** label, not the window's (`plugin_window.rs`
/// takes `tauri::Webview`). That distinction is the whole rule: the browser pane of
/// `browser.rs` is a child webview of `main`, so a window-level read reports
/// `"main"` for a page the shell does not own, and every deny-list built on window
/// labels lets it through.
///
/// `ephe-browser` is deliberately absent. The pane belongs to the shell and shows
/// whatever site the user asked for; an invoke from inside it arrives with the pane's
/// own webview label and is refused like any surface caller.
pub fn caller_is_allowed(label: &str) -> bool {
    SURFACE_CALLERS.contains(&label)
}

/// The one entry of the allow-list today: the workbench webview. A plugin surface,
/// the browser pane, an iframe webview and any label added later are all outside it.
const SURFACE_CALLERS: [&str; 1] = [WORKBENCH_LABEL];

/// Whether a command name belongs to the surface layer. The IPC door keys on
/// [`SURFACE_COMMANDS`]. A fourth name is covered when it is added to that
/// list. Sharing the prefix is not enough.
pub fn is_surface_command(command: &str) -> bool {
    SURFACE_COMMANDS.contains(&command)
}

/// The single question the IPC door asks before a command body runs: `Some(refusal)`
/// means this caller may not reach this command. Pure, so a test can walk the names
/// `lib.rs` registers and ask it of every one.
pub fn refusal_for_surface_call(command: &str, caller_label: &str) -> Option<&'static str> {
    if is_surface_command(command) && !caller_is_allowed(caller_label) {
        return Some(refusal_from_a_surface());
    }
    None
}

/// The resize floor, asked of a window label. `Some` is the smallest frame the
/// workbench may hold; `None` says the label owns its own size, because a plugin
/// surface is sized by its descriptor and 480×320 is that contract's default.
/// Without the label in the question, the floor of `main` would be imposed on every
/// window the app makes and would deny a widget the size it asked for.
pub fn workbench_size_floor(label: &str, width: u32, height: u32) -> Option<(u32, u32)> {
    if label != WORKBENCH_LABEL {
        return None;
    }
    Some((
        width.max(WORKBENCH_MINIMUM.0),
        height.max(WORKBENCH_MINIMUM.1),
    ))
}

/// The Dock-click question, decided where a test can read every branch.
///
/// `visible` is Tauri's `is_visible`, and on macOS that is `NSWindow.isVisible`.
/// Measured on macOS 26.6: the turn `miniaturize` returns, the window is still
/// on screen. Within the next frame `isVisible` is false and `isMiniaturized`
/// is true. A 5 ms poll across 200 ms never sees both true at once, and
/// `applicationShouldHandleReopen` observes that settled pair while
/// `hasVisibleWindows` is still true. AppKit deminiaturizes only after the
/// callback returns. A hidden workbench and a miniaturized one are the same
/// answer here, so the minimized flag cannot change it.
pub fn workbench_needs_reveal(visible: bool) -> bool {
    !visible
}

/// The size edge of a surface: the validator's ceiling, and its default for a
/// descriptor that named none (a zero arrives when a field is absent).
pub fn clamp_dimension(edge: u32, fallback: u32) -> u32 {
    if edge == 0 {
        fallback
    } else {
        edge.min(MAX_UI_DIMENSION).max(1)
    }
}

/// Transparency needs a compositor the shell cannot see on every platform, so a
/// surface asking for it there gets a decorated window and a note saying so.
pub fn platform_honours_transparency() -> bool {
    cfg!(target_os = "macos") || cfg!(target_os = "windows")
}

/// Only the surface route of the product server loads in a plugin window. A page
/// that leaves it stops being a plugin surface, so the shell stops allowing it.
pub fn is_surface_url(url: &Url) -> bool {
    if url.scheme() != "http" && url.scheme() != "https" {
        return false;
    }
    let Some(host) = url.host_str() else {
        return false;
    };
    if !SURFACE_HOSTS.contains(&host) {
        return false;
    }
    url.path().starts_with(SURFACE_PATH_ROOT)
}

/// The URL has to name the plugin this window carries the label of: the credential
/// in the path is bound to one plugin id (#42), and a mismatch would mount one
/// surface under another's capability.
pub fn surface_url_for_plugin(url: &Url, plugin_id: &str) -> bool {
    if !is_surface_url(url) {
        return false;
    }
    url.path()[SURFACE_PATH_ROOT.len()..].split('/').next() == Some(plugin_id)
}

pub fn surface_type_is_native(descriptor: &SurfaceDescriptor) -> bool {
    descriptor.surface_type == NATIVE_SURFACE_TYPE
}

pub fn refusal_for_unknown_handle() -> &'static str {
    REFUSAL_UNKNOWN
}

pub fn refusal_for_bad_url() -> &'static str {
    REFUSAL_BAD_URL
}

pub fn refusal_for_type() -> &'static str {
    REFUSAL_TYPE
}

pub fn refusal_from_a_surface() -> &'static str {
    REFUSAL_FROM_A_SURFACE
}

/// The four window-server failures, each as a curated constant rather than whatever
/// the runtime put in its error. They reach only the workbench, but the inconsistency
/// is how a raw engine string gets into a caller's console later.
pub fn refusal_for_build_failure() -> &'static str {
    REFUSAL_BUILD
}

pub fn refusal_for_navigation_failure() -> &'static str {
    REFUSAL_NAVIGATE
}

pub fn refusal_for_close_failure() -> &'static str {
    REFUSAL_CLOSE
}

pub fn refusal_for_geometry_failure() -> &'static str {
    REFUSAL_GEOMETRY
}

pub fn default_ui_size() -> (u32, u32) {
    DEFAULT_UI
}

/// The descriptor read as window options. Pure, so both directions of every
/// platform branch are testable on a machine that has no window server.
pub fn plan(label: String, descriptor: &SurfaceDescriptor) -> WindowPlan {
    let mut transparent = descriptor.transparent;
    let mut note = String::new();
    if transparent && !platform_honours_transparency() {
        transparent = false;
        note = "transparency refused: this platform cannot prove a compositor".to_string();
    }
    let mut title: String = descriptor.title.chars().take(MAX_UI_TITLE_CHARS).collect();
    if title.is_empty() {
        title = label.clone();
    }
    WindowPlan {
        label,
        title,
        width: clamp_dimension(descriptor.width, DEFAULT_UI.0),
        height: clamp_dimension(descriptor.height, DEFAULT_UI.1),
        always_on_top: descriptor.always_on_top,
        // An undecorated window is the shape a transparent surface needs; a
        // decorated one keeps its close button where the user can find it.
        decorations: !transparent,
        transparent,
        note,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn descriptor() -> SurfaceDescriptor {
        SurfaceDescriptor {
            surface_type: "floating-window".to_string(),
            title: "Countdown".to_string(),
            width: 360,
            height: 240,
            transparent: false,
            always_on_top: false,
        }
    }

    fn url(path: &str) -> Url {
        format!("http://127.0.0.1:8765{path}").parse().expect("url")
    }

    #[test]
    fn a_slug_builds_a_glob_safe_label() {
        assert_eq!(
            window_label("acme-countdown").expect("label"),
            "ephe-plugin-acme-countdown"
        );
    }

    #[test]
    fn a_label_cannot_be_built_from_a_name_that_is_not_a_slug() {
        let mut bad: Vec<String> = [
            "",
            "-lead",
            "trail-",
            "UPPER",
            "a b",
            "a/b",
            "a*b",
            "ünïcode",
        ]
        .iter()
        .map(|name| name.to_string())
        .collect();
        bad.push("x".repeat(MAX_SLUG_CHARS + 1));
        for name in bad {
            assert!(
                window_label(&name).is_err(),
                "a name like {name:?} would name a window"
            );
        }
    }

    #[test]
    fn the_workbench_webview_drives_the_surface_layer() {
        assert!(caller_is_allowed(WORKBENCH_LABEL));
        assert_eq!(SURFACE_CALLERS, [WORKBENCH_LABEL]);
    }

    /// The rule fix round 1 exists for. `browser.rs:70` attaches `ephe-browser` as a
    /// child webview of `main`, so a window-label read says `main` for any page that
    /// pane happens to show. The webview label says the truth, and the truth is: no.
    #[test]
    fn a_page_in_the_browser_pane_is_refused_the_surface_layer() {
        assert!(!caller_is_allowed("ephe-browser"));
    }

    #[test]
    fn a_plugin_surface_is_refused_the_surface_layer() {
        assert!(!caller_is_allowed("ephe-plugin-acme-countdown"));
        assert!(!caller_is_allowed(PLUGIN_LABEL_PREFIX));
    }

    /// What the allow-list buys over the deny-list: a label nobody has argued about
    /// yet is already refused, and casing or padding cannot smuggle the workbench's
    /// name past it.
    #[test]
    fn an_unknown_caller_is_refused_without_being_named() {
        for caller in [
            "",
            "main ",
            "Main",
            "settings",
            "ephe-webview-anything",
            "ephe-plugin-acme-countdown/../../",
        ] {
            assert!(
                !caller_is_allowed(caller),
                "{caller:?} would drive a window"
            );
        }
    }

    #[test]
    fn the_door_answers_for_the_listed_commands_only() {
        assert!(is_surface_command("plugin_window_open"));
        assert!(!is_surface_command("plugin_window_renamed"));
        assert!(!is_surface_command("browser_open"));
        let prefixed: Vec<String> = registered_handler_names()
            .into_iter()
            .filter(|name| name.starts_with("plugin_window_"))
            .collect();
        assert_eq!(
            prefixed, SURFACE_COMMANDS,
            "a prefixed name outside the list would pass the old door"
        );
    }

    /// A command name plus a caller label is the whole question, so the refusal is a
    /// property of the door rather than of any command body.
    #[test]
    fn the_door_refuses_every_surface_command_from_a_caller_the_shell_does_not_own() {
        let commands = SURFACE_COMMANDS;
        assert_eq!(commands.len(), 3, "the surface list moved");
        for command in &commands {
            assert_eq!(refusal_for_surface_call(command, WORKBENCH_LABEL), None);
            for caller in ["ephe-browser", "ephe-plugin-acme-countdown", "unknown-pane"] {
                assert_eq!(
                    refusal_for_surface_call(command, caller),
                    Some(refusal_from_a_surface()),
                    "{command} answered a caller it should not have"
                );
            }
        }
    }

    /// The structural half: `guard_before_dispatch` wraps the whole
    /// `generate_handler!` list, so a command that never calls the guard itself is
    /// still refused. If the wrap is removed, this fails.
    #[test]
    fn the_surface_door_wraps_the_registered_handler() {
        let source = include_str!("lib.rs");
        assert!(
            source.contains("plugin_window::guard_before_dispatch("),
            "lib.rs no longer routes its command handler through the surface door"
        );
        assert!(
            source.contains("plugin_window_close"),
            "the walk lost the list it is supposed to read"
        );
    }

    /// The command names the shell registers, read out of `lib.rs` itself.
    fn registered_handler_names() -> Vec<String> {
        let source = include_str!("lib.rs");
        let tail = source
            .split("generate_handler!")
            .nth(1)
            .expect("lib.rs registers a command handler");
        let list = tail.split(']').next().expect("the handler list closes");
        list.split(',')
            .map(|entry| entry.trim().trim_start_matches('['))
            .filter(|entry| !entry.is_empty() && !entry.starts_with("//"))
            .map(|entry| entry.rsplit("::").next().unwrap_or(entry).to_string())
            .collect()
    }

    #[test]
    fn the_workbench_floor_is_its_own_and_nobody_elses() {
        assert_eq!(
            workbench_size_floor(WORKBENCH_LABEL, 155, 168),
            Some(WORKBENCH_MINIMUM)
        );
        assert_eq!(
            workbench_size_floor(WORKBENCH_LABEL, 1280, 800),
            Some((1280, 800))
        );
        // A surface keeps the size its descriptor asked for.
        assert_eq!(
            workbench_size_floor("ephe-plugin-acme-countdown", 360, 240),
            None
        );
        assert_eq!(workbench_size_floor("some-other-window", 155, 168), None);
    }

    #[test]
    fn a_hidden_workbench_answers_the_dock() {
        // Once the miniaturize animation settles, AppKit reports the window as
        // not visible, so this one bit covers that state. On screen stays put.
        assert!(workbench_needs_reveal(false));
        assert!(!workbench_needs_reveal(true));
    }

    #[test]
    fn the_dock_click_is_decided_here_and_asked_of_the_workbench_only() {
        let source = include_str!("lib.rs");
        assert!(
            source.contains("workbench_needs_reveal("),
            "lib.rs answers the Dock click with a rule of its own again"
        );
        assert!(
            !source.contains("is_minimized"),
            "the Dock path reads a flag that cannot change its answer"
        );
        assert!(
            source.contains("isMiniaturized"),
            "the measured reason for leaving that flag unread has to stay beside the call"
        );
        assert!(
            !source.contains(".has_visible_windows("),
            "the counted-every-window predicate is called again"
        );
    }

    #[test]
    fn the_refusal_says_the_rule_and_nothing_else() {
        assert!(!REFUSAL_FROM_A_SURFACE.contains(PLUGIN_LABEL_PREFIX));
        assert!(!REFUSAL_FROM_A_SURFACE.contains("main"));
    }

    #[test]
    fn a_size_is_clamped_to_the_ceilings_the_validator_states() {
        assert_eq!(clamp_dimension(4097, DEFAULT_UI.0), MAX_UI_DIMENSION);
        assert_eq!(
            clamp_dimension(MAX_UI_DIMENSION, DEFAULT_UI.0),
            MAX_UI_DIMENSION
        );
        assert_eq!(clamp_dimension(360, DEFAULT_UI.0), 360);
        assert_eq!(clamp_dimension(1, DEFAULT_UI.0), 1);
        assert_eq!(clamp_dimension(0, DEFAULT_UI.0), DEFAULT_UI.0);
    }

    #[test]
    fn a_transparent_descriptor_gets_an_undecorated_window() {
        let mut descriptor = descriptor();
        descriptor.transparent = true;
        let built = plan("ephe-plugin-acme-countdown".to_string(), &descriptor);
        assert!(built.transparent || !platform_honours_transparency());
        assert_eq!(built.decorations, !built.transparent);
        assert!(built.note.is_empty() || built.note.starts_with("transparency refused"));
    }

    #[test]
    fn a_refused_transparency_says_so_and_stays_decorated() {
        // The branch a platform without a provable compositor takes. Both
        // directions are asserted here, so the fallback cannot be silent on the
        // platform this lane runs on.
        let mut descriptor = descriptor();
        descriptor.transparent = true;
        let built = plan("ephe-plugin-x".to_string(), &descriptor);
        if platform_honours_transparency() {
            assert!(built.transparent);
            assert!(built.note.is_empty());
        } else {
            assert!(!built.transparent);
            assert!(built.decorations);
            assert!(built.note.contains("transparency refused"));
        }
    }

    #[test]
    fn a_descriptor_without_size_or_title_falls_back_to_the_contracts_own() {
        let empty = SurfaceDescriptor::default();
        let built = plan("ephe-plugin-x".to_string(), &empty);
        assert_eq!((built.width, built.height), default_ui_size());
        assert_eq!(built.title, "ephe-plugin-x");
        assert!(!built.always_on_top);
    }

    #[test]
    fn always_on_top_comes_from_the_descriptor_and_nothing_else() {
        let mut descriptor = descriptor();
        descriptor.always_on_top = true;
        assert!(plan("ephe-plugin-x".to_string(), &descriptor).always_on_top);
    }

    #[test]
    fn only_the_surface_route_loads() {
        assert!(is_surface_url(&url(
            "/api/plugins/ui/acme-countdown/n0nce/"
        )));
        assert!(is_surface_url(&url("/api/plugins/ui/acme-countdown/")));
        assert!(!is_surface_url(&url("/api/settings")));
        assert!(!is_surface_url(&url("/api/plugins")));
        assert!(!is_surface_url(
            &"https://evil.example/api/plugins/ui/a/"
                .parse()
                .expect("url")
        ));
        assert!(!is_surface_url(
            &"file:///etc/passwd".parse::<Url>().expect("url")
        ));
    }

    #[test]
    fn the_url_has_to_name_the_plugin_it_mounts() {
        assert!(surface_url_for_plugin(
            &url("/api/plugins/ui/acme-countdown/n0nce/"),
            "acme-countdown"
        ));
        assert!(!surface_url_for_plugin(
            &url("/api/plugins/ui/other-countdown/n0nce/"),
            "acme-countdown"
        ));
    }

    #[test]
    fn a_long_title_is_cut_where_a_titlebar_cuts_it() {
        let mut descriptor = descriptor();
        descriptor.title = "u".repeat(MAX_UI_TITLE_CHARS + 40);
        let built = plan("ephe-plugin-x".to_string(), &descriptor);
        assert_eq!(built.title.chars().count(), MAX_UI_TITLE_CHARS);
    }

    #[test]
    fn only_a_floating_window_has_a_native_window_here() {
        assert!(surface_type_is_native(&descriptor()));
        for other in ["dock-panel", "canvas-overlay", ""] {
            let mut descriptor = descriptor();
            descriptor.surface_type = other.to_string();
            assert!(!surface_type_is_native(&descriptor), "{other} is #44");
        }
    }
}
