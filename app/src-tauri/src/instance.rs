//! Ephe — one instance (R4/W5).
//!
//! Two running Ephe apps are not a cosmetic defect: every process sees the same
//! artifact index and the same session storage, but not the same state. Tauri
//! ships nothing for this, and the official plugin keys only on the bundle id —
//! after an update the new build would quit silently while the old one kept the
//! window. Swapping a visible defect for an invisible one was never the point.
//!
//! Hence: a socket in the real configuration directory, keyed by the actual
//! path. A second launch brings the running instance to the front and exits
//! itself.

use std::io::{Read, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};

const SOCKET: &str = "ephe-desktop.sock";

pub(crate) fn config_dir() -> Option<PathBuf> {
    if let Some(dir) = std::env::var_os("EPHE_CONFIG_DIR") {
        return Some(PathBuf::from(dir));
    }
    std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".ephe"))
}

/// The socket this instance holds. While the value lives the file stays bound;
/// it disappears with the process — a crash leaves no lock somebody has to
/// delete by hand.
#[derive(Debug)]
pub struct Held {
    listener: UnixListener,
    path: PathBuf,
}

/// Did an instance already open? `OtherInstance` means: it was brought to the
/// front and the caller exits the program. `Unknown` means: nothing provable
/// (no HOME, unexpected error) — then start without a guard rather than make
/// Ephe unstartable because of a problem.
#[derive(Debug)]
pub enum Claim {
    Held(Held),
    OtherInstance,
    Unknown,
}

fn bind(dir: &Path) -> Claim {
    let path = dir.join(SOCKET);
    let attempt = UnixListener::bind(&path);
    match attempt {
        Ok(listener) => Claim::Held(Held { listener, path }),
        Err(bind_err) => {
            if bind_err.kind() != std::io::ErrorKind::AddrInUse {
                return Claim::Unknown;
            }
            match UnixStream::connect(&path) {
                Ok(mut stream) => {
                    let _ = stream.write_all(b"focus\n");
                    let _ = stream.read(&mut [0u8; 1]);
                    Claim::OtherInstance
                }
                Err(_) => {
                    // Nobody answering on the other end: the remains of a crash.
                    let _ = std::fs::remove_file(&path);
                    UnixListener::bind(&path)
                        .ok()
                        .map(|listener| Claim::Held(Held { listener, path }))
                        .unwrap_or(Claim::Unknown)
                }
            }
        }
    }
}

pub fn claim() -> Claim {
    let Some(dir) = config_dir() else {
        return Claim::Unknown;
    };
    if std::fs::create_dir_all(&dir).is_err() {
        return Claim::Unknown;
    }
    bind(&dir)
}

/// The running instance listens and reacts when someone starts it a second
/// time. A broken client must not end the loop.
pub fn wake_on_request(held: Held, on_wake: impl Fn() + Send + 'static) {
    std::thread::spawn(move || {
        for stream in held.listener.incoming().flatten() {
            let mut stream = stream;
            let mut buf = [0u8; 8];
            let _ = stream.read(&mut buf);
            on_wake();
            let _ = stream.write_all(b"\n");
        }
        let _ = std::fs::remove_file(&held.path);
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Arc;

    fn temp_dir(tag: &str) -> PathBuf {
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.subsec_micros())
            .unwrap_or(0);
        let dir = std::env::temp_dir().join(format!(
            "ephe-instance-{}-{tag}-{unique}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn zweiter_start_weckt_die_erste_instanz_und_ist_keine_zweite() {
        let dir = temp_dir("weckt");
        let held = match bind(&dir) {
            Claim::Held(held) => held,
            other => panic!("erster Start soll gebunden haben, war: {other:?}"),
        };
        let wakes = Arc::new(AtomicUsize::new(0));
        let counter = Arc::clone(&wakes);
        wake_on_request(held, move || {
            counter.fetch_add(1, Ordering::SeqCst);
        });

        // The second launch: it reports itself and gets no bind of its own.
        assert!(matches!(bind(&dir), Claim::OtherInstance));

        std::thread::sleep(std::time::Duration::from_millis(120));
        assert_eq!(
            wakes.load(Ordering::SeqCst),
            1,
            "die erste Instanz wurde nicht geweckt"
        );
    }

    #[test]
    fn ein_sockel_von_einem_abgesturzten_start_wird_ersetzt() {
        let dir = temp_dir("sockel");
        // A file with no listener — exactly the picture left behind by a SIGKILL.
        std::fs::write(dir.join(SOCKET), b"").unwrap();
        assert!(
            matches!(bind(&dir), Claim::Held(..)),
            "ein toter Socket darf Ephe nicht aussperren"
        );
    }

    #[test]
    fn ohne_konfigurationsverzeichnis_ist_nichts_belegt() {
        // No path, no socket, no reason to refuse the start.
        std::env::remove_var("EPHE_CONFIG_DIR");
        let home = std::env::var_os("HOME");
        std::env::remove_var("HOME");
        assert!(matches!(claim(), Claim::Unknown));
        if let Some(home) = home {
            std::env::set_var("HOME", home);
        }
    }
}
