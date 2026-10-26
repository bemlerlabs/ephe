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
pub enum Paritat {
    /// Shell and backend name the same version.
    Gleichstand,
    /// They name different versions; both numbers travel so the surface can say them.
    Mismatch { shell: String, backend: String },
    /// One side has no version. Reported, never treated as agreement.
    Unbekannt,
}

/// Compare the bundle's version with the one the backend reports.
pub fn vergleichen(shell: &str, backend: &str) -> Paritat {
    let shell = shell.trim();
    let backend = backend.trim();
    if shell.is_empty() || backend.is_empty() {
        return Paritat::Unbekannt;
    }
    if shell == backend {
        Paritat::Gleichstand
    } else {
        Paritat::Mismatch {
            shell: shell.to_string(),
            backend: backend.to_string(),
        }
    }
}

/// What the shell learned about the backend's project root.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WurzelFakten {
    /// The root is a work tree of this product's repository.
    pub product_checkout: bool,
    /// Nothing differs from HEAD; a dirty tree is never moved.
    pub sauber: bool,
}

/// Whether the backend may be moved to the release it is supposed to run.
///
/// A developer's checkout, a fork of another repository, and a tree with local
/// changes are each refused with the reason a log line can carry.
pub fn erlaubnis(fakten: &WurzelFakten) -> Result<(), &'static str> {
    if !fakten.product_checkout {
        return Err("the backend root is not a checkout of this product's repository");
    }
    if !fakten.sauber {
        return Err("the backend checkout carries local changes; nothing is pulled over them");
    }
    Ok(())
}

/// The remote that counts as this product. Compared on host and path so an
/// ssh form, a token-carrying https form and a trailing `.git` all agree.
pub fn ist_produkt_fern(url: &str) -> bool {
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
pub fn ist_sauber(portzelan: &str) -> bool {
    portzelan.trim().is_empty()
}

/// The command the shell runs to move a permitted checkout onto the release.
pub fn hol_befehl(root: &Path) -> [Vec<String>; 2] {
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
    fn gleiche_versionen_sind_gleichstand() {
        assert_eq!(
            vergleichen("0.1.7", "0.1.7"),
            Paritat::Gleichstand,
            "the normal state must not raise a word"
        );
        assert_eq!(vergleichen(" 0.1.7 ", "0.1.7"), Paritat::Gleichstand);
    }

    #[test]
    fn mismatch_nennt_beide_zahlen() {
        let p = vergleichen("0.1.7", "0.1.4");
        assert_eq!(
            p,
            Paritat::Mismatch {
                shell: "0.1.7".into(),
                backend: "0.1.4".into(),
            }
        );
    }

    #[test]
    fn eine_fehlende_version_ist_kein_gleichstand() {
        assert_eq!(vergleichen("0.1.7", ""), Paritat::Unbekannt);
        assert_eq!(vergleichen("", "0.1.7"), Paritat::Unbekannt);
        assert_ne!(Paritat::Unbekannt, Paritat::Gleichstand, "silence is not agreement");
    }

    #[test]
    fn eine_fremde_oder_dreckige_wurzel_wird_nie_bewegt() {
        let err = erlaubnis(&WurzelFakten {
            product_checkout: false,
            sauber: true,
        })
        .unwrap_err();
        assert!(err.contains("not a checkout"), "{err}");
        let err = erlaubnis(&WurzelFakten {
            product_checkout: true,
            sauber: false,
        })
        .unwrap_err();
        assert!(err.contains("local changes"), "{err}");
        assert!(erlaubnis(&WurzelFakten {
            product_checkout: true,
            sauber: true,
        })
        .is_ok());
    }

    #[test]
    fn jedes_url_format_der_produktquelle_zaehlt() {
        assert!(ist_produkt_fern("https://github.com/bemlerlabs/ephe.git"));
        assert!(ist_produkt_fern("https://github.com/bemlerlabs/ephe"));
        assert!(ist_produkt_fern("git@github.com:bemlerlabs/ephe.git"));
        assert!(
            !ist_produkt_fern("https://github.com/evilcorp/ephe.git"),
            "a fork is not this product"
        );
        assert!(
            !ist_produkt_fern("https://git.example.com/bemlerlabs/ephe.git"),
            "another host is not this product"
        );
        assert!(!ist_produkt_fern(""));
    }

    #[test]
    fn portzelan_entscheidet_ueber_den_lokalen_stand() {
        assert!(ist_sauber(""));
        assert!(ist_sauber("  \n"));
        assert!(!ist_sauber(" M core/chat.py\n"));
    }

    #[test]
    fn der_hol_befehl_arbeitet_in_der_wurzel_und_ruert_keine_zweige_an() {
        let befehle = hol_befehl(Path::new("/srv/ephe"));
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
mod lauf {
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

    fn vorlage(verdict: &'static str, shell: &str, backend: &str, note: &str) -> Status {
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
    pub fn pruefen_und_heilen(port: u16) -> Status {
        let shell = env!("CARGO_PKG_VERSION");
        let Some(peer) = crate::backend::statement(port) else {
            return speicher(vorlage("no_backend", shell, "", "no backend answered"));
        };
        match vergleichen(shell, &peer.version) {
            Paritat::Gleichstand => speicher(vorlage("current", shell, &peer.version, "")),
            Paritat::Unbekannt => speicher(vorlage(
                "unknown",
                shell,
                &peer.version,
                "the backend reported no version",
            )),
            Paritat::Mismatch { backend, .. } => {
                let root = std::path::Path::new(&peer.root);
                let inside = git(&["-C", &peer.root, "rev-parse", "--is-inside-work-tree"])
                    .map(|o| o.trim() == "true")
                    .unwrap_or(false);
                let url = git(&["-C", &peer.root, "remote", "get-url", "origin"]).unwrap_or_default();
                let schmutz = git(&["-C", &peer.root, "status", "--porcelain"]).unwrap_or_default();
                let fakten = WurzelFakten {
                    product_checkout: inside && ist_produkt_fern(&url),
                    sauber: ist_sauber(&schmutz),
                };
                if let Err(grund) = erlaubnis(&fakten) {
                    return speicher(vorlage("mismatch", shell, &backend, grund));
                }
                let [fetch, checkout] = hol_befehl(root);
                let bewegt = |args: &Vec<String>| {
                    git(args.iter().map(String::as_str).collect::<Vec<_>>().as_slice()).is_some()
                };
                if bewegt(&fetch) && bewegt(&checkout) {
                    speicher(vorlage(
                        "updated_restart",
                        shell,
                        &backend,
                        "the backend checkout moved to the release; restart Ephe to load it",
                    ))
                } else {
                    speicher(vorlage(
                        "mismatch",
                        shell,
                        &backend,
                        "the backend could not be moved; check the network or update it by hand",
                    ))
                }
            }
        }
    }

    fn speicher(status: Status) -> Status {
        if let Ok(mut guard) = LAST.lock() {
            *guard = Some(status.clone());
        }
        status
    }

    pub fn letzter_status() -> Status {
        LAST.lock()
            .ok()
            .and_then(|g| g.clone())
            .unwrap_or_else(|| vorlage("unknown", "", "", "the parity check has not run yet"))
    }
}

#[cfg(unix)]
pub use lauf::{letzter_status, pruefen_und_heilen};

#[cfg(not(unix))]
pub fn pruefen_und_heilen(_port: u16) -> Status {
    Status {
        verdict: "unknown",
        shell: env!("CARGO_PKG_VERSION").to_string(),
        backend: String::new(),
        note: "the parity check runs where the desktop backend runs".into(),
    }
}

#[cfg(not(unix))]
pub fn letzter_status() -> Status {
    pruefen_und_heilen(0)
}
