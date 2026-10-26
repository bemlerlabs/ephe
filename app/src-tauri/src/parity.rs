//! The shell and the backend have to run the same code.
//!
//! The updater replaces the `.app` and nothing else: the Python server named by
//! `~/.ephe/desktop.json` keeps the version it was installed with. Measured on
//! 2026-10-25 — a 0.1.6 shell starting a 0.1.4 backend, and the surface saying
//! nothing about it. Silence is the defect, so every branch below either agrees,
//! moves the backend, or says what it found.
//!
//! Moving a checkout is a write to the owner's machine. It happens only where the
//! facts below allow it, and a refused move names its reason.


/// What the two versions say about each other.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Parity {
    /// Shell and backend name the same version.
    Agreement,
    /// They name different versions; both numbers travel so the surface can say them.
    Mismatch { shell: String, backend: String },
    /// One side has no version. Reported, never treated as agreement.
    Unknown,
}

/// Compare the bundle's version with the one the backend reports.
pub fn compare(shell: &str, backend: &str) -> Parity {
    let shell = shell.trim();
    let backend = backend.trim();
    if shell.is_empty() || backend.is_empty() {
        return Parity::Unknown;
    }
    if shell == backend {
        Parity::Agreement
    } else {
        Parity::Mismatch {
            shell: shell.to_string(),
            backend: backend.to_string(),
        }
    }
}

/// What the shell learned about the backend's project root.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RootFacts {
    /// The root is a work tree of this product's repository.
    pub product_checkout: bool,
    /// Nothing differs from HEAD; a dirty tree is never moved.
    pub clean: bool,
}

/// Whether the backend may be moved to the release it is supposed to run.
///
/// A developer's checkout, a fork of another repository, and a tree with local
/// changes are each refused with the reason a log line can carry.
pub fn permission(facts: &RootFacts) -> Result<(), &'static str> {
    if !facts.product_checkout {
        return Err("the backend root is not a checkout of this product's repository");
    }
    if !facts.clean {
        return Err("the backend checkout carries local changes; nothing is pulled over them");
    }
    Ok(())
}

/// The remote that counts as this product. Compared on host and path so an
/// ssh form, a token-carrying https form and a trailing `.git` all agree.
pub fn is_product_remote(url: &str) -> bool {
    let url = url.trim().to_ascii_lowercase();
    let (host, path) = match url.split_once("://") {
        Some((_, rest)) => rest.split_once('/').unwrap_or(("", "")),
        None => match url.split_once(':') {
            // scp-like form: `git@github.com:bemlerlabs/ephe.git`
            Some((before, after)) => (before.rsplit('@').next().unwrap_or(before), after),
            None => return false,
        },
    };
    let path = path.trim_end_matches('/').trim_end_matches(".git");
    host.ends_with("github.com") && path == "bemlerlabs/ephe"
}

/// Whether two spellings name the same directory. A path that does not resolve is
/// only equal to itself, so a missing root never passes as the configured one.
pub fn same_root(configured: &std::path::Path, reported: &std::path::Path) -> bool {
    match (configured.canonicalize(), reported.canonicalize()) {
        (Ok(a), Ok(b)) => a == b,
        _ => configured == reported,
    }
}

/// Whether `git status --porcelain` output means a clean tree.
pub fn is_clean(porcelain: &str) -> bool {
    porcelain.trim().is_empty()
}

/// The arguments of the two commands that move a permitted checkout onto the
/// release. The root is never one of them: it is the process's working
/// directory, so a path read from `~/.ephe/desktop.json` cannot become part of
/// a command line.
const FETCH: [&str; 3] = ["fetch", "origin", "main:refs/remotes/origin/main"];
const CHECKOUT: [&str; 4] = ["checkout", "-B", "main", "origin/main"];

pub fn move_commands() -> [&'static [&'static str]; 2] {
    [&FETCH[..], &CHECKOUT[..]]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn equal_versions_are_agreement() {
        assert_eq!(
            compare("0.1.7", "0.1.7"),
            Parity::Agreement,
            "the normal state must not raise a word"
        );
        assert_eq!(compare(" 0.1.7 ", "0.1.7"), Parity::Agreement);
    }

    #[test]
    fn mismatch_names_both_numbers() {
        let p = compare("0.1.7", "0.1.4");
        assert_eq!(
            p,
            Parity::Mismatch {
                shell: "0.1.7".into(),
                backend: "0.1.4".into(),
            }
        );
    }

    #[test]
    fn a_missing_version_is_never_agreement() {
        assert_eq!(compare("0.1.7", ""), Parity::Unknown);
        assert_eq!(compare("", "0.1.7"), Parity::Unknown);
        assert_ne!(Parity::Unknown, Parity::Agreement, "silence is not agreement");
    }

    #[test]
    fn a_foreign_or_dirty_root_is_never_moved() {
        let err = permission(&RootFacts {
            product_checkout: false,
            clean: true,
        })
        .unwrap_err();
        assert!(err.contains("not a checkout"), "{err}");
        let err = permission(&RootFacts {
            product_checkout: true,
            clean: false,
        })
        .unwrap_err();
        assert!(err.contains("local changes"), "{err}");
        assert!(permission(&RootFacts {
            product_checkout: true,
            clean: true,
        })
        .is_ok());
    }

    #[test]
    fn every_url_form_of_the_product_remote_counts() {
        assert!(is_product_remote("https://github.com/bemlerlabs/ephe.git"));
        assert!(is_product_remote("https://github.com/bemlerlabs/ephe"));
        assert!(is_product_remote("git@github.com:bemlerlabs/ephe.git"));
        assert!(
            !is_product_remote("https://github.com/evilcorp/ephe.git"),
            "a fork is not this product"
        );
        assert!(
            !is_product_remote("https://git.example.com/bemlerlabs/ephe.git"),
            "another host is not this product"
        );
        assert!(!is_product_remote(""));
    }

    #[test]
    fn only_the_configured_root_may_be_moved() {
        assert!(same_root(std::path::Path::new("/tmp"), std::path::Path::new("/tmp")));
        assert!(!same_root(
            std::path::Path::new("/tmp"),
            std::path::Path::new("/var")
        ));
        assert!(!same_root(
            std::path::Path::new("/nonexistent-a"),
            std::path::Path::new("/nonexistent-b")
        ));
    }

    #[test]
    fn porcelain_decides_the_local_state() {
        assert!(is_clean(""));
        assert!(is_clean("  \n"));
        assert!(!is_clean(" M core/chat.py\n"));
    }

    #[test]
    fn the_move_commands_carry_no_path_at_all() {
        let [fetch, checkout] = move_commands();
        assert_eq!(fetch, FETCH.as_slice());
        assert_eq!(checkout, CHECKOUT.as_slice());
        for args in move_commands() {
            assert!(
                !args.iter().any(|a| *a == "-C" || a.starts_with('/')),
                "a command line must not carry the backend's path: {args:?}"
            );
        }
    }
}

/// What the shell found, in the shape the surface reads.
#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Status {
    /// `current`, `mismatch`, `updated_restart`, `unknown` or `no_backend`.
    pub verdict: &'static str,
    pub shell: String,
    pub backend: String,
    /// The sentence that names why the verdict is what it is.
    pub note: String,
}

#[cfg(unix)]
mod runtime {
    use super::*;
    use std::sync::Mutex;
    use std::time::{Duration, Instant};

    static LAST: Mutex<Option<Status>> = Mutex::new(None);

    /// One heal at a time. The start thread and the surface command can both ask
    /// for a check, and two `git` runs in one checkout must not overlap.
    static HEAL: Mutex<()> = Mutex::new(());

    /// The root this machine configured, remembered at start so the command can
    /// ask again later without rereading `~/.ephe/desktop.json`.
    static PROJECT: Mutex<Option<std::path::PathBuf>> = Mutex::new(None);

    /// How long a cold start may take before the check stops asking. Measured
    /// 2026-10-26: the Python backend needs seconds, and the old single 400 ms
    /// probe ran before the port existed on every launch after an update.
    const WAIT_MS: u64 = 30_000;
    const POLL_MS: u64 = 250;

    /// Ask a probe until it answers or the deadline passes.
    pub(super) fn wait_for<T>(timeout_ms: u64, poll_ms: u64, mut probe: impl FnMut() -> Option<T>) -> Option<T> {
        let deadline = Instant::now() + Duration::from_millis(timeout_ms);
        loop {
            if let Some(value) = probe() {
                return Some(value);
            }
            if Instant::now() >= deadline {
                return None;
            }
            std::thread::sleep(Duration::from_millis(poll_ms));
        }
    }

    /// Whether a remembered verdict is worth a fresh look. A backend that had not
    /// answered, or answered without a version, can be the first second of a
    /// start; a measured mismatch or agreement cannot.
    pub fn should_refresh(status: &Status) -> bool {
        matches!(status.verdict, "no_backend" | "unknown")
    }

    pub fn remember_project(path: &std::path::Path) {
        if let Ok(mut guard) = PROJECT.lock() {
            *guard = Some(path.to_path_buf());
        }
    }

    pub fn configured_project() -> Option<std::path::PathBuf> {
        PROJECT.lock().ok().and_then(|g| g.clone())
    }

    /// Run git with the backend root as the working directory. The path is never
    /// an argument: it comes from `~/.ephe/desktop.json`, and a directory the OS
    /// resolves is not a value a command line has to carry.
    fn git_in(dir: &std::path::Path, args: &[&str]) -> Option<String> {
        if !dir.is_dir() {
            return None;
        }
        let out = std::process::Command::new("git")
            .current_dir(dir)
            .args(args)
            .output()
            .ok()?;
        if !out.status.success() {
            return None;
        }
        Some(String::from_utf8_lossy(&out.stdout).to_string())
    }

    fn make_status(verdict: &'static str, shell: &str, backend: &str, note: &str) -> Status {
        Status {
            verdict,
            shell: shell.to_string(),
            backend: backend.to_string(),
            note: note.to_string(),
        }
    }

    /// Compare, move when that is allowed, and remember what happened. A move is
    /// never followed by a kill: the process on the port may belong to another
    /// shell, so the new code is loaded by the next start and the verdict says so.
    pub fn check_and_heal(port: u16, project: &std::path::Path) -> Status {
        check_and_heal_with(port, project, WAIT_MS)
    }

    /// The same check with a caller-chosen deadline. The start thread can spend the
    /// full 30 s; a surface command that only repeats a cached "no backend" answers
    /// with a shorter clock so nobody waits on it.
    pub fn check_and_heal_with(port: u16, project: &std::path::Path, wait_ms: u64) -> Status {
        let shell = env!("CARGO_PKG_VERSION");
        let _serial = HEAL.lock().unwrap_or_else(|e| e.into_inner());
        let Some(peer) = wait_for(wait_ms, POLL_MS, || crate::backend::statement(port)) else {
            return remember(make_status(
                "no_backend",
                shell,
                "",
                "no backend answered within the wait",
            ));
        };
        // The path a command may run in is the one this machine configured, never
        // the one a socket answered with: the answer is only compared against it.
        if !same_root(project, std::path::Path::new(&peer.root)) {
            return remember(make_status(
                "mismatch",
                shell,
                &peer.version,
                "the backend runs from another root than the configured one; nothing is moved",
            ));
        }
        match compare(shell, &peer.version) {
            Parity::Agreement => remember(make_status("current", shell, &peer.version, "")),
            Parity::Unknown => remember(make_status(
                "unknown",
                shell,
                &peer.version,
                "the backend reported no version",
            )),
            Parity::Mismatch { backend, .. } => {
                let root = project;
                let inside = git_in(root, &["rev-parse", "--is-inside-work-tree"])
                    .map(|o| o.trim() == "true")
                    .unwrap_or(false);
                let url = git_in(root, &["remote", "get-url", "origin"]).unwrap_or_default();
                let dirt = git_in(root, &["status", "--porcelain"]).unwrap_or_default();
                let facts = RootFacts {
                    product_checkout: inside && is_product_remote(&url),
                    clean: is_clean(&dirt),
                };
                if let Err(grund) = permission(&facts) {
                    return remember(make_status("mismatch", shell, &backend, grund));
                }
                let [fetch, checkout] = move_commands();
                let ran = |args: &[&str]| git_in(root, args).is_some();
                if ran(fetch) && ran(checkout) {
                    remember(make_status(
                        "updated_restart",
                        shell,
                        &backend,
                        "the backend checkout moved to the release; restart Ephe to load it",
                    ))
                } else {
                    remember(make_status(
                        "mismatch",
                        shell,
                        &backend,
                        "the backend could not be moved; check the network or update it by hand",
                    ))
                }
            }
        }
    }

    fn remember(status: Status) -> Status {
        if let Ok(mut guard) = LAST.lock() {
            *guard = Some(status.clone());
        }
        status
    }

    pub fn last_status() -> Status {
        LAST.lock()
            .ok()
            .and_then(|g| g.clone())
            .unwrap_or_else(|| make_status("unknown", "", "", "the parity check has not run yet"))
    }
}

#[cfg(unix)]
pub use runtime::{
    check_and_heal, check_and_heal_with, configured_project, last_status, remember_project,
    should_refresh,
};

#[cfg(not(unix))]
pub fn check_and_heal_with(_port: u16, _project: &std::path::Path, _wait_ms: u64) -> Status {
    check_and_heal(_port)
}

#[cfg(not(unix))]
pub fn remember_project(_path: &std::path::Path) {}

#[cfg(not(unix))]
pub fn configured_project() -> Option<std::path::PathBuf> {
    None
}

#[cfg(not(unix))]
pub fn should_refresh(_status: &Status) -> bool {
    false
}

#[cfg(not(unix))]
pub fn check_and_heal(_port: u16) -> Status {
    Status {
        verdict: "unknown",
        shell: env!("CARGO_PKG_VERSION").to_string(),
        backend: String::new(),
        note: "the parity check runs where the desktop backend runs".into(),
    }
}

#[cfg(not(unix))]
pub fn last_status() -> Status {
    check_and_heal(0)
}

#[cfg(all(test, unix))]
mod runtime_tests {
    use super::runtime::{should_refresh, wait_for};

    #[test]
    fn a_probe_that_answers_late_is_still_read() {
        let mut asked = 0;
        let answer = wait_for(2_000, 1, || {
            asked += 1;
            if asked < 3 {
                None
            } else {
                Some(asked)
            }
        });
        assert_eq!(answer, Some(3), "the third ask is the answer");
    }

    #[test]
    fn a_probe_that_never_answers_gives_up_at_the_deadline() {
        let started = std::time::Instant::now();
        let answer: Option<u8> = wait_for(0, 1, || None);
        assert_eq!(answer, None);
        assert!(started.elapsed() < std::time::Duration::from_secs(2));
    }

    #[test]
    fn only_a_missing_answer_is_worth_asking_again() {
        let mut status = super::Status {
            verdict: "no_backend",
            shell: "0.1.9".into(),
            backend: String::new(),
            note: String::new(),
        };
        assert!(should_refresh(&status), "a cold start asks again");
        status.verdict = "unknown";
        assert!(should_refresh(&status), "a missing version asks again");
        status.verdict = "mismatch";
        assert!(!should_refresh(&status), "a measured mismatch stands");
        status.verdict = "current";
        assert!(!should_refresh(&status), "agreement stands");
    }
}
