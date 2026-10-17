from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from core._cli_common import LOCAL_OLLAMA_BASE_URL, LOCAL_OLLAMA_HOST, MAX_VOICE_BYTES, PROJECT_ROOT, _json_get, _json_post, _print_check, _run, _venv_python

def _ollama_binary() -> str | None:
    candidates = [
        "/Applications/Ollama.app/Contents/Resources/ollama",
        "/opt/homebrew/opt/ollama/bin/ollama",
        "/opt/homebrew/bin/ollama",
        "/usr/local/bin/ollama",
        shutil.which("ollama"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def _ollama_model_candidates(model: str) -> list[str]:
    """MLX/nvfp4 variants of the tag the user named — Apple Silicon ships them as a
    suffix on the same tag, for whichever tag that is (owner decision 2026-10-11:
    the probe used to be keyed to one hardcoded model and stopped applying to any
    other)."""
    candidates = [model]
    if sys.platform == "darwin" and model:
        candidates.extend([f"{model}-mlx", f"{model}-nvfp4"])
    return list(dict.fromkeys(candidates))


def _ollama_env() -> dict[str, str]:
    env = os.environ.copy()
    env["OLLAMA_HOST"] = LOCAL_OLLAMA_HOST
    return env


def _local_ollama_detected() -> bool:
    """Fail-safe check: is a local Ollama engine running? (offline-first detection)."""
    return _json_get(f"{LOCAL_OLLAMA_BASE_URL}/api/tags", timeout=1.0) is not None


def _model_installed(model: str) -> bool:
    ollama = _ollama_binary()
    if not ollama:
        return False
    result = subprocess.run(
        [ollama, "show", model],
        text=True,
        env=_ollama_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _model_loadable(model: str) -> tuple[bool, str]:
    response = _json_post(
        f"{LOCAL_OLLAMA_BASE_URL}/api/generate",
        {"model": model, "prompt": "OK", "stream": False, "options": {"num_predict": 1}},
        timeout=30.0,
    )
    if response is None:
        return False, "could not generate a test token"
    if response.get("error"):
        return False, str(response["error"])
    return True, "test generation ok"


def _wait_for_ollama_service(timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _json_get(f"{LOCAL_OLLAMA_BASE_URL}/api/tags", timeout=1.0) is not None:
            return True
        time.sleep(0.5)
    return False


def _ensure_ollama_service() -> tuple[bool, str]:
    if _json_get(f"{LOCAL_OLLAMA_BASE_URL}/api/tags", timeout=1.0) is not None:
        return True, "Ollama service is running"

    ollama = _ollama_binary()
    if not ollama:
        return False, "Ollama CLI not found. Run install.sh or install Ollama first."

    subprocess.Popen(
        [ollama, "serve"],
        cwd=PROJECT_ROOT,
        env=_ollama_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if _wait_for_ollama_service():
        return True, "Ollama service started"
    return False, f"Ollama service did not become ready on {LOCAL_OLLAMA_BASE_URL}"


def _pull_model(model: str) -> tuple[bool, str]:
    ollama = _ollama_binary()
    if not ollama:
        return False, "Ollama CLI not found"

    saw_version_error = False
    attempted_upgrade = False
    for candidate in _ollama_model_candidates(model):
        result = subprocess.run(
            [ollama, "pull", candidate],
            cwd=PROJECT_ROOT,
            text=True,
            env=_ollama_env(),
            capture_output=True,
        )
        if result.returncode == 0:
            suffix = "" if candidate == model else f" as {candidate}"
            return True, f"pulled {model}{suffix}"
        combined = f"{result.stdout or ''}\n{result.stderr or ''}"
        if "requires a newer version of Ollama" not in combined:
            continue
        saw_version_error = True
        if attempted_upgrade:
            continue
        attempted_upgrade = True
        upgraded, upgrade_detail = _upgrade_ollama()
        if not upgraded:
            continue
        ollama = _ollama_binary()
        if not ollama:
            return False, "Ollama updated but CLI not found"
        retry = subprocess.run(
            [ollama, "pull", candidate],
            cwd=PROJECT_ROOT,
            text=True,
            env=_ollama_env(),
            capture_output=True,
        )
        if retry.returncode == 0:
            suffix = "" if candidate == model else f" as {candidate}"
            return True, f"pulled {model}{suffix} after Ollama update"
    if saw_version_error:
        version_detail = _ollama_version_detail(_ollama_binary())
        return False, (
            "Ollama is still too old for this Gemma 4 manifest. "
            f"Install the latest Ollama from https://ollama.com/download and retry. {version_detail}"
        )
    return False, f"ollama pull {model} failed"


def _upgrade_ollama() -> tuple[bool, str]:
    if sys.platform == "darwin":
        if not shutil.which("brew"):
            return False, "Ollama is too old. Install the latest version from https://ollama.com/download"
        if subprocess.run(["brew", "list", "--formula", "ollama"], cwd=PROJECT_ROOT, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            subprocess.run(["brew", "uninstall", "--formula", "ollama"], cwd=PROJECT_ROOT, text=True)
        commands = [
            ["brew", "reinstall", "--cask", "ollama-app"],
            ["brew", "upgrade", "--cask", "ollama-app"],
            ["brew", "install", "--cask", "ollama-app"],
            ["brew", "reinstall", "--cask", "ollama"],
            ["brew", "upgrade", "--cask", "ollama"],
            ["brew", "install", "--cask", "ollama"],
        ]
        for command in commands:
            result = subprocess.run(command, cwd=PROJECT_ROOT, text=True)
            if result.returncode == 0:
                subprocess.run(["pkill", "-x", "Ollama"], cwd=PROJECT_ROOT, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["pkill", "-f", "ollama serve"], cwd=PROJECT_ROOT, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(2)
                _ensure_ollama_service()
                return True, "Ollama updated"
        return False, "Ollama update failed via Homebrew; install latest from https://ollama.com/download"

    result = subprocess.run(
        ["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
        cwd=PROJECT_ROOT,
        text=True,
    )
    if result.returncode == 0:
        return True, "Ollama updated"
    return False, "Ollama update failed"


def _ollama_version_detail(ollama: str | None) -> str:
    if not ollama:
        return "Ollama CLI not found."
    result = subprocess.run([ollama, "--version"], cwd=PROJECT_ROOT, text=True, capture_output=True)
    output = (result.stdout or result.stderr or "").strip()
    return f"Current CLI: {output}" if output else f"Current CLI: {ollama}"


def _repair_repo() -> tuple[bool, str]:
    if not (PROJECT_ROOT / ".git").exists():
        return True, "not a git checkout"

    status = _run(["git", "status", "--short"], env=os.environ.copy(), capture_output=True)
    if status.returncode != 0:
        return False, "could not inspect git status"
    if (status.stdout or "").strip():
        return False, "local changes present; skip git pull to protect your work"

    fetch = _run(["git", "fetch", "--quiet", "origin"], env=os.environ.copy())
    if fetch.returncode != 0:
        return False, "git fetch failed"

    branch = _run(["git", "branch", "--show-current"], env=os.environ.copy(), capture_output=True)
    branch_name = (branch.stdout or "").strip() if branch.returncode == 0 else ""
    if not branch_name:
        return True, "detached HEAD; skip auto-update"

    behind = _run(["git", "rev-list", "--count", f"HEAD..origin/{branch_name}"], env=os.environ.copy(), capture_output=True)
    if behind.returncode != 0:
        return False, "could not compare with origin"
    if (behind.stdout or "").strip() in ("", "0"):
        return True, "repo up to date"

    pull = _run(["git", "pull", "--ff-only"], env=os.environ.copy())
    if pull.returncode != 0:
        return False, "git pull --ff-only failed"
    return True, "repo updated"


def _repair_dependencies() -> tuple[bool, str]:
    if not (PROJECT_ROOT / "pyproject.toml").exists():
        return False, "pyproject.toml missing"
    cmd = [_venv_python(), "-m", "pip", "install", "-e", ".[gui,voice]"]
    result = _run(cmd, env=os.environ.copy())
    if result.returncode == 0:
        return True, "dependencies installed"
    return False, "dependency install failed"


def _ensure_model_ready_for_start(model: str) -> tuple[bool, str]:
    service_ok, service_detail = _ensure_ollama_service()
    if not service_ok:
        return False, service_detail

    if not _model_installed(model):
        pulled, pull_detail = _pull_model(model)
        if not pulled:
            return False, pull_detail

    ready, detail = _model_loadable(model)
    if ready:
        return True, detail

    pulled, pull_detail = _pull_model(model)
    if not pulled:
        return False, f"{detail}; repair failed: {pull_detail}"

    ready, detail = _model_loadable(model)
    if ready:
        return True, f"{pull_detail}; {detail}"
    return False, f"{pull_detail}; still not loadable: {detail}"


def ensure_pwa_built() -> bool:
    """PWA build (app/dist) ensured, built on the fly when it is missing.

    Root cause (2026-08-21): ``app/dist`` is a git-ignored build artifact.
    A fresh clone does not have it — the server would otherwise have served
    just a fallback page under ``/``. Anyone using ``ephe start`` should
    still get the PWA immediately: install and build in ``app/``.

    Package manager (2026-10-09): pnpm, the same path ``install.sh``'s
    ``build_pwa()`` takes. The previous npm call was not cosmetic — ``npm
    install`` writes ``app/package-lock.json`` on the way, so one ``ephe start``
    on a fresh clone produced the second lockfile that
    ``tests/test_r46_pnpm_single_source.py`` forbids, and failed that suite from
    inside this function.

    Idempotent: if ``app/dist/index.html`` already exists, nothing happens.
    Missing pnpm/Node is not an error but a warning (the API keeps
    running, the fallback page shows the build instructions).
    """
    dist_index = PROJECT_ROOT / "app" / "dist" / "index.html"
    if dist_index.is_file():
        return True

    app_dir = PROJECT_ROOT / "app"
    package_json = app_dir / "package.json"
    if not package_json.is_file():
        _print_check(False, "PWA-Build", "app/package.json missing — PWA cannot be built; the server shows a fallback page at /")
        return False

    if shutil.which("pnpm") is None:
        _print_check(
            False,
            "PWA-Build",
            "pnpm not found — PWA is missing (server shows a fallback page at /). "
            "Enable the pinned package manager (corepack enable, needs Node.js from "
            f"https://nodejs.org) and run again: pnpm --dir {app_dir} install --frozen-lockfile"
            f" && pnpm --dir {app_dir} run build",
        )
        return False

    _print_check(True, "PWA-Build", "app/dist is missing — building the PWA now (pnpm install + pnpm run build in app/) …")
    env = os.environ.copy()
    env["OLLAMA_HOST"] = LOCAL_OLLAMA_HOST
    try:
        install = _run(["pnpm", "--dir", str(app_dir), "install", "--frozen-lockfile"], env=env, check=False)
        if install.returncode != 0:
            # lockfile problems: a plain install, the same fallback install.sh uses
            install = _run(["pnpm", "--dir", str(app_dir), "install"], env=env, check=False)
        if install.returncode == 0:
            build = _run(["pnpm", "--dir", str(app_dir), "run", "build"], env=env, check=False)
            if build.returncode == 0 and dist_index.is_file():
                _print_check(True, "PWA-Build", "app/dist/index.html present — PWA ready")
                return True
            _print_check(False, "PWA-Build", "Build finished, but app/dist/index.html is missing — the server shows a fallback page at /")
            return False
        _print_check(False, "PWA-Build", "pnpm failed — the server shows a fallback page at / (the API remains reachable)")
        return False
    except Exception as exc:  # the PWA build may never block startup
        _print_check(False, "PWA-Build", f"PWA build problem: {exc} — the server shows a fallback page at /")
        return False


def _download_piper_voice(name: str) -> Path:
    """Downloads a Piper voice (onnx + json) from the model repo — opt-in, size-capped.

    Naming schema: {locale}-{name}-{quality}, e.g. en_US-amy-medium or
    de_DE-thorsten-medium → path segments inside rhasspy/piper-voices.
    """
    import httpx

    from core.voice_config import voices_dir

    parts = name.split("-")
    if len(parts) != 3:
        raise ValueError(f"Invalid voice name: {name!r} (Schema: locale-name-quality, z. B. en_US-amy-medium)")
    locale, voice_name, quality = parts
    lang = locale.split("_")[0]
    base = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang}/{locale}/{voice_name}/{quality}/{name}"
    out_dir = voices_dir()

    def _fetch(url: str, dest: Path, max_bytes: int) -> None:
        resp = httpx.get(url, follow_redirects=True, timeout=httpx.Timeout(300.0, connect=15.0))
        resp.raise_for_status()
        if len(resp.content) > max_bytes:
            raise ValueError(f"Download too large: {len(resp.content)} > {max_bytes} Bytes")
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_bytes(resp.content)
        tmp.replace(dest)

    _fetch(f"{base}.onnx", out_dir / f"{name}.onnx", MAX_VOICE_BYTES)
    _fetch(f"{base}.onnx.json", out_dir / f"{name}.onnx.json", 1 * 1024 * 1024)
    return out_dir / f"{name}.onnx"
