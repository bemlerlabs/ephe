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
//! because both lines are written by the same small function. A `restart
//! requested` between them closes the run too: that is the path the update
//! surface walks, and it ends inside tauri rather than in this shell's exit
//! handler.
//!
//! This module also holds the bounds for the files the shell opens under `logs/`:
//! the ledger above and the log the spawned backend writes into. Both are opened
//! through one handle that rotates an oversized file to `<name>.1` and keeps it
//! owner-only.

use std::fs::OpenOptions;
use std::io::Write;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};

/// The shell's own note log does not carry a server's stdout, only the lines written here and by
/// the backend module: measured on this Mac 2026-11-16, 15 365 bytes in 231 lines over the 30
/// days since the file was born, about 512 bytes a day. So the bound is a runaway guard rather
/// than an expectation — a start loop noting every attempt reaches this within days — and the one
/// kept file holds the folder's total at twice the cap.
pub(crate) const DESKTOP_LOG_ROTATE_BYTES: u64 = 1024 * 1024;

/// Move an oversized log to `<name>.1` so the next append opens a fresh file, and say whether
/// it did. A rename rather than a truncation: the lines worth keeping are the ones already
/// written. A rename that cannot happen leaves the append going on in the old file, which is
/// the state before this existed and no reason to refuse to start the app.
pub(crate) fn rotate_if_bigger(log: &Path, cap: u64) -> bool {
    let Ok(meta) = std::fs::metadata(log) else {
        return false;
    };
    if meta.len() < cap {
        return false;
    }
    let previous = PathBuf::from(format!("{}.1", log.display()));
    if std::fs::rename(log, &previous).is_err() {
        return false;
    }
    // The rename carries the old mode along, and an older build left the log at the umask
    // default; a file nobody asked to keep should not be the one the machine shares.
    let _ = std::fs::set_permissions(&previous, std::fs::Permissions::from_mode(0o600));
    true
}

/// An append handle for a log this shell opens: rotated first, owner-only from the first byte.
/// `OpenOptions` alone leaves the mode to the umask, and a log an older build left at 644 stays
/// readable beside the owner through every later `APPEND`.
pub(crate) fn log_handle(log: &Path, cap: u64) -> std::io::Result<std::fs::File> {
    rotate_if_bigger(log, cap);
    let handle = OpenOptions::new().create(true).append(true).open(log)?;
    handle.set_permissions(std::fs::Permissions::from_mode(0o600))?;
    Ok(handle)
}

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
///
/// `restart requested` counts as an end the shell owns. The relaunch path exits
/// through tauri's `request_restart`, which calls `exit(0)` and never reaches
/// `RunEvent::Exit`, so the healthy case — the user pressed `Restart now` and the
/// new version came up — writes that line and no `exit`. Measured on 2026-11-17:
/// a relaunch left `start` and `restart requested` behind, and a reader with the
/// two kinds alone would call the successor's boot an unexplained end.
pub fn last_run(text: &str) -> LastRun {
    let mut state = LastRun::Empty;
    for raw in text.lines() {
        if raw.starts_with("start ephe ") {
            state = LastRun::Open;
        } else if raw.starts_with("exit ephe ") || raw.starts_with("restart requested ephe ") {
            state = LastRun::Ended;
        }
    }
    state
}

/// What the ledger says about the run before this one, from the file on disk.
///
/// A ledger that cannot be read says `Empty`: an unreadable file is not evidence
/// that something went wrong, and the shell has no business alarming anyone over
/// its own note log.
pub fn previous_run(home: &Path) -> LastRun {
    let path = crate::instance::device_dir_for(home)
        .join("logs")
        .join("desktop.log");
    match std::fs::read_to_string(path) {
        Ok(text) => last_run(&text),
        Err(_) => LastRun::Empty,
    }
}

/// Write this run's `start`, and the one line the ledger would otherwise lose.
///
/// The question the module exists to answer is whether the run before this one
/// ended through a path the shell owns. The moment the new `start` is appended,
/// the file can no longer answer it — the classifier reads the newest line and
/// would name *this* run instead. So the reading happens before the writing and
/// the answer lands beside the start it explains:
///
/// ```text
/// start ephe 0.7.0 pid 22329 epoch 1794928867
/// start ephe 0.7.0 pid 76401 epoch 1794950727
/// previous start unmatched ephe 0.7.0 pid 76401 epoch 1794950728
/// ```
///
/// Whether the answer is owed is returned so the caller can act on it; nobody
/// does today, and the ledger is the surface.
pub fn open_run(home: &Path) -> bool {
    let owed = previous_run(home) == LastRun::Open;
    note(home, "start");
    if owed {
        note(home, "previous start unmatched");
    }
    owed
}

/// The same for a shell with no home in hand.
pub fn open_run_here() {
    let Some(home) = std::env::var_os("HOME").map(std::path::PathBuf::from) else {
        return;
    };
    open_run(&home);
}

/// Append one line to the file the shell owns, through the handle that bounds it and keeps it
/// owner-only. A ledger that cannot be written stays silent: it must never be the reason a start
/// fails.
pub fn write(home: &Path, text: &str) {
    let path = crate::instance::device_dir_for(home)
        .join("logs")
        .join("desktop.log");
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Ok(mut file) = log_handle(&path, DESKTOP_LOG_ROTATE_BYTES) {
        let _ = writeln!(file, "{text}");
    }
}

/// The line for a moment the shell is living through: its own version and pid.
pub fn note(home: &Path, kind: &str) {
    write(
        home,
        &line(kind, env!("CARGO_PKG_VERSION"), std::process::id(), stamp()),
    );
}

/// The same line, with the webview the shell turned away named beside it. Refusals are the one
/// kind where the shell's own fields answer nothing: 34 `browser_pane_refused_caller` lines sat
/// in this machine's ledger on 2026-11-17, and not one of them said which caller it refused —
/// the label went to `log::warn!`, which a release build never registers.
pub fn note_caller(home: &Path, kind: &str, caller: &str) {
    write(
        home,
        &caller_line(
            kind,
            env!("CARGO_PKG_VERSION"),
            std::process::id(),
            stamp(),
            caller,
        ),
    );
}

/// The seconds the ledger prints, read once per written line.
fn stamp() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or_default()
}

/// [`line`] plus the one field a refusal needs, so the four fields the ledger is built of keep
/// one home.
fn caller_line(kind: &str, version: &str, pid: u32, epoch_s: u64, caller: &str) -> String {
    format!(
        "{} caller {}",
        line(kind, version, pid, epoch_s),
        tame(caller)
    )
}

/// The characters a webview label is made of, capped. A label arrives from a webview, and the
/// ledger is one line per event: a newline in here would write a second line, and a label opening
/// with `start ` would open a run this shell never started.
fn tame(caller: &str) -> String {
    caller
        .chars()
        .take(64)
        .map(|c| {
            if c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '-') {
                c
            } else {
                '_'
            }
        })
        .collect()
}

/// The same line for a caller with no home in hand. A machine without `HOME`
/// gets no ledger, which is the same answer the rest of the shell gives there.
pub fn note_here(kind: &str) {
    let Some(home) = std::env::var_os("HOME").map(std::path::PathBuf::from) else {
        return;
    };
    note(&home, kind);
}

/// [`note_caller`] for a caller with no home in hand.
pub fn note_caller_here(kind: &str, caller: &str) {
    let Some(home) = std::env::var_os("HOME").map(std::path::PathBuf::from) else {
        return;
    };
    note_caller(&home, kind, caller);
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
    fn a_refusal_names_the_caller_it_turned_away() {
        assert_eq!(
            caller_line("browser_pane_refused_caller", "0.7.0", 44184, 1794946912, "ephe-plugin-citations"),
            "browser_pane_refused_caller ephe 0.7.0 pid 44184 epoch 1794946912 caller ephe-plugin-citations"
        );
    }

    #[test]
    fn a_caller_cannot_write_a_second_line_or_open_a_run() {
        // The label arrives from a webview, and the ledger is one line per event: whatever a
        // caller carries has to stay inside its own field and can neither start a line nor
        // impersonate the one kind the classifier reads as an open run.
        let forged = "start\nstart ephe 9.9.9 pid 1 epoch 1";
        let written = caller_line("browser_pane_refused_caller", "0.7.0", 7, 11, forged);
        assert_eq!(written.lines().count(), 1, "{written}");
        assert_eq!(last_run(&written), LastRun::Empty, "{written}");
        assert_eq!(tame(&"a".repeat(200)).len(), 64, "the field is capped");
    }

    #[test]
    fn a_start_that_never_reached_an_exit_is_named_as_open() {
        let text =
            "start ephe 0.5.3 pid 6825 epoch 1\nport 8765 answered, but not as an Ephe backend\n";
        assert_eq!(last_run(text), LastRun::Open);
    }

    #[test]
    fn an_exit_after_that_start_closes_the_run() {
        let text = "start ephe 0.5.3 pid 6825 epoch 1\nexit ephe 0.5.3 pid 6825 epoch 9\n";
        assert_eq!(last_run(text), LastRun::Ended);
    }

    #[test]
    fn a_restart_the_user_asked_for_closes_the_run() {
        // The relaunch path reaches `exit(0)` inside tauri and never the shell's
        // own `RunEvent::Exit`, so this line is all the healthy case leaves.
        let text = "start ephe 0.7.0 pid 1 epoch 1\nrestart requested ephe 0.7.0 pid 1 epoch 8\n";
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

    /// The three states a boot can meet in the ledger, and the line each one earns.
    #[test]
    fn a_boot_after_an_unmatched_start_says_so_beside_its_own_start() {
        let dir = std::env::temp_dir().join(format!("ephe-runlog-open-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        assert_eq!(previous_run(&dir), LastRun::Empty, "no file, no claim");

        assert!(!open_run(&dir), "a first run owes no verdict");
        let log = dir.join(".ephe/logs/desktop.log");
        let first = std::fs::read_to_string(&log).expect("ledger");
        assert_eq!(first.lines().count(), 1, "one line, its own start: {first}");
        assert!(first.starts_with("start ephe "), "{first}");

        assert!(
            open_run(&dir),
            "the run above never reached an exit, so this one says it"
        );
        let text = std::fs::read_to_string(&log).expect("ledger");
        let lines: Vec<&str> = text.lines().collect();
        assert_eq!(lines.len(), 3, "{text}");
        assert!(lines[1].starts_with("start ephe "), "{lines:?}");
        assert!(
            lines[2].starts_with("previous start unmatched ephe "),
            "the verdict sits after the start it explains: {lines:?}"
        );
        assert_eq!(
            last_run(&text),
            LastRun::Open,
            "the verdict line is not a run"
        );

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_boot_after_an_exit_leaves_the_question_unasked() {
        let dir = std::env::temp_dir().join(format!("ephe-runlog-clean-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        write(
            &dir,
            &format!(
                "{}\n{}",
                line("start", "0.0.0", 1, 2),
                line("exit", "0.0.0", 1, 9)
            ),
        );
        assert_eq!(previous_run(&dir), LastRun::Ended);

        assert!(
            !open_run(&dir),
            "a run that ended on its own path needs no verdict"
        );
        let text = std::fs::read_to_string(dir.join(".ephe/logs/desktop.log")).expect("ledger");
        assert!(!text.contains("unmatched"), "{text}");
        assert_eq!(last_run(&text), LastRun::Open, "and the new run is open");

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn a_boot_after_a_requested_restart_leaves_the_question_unasked() {
        let dir = std::env::temp_dir().join(format!("ephe-runlog-restart-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        write(
            &dir,
            &format!(
                "{}\n{}",
                line("start", "0.0.0", 1, 2),
                line("restart requested", "0.0.0", 1, 8)
            ),
        );
        assert_eq!(previous_run(&dir), LastRun::Ended);

        assert!(
            !open_run(&dir),
            "a restart the user asked for is not an end nothing reported"
        );
        let text = std::fs::read_to_string(dir.join(".ephe/logs/desktop.log")).expect("ledger");
        assert!(!text.contains("unmatched"), "{text}");

        let _ = std::fs::remove_dir_all(&dir);
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

    /// Both of the file's writers go through one handle now, so its mode and its bound are
    /// pinned here rather than in the backend module that only names its own cap.
    #[test]
    fn the_note_log_is_owner_only_and_one_file_deep() {
        let dir = std::env::temp_dir().join(format!("ephe-runlog-note-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let log_path = dir.join(".ephe/logs/desktop.log");
        std::fs::create_dir_all(log_path.parent().expect("logs")).expect("logs dir");
        std::fs::write(&log_path, "from an older build\n").expect("older build");
        std::fs::set_permissions(&log_path, std::fs::Permissions::from_mode(0o644)).expect("644");

        write(&dir, "the shell says this");
        let text = std::fs::read_to_string(&log_path).expect("note");
        assert!(text.contains("the shell says this"), "the note arrived");
        assert!(
            text.starts_with("from an older build"),
            "the earlier notes stay"
        );
        let mode = std::fs::symlink_metadata(&log_path)
            .expect("note")
            .permissions()
            .mode()
            & 0o777;
        assert_eq!(
            mode, 0o600,
            "the log the shell owns is not readable beside the owner"
        );

        std::fs::write(&log_path, vec![b'x'; DESKTOP_LOG_ROTATE_BYTES as usize]).expect("runaway");
        write(&dir, "after the runaway");
        let previous = PathBuf::from(format!("{}.1", log_path.display()));
        assert_eq!(
            std::fs::read(&previous).expect("kept").len(),
            DESKTOP_LOG_ROTATE_BYTES as usize
        );
        assert_eq!(
            std::fs::read_to_string(&log_path).expect("fresh"),
            "after the runaway\n",
            "the note after a rotation opens a new file"
        );
        let previous_mode = std::fs::symlink_metadata(&previous)
            .expect("kept")
            .permissions()
            .mode()
            & 0o777;
        assert_eq!(previous_mode, 0o600, "the rotated note log is private too");
        let _ = std::fs::remove_dir_all(&dir);
    }
}
