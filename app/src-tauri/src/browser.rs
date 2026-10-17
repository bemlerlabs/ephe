//! Ephe — the real browser pane (W1)
//!
//! The URL pane in the agent panel was an `<iframe>`. That is enough for own
//! dev servers, but pages sending `X-Frame-Options`/`frame-ancestors`
//! (google.com, github.com, …) paint a white box into a surface that just
//! reported "done". This module loads the page as a **child WebView** over the
//! pane's frame area — real engine, real history, real load events.
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

use std::process::Stdio;

use tauri::{AppHandle, Emitter, Manager, Position, Rect, Size};

/// Label of the child WebView — deliberately not "main", so events sent to
/// `emit_to("main", …)` do not land on the loaded webpage.
const BROWSER_LABEL: &str = "ephe-browser";
const MAIN_LABEL: &str = "main";

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

/// Opens (or navigates) the address in the main window's child WebView.
///
/// `async` because `Window::add_child` blocks the main thread until the WebView
/// exists: in a sync command that would be a deadlock on macOS.
#[tauri::command]
pub async fn browser_open(app: AppHandle, url: String, bounds: Bounds) -> Result<(), String> {
    let parsed: tauri::Url = url
        .parse()
        .map_err(|e| format!("Ungültige Adresse {url}: {e}"))?;
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
        // IPC bridge to every WebView globally (withGlobalTauri) — a loaded page
        // must not find it, or it can quit Ephe or reposition the pane. Its own
        // initialization script is the only edge this pane has.
        .initialization_script(
            "for (const k of ['__TAURI__','__TAURI_INTERNALS__','__TAURI_METADATA__']) { try { delete window[k] } catch (e) { try { window[k] = undefined } catch (e2) {} } }",
        )
        .on_navigation({
            let app = app.clone();
            move |url| {
                report(
                    &app,
                    "browser:navigation",
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
                    "browser:load",
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
                    "browser:title",
                    serde_json::json!({ "title": title }),
                );
            }
        })
        // target="_blank" must not spawn a second window nobody controls: the
        // address comes back into the pane and the user decides there.
        .on_new_window({
            let app = app.clone();
            move |url, _features| {
                report(
                    &app,
                    "browser:new-window",
                    serde_json::json!({ "url": url.as_str() }),
                );
                tauri::webview::NewWindowResponse::Deny
            }
        });

    if cfg!(debug_assertions) {
        builder = builder.devtools(true);
    }

    window
        .add_child(builder, tauri::LogicalPosition::new(bounds.x, bounds.y), tauri::LogicalSize::new(bounds.width, bounds.height))
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub async fn browser_bounds(app: AppHandle, bounds: Bounds) -> Result<(), String> {
    if let Some(webview) = app.get_webview(BROWSER_LABEL) {
        webview
            .set_bounds(rect(bounds))
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Show/hide without destroy — the page state (scroll position, form input)
/// survives when the tab is only away for a moment.
#[tauri::command]
pub async fn browser_visible(app: AppHandle, visible: bool) -> Result<(), String> {
    if let Some(webview) = app.get_webview(BROWSER_LABEL) {
        if visible {
            webview.show().map_err(|e| e.to_string())?;
        } else {
            webview.hide().map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

/// History of the child WebView. `eval` is honest here: it is the history of
/// exactly this frame, not of the Ephe window.
#[tauri::command]
pub async fn browser_history(app: AppHandle, action: String) -> Result<(), String> {
    let js = match action.as_str() {
        "back" => "window.history.back()",
        "forward" => "window.history.forward()",
        "reload" => "window.location.reload()",
        other => return Err(format!("unbekanntes Historie-Kommando {other}")),
    };
    let webview = app
        .get_webview(BROWSER_LABEL)
        .ok_or_else(|| "Browser-Pane ist nicht geöffnet".to_string())?;
    webview.eval(js).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn browser_close(app: AppHandle) -> Result<(), String> {
    if let Some(webview) = app.get_webview(BROWSER_LABEL) {
        webview.close().map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// "Open in browser" — inside the shell `window.open` is no way out, so the
/// call goes through the operating system.
#[tauri::command]
pub async fn browser_open_external(url: String) -> Result<(), String> {
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

