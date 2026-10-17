#!/usr/bin/env python3
"""Reproducible build of the pinned CPython WASI guest (wave E1).

The guest (~29 MB interpreter + stdlib tree) must NOT enter git. It lives under
``~/.ephe/cells/<install_dir>`` and is verified against ``core/cpython_guest.manifest.json``.
The recipe below is the single source of truth for what has to be built so the hashes in
the manifest stay reproducible — a guest without a recipe is a rumour.

Flow (every step can also be invoked alone via the flags):

  fetch   load the Python source and wasi-sdk with pinned SHA-256
  build   ``Tools/wasm/wasi.py`` cross-build, patch ``ac_cv_func_fdatasync=no``
  stage   stdlib tree from the source (pristine) + _sysconfigdata + bytecode
  install open-write-delete into ``~/.ephe/cells``, read-only afterwards (0444/0555)
  record  write the entry hash + tree digest back into the manifest
  smoke   ``print(1+1)`` through core.cpython_cell — if the run fails, the script fails

Why the patch is needed: Ephemora Cell refuses every Preview1 module that imports
``fd_datasync`` (wasi_runtime P1 #12); CPython's ``os.fdatasync`` pulls exactly that
import. Without the option no CPython runs inside the cell.

Why the stdlib is read-only: the guest has ``/`` as a preopen. A write test showed
that otherwise a model can rebuild its own interpreter (json/__init__.py = "x").
Read-only file permissions are the plain answer; the manifest digest additionally
checks that the tree is unchanged.

Examples::

    python3 build_cpython_guest.py                 # everything
    python3 build_cpython_guest.py --no-build      # stage/install/record/smoke
    python3 build_cpython_guest.py --verify        # just look
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent
MANIFEST_FILE = REPO / "core" / "cpython_guest.manifest.json"
sys.path.insert(0, str(REPO))

#: was tested during the build (Darwin arm64); other platforms need their own pins.
SDK_URLS = {
    "arm64-macos": (
        "https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-24/wasi-sdk-24.0-arm64-macos.tar.gz",
        "aeae999396d5f5caa5ce419f52e83c35869d5fd21d40af80acba2c80f51b0b3a",
    ),
}

#: Folders an agent never needs that only inflate the tree.
PRUNE_DIRS = {"test", "tests", "idle_test", "turtledemo", "site-packages", "__pycache__"}
PRUNE_SUFFIXES = {".whl", ".png", ".gif", ".svg", ".po", ".mo", ".xpm", ".tm"}


def log(msg: str) -> None:
    print(f"[guest-build] {msg}", flush=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(root: Path) -> tuple[str, int]:
    """(SHA-256 over path+content, file count) — the same computation as core.cpython_cell."""
    lines: list[str] = []
    count = 0
    for path in sorted(root.rglob("*")):
        if path.is_file():
            count += 1
            lines.append(f"{path.relative_to(root).as_posix()}\0{sha256_file(path)}\n")
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest(), count


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))


def save_manifest(man: dict[str, Any]) -> None:
    MANIFEST_FILE.write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")



def _download(url: str, target: Path) -> None:
    import urllib.request

    log(f"downloading {url}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as resp, target.open("wb") as fh:
        shutil.copyfileobj(resp, fh)


def _fetch_pinned(url: str, sha256: str, target: Path, label: str) -> None:
    if not target.is_file():
        _download(url, target)
    actual = sha256_file(target)
    if actual != sha256:
        raise SystemExit(
            f"{label} SHA-256 mismatch: {actual} != {sha256} ({target}). "
            "Nothing is built — check the manifest pin or re-record it."
        )
    log(f"{label} verified ({target.name})")


def fetch(scratch: Path, man: dict[str, Any], *, force: bool) -> tuple[Path, Path]:
    prov = man["provenance"]
    sdk = SDK_URLS.get(_platform())
    if sdk is None:
        raise SystemExit(
            f"no wasi-sdk pin for platform {_platform()}; the recorded build ran on "
            "Darwin arm64 (wasi-sdk 24.0-arm64-macos). Add the pin and try again."
        )
    tarballs = {
        "wasi-sdk.tar.gz": (sdk[0], sdk[1]),
        "Python.tar.xz": (prov["source_url"], prov["source_sha256"]),
    }
    if force:
        for name in tarballs:
            (scratch / name).unlink(missing_ok=True)
    sdk_path, py_path = scratch / "wasi-sdk.tar.gz", scratch / "Python.tar.xz"
    _fetch_pinned(*tarballs["wasi-sdk.tar.gz"], target=sdk_path, label="wasi-sdk")
    _fetch_pinned(*tarballs["Python.tar.xz"], target=py_path, label="Python sources")
    _extract(sdk_path, scratch / "wasi-sdk", "wasi-sdk")
    _extract(py_path, scratch / "Python-src", "Python-")
    return _sdk_dir(scratch / "wasi-sdk"), _checkout(scratch)


def _sdk_dir(target: Path) -> Path:
    """The folder holding `bin/clang` — the archive carries its version as the top folder."""
    for root in (target, *sorted(target.glob("wasi-sdk*"))):
        if (root / "bin" / "clang").is_file():
            return root
    raise SystemExit(f"no wasi-sdk with bin/clang under {target} — check the archive")


def _platform() -> str:
    import platform

    machine = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x86_64"}.get(
        platform.machine().lower(), platform.machine().lower()
    )
    system = {"Darwin": "macos", "Linux": "linux"}.get(platform.system(), platform.system().lower())
    return f"{machine}-{system}"


def _extract(archive: Path, target: Path, prefix: str) -> None:
    if any(target.glob(f"{prefix}*")):
        return
    target.mkdir(parents=True, exist_ok=True)
    log(f"extracting {archive.name} -> {target}")
    # filter="data" (Python >= 3.12): no paths outside the target folder.
    with tarfile.open(archive) as tf:
        tf.extractall(target, filter="data")


def _checkout(scratch: Path) -> Path:
    """The source folder — freshly unpacked or from earlier manual work."""
    for root in (scratch / "Python-src", scratch):
        candidates = sorted(root.glob("Python-*/Lib"))
        if candidates:
            return candidates[0].parent
    raise SystemExit(f"no Python checkout under {scratch / 'Python-src'} or {scratch}")



def build(scratch: Path, sdk: Path, jobs: int) -> Path:
    checkout = _checkout(scratch)
    # MAKEFLAGS instead of `-j`: wasi.py only passes configure-* arguments through,
    # make-build-python knows no `--` (it would abort with "unrecognized arguments").
    env = dict(os.environ, WASI_SDK_PATH=str(sdk), MAKEFLAGS=f"-j{jobs}")
    wasi = [sys.executable, "Tools/wasm/wasi.py"]
    steps = [
        (wasi + ["configure-build-python"], "configure build-Python"),
        (wasi + ["make-build-python"], "build build-Python"),
        (wasi + ["configure-host", "--host-runner", "echo", "--", "ac_cv_func_fdatasync=no"],
         "host-configure (without fdatasync)"),
    ]
    for cmd, label in steps:
        _run(cmd, cwd=checkout, env=env, label=label)
    # make-host would invoke the runner for every test action; the echo-runner
    # + direct make is the same build without the wasmtime CLI (Ephemora uses the
    # wasmtime Python binding, not the program).
    cross = checkout / "cross-build" / "wasm32-wasip1"
    # absolute: wasi-env sits in the source root, the make runs in cross-build/…
    _run([str(checkout / "Tools/wasm/wasi-env"), "make", "all"],
         cwd=cross, env=env, label="build CPython for wasm32-wasip1")
    entry = cross / "python.wasm"
    if not entry.is_file():
        raise SystemExit(f"the build produced no {entry}")
    return entry


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str], label: str) -> None:
    log(f"{label}: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stdout + "\n" + result.stderr)[-4000:]
        raise SystemExit(f"{label} failed (exit {result.returncode}):\n{tail}")



def _keep(rel: Path) -> bool:
    if any(part in PRUNE_DIRS for part in rel.parts):
        return False
    if rel.suffix in PRUNE_SUFFIXES:
        return False
    return True


def stage(scratch: Path, entry: Path, man: dict[str, Any]) -> Path:
    checkout = _checkout(scratch)
    stage_dir = scratch / "stage"
    if stage_dir.exists():
        shutil.rmtree(stage_dir)  # stage/ holds only what this script built here
    version = str(man["guest"]["version"])  # 3.13.16 -> directory python3.13
    # Layout = exactly the installation directory: <entry> + stdlib_dir/usr/local/…
    lib_target = (stage_dir / str(man["guest"]["stdlib_dir"])
                  / "usr" / "local" / "lib" / f"python{'.'.join(version.split('.')[:2])}")
    lib_target.mkdir(parents=True)
    shutil.copy2(entry, stage_dir / Path(man["guest"]["entry"]))

    copied = 0
    for source in sorted((checkout / "Lib").rglob("*")):
        rel = source.relative_to(checkout / "Lib")
        if source.is_dir():
            lib_target.joinpath(rel).mkdir(parents=True, exist_ok=True)
            continue
        if not _keep(rel):
            continue
        shutil.copy2(source, lib_target / rel)
        copied += 1

    # sysconfig without this file cannot let the interpreter find its platform
    # (PYTHONHOME=/usr/local covers the stdlib; build_time_vars needs this file).
    for candidate in (checkout / "cross-build").rglob("_sysconfigdata__wasi_*.py"):
        shutil.copy2(candidate, lib_target / candidate.name)
        break

    guest_pair = tuple(int(part) for part in version.split(".")[:2])
    if sys.version_info[:2] == guest_pair:
        # Timestamp-based .pyc of the sources: boot ~0.86 s instead of import-compile.
        _run([sys.executable, "-m", "compileall", "-q", "-f", str(lib_target)],
             cwd=checkout, env=dict(os.environ), label="pre-compile bytecode")
    else:
        log(f"WARNING: host Python {sys.version.split()[0]} is not {'.'.join(map(str, guest_pair))} — "
            "without matching .pyc the guest loads slower")

    log(f"stdlib staged: {copied} source files in {lib_target}")
    return stage_dir



def install(stage_dir: Path, target: Path) -> None:
    cells_root = (target.parent.parent / "cells").resolve()
    if not str(target.resolve()).startswith(str(cells_root) + os.sep):
        raise SystemExit(f"target {target} is not under {cells_root} — aborting")
    if target.exists():
        for path in [target, *target.rglob("*")]:
            try:
                path.chmod(0o700 if path.is_dir() else 0o600)
            except OSError:
                pass
        shutil.rmtree(target)
        log(f"removed the old installation ({target})")
    shutil.copytree(stage_dir, target, symlinks=False)
    # Read-only: the guest has / as a preopen, and a write test showed a
    # self-manipulating interpreter. The lid = permissions + manifest digest.
    for path in sorted(target.rglob("*"), key=lambda p: str(p), reverse=True):
        path.chmod(0o555 if path.is_dir() else 0o444)
    target.chmod(0o555)
    log(f"installed to {target} (read-only)")



def record(target: Path, man: dict[str, Any]) -> dict[str, Any]:
    entry = target / man["guest"]["entry"]
    root = target / man["guest"]["stdlib_dir"]
    digest, files = tree_digest(root)
    man["guest"].update({
        "entry_sha256": sha256_file(entry),
        "entry_bytes": entry.stat().st_size,
        "root_tree_sha256": digest,
        "root_tree_files": files,
    })
    man["provenance"]["toolchain"]["host"] = f"{sys.platform} {_platform()}"
    save_manifest(man)
    log(f"manifest written: entry={man['guest']['entry_sha256'][:12]}… "
        f"tree={digest[:12]}… ({files} files)")
    return man


def smoke(session: str = "guest-build-smoke") -> None:
    import asyncio

    from core import cpython_cell, cpython_guest

    if not cpython_guest.cell_ready():
        state = cpython_guest.guest_state(deep=True)
        raise SystemExit(f"guest is not verified after installation: {state['reason']}")
    report = asyncio.run(cpython_cell.run_python("print(1 + 1)", session, reset=True))
    if "2" not in report.get("stdout", "") or report.get("status") != "OK":
        raise SystemExit(f"smoke run failed: {cpython_cell.format_report(report)}")
    log("smoke run print(1+1) -> 2 inside the cell")


def verify(man: dict[str, Any]) -> int:
    from core import cpython_guest

    state = cpython_guest.guest_state(deep=True)
    for key in ("version", "installed", "library", "entry_ok", "tree_ok", "reason", "path"):
        print(f"  {key}: {state[key]}")
    ok = bool(state["entry_ok"] and state["tree_ok"])
    print(f"[guest-build] {'verified' if ok else 'UNVERIFIED'}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scratch", default=None, help="build folder (default: ~/.ephe/build/cpython-wasi)")
    parser.add_argument("--no-build", action="store_true", help="reuse sources/build, only stage+install")
    parser.add_argument("--verify", action="store_true", help="only check the installation against the manifest")
    parser.add_argument("--stage-only", action="store_true",
                        help="build and stage, but do not install: compare the hashes")
    parser.add_argument("--force-download", action="store_true", help="re-fetch the archive even if it exists")
    parser.add_argument("--jobs", type=int, default=max(2, (os.cpu_count() or 4) - 1))
    parser.add_argument("--skip-smoke", action="store_true")
    args = parser.parse_args(argv)

    man = load_manifest()
    from core import engine_config

    config_dir = Path(engine_config.CONFIG_DIR)
    target = config_dir / man["guest"]["install_dir"]

    if args.verify:
        return verify(man)

    scratch = Path(args.scratch) if args.scratch else config_dir / "build" / "cpython-wasi"
    scratch.mkdir(parents=True, exist_ok=True)

    if args.no_build:
        entry = _checkout(scratch) / "cross-build" / "wasm32-wasip1" / "python.wasm"
        if not entry.is_file():
            raise SystemExit(f"--no-build needs an existing build: {entry} is missing")
        log(f"build skipped, using {entry}")
    else:
        sdk, _ = fetch(scratch, man, force=args.force_download)
        entry = build(scratch, sdk, args.jobs)

    stage_dir = stage(scratch, entry, man)
    if args.stage_only:
        root = stage_dir / str(man["guest"]["stdlib_dir"])
        digest, files = tree_digest(root)
        log(f"built:   entry {sha256_file(entry)} ({entry.stat().st_size} bytes)")
        log(f"built:   tree  {digest} ({files} files)")
        log(f"pinned:  entry {man['guest']['entry_sha256']} / tree {man['guest']['root_tree_sha256']}")
        return 0
    install(stage_dir, target)
    record(target, man)
    if not args.skip_smoke:
        smoke()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
