//! The shell's own run ledger: one line when it starts, one when it ends on a
//! path it controls.
//!
//! A release build registers no logger — `lib.rs` installs `tauri_plugin_log`
//! only under `cfg!(debug_assertions)` — so when the window vanished twice on
//! 2026-11-02 there was nothing to read afterwards: no crash report, nothing in
//! the system log, and the shell's note file last written the day before. The
//! ledger answers the one question a user asks after that: did the shell end
//! through a path it owns, or did something else end it?
//!
//! `start` with no matching `exit` is the answer, and it is an answer only
//! because both lines are written by the same small function.

use std::fs::OpenOptions;
use std::io::Write;
use std::path::Path;

/// What the ledger can say about the most recent run in a file's text.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LastRun {
    /// Nothing was ever recorded.
    Empty,
    /// The shell started and never reached an exit it controls.
    Open,
    /// The shell started and ended through one of its own quit paths.
    Ended,
}

/// One ledger line, built apart from the file so it can be read back apart too.
pub fn line(kind: &str, version: &str, pid: u32, epoch_s: u64) -> String {
    format!("{kind} ephe {version} pid {pid} epoch {epoch_s}")
}

/// The kind of the newest ledger line, ignoring every line the writer did not make.
///
/// One pass, so the newest line keeps the authority: an exit after a start ends
/// the run, and a start after an exit begins the next one.
pub fn last_run(text: &str) -> LastRun {
    let mut state = LastRun::Empty;
    for raw in text.lines() {
        if raw.starts_with("start ephe ") {
            state = LastRun::Open;
        } else if raw.starts_with("exit ephe ") {
            state = LastRun::Ended;
        }
    }
    state
}

/// Append one line to the file the shell owns. A ledger that cannot be written
/// stays silent: it must never be the reason a start fails.
pub fn write(home: &Path, text: &str) {
    let path = home.join(".ephe").join("logs").join("desktop.log");
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(&path) {
        let _ = writeln!(file, "{text}");
    }
}

/// The line for a moment the shell is living through: its own version and pid.
pub fn note(home: &Path, kind: &str) {
    let epoch = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or_default();
    write(home, &line(kind, env!("CARGO_PKG_VERSION"), std::process::id(), epoch));
}

/// The same line for a caller with no home in hand. A machine without `HOME`
/// gets no ledger, which is the same answer the rest of the shell gives there.
pub fn note_here(kind: &str) {
    let Some(home) = std::env::var_os("HOME").map(std::path::PathBuf::from) else {
        return;
    };
    note(&home, kind);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_line_names_the_kind_the_version_the_pid_and_the_clock() {
        assert_eq!(
            line("start", "0.5.3", 6825, 1793629987),
            "start ephe 0.5.3 pid 6825 epoch 1793629987"
        );
    }

    #[test]
    fn a_start_that_never_reached_an_exit_is_named_as_open() {
        let text = "start ephe 0.5.3 pid 6825 epoch 1\nport 8765 answered, but not as an Ephe backend\n";
        assert_eq!(last_run(text), LastRun::Open);
    }

    #[test]
    fn an_exit_after_that_start_closes_the_run() {
        let text = "start ephe 0.5.3 pid 6825 epoch 1\nexit ephe 0.5.3 pid 6825 epoch 9\n";
        assert_eq!(last_run(text), LastRun::Ended);
    }

    #[test]
    fn the_next_start_reopens_it_whatever_came_before() {
        let text = "exit ephe 0.5.2 pid 1 epoch 1\nstart ephe 0.5.3 pid 2 epoch 2\n";
        assert_eq!(last_run(text), LastRun::Open);
    }

    #[test]
    fn a_file_with_nothing_of_ours_in_it_says_nothing() {
        assert_eq!(last_run(""), LastRun::Empty);
        assert_eq!(last_run("backend parity mismatch\n"), LastRun::Empty);
    }

    #[test]
    fn the_ledger_creates_the_directory_it_writes_into() {
        let dir = std::env::temp_dir().join(format!("ephe-runlog-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        write(&dir, &line("start", "0.0.0", 1, 2));
        let text = std::fs::read_to_string(dir.join(".ephe/logs/desktop.log")).expect("a ledger");
        assert!(text.contains("start ephe 0.0.0"), "{text}");
        assert_eq!(last_run(&text), LastRun::Open);
        let _ = std::fs::remove_dir_all(&dir);
    }
}
