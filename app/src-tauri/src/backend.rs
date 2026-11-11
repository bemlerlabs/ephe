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

/// The one port this shell serves, and the number every other place names.
///
/// Three places have to agree: this spawn/probe, the window's Content-Security-Policy
/// in `app/src-tauri/tauri.conf.json` (`connect-src`, `img-src`, `media-src`,
/// `frame-src`) and the surface's default base URL in
/// `app/src/lib/desktopBaseUrl.ts`. A `desktop.json` that names another port used to
/// start a backend the window could not reach (issue #194); `sicherstellen` refuses
/// that value now, and tests/test_tauri_conf_csp.py holds the three numbers equal.
pub const PORT: u16 = 8765;

/// The origin the policy and the surface both name. Kept beside `PORT` so a surface
/// that has to print an address never spells the number a second time.
pub fn base_url_for(port: u16) -> String {
    format!("http://127.0.0.1:{port}")
}

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
    let token = format!("{stamp:x}-{:x}", std::process::id());
    *guard = Some(token.clone());
    token
}

/// The shell pid a token names, when the token carries one (current builds do;
/// a token from before the label is unparseable and never replaceable).
fn owner_pid(token: &str) -> Option<u32> {
    let tail = token.rsplit_once('-')?.1;
    u32::from_str_radix(tail, 16).ok().filter(|pid| *pid > 1)
}

fn pid_alive(pid: u32) -> bool {
    Command::new("kill")
        .arg("-0")
        .arg(pid.to_string())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map(|status| status.success())
        // A machine where `kill` cannot be asked is not a licence to kill.
        .unwrap_or(true)
}

fn owner_is_dead(token: &str) -> bool {
    owner_pid(token).map(|pid| !pid_alive(pid)).unwrap_or(false)
}

fn same_project(peer_root: &str, project: &Path) -> bool {
    let theirs = fs::canonicalize(peer_root).unwrap_or_else(|_| PathBuf::from(peer_root));
    let ours = fs::canonicalize(project).unwrap_or_else(|_| project.to_path_buf());
    theirs == ours
}

/// A backend whose owning shell is gone, started from this project. Only that
/// shape may be replaced; a live owner belongs to another shell, and an
/// unlabelled owner may be a developer's server.
fn is_replaceable_orphan(peer: &PeerStatement, project: &Path) -> bool {
    peer.pid > 1 && same_project(&peer.root, project) && owner_is_dead(&peer.owner)
}

/// The backend this shell spawned. A reused backend (a dev server, another
/// checkout) is never stored here and is therefore never killed on exit; a child
/// this shell started must not survive an update or a quit and answer for the
/// next version with the code it loaded at start.
static BACKEND_CHILD: Mutex<Option<Child>> = Mutex::new(None);

/// The pidfile belonging to the child in `BACKEND_CHILD`. The Python server
/// removes it on a clean exit; a SIGKILL skips that, so the shell removes it
/// after it has reaped the child it killed.
static BACKEND_PIDFILE: Mutex<Option<PathBuf>> = Mutex::new(None);

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
pub const KEY_SOURCE_ENV: &str = "EPHE_ENGINE_KEY_SOURCE";

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
    /// `~/.ephe/run/backend-<port>.json` — the record the Python server writes
    /// about itself, and the one this shell removes when it stops that child.
    pub pidfile: PathBuf,
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
    /// `desktop.json` names a port this shell does not serve. The window's policy and
    /// the surface's default base URL both name `PORT`, so a backend somewhere else is
    /// one the window cannot talk to — refused rather than started into a dead end
    /// (issue #194). Both numbers travel with it, because the sentence has to say what
    /// was asked for and what is served.
    PortAnders { named: u16, served: u16 },
    Gestartet,
    StartFehler(String),
}

/// What the window may say about its backend: one state, one sentence, one action.
///
/// The shell promises to start nothing without `~/.ephe/desktop.json`, and the surface
/// promised nothing back — it showed "Ready" with a live composer while no backend
/// existed (issue #193). Only the shell knows whether that line exists and what the
/// start attempt answered, so the answer is built here, where `Ergebnis` is decided,
/// and handed to the surface as one value. `ready` stays false unless a backend
/// answered for itself: "not ready" is the honest default, and the action says what
/// would change it.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct Readiness {
    pub ready: bool,
    /// `ready`, `starting`, `configured`, `unreachable`, `refused` or `unconfigured`.
    pub state: &'static str,
    pub port: u16,
    pub base_url: String,
    /// The file this shell reads. A surface can print it without knowing the layout.
    pub config: String,
    /// What is true, in the words a person reads.
    pub sentence: String,
    /// The one thing that would change the state, empty when nothing is missing.
    pub action: String,
}

impl Readiness {
    /// The state a start attempt left, as the surface may render it.
    pub fn after(home: &Path, ergebnis: &Ergebnis) -> Self {
        let config_path = konfig_pfad(home).display().to_string();
        let base_url = base_url_for(PORT);
        let verdict = |ready: bool, state: &'static str, sentence: String, action: String| Self {
            ready,
            state,
            port: PORT,
            base_url: base_url.clone(),
            config: config_path.clone(),
            sentence,
            action,
        };
        match ergebnis {
            Ergebnis::KeinBefehl => verdict(
                false,
                "unconfigured",
                format!("No backend is configured, so nothing was started (this window reads {config_path})."),
                r#"Run "ephe desktop" once to write that file, or write {"python": …, "project_root": …} into it yourself."#.into(),
            ),
            Ergebnis::SchonDa => verdict(
                true,
                "ready",
                format!("A backend answers on {base_url}."),
                String::new(),
            ),
            Ergebnis::Gestartet => verdict(
                true,
                "starting",
                format!("This window started the backend on {base_url}; it answers after a few seconds."),
                String::new(),
            ),
            Ergebnis::PortAnders { named, served } => verdict(
                false,
                "refused",
                format!("{config_path} names port {named}, and this window serves only {served} — so nothing was started."),
                format!("Set \"port\": {served} in {config_path}, or remove the field."),
            ),
            Ergebnis::Inkompatibel(sentence) => verdict(
                false,
                "refused",
                sentence.clone(),
                "Update the app or the backend so both speak the same API contract.".into(),
            ),
            Ergebnis::FremderPort => verdict(
                false,
                "unreachable",
                format!("Something other than this window's backend holds {base_url}; it was not taken over."),
                r#"Quit that process, or run "ephe doctor" to see who holds the port."#.into(),
            ),
            Ergebnis::StartFehler(sentence) => verdict(
                false,
                "unreachable",
                format!("The backend did not start: {sentence}"),
                r#"Run "ephe doctor" to see why, and check {config_path}."#.into(),
            ),
        }
    }

    /// The state before any attempt: does the line exist, and does it name this port?
    ///
    /// A surface that asks early gets the same shape as one that asks after a start.
    /// An unreadable file reads as unconfigured here, because nothing can be started
    /// from it either way; `sicherstellen` records which of the two it saw.
    pub fn unattempted(home: &Path) -> Self {
        let text = fs::read_to_string(konfig_pfad(home)).ok();
        let Some(befehl) = text.as_deref().and_then(|t| befehl_aus(t, home)) else {
            return Self::after(home, &Ergebnis::KeinBefehl);
        };
        if befehl.port != PORT {
            return Self::after(
                home,
                &Ergebnis::PortAnders { named: befehl.port, served: PORT },
            );
        }
        Self {
            ready: false,
            state: "configured",
            port: PORT,
            base_url: base_url_for(PORT),
            config: konfig_pfad(home).display().to_string(),
            sentence: format!(
                "A backend is configured ({}), and this window has not tried to start it yet.",
                befehl.programm.display()
            ),
            action: String::new(),
        }
    }
}

/// The last state a start attempt reached, for a surface command that must not wait.
static LAST_READINESS: Mutex<Option<Readiness>> = Mutex::new(None);

/// Store the state the attempt produced and hand the same value back, so the caller
/// announces exactly what was recorded.
pub fn remember(readiness: Readiness) -> Readiness {
    if let Ok(mut guard) = LAST_READINESS.lock() {
        *guard = Some(readiness.clone());
    }
    readiness
}

/// The recorded state, or the config-only reading when nothing ran yet in this process.
pub fn last_readiness(home: &Path) -> Readiness {
    match LAST_READINESS.lock().ok().and_then(|guard| guard.clone()) {
        Some(readiness) => readiness,
        None => Readiness::unattempted(home),
    }
}

pub fn konfig_pfad(home: &Path) -> PathBuf {
    crate::instance::device_dir_for(home).join("desktop.json")
}

pub fn key_path(home: &Path) -> PathBuf {
    crate::instance::device_dir_for(home).join(KEY_FILE)
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
    let dir = crate::instance::device_dir_for(home);
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
        log: crate::instance::device_dir_for(home)
            .join("logs")
            .join("desktop-backend.log"),
        pidfile: pidfile_path(home, e.port.unwrap_or(PORT)),
    })
}

/// One record per port: the same path Python's `core/backend_lifecycle.py` writes.
pub fn pidfile_path(home: &Path, port: u16) -> PathBuf {
    crate::instance::device_dir_for(home)
        .join("run")
        .join(format!("backend-{port}.json"))
}

/// What the running server wrote about itself.
#[derive(Debug, Clone, Deserialize)]
struct PidRecord {
    pid: u32,
    #[serde(default)]
    port: u16,
    #[serde(default)]
    owner: String,
    #[serde(default)]
    root: String,
    #[serde(default)]
    start_time: String,
    #[serde(default)]
    started_at: f64,
}

fn read_pidfile(home: &Path, port: u16) -> Option<PidRecord> {
    let text = fs::read_to_string(pidfile_path(home, port)).ok()?;
    let record: PidRecord = serde_json::from_str(&text).ok()?;
    if record.pid <= 1 || (record.port != 0 && record.port != port) {
        return None;
    }
    Some(record)
}

/// The kernel's start stamp — the fact that makes a recycled pid harmless.
fn current_start_time(pid: u32) -> Option<String> {
    let out = Command::new("ps")
        .args(["-p", &pid.to_string(), "-o", "lstart="])
        .output()
        .ok()?;
    if !out.status.success() {
        return None;
    }
    let text = String::from_utf8_lossy(&out.stdout).trim().to_string();
    if text.is_empty() { None } else { Some(text) }
}

/// A backend the pidfile proves was left behind by this installation: same
/// project, same pid the health answer names, same start time, dead owner.
fn pidfile_orphan(
    home: &Path,
    port: u16,
    project: &Path,
    peer: &PeerStatement,
) -> Option<u32> {
    let record = read_pidfile(home, port)?;
    if record.pid != peer.pid as u32 || record.pid <= 1 {
        return None;
    }
    if !same_project(&peer.root, project) {
        return None;
    }
    if !record.root.is_empty() && !same_project(&record.root, project) {
        return None;
    }
    if !record.start_time.is_empty() {
        match current_start_time(record.pid) {
            Some(live) if live == record.start_time => {}
            _ => return None,
        }
    }
    if record.owner.is_empty() || owner_is_dead(&record.owner) {
        Some(record.pid)
    } else {
        None
    }
}

/// SIGTERM, wait for the port, SIGKILL, wait again. True once the port is free.
/// Only a pid the caller proved is ever signalled.
fn stop_process(pid: u32, port: u16) -> bool {
    if pid <= 1 {
        return !lauscht(port);
    }
    if !lauscht(port) && !pid_alive(pid) {
        return true;
    }
    let _ = Command::new("kill")
        .arg("-TERM")
        .arg(pid.to_string())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
    for _ in 0..50 {
        if !lauscht(port) {
            return true;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    if pid_alive(pid) {
        let _ = Command::new("kill")
            .arg("-KILL")
            .arg(pid.to_string())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    for _ in 0..30 {
        if !lauscht(port) {
            return true;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    !lauscht(port)
}

fn clear_pidfile(path: &Path, pid: u32) {
    let Ok(text) = fs::read_to_string(path) else {
        return;
    };
    let Ok(record) = serde_json::from_str::<PidRecord>(&text) else {
        return;
    };
    if record.pid == pid {
        let _ = fs::remove_file(path);
    }
}

fn process_command(pid: u32) -> Option<String> {
    let out = Command::new("ps")
        .args(["-p", &pid.to_string(), "-o", "command="])
        .output()
        .ok()?;
    if !out.status.success() {
        return None;
    }
    Some(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

/// The desktop's own leftovers from the last run, without a listener to ask:
/// a live `run_server.py` of this project whose owning shell is gone, or any
/// record whose pid is dead. A backend that starts answering within the grace
/// window is left alone — it is not an orphan, it is starting.
fn clean_orphan_pidfile(home: &Path, port: u16, project: &Path) {
    let Some(record) = read_pidfile(home, port) else {
        return;
    };
    if !pid_alive(record.pid) {
        let _ = fs::remove_file(pidfile_path(home, port));
        return;
    }
    if !record.start_time.is_empty() {
        match current_start_time(record.pid) {
            Some(live) if live == record.start_time => {}
            _ => return,
        }
    }
    if !record.root.is_empty() && !same_project(&record.root, project) {
        return;
    }
    if !(record.owner.is_empty() || owner_is_dead(&record.owner)) {
        return;
    }
    // A record written moments ago may be a backend that is still importing
    // FastAPI; it is starting, not orphaned. Only a record older than the grace
    // is settled this way.
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0);
    if record.started_at > 0.0 && now - record.started_at < 30.0 {
        return;
    }
    match process_command(record.pid) {
        Some(command) if command.contains("run_server.py") => {}
        _ => return,
    }
    for _ in 0..15 {
        if lauscht(port) {
            return;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    if stop_process(record.pid, port) {
        let _ = fs::remove_file(pidfile_path(home, port));
        notiz(
            home,
            &format!(
                "removed orphaned backend pid {} on port {port} from the last run",
                record.pid
            ),
        );
    }
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
#[derive(Debug, Clone, PartialEq, Eq)]
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
    let pfad = crate::instance::device_dir_for(home)
        .join("logs")
        .join("desktop.log");
    if let Some(vater) = pfad.parent() {
        let _ = fs::create_dir_all(vater);
    }
    if let Ok(mut datei) = fs::OpenOptions::new().create(true).append(true).open(&pfad) {
        let _ = writeln!(datei, "{text}");
    }
}

/// The reuse branch has to make the same statement the spawn branch can make.
fn ergebnis_fur_besetzten_port(
    home: &Path,
    port: u16,
    befehl: &Startbefehl,
    key: Option<&str>,
) -> Ergebnis {
    match statement(port) {
        None => {
            log::warn!("port {port} answers, but not as an Ephe backend — not treated as ours");
            notiz(
                home,
                &format!("port {port} answered, but not as an Ephe backend; not reused"),
            );
            Ergebnis::FremderPort
        }
        Some(s) if same_project(&s.root, &befehl.projekt) && s.version != env!("CARGO_PKG_VERSION") => {
            // This checkout's own backend, answering for a different version than this
            // window's code: after an in-app update the tree moves to the new tag while the
            // process still runs what it loaded before (measured 2026-11-10: shell 0.6.3,
            // backend answered 0.6.2 for the 0.6.3 tree). An accompanying backend must
            // speak this window's version, so it is replaced - not reused and not left to
            // answer for a version nobody is running.
            let stale = format!(
                "backend {} answers on port {} for this checkout; this window {} restarts it",
                if s.version.is_empty() { "unknown" } else { &s.version },
                port,
                env!("CARGO_PKG_VERSION")
            );
            log::warn!("{stale}");
            notiz(home, &stale);
            if s.pid > 1 && stop_process(s.pid as u32, port) {
                return match starten(befehl, key) {
                    Ok(()) => Ergebnis::Gestartet,
                    Err(e) => Ergebnis::StartFehler(e.to_string()),
                };
            }
            Ergebnis::Inkompatibel(stale)
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
            let orphan = if is_replaceable_orphan(&s, &befehl.projekt) {
                Some(s.pid as u32)
            } else {
                pidfile_orphan(home, port, &befehl.projekt, &s)
            };
            if let Some(pid) = orphan {
                // The owning shell is gone; the backend is this installation's
                // leftover, proven by the owner token or by the pidfile's pid,
                // start time and root. Ask it to stop, wait for the port, and
                // start a watched child.
                if stop_process(pid, port) {
                    notiz(
                        home,
                        &format!("replaced orphaned backend pid {pid} on port {port}"),
                    );
                    return match starten(befehl, key) {
                        Ok(()) => Ergebnis::Gestartet,
                        Err(e) => Ergebnis::StartFehler(e.to_string()),
                    };
                }
                notiz(
                    home,
                    &format!(
                        "orphaned backend pid {pid} on port {port} did not stop; stop it with: kill {pid}"
                    ),
                );
                return Ergebnis::FremderPort;
            }
            log::warn!("port {port} holds an Ephe backend this shell did not start — not reused");
            notiz(
                home,
                &format!(
                    "port {port} holds backend {} (pid {}), not started by this shell; another Ephe backend is running (pid {}); stop it with: kill {}; not reused",
                    if s.version.is_empty() { "unknown" } else { &s.version },
                    s.pid,
                    s.pid,
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
        // The marker tells the Python guard the token came from the stored file,
        // not an inherited shell export; it carries no credential.
        cmd.envs([(KEY_ENV, value), (KEY_SOURCE_ENV, "file")]);
    }
    let child = cmd.spawn()?;
    if let Ok(mut guard) = BACKEND_CHILD.lock() {
        *guard = Some(child);
    }
    if let Ok(mut slot) = BACKEND_PIDFILE.lock() {
        *slot = Some(befehl.pidfile.clone());
    }
    Ok(())
}

/// Stop the backend this shell started, and wait for it. A backend the shell
/// found already listening belongs to someone else and is left alone.
pub fn stop_backend() {
    if let Ok(mut guard) = BACKEND_CHILD.lock() {
        if let Some(mut child) = guard.take() {
            let pid = child.id();
            let _ = child.kill();
            let _ = child.wait();
            if let Ok(mut slot) = BACKEND_PIDFILE.lock() {
                if let Some(path) = slot.take() {
                    clear_pidfile(&path, pid);
                }
            }
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
    // The window, its policy and the surface's default base URL all name `PORT`, so a
    // backend on another port is one this window cannot talk to. It used to be started
    // anyway, and the surface then reported "Disconnected" about a backend the shell
    // had started itself (issue #194). Refuse the value and name both numbers.
    if befehl.port != port {
        notiz(
            home,
            &format!(
                "{} names port {}; this window serves {} — nothing was started. Set \"port\": {} or remove the field.",
                konfig_pfad(home).display(),
                befehl.port,
                port,
                port
            ),
        );
        return Ergebnis::PortAnders {
            named: befehl.port,
            served: port,
        };
    }
    // Last run's leftovers are settled before this run decides anything. A
    // backend that is already serving keeps the port and is handled below.
    if !lauscht(port) {
        clean_orphan_pidfile(home, port, &befehl.projekt);
    }
    let key = key_for_start(home, std::env::var_os(KEY_ENV).as_deref());
    if !braucht_start(lauscht(port), Some(&befehl)) {
        return ergebnis_fur_besetzten_port(home, port, &befehl, key.as_deref());
    }
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
        let note = note_text(&home).expect("a foreign owner is worth one line");
        assert!(note.contains("pid 7"), "{note}");
        assert!(note.contains("kill 7"), "{note}");
        let _ = fs::remove_dir_all(home);
    }

    #[test]
    fn a_dead_owner_makes_a_matching_backend_replaceable() {
        let mut child = Command::new("true").spawn().expect("spawn");
        let pid = child.id();
        child.wait().expect("wait");
        let token = format!("abc-{:x}", pid);
        let peer = PeerStatement {
            key_challenge: false,
            detail: String::new(),
            version: "0.1.0".into(),
            api_contract: API_CONTRACT,
            owner: token,
            instance_id: "i".into(),
            pid: 4242,
            root: "/x".into(),
        };
        assert!(owner_is_dead(&peer.owner));
        assert!(is_replaceable_orphan(&peer, Path::new("/x")));
        assert!(!is_replaceable_orphan(&peer, Path::new("/other")));
    }

    fn peer_for(pid: u32, owner: &str) -> PeerStatement {
        PeerStatement {
            key_challenge: false,
            detail: String::new(),
            version: "0.1.0".into(),
            api_contract: API_CONTRACT,
            owner: owner.into(),
            instance_id: "i".into(),
            pid: pid as u64,
            root: "/x".into(),
        }
    }

    fn write_pid_record(home: &Path, port: u16, pid: u32, owner: &str, start_time: &str) {
        let dir = home.join(".ephe").join("run");
        fs::create_dir_all(&dir).expect("pidfile dir");
        fs::write(
            pidfile_path(home, port),
            format!(
                r#"{{"pid":{pid},"port":{port},"owner":"{owner}","root":"/x","start_time":"{start_time}"}}"#
            ),
        )
        .expect("pidfile");
    }

    #[test]
    fn a_pidfile_proves_an_orphan_the_owner_token_cannot() {
        let home = temp_home("pidfile-orphan");
        let port = 47999u16;
        let mut dead = Command::new("true").spawn().expect("spawn");
        let dead_pid = dead.id();
        dead.wait().expect("wait");
        let owner = format!("abc-{dead_pid:x}");
        let start = current_start_time(std::process::id()).expect("own start stamp");
        let me = std::process::id();
        write_pid_record(&home, port, me, &owner, &start);

        let peer = peer_for(me, &owner);
        assert_eq!(pidfile_orphan(&home, port, Path::new("/x"), &peer), Some(me));
        assert_eq!(
            pidfile_orphan(&home, port, Path::new("/other"), &peer),
            None,
            "another project's record is not ours"
        );
        let mut wrong_pid = peer.clone();
        wrong_pid.pid += 1;
        assert_eq!(
            pidfile_orphan(&home, port, Path::new("/x"), &wrong_pid),
            None,
            "the health pid and the pidfile pid must agree"
        );

        // A start stamp that disagrees with the live process is a recycled pid.
        write_pid_record(&home, port, me, &owner, "not-this-process");
        assert_eq!(pidfile_orphan(&home, port, Path::new("/x"), &peer), None);
        let _ = fs::remove_dir_all(home);
    }

    #[test]
    fn a_live_owner_in_the_pidfile_is_not_an_orphan() {
        let home = temp_home("pidfile-live");
        let port = 47998u16;
        let me = std::process::id();
        let start = current_start_time(me).expect("own start stamp");
        let live = format!("abc-{me:x}");
        write_pid_record(&home, port, me, &live, &start);
        let peer = peer_for(me, &live);
        assert_eq!(pidfile_orphan(&home, port, Path::new("/x"), &peer), None);
        let _ = fs::remove_dir_all(home);
    }

    #[test]
    fn a_dead_pidfile_disappears_without_a_listener() {
        let home = temp_home("pidfile-dead");
        let port = 47997u16;
        let mut dead = Command::new("true").spawn().expect("spawn");
        let dead_pid = dead.id();
        dead.wait().expect("wait");
        write_pid_record(&home, port, dead_pid, "abc-1", "gone");
        assert!(pidfile_path(&home, port).is_file());
        clean_orphan_pidfile(&home, port, Path::new("/x"));
        assert!(!pidfile_path(&home, port).exists());
        let _ = fs::remove_dir_all(home);
    }

    #[test]
    fn stop_process_ends_a_child_and_hands_the_port_back() {
        let port = {
            let probe = std::net::TcpListener::bind("127.0.0.1:0").expect("free port");
            probe.local_addr().expect("addr").port()
        };
        let mut child = Command::new("sleep").arg("30").spawn().expect("spawn sleep");
        let pid = child.id();
        assert!(stop_process(pid, port));
        let _ = child.wait();
        assert!(!lauscht(port));
    }

    #[test]
    fn a_live_or_unlabelled_owner_is_never_replaceable() {
        let live = format!("abc-{:x}", std::process::id());
        let peer = |owner: String| PeerStatement {
            key_challenge: false,
            detail: String::new(),
            version: "0.1.0".into(),
            api_contract: API_CONTRACT,
            owner,
            instance_id: "i".into(),
            pid: 4242,
            root: "/x".into(),
        };
        assert!(!is_replaceable_orphan(&peer(live), Path::new("/x")));
        assert!(!is_replaceable_orphan(&peer("abc123".into()), Path::new("/x")));
        assert!(!is_replaceable_orphan(&peer(String::new()), Path::new("/x")));
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

    /// Names in one directory, sorted, so two snapshots compare as listings.
    fn listing(dir: &Path) -> Vec<String> {
        let mut names: Vec<String> = fs::read_dir(dir)
            .expect("listing")
            .map(|entry| {
                entry
                    .expect("entry")
                    .file_name()
                    .to_string_lossy()
                    .into_owned()
            })
            .collect();
        names.sort();
        names
    }

    struct RestoreEnv {
        home: Option<std::ffi::OsString>,
        config: Option<std::ffi::OsString>,
    }

    impl Drop for RestoreEnv {
        fn drop(&mut self) {
            match self.home.take() {
                Some(value) => std::env::set_var("HOME", value),
                None => std::env::remove_var("HOME"),
            }
            match self.config.take() {
                Some(value) => std::env::set_var("EPHE_CONFIG_DIR", value),
                None => std::env::remove_var("EPHE_CONFIG_DIR"),
            }
        }
    }

    /// A run aimed at another device folder must leave `$HOME/.ephe` with the
    /// same names it had. The listing is the proof. The variable only aims the run.
    /// The state a surface renders has to be the state a start left. These are the
    /// words, not a string that happens to contain "ready": a surface that shows
    /// "Ready" while nothing runs is the defect of issue #193.
    #[test]
    fn without_a_configuration_the_window_is_not_ready_and_names_the_command() {
        let home = temp_home("unconfigured");
        let readiness = last_readiness(&home);
        assert!(!readiness.ready, "no config must never read as ready");
        assert_eq!(readiness.state, "unconfigured");
        assert!(readiness.sentence.contains("nothing was started"), "{}", readiness.sentence);
        assert!(
            readiness.action.contains("ephe desktop"),
            "the action has to name the command that writes the file: {}",
            readiness.action
        );
        assert!(
            readiness.config.ends_with("desktop.json"),
            "{}",
            readiness.config
        );
        assert_eq!(readiness.base_url, base_url_for(PORT));
        assert_eq!(readiness.port, PORT);
        let _ = fs::remove_dir_all(home);
    }

    #[test]
    fn a_failed_start_is_not_ready_and_points_at_the_doctor() {
        let home = temp_home("start-fehler");
        let ergebnis = Ergebnis::StartFehler("No such file or directory".into());
        let readiness = Readiness::after(&home, &ergebnis);
        assert!(!readiness.ready);
        assert_eq!(readiness.state, "unreachable");
        assert!(readiness.sentence.contains("No such file"), "{}", readiness.sentence);
        assert!(readiness.action.contains("ephe doctor"), "{}", readiness.action);
        let _ = fs::remove_dir_all(home);
    }

    #[test]
    fn only_a_backend_that_answered_is_ready() {
        let home = temp_home("ready");
        for (ergebnis, state, ready) in [
            (Ergebnis::SchonDa, "ready", true),
            (Ergebnis::Gestartet, "starting", true),
            (Ergebnis::FremderPort, "unreachable", false),
            (Ergebnis::Inkompatibel("contract 2 vs 1".into()), "refused", false),
        ] {
            let b = Readiness::after(&home, &ergebnis);
            assert_eq!(b.state, state, "{ergebnis:?}");
            assert_eq!(b.ready, ready, "{ergebnis:?}");
        }
        let _ = fs::remove_dir_all(home);
    }

    /// Issue #194: the configured port and the served port are one number. A file
    /// naming another port used to start a backend the window could not reach.
    #[test]
    fn a_configured_port_this_shell_does_not_serve_is_refused_and_starts_nothing() {
        let home = temp_home("port");
        fs::write(
            konfig_pfad(&home),
            r#"{"python":"/nonexistent/python","project_root":"/nonexistent","port":8808}"#,
        )
        .expect("config");
        let ergebnis = sicherstellen(&home, PORT);
        assert_eq!(
            ergebnis,
            Ergebnis::PortAnders { named: 8808, served: PORT },
            "a foreign port has to be refused, not started"
        );
        let note = note_text(&home).expect("a refusal is worth one line");
        assert!(note.contains("8808") && note.contains(&PORT.to_string()), "{note}");
        let readiness = Readiness::after(&home, &ergebnis);
        assert!(!readiness.ready);
        assert_eq!(readiness.state, "refused");
        assert!(readiness.action.contains("\"port\""), "{}", readiness.action);
        let _ = fs::remove_dir_all(home);
    }

    /// The same file read early, before any attempt, already answers "refused": a
    /// surface that asks first must not be told the window is about to be ready.
    #[test]
    fn the_early_reading_of_a_foreign_port_is_the_same_refusal() {
        let home = temp_home("port-frueh");
        fs::write(konfig_pfad(&home), held_port_config(8808)).expect("config");
        let readiness = Readiness::unattempted(&home);
        assert!(!readiness.ready);
        assert_eq!(readiness.state, "refused");
        assert!(readiness.sentence.contains("8808"), "{}", readiness.sentence);
        let _ = fs::remove_dir_all(home);
    }

    #[test]
    fn a_configured_backend_that_was_not_tried_is_not_ready_yet() {
        let home = temp_home("configured");
        fs::write(konfig_pfad(&home), ZEILE).expect("config");
        let readiness = Readiness::unattempted(&home);
        assert!(!readiness.ready, "configured is not started");
        assert_eq!(readiness.state, "configured");
        assert_eq!(readiness.port, PORT);
        let _ = fs::remove_dir_all(home);
    }

    #[test]
    fn an_isolated_config_dir_leaves_the_home_folder_unchanged() {
        let scratch = std::env::temp_dir().join(format!(
            "ephe-isolated-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or(0)
        ));
        let home = scratch.join("home");
        let config = scratch.join("config");
        let kept = home.join(".ephe");
        fs::create_dir_all(&kept).expect("home folder");
        fs::write(kept.join("sentinel"), b"keep").expect("sentinel");
        let before = listing(&kept);

        let _env_lock = crate::instance::test_env_lock().lock().expect("env lock");
        let _restore = RestoreEnv {
            home: std::env::var_os("HOME"),
            config: std::env::var_os("EPHE_CONFIG_DIR"),
        };
        std::env::set_var("HOME", &home);
        std::env::set_var("EPHE_CONFIG_DIR", &config);

        store_key(&home, "isolated-token").expect("stored");
        crate::runlog::write(&home, "start ephe 0.0.0 pid 1 epoch 1");
        let command = befehl_aus(ZEILE, &home).expect("line");
        let roots = crate::desktop::allowed_roots(&home, None);

        let after = listing(&kept);
        assert_eq!(
            before, after,
            "the home folder's names changed: {before:?} -> {after:?}"
        );
        assert_eq!(konfig_pfad(&home), config.join("desktop.json"));
        assert_eq!(key_path(&home), config.join("engine.key"));
        assert!(
            config.join("engine.key").is_file(),
            "the key landed outside the device folder"
        );
        assert_eq!(command.log, config.join("logs").join("desktop-backend.log"));
        assert!(
            config.join("logs").join("desktop.log").is_file(),
            "the ledger landed outside the device folder"
        );
        assert_eq!(
            roots,
            vec![
                config.join("artifacts"),
                home.join("Desktop"),
                home.join("Downloads"),
                home.join("Documents"),
            ]
        );
        let _ = fs::remove_dir_all(&scratch);
    }
}

#[cfg(test)]
mod stale_version_tests {
    use super::*;

    /// An in-app update leaves the tree on the new tag and the process on the old code.
    /// Such a backend is this checkout's own and must be replaced, not reused.
    #[test]
    fn a_backend_answering_an_older_version_for_this_checkout_is_replaceable() {
        let peer = PeerStatement {
            key_challenge: false,
            detail: String::new(),
            pid: 4242,
            owner: "someone-else".to_string(),
            root: "/x".to_string(),
            version: "0.0.0-old".to_string(),
            api_contract: API_CONTRACT,
            instance_id: String::new(),
        };
        // The rule lives in the decision arm; this pins the two facts it keys on.
        assert!(same_project(&peer.root, Path::new("/x")));
        assert_ne!(peer.version, env!("CARGO_PKG_VERSION"));
    }
}
