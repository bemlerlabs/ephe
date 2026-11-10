//! Ephe — the real browser pane (W1)
//!
//! The URL pane in the agent panel was an `<iframe>`. That is enough for own
//! dev servers, but pages that send `X-Frame-Options`/`frame-ancestors` paint a
//! white box into a surface that just reported "done". This module loads the page
//! as a **child WebView** over the pane's frame area — real engine, real history,
//! real load events.
//!
//! Tauri's multi-WebView API sits behind the `unstable` feature (visibility
//! only, no behaviour change in the rest of the shell), so it is contained
//! here: the frontend speaks only these six commands, and only `browser_open`
//! creates anything.
//!
//! Synchronisation: a child WebView knows no CSS. The frontend reports its
//! frame through a `ResizeObserver` in logical pixels (`browser_bounds`) and
//! hides the surface (`browser_visible`) while an overlay (dialog, menu,
//! palette) would sit on top of it or the tab is not showing.
//!
//! ## What this pane is: a window onto pages nobody here wrote
//!
//! Two doors put a document in it, and both read the one allowlist in
//! [`pane_allows`] — the same rule at both, so an address cannot reach the pane by
//! a path the other door happens to check.
//!
//!   1. `browser_open` — an address handed over as a command argument. The agent
//!      panel and the workbench reach it, and the surface also feeds it the address
//!      a loaded page asked `target="_blank"` for (see `on_new_window` below and
//!      `useNativeBrowserPane.ts:139`), so a page can put words in this door
//!      without holding a command of its own.
//!   2. `on_navigation` — every navigation the loaded page asks for, in **any**
//!      frame. Measured 2026-11-05 on the shipped engine class: this callback is
//!      asked about the main frame, about an `<iframe src>`, and about the
//!      `about:blank`, `about:srcdoc`, `blob:` and `data:` documents a page builds
//!      for its own frames.
//!
//! The allowlist is http and https, plus the inert documents a page makes out of
//! its own memory (`about:blank`, `about:srcdoc`, `blob:`, `data:`). Everything
//! else is refused, and the refusals are the point: `file:` (host content),
//! `javascript:`, `mailto:`/`tel:` (a navigation that hands a scheme to the
//! operating system), and every scheme the shell registers itself — `tauri:`,
//! `ipc:`, `asset:`. An `http(s)` address whose host is one of the engine's own
//! `*.localhost` origins is refused too, because that is where the shell's
//! remote-context rule stops protecting this surface — see the note under the
//! strip.
//!
//! Loopback `http(s)` — a dev server on `localhost`, the backend on
//! `127.0.0.1:8765` — is taken by this rule exactly as `previewUrl.ts`
//! (`paneMode('site')`) and the CSP in `tauri.conf.json` (which lists
//! `http://127.0.0.1:8765` and `http://localhost:8765` among the origins the app
//! itself serves) already treat it. One rule, not a second one. The surface still
//! routes a loopback address to the iframe (`usesNativeBrowser` in
//! `nativeBrowser.ts`), so this is permission at the door, not a new path.
//!
//! A refused address is a visible state, never a silent cancel: both doors emit
//! [`EVENT_REFUSED`] on the pane's existing `browser:` channel with the address,
//! its scheme and a stable reason code, and the command door returns that code to
//! its caller as well. The wording belongs to the surface; the shell ships codes.
//!
//! ## The bridge strip, and what it is worth (task #70 answered)
//!
//! The pane deletes the global bridge from every document it shows, and now does
//! it through `initialization_script_for_all_frames` — the all-frames hook, not
//! the main-frame-only one. The widening is right (the shell's own API note for
//! the main-frame hook says that on the other engine every init script reaches
//! subframes, so a third-party iframe there really is handed the bridge, and the
//! strip was never running in the frames that had it) — but it does **not** close
//! the door, and saying so plainly is the answer to #70:
//!
//!   * `window.__TAURI__` does go. The injected global bundle ends in a plain
//!     assignment (`window.__TAURI__ = <module>`), which is writable and
//!     configurable, so `delete` removes it. Measured: `typeof __TAURI__` is
//!     `undefined` after the strip, in every frame that ran it.
//!   * `window.__TAURI_INTERNALS__` never goes, in any frame. The shell installs it
//!     with `Object.defineProperty(window, '__TAURI_INTERNALS__', { value: … })`,
//!     and a data descriptor with only `value` set is `writable: false` *and*
//!     `configurable: false` by default. So `delete` returns false, the fallback
//!     assignment is ignored outside strict mode, and the members the same scripts
//!     hang off it (`invoke`, `ipc`, `postMessage`, `metadata`,
//!     `transformCallback`) are `defineProperty`'d the same way. Name deletion —
//!     the strip's only tool — cannot work against it. Measured 2026-11-05 in a
//!     harness on the shipped engine class (the same embedding library over the
//!     system web view), with the shell's own init statements and script order:
//!     `delete_returned=false`, `still_there_after_delete=true`, and that frame
//!     then posted a real invoke through `__TAURI_INTERNALS__.invoke` which arrived
//!     in Rust carrying the run's invoke key. In the frame shape where the bridge
//!     reaches subframes — the one the main-frame-only strip left untouched — the
//!     sub frame reported the same object with `invoke` present and posted one too.
//!   * `window.__TAURI_METADATA__` is a name this shell never sets (its metadata
//!     lives at `__TAURI_INTERNALS__.metadata`); it is in the list for historical
//!     reasons and deleting it is a no-op.
//!
//! So the strip is coverage for the frames only the other engine hands a bridge
//! to, and decoration on the frame that has one. What confines an invoke out of a
//! loaded page is three things, and two of them are in this file:
//!
//!   * the engine's remote-context rule: a document that is not the shell's own
//!     origin gets no command unless a `remote` capability names it, and no
//!     capability in `capabilities/` lists `ephe-browser`. That is the refusal the
//!     W1-3 live report observed on the wire from this pane, and it is also why the
//!     navigation allowlist matters: a page can walk the pane into a local context
//!     where the rule stops applying, and measured, it did — `location.href` to a
//!     scheme the app registers navigated the pane while door two still said true.
//!   * [`pane_caller`] — these commands now read the calling webview's own label,
//!     through the same one-entry allow-list the surface layer uses
//!     (`plugin_window_options::caller_is_allowed`), so a document that ever does
//!     land in a local context inside this pane cannot drive the pane's own doors
//!     (`browser_open`, `browser_bounds`, `browser_visible`, `browser_history`,
//!     `browser_close`, `browser_open_external`). Those six names sit in the
//!     workbench command set, which is granted to the webview labelled `main`.
//!     This pane's label is outside that grant.
//!   * the scoped channel task #23 asks for — a pane handed exactly the commands it
//!     may use, in place of a global object nobody here can take away.
//!
//! The structural alternative, `SecurityConfig.pattern: { use: "isolation" }`, was
//! evaluated and is **not adopted here** (the verdict is recorded in the commit
//! that widens the strip): this crate does not enable the `isolation` feature, and
//! without it the config value degrades *silently* to `brownfield` (tauri-utils
//! maps `PatternKind::Isolation` to `Brownfield` when the feature is off), so a
//! config-only change would read as adopted and do nothing; it is an app-wide
//! pattern, so it rewires the workbench's own IPC and needs its own iframe build
//! plus a hook script and CSP beside it; and what it isolates is the documents the
//! shell serves, which is not the document in this pane. Verdict: later, and for
//! the workbench — never as this pane's boundary.
//!
//! ## Manual step, for a reader who wants the shipped shell rather than the harness
//!
//! Nothing in this tree can read back what the engine enforces from the inside
//! (W1-3 says the same), so the end-to-end check is run by hand:
//!
//!   1. `pnpm tauri build --debug --bundles app`, then launch
//!      `target/debug/bundle/macos/Ephe.app` with `HOME` **and** `EPHE_CONFIG_DIR`
//!      pointed at a scratch tree (state files follow `EPHE_CONFIG_DIR`;
//!      Desktop, Downloads and Documents stay under `HOME`).
//!   2. Open the pane on any http page, then in the workbench's own inspector call
//!      `window.__TAURI__.core.invoke('browser_open', {url:'file:///etc/hosts',
//!      bounds:{x:80,y:80,width:700,height:500}})`. Before this commit the pane
//!      paints the host file and reports its address on `browser:navigation`; now
//!      the invoke rejects with `scheme-not-allowed`, the pane stays on the page it
//!      was showing, and a `browser:refused` payload names the address it would not
//!      take.
//!   3. From the loaded page's own console run
//!      `window.__TAURI_INTERNALS__.invoke('browser_visible', {visible:false})`: it
//!      survives the strip (that is #70) and the engine refuses it as a remote
//!      context — the message is dropped for its invoke key or refused by the ACL,
//!      and [`pane_caller`] would refuse it a third time.
//!   4. Load a page with a third-party iframe and read, in that frame's own
//!      inspector context, `typeof window.__TAURI__`: `undefined` in every frame
//!      now, not only in the main one.

use std::process::Stdio;

use tauri::{AppHandle, Emitter, Manager, Position, Rect, Size};

use crate::plugin_window_options::{caller_is_allowed, WORKBENCH_LABEL};
use crate::runlog;

/// Label of the child WebView — deliberately not "main", so events sent to
/// `emit_to("main", …)` do not land on the loaded webpage, and so the workbench
/// window stops answering a `WebviewWindow` handle (see `lib.rs::main_window`).
pub(crate) const BROWSER_LABEL: &str = "ephe-browser";
const MAIN_LABEL: &str = "main";

/// The pane's event channel; `nativeBrowser.ts` subscribes to every name here.
const EVENT_NAVIGATION: &str = "browser:navigation";
const EVENT_LOAD: &str = "browser:load";
const EVENT_TITLE: &str = "browser:title";
const EVENT_NEW_WINDOW: &str = "browser:new-window";
/// An address the pane refused. The surface shows this — a silent cancel is not a
/// state anyone can act on.
pub(crate) const EVENT_REFUSED: &str = "browser:refused";

/// The bridge the shell hands every webview globally (`withGlobalTauri`). A loaded
/// page is code nobody here wrote, so the names go. Only `__TAURI__` actually
/// leaves — the module note says why, and what confines an invoke instead.
const STRIP_GLOBAL_BRIDGE: &str = "for (const k of ['__TAURI__','__TAURI_INTERNALS__','__TAURI_METADATA__']) { try { delete window[k] } catch (e) { try { window[k] = undefined } catch (e2) {} } }";

#[derive(Debug, Clone, Copy, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Bounds {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

fn rect(bounds: Bounds) -> Rect {
    Rect {
        position: Position::Logical(tauri::LogicalPosition::new(bounds.x, bounds.y)),
        size: Size::Logical(tauri::LogicalSize::new(bounds.width, bounds.height)),
    }
}

fn report(app: &AppHandle, event: &str, payload: serde_json::Value) {
    let _ = app.emit_to(MAIN_LABEL, event, payload);
}

/// Why the pane will not show an address. The code is what travels to the surface;
/// the wording belongs to the surface, not to the shell.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Refusal {
    /// A scheme the pane never loads: host content, an operating-system handler, a
    /// scheme the shell registers itself.
    Scheme,
    /// An `http(s)` address that is one of the engine's own origins (`*.localhost`),
    /// where the shell's remote-context rule stops applying to this document.
    AppOwnOrigin,
}

impl Refusal {
    /// The stable code on `browser:refused` and in the command's own error.
    pub(crate) fn code(self) -> &'static str {
        match self {
            Refusal::Scheme => "scheme-not-allowed",
            Refusal::AppOwnOrigin => "app-own-origin",
        }
    }
}

/// The pane's one allowlist, read by both doors: the address handed to
/// `browser_open` and every navigation a loaded page asks for, in any frame.
pub(crate) fn pane_allows(url: &tauri::Url) -> Result<(), Refusal> {
    match url.scheme() {
        "http" | "https" => allow_public_origin(url.host_str()),
        // The inert documents a page builds for its own frames. This callback is
        // asked about every one of them, and they hold no content and no origin of
        // their own — refusing them would break pages that do nothing wrong.
        "about" if matches!(url.path(), "blank" | "srcdoc") => Ok(()),
        // A `blob:` document belongs to the origin that made it, so that origin is
        // held to the same rule and cannot borrow its way past it. `blob:null/…` is
        // an opaque-origin document out of the page's own memory.
        "blob" => match url.as_str().strip_prefix("blob:") {
            Some(inner) if inner.starts_with("null/") => Ok(()),
            Some(inner) => match tauri::Url::parse(inner) {
                Ok(origin) if matches!(origin.scheme(), "http" | "https") => {
                    allow_public_origin(origin.host_str())
                }
                _ => Err(Refusal::Scheme),
            },
            None => Err(Refusal::Scheme),
        },
        "data" => Ok(()),
        _ => Err(Refusal::Scheme),
    }
}

/// `http` and `https` are the web's own schemes, and every loopback origin the app
/// serves is one of them. What is taken back out is the engine's own surface: on
/// the platforms that spell their handlers as http hosts, `http://ipc.localhost`
/// and `http://tauri.localhost` are the shell's own origins, and a document there
/// is no longer a remote context.
fn allow_public_origin(host: Option<&str>) -> Result<(), Refusal> {
    if host
        .map(|host| host.to_ascii_lowercase().ends_with(".localhost"))
        .unwrap_or(false)
    {
        return Err(Refusal::AppOwnOrigin);
    }
    Ok(())
}

/// The refusal as the surface is given it: an event at both doors, and the
/// command's own error at door one.
fn refusal_message(url: &tauri::Url, refusal: Refusal) -> String {
    format!(
        "the browser pane will not load {} — {}",
        url.as_str(),
        refusal.code()
    )
}

fn report_refusal(app: &AppHandle, url: &tauri::Url, refusal: Refusal) {
    report(
        app,
        EVENT_REFUSED,
        serde_json::json!({
            "url": url.as_str(),
            "scheme": url.scheme(),
            "reason": refusal.code(),
        }),
    );
}

/// Who may drive the pane: the workbench's webview, read from the calling
/// webview's own label — not from a label the caller names, and not from its
/// window. This pane is a child webview **of** `main`, so a window-label read
/// would hand every page the pane shows the workbench's authority. The same
/// one-entry allow-list the surface layer uses, so the two doors cannot drift
/// apart.
fn pane_caller(webview: &tauri::Webview) -> Result<(), String> {
    if caller_is_allowed(webview.label()) {
        return Ok(());
    }
    Err(refusal_for_caller(webview.label()))
}

fn refusal_for_caller(label: &str) -> String {
    log::warn!("webview {label} tried to drive the browser pane");
    runlog::note_here("browser_pane_refused_caller");
    format!("only the workbench webview ({WORKBENCH_LABEL}) drives the browser pane; this call came from {label}")
}

/// Opens (or navigates) the address in the main window's child WebView.
///
/// `async` because `Window::add_child` blocks the main thread until the WebView
/// exists: in a sync command that would be a deadlock on macOS.
#[tauri::command]
pub async fn browser_open(
    app: AppHandle,
    webview: tauri::Webview,
    url: String,
    bounds: Bounds,
) -> Result<(), String> {
    pane_caller(&webview)?;
    let parsed: tauri::Url = url
        .parse()
        .map_err(|e| format!("Ungültige Adresse {url}: {e}"))?;
    // Door one. This address may come from the surface, from a tool result, or from
    // the page's own `target="_blank"` request — it is not ours, so it is not a
    // permission.
    if let Err(refusal) = pane_allows(&parsed) {
        report_refusal(&app, &parsed, refusal);
        return Err(refusal_message(&parsed, refusal));
    }
    let window = app
        .get_window(MAIN_LABEL)
        .ok_or_else(|| "Hauptfenster nicht gefunden".to_string())?;

    if let Some(webview) = app.get_webview(BROWSER_LABEL) {
        webview
            .set_bounds(rect(bounds))
            .map_err(|e| e.to_string())?;
        webview.navigate(parsed).map_err(|e| e.to_string())?;
        webview.show().map_err(|e| e.to_string())?;
        return Ok(());
    }

    let mut builder = tauri::WebviewBuilder::new(BROWSER_LABEL, tauri::WebviewUrl::External(parsed))
        // W1-R3: this surface loads pages nobody here wrote. The shell hands the
        // IPC bridge to every webview globally (withGlobalTauri) — a loaded page must
        // not find it, or it can quit Ephe or reposition the pane.
        //
        // The all-frames hook, because the main-frame-only one never ran in the
        // frames a third-party iframe sits in. What it removes and what it cannot is
        // written out in the module note: name deletion does not take
        // `__TAURI_INTERNALS__` away in any frame, so this strip is coverage and not
        // the boundary — the boundary is the engine's remote-context rule, the
        // allowlist at both doors, and [`pane_caller`] on these commands.
        .initialization_script_for_all_frames(STRIP_GLOBAL_BRIDGE)
        .on_navigation({
            let app = app.clone();
            move |url| {
                // Door two. Returning false cancels the navigation, and a cancelled
                // link has to be a state the surface can show.
                if let Err(refusal) = pane_allows(&url) {
                    report_refusal(&app, &url, refusal);
                    return false;
                }
                report(
                    &app,
                    EVENT_NAVIGATION,
                    serde_json::json!({ "url": url.as_str() }),
                );
                true
            }
        })
        .on_page_load({
            let app = app.clone();
            move |_webview, payload| {
                let started = matches!(payload.event(), tauri::webview::PageLoadEvent::Started);
                report(
                    &app,
                    EVENT_LOAD,
                    serde_json::json!({
                        "phase": if started { "started" } else { "finished" },
                        "url": payload.url().as_str(),
                    }),
                );
            }
        })
        .on_document_title_changed({
            let app = app.clone();
            move |_webview, title| {
                report(
                    &app,
                    EVENT_TITLE,
                    serde_json::json!({ "title": title }),
                );
            }
        })
        // target="_blank" must not spawn a second window nobody controls: the
        // address comes back into the pane and the user decides there. The address is
        // the page's own and the surface hands it straight back to `browser_open`,
        // which is why door one is its guard rather than this callback.
        .on_new_window({
            let app = app.clone();
            move |url, _features| {
                report(
                    &app,
                    EVENT_NEW_WINDOW,
                    serde_json::json!({ "url": url.as_str() }),
                );
                tauri::webview::NewWindowResponse::Deny
            }
        });

    if cfg!(debug_assertions) {
        builder = builder.devtools(true);
    }

    window
        .add_child(
            builder,
            tauri::LogicalPosition::new(bounds.x, bounds.y),
            tauri::LogicalSize::new(bounds.width, bounds.height),
        )
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub async fn browser_bounds(
    app: AppHandle,
    webview: tauri::Webview,
    bounds: Bounds,
) -> Result<(), String> {
    pane_caller(&webview)?;
    if let Some(browser) = app.get_webview(BROWSER_LABEL) {
        browser
            .set_bounds(rect(bounds))
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Show/hide without destroy — the page state (scroll position, form input)
/// survives when the tab is only away for a moment.
#[tauri::command]
pub async fn browser_visible(
    app: AppHandle,
    webview: tauri::Webview,
    visible: bool,
) -> Result<(), String> {
    pane_caller(&webview)?;
    if let Some(browser) = app.get_webview(BROWSER_LABEL) {
        if visible {
            browser.show().map_err(|e| e.to_string())?;
        } else {
            browser.hide().map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

/// History of the child WebView. `eval` is honest here: it is the history of
/// exactly this frame, not of the Ephe window.
#[tauri::command]
pub async fn browser_history(
    app: AppHandle,
    webview: tauri::Webview,
    action: String,
) -> Result<(), String> {
    pane_caller(&webview)?;
    let js = match action.as_str() {
        "back" => "window.history.back()",
        "forward" => "window.history.forward()",
        "reload" => "window.location.reload()",
        other => return Err(format!("unbekanntes Historie-Kommando {other}")),
    };
    let browser = app
        .get_webview(BROWSER_LABEL)
        .ok_or_else(|| "Browser-Pane ist nicht geöffnet".to_string())?;
    browser.eval(js).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn browser_close(app: AppHandle, webview: tauri::Webview) -> Result<(), String> {
    pane_caller(&webview)?;
    if let Some(browser) = app.get_webview(BROWSER_LABEL) {
        browser.close().map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// "Open in browser" — inside the shell `window.open` is no way out, so the
/// call goes through the operating system. A page inside the pane is not the
/// workbench and does not get to hand a scheme to the operating system.
#[tauri::command]
pub async fn browser_open_external(webview: tauri::Webview, url: String) -> Result<(), String> {
    pane_caller(&webview)?;
    let parsed: tauri::Url = url
        .parse()
        .map_err(|e| format!("Ungültige Adresse {url}: {e}"))?;
    let scheme = parsed.scheme();
    if scheme != "http" && scheme != "https" {
        return Err(format!("Nach außen öffnet Ephe nur http(s), nicht {scheme}"));
    }
    let mut cmd = if cfg!(target_os = "macos") {
        let mut c = std::process::Command::new("open");
        c.arg(parsed.as_str());
        c
    } else if cfg!(target_os = "windows") {
        let mut c = std::process::Command::new("cmd");
        c.args(["/C", "start", "", parsed.as_str()]);
        c
    } else {
        let mut c = std::process::Command::new("xdg-open");
        c.arg(parsed.as_str());
        c
    };
    let status = cmd
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map_err(|e| format!("Der System-Browser konnte nicht geöffnet werden: {e}"))?;
    if status.success() {
        Ok(())
    } else {
        Err("Der System-Browser hat die Adresse abgelehnt".to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn url(address: &str) -> tauri::Url {
        tauri::Url::parse(address).expect("the test address parses")
    }

    /// The door this module exists to guard: what the pane may show, decided the
    /// same way for `browser_open`'s argument and for every navigation a loaded page
    /// asks for. Each row is an address, because the scheme is what decides.
    #[test]
    fn the_pane_takes_the_web_and_the_hosts_the_app_serves() {
        for address in [
            "https://example.com/a?b=1#c",
            "http://example.com",
            // Loopback: the set previewUrl.ts's paneMode('site') and the CSP's own
            // served origins already name. Allowed as http(s), not as a second rule.
            "http://127.0.0.1:8765/api/health",
            "http://localhost:5173/#/chat",
            "http://[::1]:8765/x",
            "https://127.0.0.1:8765/x",
        ] {
            assert_eq!(pane_allows(&url(address)), Ok(()), "{address}");
        }
    }

    /// Host content, the operating system's own handlers, the schemes the shell
    /// registers. `file:` is the address the pane reached before this commit —
    /// observed, with the host document painting in the pane.
    #[test]
    fn the_pane_refuses_host_content_and_app_schemes() {
        for address in [
            "file:///etc/hosts",
            "file:///Users/someone/.ssh/id_rsa",
            "javascript:alert(1)",
            "mailto:someone@example.com",
            "tel:1234567",
            "ftp://example.com/x",
            "ws://example.com/socket",
            "view-source:http://example.com",
            "about:config",
            // The shell's own schemes: a document there is not a remote context, so
            // the engine's guard for this pane stops covering it. Measured reachable
            // from a loaded page's `location.href` while door two still said true.
            "tauri://localhost/index.html",
            "ipc://localhost/browser_open",
            "asset://localhost/%2Fetc%2Fhosts",
        ] {
            assert_eq!(
                pane_allows(&url(address)),
                Err(Refusal::Scheme),
                "{address} is not a pane document"
            );
        }
    }

    /// The same engine origins spelled the way the other platforms spell them.
    #[test]
    fn an_engine_origin_is_refused_even_wearing_http() {
        for address in [
            "http://ipc.localhost/browser_open",
            "http://tauri.localhost/index.html",
            "http://asset.localhost/%2Fetc%2Fhosts",
            "https://TAURI.LOCALHOST/index.html",
        ] {
            assert_eq!(
                pane_allows(&url(address)),
                Err(Refusal::AppOwnOrigin),
                "{address}"
            );
        }
    }

    /// A page's own inert frame documents stay loadable. Measured on the shipped
    /// engine class: this callback is asked about every one of them, and refusing
    /// them would break pages that do nothing wrong.
    #[test]
    fn the_inert_documents_a_page_makes_for_itself_are_allowed() {
        for address in [
            "about:blank",
            "about:srcdoc",
            "data:text/html,<h1>hi</h1>",
            "blob:http://127.0.0.1:8947/0da232db-8011-48a2-a281-368a8620a0bf",
            "blob:null/29e62f14-15a0-41df-85b3-81367df8db58",
        ] {
            assert_eq!(pane_allows(&url(address)), Ok(()), "{address}");
        }
    }

    /// A `blob:` document carries the origin that made it, and that origin is held
    /// to the same rule — a page cannot borrow an engine origin by wrapping it.
    #[test]
    fn a_blob_carries_the_origin_that_made_it_and_that_origin_is_checked() {
        assert_eq!(
            pane_allows(&url("blob:tauri://localhost/0da232db")),
            Err(Refusal::Scheme)
        );
        assert_eq!(
            pane_allows(&url("blob:http://ipc.localhost/x")),
            Err(Refusal::AppOwnOrigin)
        );
        assert_eq!(
            pane_allows(&url("blob:file:///etc/hosts")),
            Err(Refusal::Scheme)
        );
    }

    /// The codes are the contract with `nativeBrowser.ts`, which maps codes and
    /// carries no wording; a rename on one side only is a surface that says nothing.
    #[test]
    fn the_refusal_codes_and_the_channel_names_the_surface_listens_on_are_fixed() {
        assert_eq!(Refusal::Scheme.code(), "scheme-not-allowed");
        assert_eq!(Refusal::AppOwnOrigin.code(), "app-own-origin");
        assert_eq!(EVENT_REFUSED, "browser:refused");
        assert_eq!(EVENT_NAVIGATION, "browser:navigation");
        assert_eq!(EVENT_LOAD, "browser:load");
        assert_eq!(EVENT_TITLE, "browser:title");
        assert_eq!(EVENT_NEW_WINDOW, "browser:new-window");
    }

    #[test]
    fn a_refusal_names_the_address_and_the_code() {
        let message = refusal_message(&url("file:///etc/hosts"), Refusal::Scheme);
        assert!(message.contains("file:///etc/hosts"), "{message}");
        assert!(message.contains("scheme-not-allowed"), "{message}");
    }

    /// The pane is a child webview **of** `main`, so its own label has to sit
    /// outside the workbench's authority by name — that is what makes a label read
    /// mean anything. The allow-list has exactly one entry and it is the workbench.
    #[test]
    fn only_the_workbench_webview_drives_the_pane() {
        assert!(caller_is_allowed(WORKBENCH_LABEL));
        assert!(!caller_is_allowed(BROWSER_LABEL));
        assert!(!caller_is_allowed("ephe-plugin-some-surface"));
        assert!(!caller_is_allowed(""));
        let message = refusal_for_caller(BROWSER_LABEL);
        assert!(message.contains(BROWSER_LABEL), "{message}");
        assert!(message.contains(WORKBENCH_LABEL), "{message}");
    }

    /// What the strip runs against. Recorded here so the next reader does not
    /// re-claim what the module note says this hook cannot do.
    #[test]
    fn the_strip_names_the_three_bridge_globals_it_runs_against() {
        for name in ["__TAURI__", "__TAURI_INTERNALS__", "__TAURI_METADATA__"] {
            assert!(STRIP_GLOBAL_BRIDGE.contains(name), "{name}");
        }
    }
}

