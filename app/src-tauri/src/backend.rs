//! Ephe — the backend behind the app icon (R7).
//!
//! An icon that only opens the window and then shows "Disconnected" is not a
//! desktop program. `ephe desktop` used to start the backend as CLI prep work;
//! launched from Finder or the Dock that step is missing entirely (measured
//! 2026-10-08: nothing is listening on 8765 and the surface reports
//! Disconnected). So the app listens for itself and starts whatever the
//! installer recorded in `~/.ephe/desktop.json`.
//!
//! Without that line **nothing is guessed**: a program that goes looking for a
//! Python interpreter and finds one where none belongs is worse than a surface
//! that honestly says its backend is missing.

use serde::Deserialize;
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

pub const PORT: u16 = 8765;

//: The wire contract this shell can read. Mirrors `core._version.API_CONTRACT`; a
//: backend that speaks another one is refused with both numbers, not reused.
pub const API_CONTRACT: u32 = 1;

//: This shell process's claim on the backend it starts. A backend reports it in
//: `/api/health`, so a process this shell did not spawn is never taken for its own.
static OWNER: Mutex<Option<String>> = Mutex::new(None);

fn owner_token() -> String {
    let mut guard = OWNER.lock().expect("owner token");
    if let Some(token) = guard.as_ref() {
        return token.clone();
    }
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let token = format!("{stamp:x}{:x}", std::process::id());
    *guard = Some(token.clone());
    token
}

/// The backend this shell spawned. A reused backend (a dev server, another
/// checkout) is never stored here and is therefore never killed on exit; a child
/// this shell started must not survive an update or a quit and answer for the
/// next version with the code it loaded at start.
static BACKEND_CHILD: Mutex<Option<Child>> = Mutex::new(None);

/// The one variable a keyed endpoint is authenticated by, and the one place the
/// desktop app reads it from.
///
/// A `.app` opened from Finder or the Dock inherits no shell environment: measured
/// 2026-10-10 against the installed build, the process on 8765 carries 36
/// environment variables and not one `EPHE_` among them. So
/// `export EPHE_OPENAI_COMPAT_API_KEY=… && ephe start` authenticates a backend that
/// was started in a terminal, and never the one started by this module.
/// `~/.ephe/engine.key` is the desktop equivalent of that export. The user writes it;
/// nothing here creates, suggests or guesses it — which is why the value is handed to
/// the child as an environment variable instead of becoming a second resolver: the
/// engine still reads exactly one source for a key (AGENTS.md), and `engine.json`
/// still holds no secret field.
pub const KEY_ENV: &str = "EPHE_OPENAI_COMPAT_API_KEY";
pub const KEY_FILE: &str = "engine.key";

#[derive(Debug, Clone, Deserialize)]
struct Eintrag {
    python: String,
    project_root: String,
    #[serde(default)]
    port: Option<u16>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Startbefehl {
    pub programm: PathBuf,
    pub projekt: PathBuf,
    pub port: u16,
    pub log: PathBuf,
}

#[derive(Debug, PartialEq, Eq)]
pub enum Ergebnis {
    /// no configuration line — nothing to start, nothing to guess
    KeinBefehl,
    /// our own backend holds the port and says it can use its engine
    SchonDa,
    /// something holds the port that does not answer as an Ephe backend. Not
    /// reused as ours and never handed a token: a completed handshake proves a
    /// listener, not an owner.
    FremderPort,
    /// an Ephe backend, but not one this shell can own: another contract or owner.
    /// The sentence names both versions, so the surface can say what it found.
    Inkompatibel(String),
    Gestartet,
    StartFehler(String),
}

pub fn konfig_pfad(home: &Path) -> PathBuf {
    home.join(".ephe").join("desktop.json")
}

pub fn key_path(home: &Path) -> PathBuf {
    home.join(".ephe").join(KEY_FILE)
}

/// The stored token, or nothing. A file that group or other can read is not a
/// secret the user stored but one the machine leaks to more processes than its
/// owner, so it is refused rather than used — same for a symlink and for a file
/// that is not exactly one non-empty line.
fn key_from_file(home: &Path) -> Option<String> {
    let path = key_path(home);
    let meta = fs::symlink_metadata(&path).ok()?;
    if !meta.is_file() || meta.permissions().mode() & 0o077 != 0 {
        return None;
    }
    let text = fs::read_to_string(&path).ok()?.trim().to_owned();
    if text.is_empty() || text.contains('\n') {
        return None;
    }
    Some(text)
}

/// Which token the spawned backend gets. An inherited one wins: whoever exported
/// the variable for this process named that value deliberately, and a file on disk
/// must not quietly replace it. Neither present means no token, so a keyed endpoint
/// answers with its own rejection instead of Ephe sending a guessed credential.
pub fn key_for_start(home: &Path, inherited: Option<&std::ffi::OsStr>) -> Option<String> {
    match inherited {
        Some(value) if !value.is_empty() => None,
        _ => key_from_file(home),
    }
}

/// Store the token the desktop's next start reads. The settings field is the one place
/// a user types a key without a terminal, and until now nothing wrote the file the spawn
/// consults: the token lived in the env of the process that served the request, so the
/// next desktop start resolved none of its two sources (measured 2026-10-11, carried as
/// the strict xfail in `tests/test_desktop_spawn_reaches_keyed_engine.py`).
///
/// The file is written owner-only from the first byte, through a temp name and a rename,
/// so no half-written secret is ever readable. `key_from_file` is the contract this has to
/// satisfy: exactly one line, no group or other bit.
pub fn store_key(home: &Path, value: &str) -> Result<(), String> {
    let text = value.trim();
    if text.is_empty() {
        return Err("engine key is empty".into());
    }
    if text.contains('\n') {
        return Err("engine key must be one line".into());
    }
    let dir = home.join(".ephe");
    fs::create_dir_all(&dir).map_err(|e| format!("cannot open {}: {e}", dir.display()))?;
    // Same least privilege the engine config uses: the folder is the owner's alone.
    let _ = fs::set_permissions(&dir, fs::Permissions::from_mode(0o700));
    let target = key_path(home);
    let temp = target.with_extension("key.tmp");
    {
        use std::os::unix::fs::OpenOptionsExt;
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&temp)
            .map_err(|e| format!("cannot write {}: {e}", temp.display()))?;
        file.write_all(text.as_bytes())
            .and_then(|_| file.write_all(b"\n"))
            .map_err(|e| format!("cannot write {}: {e}", temp.display()))?;
    }
    fs::rename(&temp, &target).map_err(|e| format!("cannot store {}: {e}", target.display()))?;
    Ok(())
}

/// Remove the stored token. A user who deleted a key from a settings field must not leave
/// a credential on disk that the next start reads back.
pub fn clear_key(home: &Path) -> Result<(), String> {
    let target = key_path(home);
    match fs::remove_file(&target) {
        Ok(()) => Ok(()),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(format!("cannot remove {}: {e}", target.display())),
    }
}

/// Whether a token is stored, as a boolean. The value is never returned to the frontend:
/// the shell renders the webview, and a string that reaches the page is a string a
/// devtools panel can read.
pub fn key_is_stored(home: &Path) -> bool {
    key_from_file(home).is_some()
}

/// Turn the installer's line into a start command. Empty paths are not a
/// command — otherwise the next launch spawns a program called `""`.
pub fn befehl_aus(text: &str, home: &Path) -> Option<Startbefehl> {
    let e: Eintrag = serde_json::from_str(text).ok()?;
    if e.python.trim().is_empty() || e.project_root.trim().is_empty() {
        return None;
    }
    Some(Startbefehl {
        programm: PathBuf::from(e.python),
        projekt: PathBuf::from(e.project_root),
        port: e.port.unwrap_or(PORT),
        log: home.join(".ephe").join("logs").join("desktop-backend.log"),
    })
}

/// Is someone listening? Only a completed handshake counts — a socket that
/// swallows the SYN runs into the timeout and counts as closed.
pub fn lauscht(port: u16) -> bool {
    let Some(addr) = ("127.0.0.1", port)
        .to_socket_addrs()
        .ok()
        .and_then(|mut i| i.next())
    else {
        return false;
    };
    TcpStream::connect_timeout(&addr, Duration::from_millis(400)).is_ok()
}

pub fn braucht_start(port_offen: bool, befehl: Option<&Startbefehl>) -> bool {
    !port_offen && befehl.is_some()
}

/// What a process on the port reports about its own engine.
#[derive(Debug, PartialEq, Eq)]
pub struct PeerStatement {
    pub key_challenge: bool,
    pub detail: String,
    pub version: String,
    pub api_contract: u32,
    pub owner: String,
    pub instance_id: String,
    pub pid: u64,
    pub root: String,
}

/// Ask the running backend instead of guessing from the socket.
///
/// A process cannot receive an environment variable after it started, so the
/// desktop token can only ever reach a backend this module spawns. That makes the
/// reuse branch blind unless it asks — and `lauscht()` alone is not an answer: any
/// listener passes it, while the desktop path, the dev proxy and the bench harness
/// all talk to whoever owns the port (measured 2026-10-10: a key file with a valid
/// mode sat unused while a backend without one held 8765).
pub fn statement(port: u16) -> Option<PeerStatement> {
    let addr = ("127.0.0.1", port).to_socket_addrs().ok()?.next()?;
    let mut stream = TcpStream::connect_timeout(&addr, Duration::from_millis(400)).ok()?;
    stream
        .set_read_timeout(Some(Duration::from_millis(1_500)))
        .ok()?;
    stream
        .write_all(
            b"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nAccept: application/json\r\nConnection: close\r\n\r\n",
        )
        .ok()?;
    let mut raw = Vec::new();
    stream.read_to_end(&mut raw).ok()?;
    let text = String::from_utf8_lossy(&raw);
    // uvicorn answers JSON with a content length, so the body starts at the first
    // brace and nothing follows it. Anything else is not an Ephe backend.
    let body = text.get(text.find('{')?..)?;
    let value: serde_json::Value = serde_json::from_str(body).ok()?;
    Some(PeerStatement {
        key_challenge: value.get("engine_key_challenge").and_then(|v| v.as_bool())?,
        detail: value
            .get("detail")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string(),
        version: value
            .get("version")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string(),
        api_contract: value.get("api_contract").and_then(|v| v.as_u64()).unwrap_or(0) as u32,
        owner: value
            .get("owner")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string(),
        instance_id: value
            .get("instance_id")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string(),
        pid: value.get("pid").and_then(|v| v.as_u64()).unwrap_or(0),
        root: value
            .get("root")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string(),
    })
}

/// A release build registers no logger (`lib.rs` installs `tauri_plugin_log` only
/// under `cfg!(debug_assertions)`), so a `log::warn!` alone would lose the statement
/// in exactly the build the user installs. The note goes to the file the shell owns.
fn notiz(home: &Path, text: &str) {
    let pfad = home.join(".ephe").join("logs").join("desktop.log");
    if let Some(vater) = pfad.parent() {
        let _ = fs::create_dir_all(vater);
    }
    if let Ok(mut datei) = fs::OpenOptions::new().create(true).append(true).open(&pfad) {
        let _ = writeln!(datei, "{text}");
    }
}

/// The reuse branch has to make the same statement the spawn branch can make.
fn ergebnis_fur_besetzten_port(home: &Path, port: u16) -> Ergebnis {
    match statement(port) {
        None => {
            log::warn!("port {port} answers, but not as an Ephe backend — not treated as ours");
            notiz(
                home,
                &format!("port {port} answered, but not as an Ephe backend; not reused"),
            );
            Ergebnis::FremderPort
        }
        Some(s) if s.api_contract != API_CONTRACT => {
            let found = format!(
                "backend {} speaks contract {}; this shell {} expects contract {}",
                if s.version.is_empty() { "unknown" } else { &s.version },
                s.api_contract,
                env!("CARGO_PKG_VERSION"),
                API_CONTRACT
            );
            log::warn!("incompatible backend on port {port}: {found}");
            notiz(home, &format!("port {port}: {found}; not reused"));
            Ergebnis::Inkompatibel(found)
        }
        Some(s) if s.owner != owner_token() => {
            log::warn!("port {port} holds an Ephe backend this shell did not start — not reused");
            notiz(
                home,
                &format!(
                    "port {port} holds backend {} (pid {}), not started by this shell; not reused",
                    if s.version.is_empty() { "unknown" } else { &s.version },
                    s.pid
                ),
            );
            Ergebnis::FremderPort
        }
        Some(s) if s.key_challenge => {
            // The window still opens on that backend: it is the one the user has.
            // What changes is that the reason is recorded where it can be found.
            log::warn!("the running backend is refused by its engine: {}", s.detail);
            notiz(home, &format!("the running backend is refused by its engine: {}", s.detail));
            Ergebnis::SchonDa
        }
        Some(_) => Ergebnis::SchonDa,
    }
}

fn starten(befehl: &Startbefehl, key: Option<&str>) -> std::io::Result<()> {
    if let Some(vater) = befehl.log.parent() {
        fs::create_dir_all(vater)?;
    }
    let log = fs::OpenOptions::new().create(true).append(true).open(&befehl.log)?;
    let log_fehler = log.try_clone()?;
    let mut cmd = Command::new(&befehl.programm);
    cmd.arg(befehl.projekt.join("run_server.py"))
        .arg("--port")
        .arg(befehl.port.to_string())
        .current_dir(&befehl.projekt)
        .env("EPHE_BACKEND_OWNER", owner_token())
        .env("EPHE_PARENT_PID", std::process::id().to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::from(log))
        .stderr(Stdio::from(log_fehler));
    // The token goes to the child as an environment variable and into no argv, no
    // log line and no config file: a command line is visible in `ps` to every user
    // on the machine, the child's environment only to its own user.
    if let Some(value) = key {
        cmd.env(KEY_ENV, value);
    }
    let child = cmd.spawn()?;
    if let Ok(mut guard) = BACKEND_CHILD.lock() {
        *guard = Some(child);
    }
    Ok(())
}

/// Stop the backend this shell started, and wait for it. A backend the shell
/// found already listening belongs to someone else and is left alone.
pub fn stop_backend() {
    if let Ok(mut guard) = BACKEND_CHILD.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

/// What the start attempted. Blocks at most on the port probe (400 ms), so it
/// belongs on a thread rather than in `setup`.
pub fn sicherstellen(home: &Path, port: u16) -> Ergebnis {
    let text = match fs::read_to_string(konfig_pfad(home)) {
        Ok(t) => t,
        Err(_) => return Ergebnis::KeinBefehl,
    };
    let Some(befehl) = befehl_aus(&text, home) else {
        return Ergebnis::KeinBefehl;
    };
    if !braucht_start(lauscht(port), Some(&befehl)) {
        return ergebnis_fur_besetzten_port(home, port);
    }
    let key = key_for_start(home, std::env::var_os(KEY_ENV).as_deref());
    match starten(&befehl, key.as_deref()) {
        Ok(()) => Ergebnis::Gestartet,
        Err(e) => Ergebnis::StartFehler(e.to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    const ZEILE: &str = r#"{"python":"/x/.venv/bin/python","project_root":"/x/ephe","port":8765}"#;

    #[test]
    fn installerzeile_wird_zum_befehl() {
        let b = befehl_aus(ZEILE, Path::new("/home")).expect("Zeile ist gültig");
        assert_eq!(b.programm, PathBuf::from("/x/.venv/bin/python"));
        assert_eq!(b.projekt, PathBuf::from("/x/ephe"));
        assert_eq!(b.port, 8765);        assert_eq!(b.log, PathBuf::from("/home/.ephe/logs/desktop-backend.log"));
    }

    #[test]
    fn port_ist_optional_und_faellt_auf_die_vereinbarung() {
        let b = befehl_aus(
            r#"{"python":"/p","project_root":"/r"}"#,
            Path::new("/home"),
        )
        .expect("port fehlt, ist aber kein Fehler");
        assert_eq!(b.port, PORT);
    }

    #[test]
    fn leere_pfade_sind_kein_befehl() {
        assert!(befehl_aus(r#"{"python":"","project_root":"/r"}"#, Path::new("/h")).is_none());
        assert!(befehl_aus(r#"{"python":"/p","project_root":"  "}"#, Path::new("/h")).is_none());
        assert!(befehl_aus("kein json", Path::new("/h")).is_none());
    }

    #[test]
    fn gestartet_wird_nur_wenn_keiner_horcht_und_ein_befehl_da_ist() {
        let befehl = befehl_aus(ZEILE, Path::new("/h"));
        assert!(braucht_start(false, befehl.as_ref()));
        assert!(!braucht_start(true, befehl.as_ref()), "Port besetzt → kein zweiter Server");
        assert!(!braucht_start(false, None), "ohne Zeile wird nichts geraten");
    }

    #[test]
    fn ohne_zeile_und_mit_unlesbarer_zeile_passiert_nichts() {
        let home = std::env::temp_dir().join(format!("ephe-backend-{}", std::process::id()));
        let _ = fs::create_dir_all(home.join(".ephe"));
        // no file at all
        assert_eq!(sicherstellen(&home, 4), Ergebnis::KeinBefehl);
        // file exists, but is not JSON
        let _ = fs::write(konfig_pfad(&home), "{ kaputt");
        assert_eq!(sicherstellen(&home, 4), Ergebnis::KeinBefehl);
        // file exists, but the paths are empty
        let _ = fs::write(konfig_pfad(&home), r#"{"python":"","project_root":""}"#);
        assert_eq!(sicherstellen(&home, 4), Ergebnis::KeinBefehl);
        let _ = fs::remove_dir_all(home);
    }

    fn temp_home(tag: &str) -> PathBuf {
        let home =
            std::env::temp_dir().join(format!("ephe-key-{}-{}", std::process::id(), tag));
        let _ = fs::remove_dir_all(&home);
        fs::create_dir_all(home.join(".ephe")).expect("config dir");
        home
    }

    fn write_key(home: &Path, text: &str, mode: u32) {
        fs::write(key_path(home), text).expect("key file");
        fs::set_permissions(key_path(home), fs::Permissions::from_mode(mode)).expect("mode");
    }

    #[test]
    fn owner_only_key_file_reaches_the_start() {
        let home = temp_home("owner");
        write_key(&home, "stored-token\n", 0o600);
        assert_eq!(key_for_start(&home, None).as_deref(), Some("stored-token"));
        // an empty inherited variable is not a chosen one
        assert_eq!(
            key_for_start(&home, Some(std::ffi::OsStr::new(""))).as_deref(),
            Some("stored-token")
        );
        let _ = fs::remove_dir_all(home);
    }

    #[test]
    fn inherited_key_wins_over_the_file() {
        let home = temp_home("inherit");
        write_key(&home, "stored-token", 0o600);
        assert_eq!(key_for_start(&home, Some(std::ffi::OsStr::new("exported-token"))), None);
        let _ = fs::remove_dir_all(home);
    }

    #[test]
    fn a_key_file_that_others_can_read_is_refused() {
        for mode in [0o644_u32, 0o640, 0o606] {
            let home = temp_home(&format!("leaky{mode:o}"));
            write_key(&home, "stored-token", mode);
            assert_eq!(key_for_start(&home, None), None, "mode {mode:o} is not owner-only");
            let _ = fs::remove_dir_all(home);
        }
    }

    #[test]
    fn nothing_stored_and_nothing_chosen_means_no_key() {
        let home = temp_home("absent");
        assert_eq!(key_for_start(&home, None), None);
        // empty file and multi-line file are not a token, and no line is guessed
        write_key(&home, "  \n", 0o600);
        assert_eq!(key_for_start(&home, None), None);
        write_key(&home, "first-token\nsecond-token\n", 0o600);
        assert_eq!(key_for_start(&home, None), None);
        let _ = fs::remove_dir_all(home);
    }

    /// A listener that answers the health question, so the reuse branch has a
    /// peer to talk to. Returns the port it holds.
    fn responder(body: &'static str) -> u16 {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("free port");
        let port = listener.local_addr().expect("addr").port();
        std::thread::spawn(move || {
            for stream in listener.incoming().filter_map(|s| s.ok()) {
                let mut stream = stream;
                // Read the request before answering: a peer that is closed with
                // unread bytes in its receive buffer gets a reset, not a response.
                let mut probe = [0u8; 512];
                let _ = stream.read(&mut probe);
                let answer = format!(
                    "HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: {}\r\n\r\n{}",
                    body.len(),
                    body
                );
                let _ = stream.write_all(answer.as_bytes());
                let _ = stream.flush();
            }
        });
        port
    }

    fn held_port_config(port: u16) -> String {
        format!(r#"{{"python":"/p","project_root":"/r","port":{port}}}"#)
    }

    /// What the release build can still show the user: `~/.ephe/logs/desktop.log`.
    fn note_text(home: &Path) -> Option<String> {
        fs::read_to_string(home.join(".ephe").join("logs").join("desktop.log"))
            .ok()
            .filter(|text| !text.trim().is_empty())
    }

    fn health_body(extra: &str) -> &'static str {
        Box::leak(
            format!(
                r#"{{"status":"ok","version":"{}","api_contract":{},"owner":"{}","instance_id":"i","pid":42,"root":"/x",{}}}"#,
                env!("CARGO_PKG_VERSION"),
                API_CONTRACT,
                owner_token(),
                extra
            )
            .into_boxed_str(),
        )
    }

    #[test]
    fn a_backend_that_reports_a_clean_engine_is_reused() {
        let port = responder(health_body(r#""engine_key_challenge":false,"detail":"engine reachable""#));
        assert_eq!(
            statement(port),
            Some(PeerStatement {
                key_challenge: false,
                detail: "engine reachable".into(),
                version: env!("CARGO_PKG_VERSION").into(),
                api_contract: API_CONTRACT,
                owner: owner_token(),
                instance_id: "i".into(),
                pid: 42,
                root: "/x".into(),
            })
        );
        let home = temp_home("reuse-ok");
        fs::write(konfig_pfad(&home), held_port_config(port)).expect("config");
        assert_eq!(sicherstellen(&home, port), Ergebnis::SchonDa);
        assert!(
            note_text(&home).is_none(),
            "a working start writes no note — the log stays a record of problems"
        );
        let _ = fs::remove_dir_all(home);
    }

    #[test]
    fn a_backend_refused_by_its_engine_is_still_the_backend_the_user_has() {
        let port = responder(health_body(
            r#""engine_key_challenge":true,"detail":"http://h:1/v1 answers HTTP 401 to an unauthenticated request.""#,
        ));
        let said = statement(port).expect("the peer answers");
        assert!(said.key_challenge);
        assert!(said.detail.contains("HTTP 401"));
        let home = temp_home("reuse-challenge");
        fs::write(konfig_pfad(&home), held_port_config(port)).expect("config");
        assert_eq!(sicherstellen(&home, port), Ergebnis::SchonDa);
        let note = note_text(&home).expect("the reuse branch records what it saw");
        assert!(note.contains("HTTP 401"), "{note}");
        let _ = fs::remove_dir_all(home);
    }

    #[test]
    fn a_backend_from_another_shell_is_not_reused() {
        // Same contract, different owner: only the shell that started it may adopt it.
        let body = Box::leak(
            format!(
                r#"{{"status":"ok","version":"{}","api_contract":{},"owner":"someone-else","pid":7,"engine_key_challenge":false}}"#,
                env!("CARGO_PKG_VERSION"),
                API_CONTRACT
            )
            .into_boxed_str(),
        );
        let port = responder(body);
        let home = temp_home("foreign-owner");
        fs::write(konfig_pfad(&home), held_port_config(port)).expect("config");
        assert_eq!(sicherstellen(&home, port), Ergebnis::FremderPort);
        let _ = fs::remove_dir_all(home);
    }

    #[test]
    fn a_backend_on_another_contract_names_both_versions() {
        let body = Box::leak(
            format!(
                r#"{{"status":"ok","version":"0.1.0-beta.1","api_contract":{},"owner":"{}","pid":7,"engine_key_challenge":false}}"#,
                API_CONTRACT + 99,
                owner_token()
            )
            .into_boxed_str(),
        );
        let port = responder(body);
        let home = temp_home("incompatible");
        fs::write(konfig_pfad(&home), held_port_config(port)).expect("config");
        match sicherstellen(&home, port) {
            Ergebnis::Inkompatibel(text) => {
                assert!(text.contains("0.1.0-beta.1"), "{text}");
                assert!(text.contains(&(API_CONTRACT + 99).to_string()), "{text}");
            }
            other => panic!("expected an incompatibility, got {other:?}"),
        }
        let _ = fs::remove_dir_all(home);
    }

    #[test]
    fn a_foreign_listener_is_not_taken_for_our_backend() {
        // The measured gap: `lauscht()` is satisfied by any completed handshake.
        let squatter = std::net::TcpListener::bind("127.0.0.1:0").expect("free port");
        let port = squatter.local_addr().expect("addr").port();
        std::thread::spawn(move || {
            for stream in squatter.incoming().filter_map(|s| s.ok()) {
                let _ = stream; // accepts, never answers
            }
        });
        assert!(lauscht(port), "the port reads as taken");
        assert!(statement(port).is_none(), "a peer that says nothing is not Ephe");
        let home = temp_home("foreign");
        fs::write(konfig_pfad(&home), held_port_config(port)).expect("config");
        assert_eq!(sicherstellen(&home, port), Ergebnis::FremderPort);
        let note = note_text(&home).expect("a foreign listener is worth one line");
        assert!(note.contains("not reused"), "{note}");
        let _ = fs::remove_dir_all(home);
    }

    #[test]
    fn an_answer_that_is_not_the_health_document_is_no_statement() {
        let port = responder(r#"{"status":"ok"}"#);
        assert!(statement(port).is_none(), "no engine_key_challenge field, no claim");
    }

    /// The start config is not a place for a token: an `api_key` field in
    /// desktop.json is ignored, so nobody can put the secret where the engine
    /// choice lives and have it take effect.
    #[test]
    fn desktop_config_line_has_no_place_for_a_key() {
        let with_key = r#"{"python":"/p","project_root":"/r","api_key":"stored-token"}"#;
        let b = befehl_aus(with_key, Path::new("/home")).expect("unknown field is ignored");
        assert_eq!(b.programm, PathBuf::from("/p"));
        assert_eq!(b.log, PathBuf::from("/home/.ephe/logs/desktop-backend.log"));
    }

    #[test]
    fn a_stored_key_is_the_key_the_next_start_reads() {
        let home = temp_home("store");
        store_key(&home, "typed-token\n").expect("stored");
        assert_eq!(key_for_start(&home, None).as_deref(), Some("typed-token"));
        assert!(key_is_stored(&home));
        let mode = fs::symlink_metadata(key_path(&home))
            .expect("file")
            .permissions()
            .mode()
            & 0o777;
        assert_eq!(mode, 0o600, "owner-only from the first byte");
        assert!(
            !key_path(&home).with_extension("key.tmp").exists(),
            "the temp name is renamed away, not left next to the secret"
        );
        let _ = fs::remove_dir_all(home);
    }

    #[test]
    fn an_empty_or_multi_line_key_is_refused_and_nothing_is_written() {
        let home = temp_home("refuse");
        assert!(store_key(&home, "   ").is_err());
        assert!(store_key(&home, "one\ntwo").is_err());
        assert!(
            !key_path(&home).is_file(),
            "a refusal leaves no file behind"
        );
        assert!(!key_is_stored(&home));
        let _ = fs::remove_dir_all(home);
    }

    #[test]
    fn clearing_leaves_the_next_start_with_no_token() {
        let home = temp_home("clear");
        store_key(&home, "typed-token").expect("stored");
        clear_key(&home).expect("removed");
        assert!(!key_is_stored(&home));
        assert_eq!(key_for_start(&home, None), None);
        clear_key(&home).expect("removing what is gone is not a state the surface explains");
        let _ = fs::remove_dir_all(home);
    }

    #[test]
    fn the_store_never_overrides_an_inherited_token() {
        let home = temp_home("precedence");
        store_key(&home, "stored-token").expect("stored");
        assert_eq!(
            key_for_start(&home, Some(std::ffi::OsStr::new("exported-token"))),
            None,
            "the file cannot quietly replace the value exported for this process"
        );
        let _ = fs::remove_dir_all(home);
    }

    #[cfg(unix)]
    #[test]
    fn the_spawned_backend_is_stopped_with_its_shell() {
        let child = Command::new("sleep").arg("30").spawn().expect("spawn sleep");
        let pid = child.id();
        *BACKEND_CHILD.lock().expect("child slot") = Some(child);
        stop_backend();
        assert!(BACKEND_CHILD.lock().expect("child slot").is_none());
        let alive = Command::new("kill")
            .arg("-0")
            .arg(pid.to_string())
            .status()
            .map(|status| status.success())
            .unwrap_or(false);
        assert!(!alive, "the backend child survived stop_backend");
    }
}
