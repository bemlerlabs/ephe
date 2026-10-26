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

use std::path::Path;

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

/// Whether `git status --porcelain` output means a clean tree.
pub fn is_clean(porcelain: &str) -> bool {
    porcelain.trim().is_empty()
}

/// The command the shell runs to move a permitted checkout onto the release.
pub fn move_commands(root: &Path) -> [Vec<String>; 2] {
    let root = root.display().to_string();
    [
        vec![
            "git".into(),
            "-C".into(),
            root.clone(),
            "fetch".into(),
            "origin".into(),
            "main:refs/remotes/origin/main".into(),
        ],
        vec![
            "git".into(),
            "-C".into(),
            root,
            "checkout".into(),
            "-B".into(),
            "main".into(),
            "origin/main".into(),
        ],
    ]
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
    fn porcelain_decides_the_local_state() {
        assert!(is_clean(""));
        assert!(is_clean("  \n"));
        assert!(!is_clean(" M core/chat.py\n"));
    }

    #[test]
    fn the_move_commands_work_in_the_root_and_touch_no_branch() {
        let befehle = move_commands(Path::new("/srv/ephe"));
        assert_eq!(befehle[0][..4], ["git", "-C", "/srv/ephe", "fetch"]);
        assert_eq!(befehle[0][4], "origin");
        assert_eq!(befehle[0][5], "main:refs/remotes/origin/main");
        assert_eq!(befehle[1][..4], ["git", "-C", "/srv/ephe", "checkout"]);
        assert_eq!(befehle[1][6], "origin/main");
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

    static LAST: Mutex<Option<Status>> = Mutex::new(None);

    fn git(args: &[&str]) -> Option<String> {
        let out = std::process::Command::new("git").args(args).output().ok()?;
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
    pub fn check_and_heal(port: u16) -> Status {
        let shell = env!("CARGO_PKG_VERSION");
        let Some(peer) = crate::backend::statement(port) else {
            return remember(make_status("no_backend", shell, "", "no backend answered"));
        };
        match compare(shell, &peer.version) {
            Parity::Agreement => remember(make_status("current", shell, &peer.version, "")),
            Parity::Unknown => remember(make_status(
                "unknown",
                shell,
                &peer.version,
                "the backend reported no version",
            )),
            Parity::Mismatch { backend, .. } => {
                let root = std::path::Path::new(&peer.root);
                let inside = git(&["-C", &peer.root, "rev-parse", "--is-inside-work-tree"])
                    .map(|o| o.trim() == "true")
                    .unwrap_or(false);
                let url = git(&["-C", &peer.root, "remote", "get-url", "origin"]).unwrap_or_default();
                let dirt = git(&["-C", &peer.root, "status", "--porcelain"]).unwrap_or_default();
                let facts = RootFacts {
                    product_checkout: inside && is_product_remote(&url),
                    clean: is_clean(&dirt),
                };
                if let Err(grund) = permission(&facts) {
                    return remember(make_status("mismatch", shell, &backend, grund));
                }
                let [fetch, checkout] = move_commands(root);
                let ran = |args: &Vec<String>| {
                    git(args.iter().map(String::as_str).collect::<Vec<_>>().as_slice()).is_some()
                };
                if ran(&fetch) && ran(&checkout) {
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
pub use runtime::{last_status, check_and_heal};

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
