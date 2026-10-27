//! N3/N4 — the two native gestures the WebView cannot make itself.
//!
//! A typed clipboard write (`text/plain` plus `text/html`) and the Finder verbs on
//! a file the user already owns. Both receive their payload from the page, so both
//! are fenced here rather than trusted: the clipboard by a hard byte cap, the file
//! verbs by canonicalization and an allow-list of roots. The reasons are plain —
//! a WebView page must not be able to hand the shell an arbitrary path to open.
//!
//! The allowed roots are the ones a file from this product actually lives in: the
//! artifact store, the configured project, and the three folders a save dialog
//! usually lands in. A copy saved anywhere else is refused by design; the surface
//! is told so instead of a button that quietly does nothing.

use std::path::{Path, PathBuf};

/// Well above a pasted document, well below a memory fault.
pub const MAX_CLIPBOARD_BYTES: usize = 10 * 1024 * 1024;

/// The payload as it will be written, or the refusal. Checked before the
/// pasteboard is touched, so a refused copy leaves the previous clipboard alone.
pub fn clipboard_bytes(plain: &str, html: Option<&str>) -> Result<usize, String> {
    let total = plain
        .len()
        .saturating_add(html.map(str::len).unwrap_or_default());
    if total > MAX_CLIPBOARD_BYTES {
        return Err(format!(
            "clipboard payload is {total} bytes, above the {MAX_CLIPBOARD_BYTES}-byte cap"
        ));
    }
    Ok(total)
}

/// The roots a file action may reach, given the home directory and the project
/// the shell was configured with.
pub fn allowed_roots(home: &Path, project: Option<&Path>) -> Vec<PathBuf> {
    let mut roots = vec![home.join(".ephe").join("artifacts")];
    for folder in ["Desktop", "Downloads", "Documents"] {
        roots.push(home.join(folder));
    }
    if let Some(project) = project {
        roots.push(project.to_path_buf());
    }
    roots
}

/// Canonicalize a path from the page and prove it is a regular file inside one of
/// the roots. `canonicalize` is what resolves `..` and symlinks, so the fence
/// compares what the file really is, never the text that arrived.
pub fn resolve_allowed_file(raw: &str, roots: &[PathBuf]) -> Result<PathBuf, String> {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return Err("no path was given".to_string());
    }
    let target = std::fs::canonicalize(trimmed)
        .map_err(|_| format!("path does not exist: {trimmed}"))?;
    let resolved_roots: Vec<PathBuf> = roots
        .iter()
        .filter_map(|root| std::fs::canonicalize(root).ok())
        .collect();
    if !resolved_roots.iter().any(|root| target.starts_with(root)) {
        return Err("path is outside the folders Ephe may act on".to_string());
    }
    let meta = std::fs::metadata(&target).map_err(|_| format!("path is unreadable: {trimmed}"))?;
    if !meta.is_file() {
        return Err("path is not a regular file".to_string());
    }
    Ok(target)
}

/// The workspace the shell was configured to run, when `desktop.json` names one.
#[cfg(unix)]
pub fn configured_project(home: &Path) -> Option<PathBuf> {
    let text = std::fs::read_to_string(crate::backend::konfig_pfad(home)).ok()?;
    Some(crate::backend::befehl_aus(&text, home)?.projekt)
}

/// The roots for this machine. HOME absent means no roots at all, which refuses
/// every path — the same fail-closed answer as a missing configuration.
pub fn default_roots() -> Vec<PathBuf> {
    let Some(home) = std::env::var_os("HOME").map(PathBuf::from) else {
        return Vec::new();
    };
    #[cfg(unix)]
    let project = configured_project(&home);
    #[cfg(not(unix))]
    let project: Option<PathBuf> = None;
    allowed_roots(&home, project.as_deref())
}

#[cfg(target_os = "macos")]
pub fn write_clipboard(plain: &str, html: Option<&str>) -> Result<(), String> {
    use objc2_app_kit::{NSPasteboard, NSPasteboardTypeHTML, NSPasteboardTypeString};
    use objc2_foundation::NSString;

    // The pasteboard types are immutable AppKit framework constants; reading an
    // `extern static` is the one unsafe step here.
    let (text_type, html_type) = unsafe { (NSPasteboardTypeString, NSPasteboardTypeHTML) };

    let pasteboard = NSPasteboard::generalPasteboard();
    pasteboard.clearContents();
    let plain_text = NSString::from_str(plain);
    if !pasteboard.setString_forType(&plain_text, text_type) {
        return Err("the clipboard refused the plain text".to_string());
    }
    if let Some(html) = html {
        let html_text = NSString::from_str(html);
        if !pasteboard.setString_forType(&html_text, html_type) {
            return Err("the clipboard refused the HTML face".to_string());
        }
    }
    Ok(())
}

#[cfg(not(target_os = "macos"))]
pub fn write_clipboard(_plain: &str, _html: Option<&str>) -> Result<(), String> {
    Err("the typed clipboard is a macOS feature in this build".to_string())
}

/// The dock badge is a short label beside the icon; a page cannot write more.
pub const MAX_BADGE_CHARS: usize = 12;

/// `None` clears the badge, a short label sets it, anything longer is refused.
pub fn dock_badge(label: &str) -> Result<Option<String>, String> {
    let trimmed = label.trim();
    if trimmed.is_empty() {
        return Ok(None);
    }
    if trimmed.chars().count() > MAX_BADGE_CHARS {
        return Err(format!(
            "badge label is longer than {MAX_BADGE_CHARS} characters"
        ));
    }
    Ok(Some(trimmed.to_string()))
}

/// A dock progress value in 0..=100, rounded; `None` clears the bar. A value
/// outside the range is a caller bug and comes back as a refusal, not a clamp:
/// a bar that quietly shows 100 % for 180 % is a measurement nobody can trust.
pub fn dock_progress(percent: Option<f64>) -> Result<Option<u64>, String> {
    match percent {
        None => Ok(None),
        Some(value) if value.is_finite() && (0.0..=100.0).contains(&value) => {
            Ok(Some(value.round() as u64))
        }
        Some(_) => Err("dock progress must be between 0 and 100".to_string()),
    }
}

/// N5: open the file in the Quick Look panel. `qlmanage -p` runs detached: the
/// command returns once the panel process exists, so the event loop is never
/// held while a person reads the preview.
#[cfg(target_os = "macos")]
pub fn quick_look(path: &Path) -> Result<(), String> {
    std::process::Command::new("/usr/bin/qlmanage")
        .arg("-p")
        .arg(path)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .map(|_child| ())
        .map_err(|error| format!("Quick Look was not reachable: {error}"))
}

#[cfg(not(target_os = "macos"))]
pub fn quick_look(_path: &Path) -> Result<(), String> {
    Err("Quick Look is a macOS feature in this build".to_string())
}

/// Show the file in its folder. `-R` selects rather than launches it.
#[cfg(target_os = "macos")]
pub fn reveal(path: &Path) -> Result<(), String> {
    run_open(true, path)
}

/// Open the file with whatever the user set as its default application.
#[cfg(target_os = "macos")]
pub fn open_default(path: &Path) -> Result<(), String> {
    run_open(false, path)
}

#[cfg(target_os = "macos")]
fn run_open(select: bool, path: &Path) -> Result<(), String> {
    let mut command = std::process::Command::new("/usr/bin/open");
    if select {
        command.arg("-R");
    }
    let status = command
        .arg(path)
        .status()
        .map_err(|error| format!("Finder was not reachable: {error}"))?;
    if status.success() {
        Ok(())
    } else {
        Err("Finder refused the request".to_string())
    }
}

#[cfg(not(target_os = "macos"))]
pub fn reveal(_path: &Path) -> Result<(), String> {
    Err("the Finder verbs are a macOS feature in this build".to_string())
}

#[cfg(not(target_os = "macos"))]
pub fn open_default(_path: &Path) -> Result<(), String> {
    Err("the Finder verbs are a macOS feature in this build".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU32, Ordering};

    static NEXT: AtomicU32 = AtomicU32::new(0);

    /// A fresh directory per test, removed by `Scratch` on drop.
    struct Scratch(PathBuf);

    impl Scratch {
        fn new() -> Self {
            let n = NEXT.fetch_add(1, Ordering::Relaxed);
            let dir = std::env::temp_dir().join(format!(
                "ephe-desktop-test-{}-{n}",
                std::process::id()
            ));
            std::fs::create_dir_all(&dir).expect("scratch dir");
            Scratch(dir)
        }

        fn file(&self, rel: &str) -> PathBuf {
            let path = self.0.join(rel);
            if let Some(parent) = path.parent() {
                std::fs::create_dir_all(parent).expect("parent");
            }
            std::fs::write(&path, b"x").expect("file");
            path
        }
    }

    impl Drop for Scratch {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn clipboard_cap_counts_both_faces() {
        assert!(clipboard_bytes("hello", None).is_ok());
        assert!(clipboard_bytes("hello", Some("<p>hello</p>")).is_ok());
        let at_cap = "x".repeat(MAX_CLIPBOARD_BYTES);
        assert!(clipboard_bytes(&at_cap, None).is_ok(), "the cap itself is allowed");
        let over = "x".repeat(MAX_CLIPBOARD_BYTES + 1);
        assert!(clipboard_bytes(&over, None).is_err());
        let half = "x".repeat(MAX_CLIPBOARD_BYTES / 2 + 1);
        assert!(clipboard_bytes(&half, Some(&half)).is_err());
    }

    #[test]
    fn a_file_inside_a_root_is_allowed() {
        let scratch = Scratch::new();
        let root = scratch.0.join("artifacts");
        let file = scratch.file("artifacts/report.md");

        let resolved = resolve_allowed_file(file.to_str().unwrap(), &[root]).expect("allowed");
        assert!(resolved.ends_with("report.md"));
    }

    #[test]
    fn a_file_outside_the_roots_is_refused() {
        let scratch = Scratch::new();
        let root = scratch.0.join("artifacts");
        std::fs::create_dir_all(&root).unwrap();
        let outside = scratch.file("elsewhere/secret.txt");

        let error = resolve_allowed_file(outside.to_str().unwrap(), &[root]).unwrap_err();
        assert!(error.contains("outside"), "{error}");
    }

    #[test]
    fn traversal_and_symlinks_resolve_before_the_fence() {
        let scratch = Scratch::new();
        let root = scratch.0.join("artifacts");
        std::fs::create_dir_all(&root).unwrap();
        let outside = scratch.file("elsewhere/secret.txt");
        let link = root.join("link.txt");
        std::os::unix::fs::symlink(&outside, &link).unwrap();

        // `..` inside an allowed root still names a file outside it.
        let sneaky = format!("{}/../elsewhere/secret.txt", root.display());
        assert!(resolve_allowed_file(&sneaky, &[root.clone()]).is_err());
        assert!(resolve_allowed_file(link.to_str().unwrap(), &[root]).is_err());
    }

    #[test]
    fn a_directory_is_not_a_file_action() {
        let scratch = Scratch::new();
        let root = scratch.0.join("artifacts");
        let directory = root.join("folder");
        std::fs::create_dir_all(&directory).unwrap();

        let error = resolve_allowed_file(directory.to_str().unwrap(), &[root]).unwrap_err();
        assert!(error.contains("regular file"), "{error}");
    }

    #[test]
    fn a_missing_path_is_refused() {
        let scratch = Scratch::new();
        let root = scratch.0.join("artifacts");
        std::fs::create_dir_all(&root).unwrap();
        let missing = root.join("never-written.md");

        assert!(resolve_allowed_file(missing.to_str().unwrap(), &[root]).is_err());
        assert!(resolve_allowed_file("   ", &[]).is_err());
    }

    #[test]
    fn dock_badge_takes_a_short_label_and_clears_on_empty() {
        assert_eq!(dock_badge("").unwrap(), None);
        assert_eq!(dock_badge("   ").unwrap(), None);
        assert_eq!(dock_badge(" 2/5 ").unwrap().as_deref(), Some("2/5"));
        assert_eq!(dock_badge("●").unwrap().as_deref(), Some("●"));
        assert!(dock_badge(&"x".repeat(MAX_BADGE_CHARS + 1)).is_err());
    }

    #[test]
    fn dock_progress_refuses_values_outside_the_scale() {
        assert_eq!(dock_progress(None).unwrap(), None);
        assert_eq!(dock_progress(Some(0.0)).unwrap(), Some(0));
        assert_eq!(dock_progress(Some(42.6)).unwrap(), Some(43));
        assert_eq!(dock_progress(Some(100.0)).unwrap(), Some(100));
        assert!(dock_progress(Some(100.5)).is_err());
        assert!(dock_progress(Some(-1.0)).is_err());
        assert!(dock_progress(Some(f64::NAN)).is_err());
        assert!(dock_progress(Some(f64::INFINITY)).is_err());
    }

    #[test]
    fn quick_look_is_fenced_like_every_other_file_verb() {
        let scratch = Scratch::new();
        let root = scratch.0.join("artifacts");
        std::fs::create_dir_all(&root).unwrap();
        let outside = scratch.file("elsewhere/secret.txt");
        assert!(resolve_allowed_file(outside.to_str().unwrap(), &[root]).is_err());
    }

    #[test]
    fn roots_name_the_store_the_project_and_the_save_folders() {
        let home = Path::new("/Users/someone");
        let project = Path::new("/Users/someone/work/ephe");
        let roots = allowed_roots(home, Some(project));

        assert_eq!(
            roots,
            vec![
                home.join(".ephe/artifacts"),
                home.join("Desktop"),
                home.join("Downloads"),
                home.join("Documents"),
                project.to_path_buf(),
            ]
        );
        assert_eq!(allowed_roots(home, None).len(), 4);
    }
}
