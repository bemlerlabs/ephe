#!/usr/bin/env python3
"""The start-up numbers `docs/PERFORMANCE_BASELINE.md` publishes, from the checkout's own code.

Task #39 asked for measured start-up costs instead of a claim. This is the instrument behind
the table: it starts *this* tree's server in a subprocess, polls `/api/health` until the first
200, and reports the median over N runs. Three definitions the numbers need, because "start-up"
is only comparable when each one is fixed:

* **ready** is the first HTTP 200 from `/api/health`, not the first line on stderr and not the
  bind. The desktop shell treats a backend as usable when that route answers, so the number
  describes the thing the product waits for.
* **cold** removes the first-party `__pycache__` trees (`core/`, `server/`, the checkout root)
  before *each* run, so every sample compiles the sources again. **warm** runs one unmeasured
  start first and then leaves the bytecode caches in place. Neither mode drops the OS file cache
  -- that needs root on macOS -- so "cold" here means cold bytecode. The measured difference is
  what the cache is worth; a reboot costs more.
* **pinned config**: the run gets `EPHE_MODEL_PROVIDER=local_ollama`, a model tag and a closed
  loopback port for the probe. Without it the number would follow whatever `engine.json` on the
  machine points at (a remote engine can spend the probe's 2 s timeout), which makes the table
  depend on one person's config. `--live` drops the pin and measures the machine's real choice;
  the doc carries both rows where it matters, each labelled.

Commands, one per mode (from the checkout root, inside the project venv):

    python scripts/bench_startup.py --runs 5                 # cold and warm health 200
    python scripts/bench_startup.py --runs 5 --imports --imports-cold
    python scripts/bench_startup.py --runs 5 --doctor        # `ephe doctor`
    python scripts/bench_startup.py --runs 5 --live          # the machine's engine.json
    python scripts/bench_startup.py --runs 3 --warm-only \
      --env EPHE_MODEL_PROVIDER=openai_compatible --env EPHE_OPENAI_COMPAT_BASE_URL=...

The output is the table the doc quotes; `--json PATH` also writes it machine-readably. Nothing
here writes into the checkout (config, logs and the health probe's state go to a temp folder),
and no repository file is modified except the `__pycache__` directories `--cold` removes and
Python recreates.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import queue
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
#: The modules a cold start has to compile from source. Site-packages bytecode ships in the
#: wheels and is not this checkout's to invalidate, so only first-party trees are cleared.
COLD_TREES = ("core", "server", "utils", "scripts")
#: How long one start may take before it is a failed measurement rather than a slow one. The
#: warm median on the machine this was written on is 1.2 s; 60 s is not a budget, it is a stop.
READY_TIMEOUT_S = 60.0
POLL_INTERVAL_S = 0.005


@dataclass
class Sample:
    """One start: when the banner named the port, and when `/api/health` first answered."""

    banner_ms: float = 0.0
    ready_ms: float = 0.0
    port: int = 0
    status: str = ""
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "banner_ms": round(self.banner_ms, 1),
            "ready_ms": round(self.ready_ms, 1),
            "port": self.port,
            "status": self.status,
            "error": self.error,
        }


@dataclass
class ImportSample:
    total_ms: float = 0.0
    #: (module, self time in ms). Cumulative already contains the children, so a ranking by
    #: cumulative would put `server.main` and its ancestors on every row; the doc asks what
    #: the modules cost themselves.
    self_ms: list[tuple[str, float]] = field(default_factory=list)


def _machine() -> dict:
    """What the table has to name, so a number can be compared with another machine."""
    import subprocess as sp

    def run(*cmd: str) -> str:
        try:
            out = sp.run(cmd, capture_output=True, text=True, timeout=10, check=False)
            return out.stdout.strip()
        except (OSError, sp.SubprocessError):
            return ""

    return {
        "platform": platform.platform(),
        "machine": run("sysctl", "-n", "hw.model") or platform.machine(),
        "cpu": run("sysctl", "-n", "machdep.cpu.brand_string") or platform.processor(),
        "python": platform.python_version(),
        "git": run("git", "-C", str(ROOT), "rev-parse", "--short=12", "HEAD"),
        "date": time.strftime("%Y-%m-%d"),
    }


def _child_env(config_dir: Path, live: bool, overrides: dict[str, str] | None = None) -> dict:
    """The environment every start runs with. `--live` is the only branch that reads user state."""
    env = dict(os.environ)
    env.pop("EPHE_SETUP_MODE", None)
    env["EPHE_CONFIG_DIR"] = str(config_dir)
    env["PYTHONUNBUFFERED"] = "1"
    # Kill inherited knobs that would make two machines' numbers describe different products.
    for name in ("PYTHONSTARTUP", "PYTHONPATH"):
        env.pop(name, None)
    if live:
        env.update(overrides or {})
        return env
    env.update(
        {
            "EPHE_MODEL_PROVIDER": "local_ollama",
            "EPHE_MODEL": "bench:1b",
            "EPHE_LOCAL_OLLAMA_BASE_URL": "http://127.0.0.1:9",
        }
    )
    env.update(overrides or {})
    return env


def _clear_caches() -> int:
    removed = 0
    for tree in COLD_TREES:
        base = ROOT / tree
        if not base.is_dir():
            continue
        for cache in base.rglob("__pycache__"):
            if ".venv" in cache.parts:
                continue
            shutil.rmtree(cache, ignore_errors=True)
            removed += 1
    for cache in ROOT.glob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
        removed += 1
    return removed


def _read_banner(proc: subprocess.Popen, out: "queue.Queue[str]") -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        out.put(line)


def _start_once(env: dict, workdir: Path) -> Sample:
    sample = Sample()
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "run_server.py"), "--port", "0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        cwd=str(workdir),
    )
    lines: "queue.Queue[str]" = queue.Queue()
    reader = threading.Thread(target=_read_banner, args=(proc, lines), daemon=True)
    reader.start()
    try:
        deadline = t0 + READY_TIMEOUT_S
        port = 0
        tail: list[str] = []
        while time.perf_counter() < deadline:
            try:
                line = lines.get(timeout=0.05)
            except queue.Empty:
                if proc.poll() is not None:
                    break
                continue
            tail.append(line.rstrip())
            if "URL:" in line:
                port = int(line.rsplit(":", 1)[1].strip())
                sample.banner_ms = (time.perf_counter() - t0) * 1000.0
                break
        if not port:
            sample.error = "no port in the start banner: " + " | ".join(tail[-4:])
            return sample
        sample.port = port
        url = f"http://127.0.0.1:{port}/api/health"
        while time.perf_counter() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=1.0) as resp:
                    body = resp.read()
                    if resp.status == 200:
                        payload = json.loads(body or b"{}")
                        sample.ready_ms = (time.perf_counter() - t0) * 1000.0
                        sample.status = str(payload.get("status", ""))
                        return sample
            except (urllib.error.URLError, ConnectionError, OSError, ValueError):
                time.sleep(POLL_INTERVAL_S)
        sample.error = "no 200 from /api/health within %.0f s" % READY_TIMEOUT_S
        return sample
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        reader.join(timeout=1)


def bench_startup(
    runs: int,
    cold: bool,
    live: bool,
    config_dir: Path,
    workdir: Path,
    overrides: dict[str, str] | None = None,
) -> dict:
    env = _child_env(config_dir, live, overrides)
    if not cold:
        # One unmeasured start so the first measured sample is not the one that pays for
        # the compile; the doc calls that state "warm".
        _start_once(env, workdir)
    samples: list[Sample] = []
    for i in range(runs):
        if cold:
            _clear_caches()
        sample = _start_once(env, workdir)
        samples.append(sample)
        state = sample.error or f"ready {sample.ready_ms:.0f} ms"
        print(f"  run {i + 1}/{runs}: {state}", flush=True)
    ok = [s for s in samples if not s.error]
    if not ok:
        return {"mode": "cold" if cold else "warm", "runs": runs, "samples": []}
    return {
        "mode": "cold" if cold else "warm",
        "runs": runs,
        "samples": [s.as_dict() for s in samples],
        "banner_ms": {
            "median": round(statistics.median(s.banner_ms for s in ok), 1),
            "min": round(min(s.banner_ms for s in ok), 1),
            "max": round(max(s.banner_ms for s in ok), 1),
        },
        "ready_ms": {
            "median": round(statistics.median(s.ready_ms for s in ok), 1),
            "min": round(min(s.ready_ms for s in ok), 1),
            "max": round(max(s.ready_ms for s in ok), 1),
        },
    }


def _parse_importtime(stderr: str) -> ImportSample:
    """`python -X importtime` lines are `import time: self | cumulative | name` (µs)."""
    sample = ImportSample()
    for line in stderr.splitlines():
        if not line.startswith("import time:"):
            continue
        _, _, rest = line.partition(":")
        parts = rest.split("|")
        if len(parts) != 3:
            continue
        try:
            self_us = int(parts[0].strip())
            cumulative_us = int(parts[1].strip())
        except ValueError:
            continue
        name = parts[2].strip()
        if name == "server.main":
            sample.total_ms = cumulative_us / 1000.0
        if name:
            sample.self_ms.append((name, self_us / 1000.0))
    return sample


def bench_import(runs: int, workdir: Path, cold: bool = False) -> dict:
    """`import server.main`, N runs, the top ten modules by self time."""
    samples: list[ImportSample] = []
    for i in range(runs):
        if cold:
            _clear_caches()
        proc = subprocess.run(
            [sys.executable, "-X", "importtime", "-c", "import server.main"],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        parsed = _parse_importtime(proc.stderr)
        samples.append(parsed)
        print(f"  run {i + 1}/{runs}: import {parsed.total_ms:.0f} ms", flush=True)
    totals = [s.total_ms for s in samples if s.total_ms]
    if not totals:
        return {"runs": runs, "samples": []}
    # The median run is quoted whole, so its module list sums to the quoted total; a median
    # per module taken over runs that import different paths would not.
    totals_sorted = sorted(totals)
    median_total = totals_sorted[len(totals_sorted) // 2]
    median_run = min(samples, key=lambda s: abs(s.total_ms - median_total))
    top = sorted(median_run.self_ms, key=lambda item: item[1], reverse=True)[:10]
    return {
        "mode": "cold" if cold else "warm",
        "runs": runs,
        "total_median_ms": round(statistics.median(totals), 1),
        "total_min_ms": round(min(totals), 1),
        "total_max_ms": round(max(totals), 1),
        "median_run_total_ms": round(median_run.total_ms, 1),
        "top_self_ms": [{"module": name, "self_ms": round(cost, 2)} for name, cost in top],
    }


def bench_doctor(runs: int, workdir: Path) -> dict:
    """`ephe doctor` against this machine as it is (its own engine.json, its own network).

    The exit code is a verdict (`1` = a required check failed); a timed run
    counts whatever verdict it reached, and the number is only the wall clock. A doctor with
    a pinned, dead engine would answer a different question than the user's, so this mode
    ignores the bench's temp config on purpose.
    """
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env.pop("EPHE_SETUP_MODE", None)
    times: list[float] = []
    for i in range(runs):
        t0 = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, str(ROOT / "ephe_cli.py"), "doctor", "--json"],
            cwd=str(workdir),
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        elapsed = (time.perf_counter() - t0) * 1000.0
        print(f"  run {i + 1}/{runs}: doctor {elapsed:.0f} ms (exit {proc.returncode})", flush=True)
        if proc.returncode in (0, 1):
            times.append(elapsed)
    if not times:
        return {"runs": runs, "samples": []}
    return {
        "runs": runs,
        "median_ms": round(statistics.median(times), 0),
        "min_ms": round(min(times), 0),
        "max_ms": round(max(times), 0),
        "samples": [round(t) for t in times],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=5, help="measured repetitions (default 5)")
    parser.add_argument("--imports", action="store_true", help="also measure `import server.main`")
    parser.add_argument(
        "--imports-cold", action="store_true", help="measure the import with the caches cleared"
    )
    parser.add_argument("--doctor", action="store_true", help="also measure `ephe doctor`")
    parser.add_argument("--warm-only", action="store_true", help="skip the cold half")
    parser.add_argument("--live", action="store_true", help="use the machine's engine.json, unpinned")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="extra environment for the measured start, applied after the pin (repeatable)",
    )
    parser.add_argument("--json", type=Path, help="write the result here as JSON")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be >= 1")
    overrides = {}
    for item in args.env:
        key, sep, value = item.partition("=")
        if not sep or not key:
            parser.error(f"--env wants KEY=VALUE, got {item!r}")
        overrides[key] = value

    result: dict = {"machine": _machine(), "pinned": not args.live}
    config_dir = Path(tempfile.mkdtemp(prefix="ephe-bench-config-"))
    workdir = Path(tempfile.mkdtemp(prefix="ephe-bench-work-"))
    try:
        modes = ["warm"] if args.warm_only else ["cold", "warm"]
        result["startup"] = []
        for mode in modes:
            print(f"startup ({mode}):", flush=True)
            result["startup"].append(
                bench_startup(args.runs, cold=mode == "cold", live=args.live,
                              config_dir=config_dir, workdir=workdir, overrides=overrides)
            )
        if args.imports or args.imports_cold:
            result["import"] = []
        if args.imports:
            print("import (`import server.main`, warm):", flush=True)
            result["import"].append(bench_import(args.runs, workdir, cold=False))
        if args.imports_cold:
            print("import (`import server.main`, cold):", flush=True)
            result["import"].append(bench_import(args.runs, workdir, cold=True))
        if args.doctor:
            print("doctor:", flush=True)
            result["doctor"] = bench_doctor(args.runs, workdir)
    finally:
        shutil.rmtree(config_dir, ignore_errors=True)
        shutil.rmtree(workdir, ignore_errors=True)

    print("\nresult:")
    print(json.dumps(result, indent=2))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
