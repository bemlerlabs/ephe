#!/usr/bin/env python3
"""Run one plugin's golden matrix and record every rep with its provenance.

The engine is whatever `ephe configure` persisted; this script never picks one.
A missing engine, a missing golden suite or an existing report without --force
is an error, not a fallback.

    python3 scripts/catalog_matrix.py documents --runs 3 --out docs/MATRIX.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_golden  # noqa: E402
from core.engine_config import resolve_engine_choice  # noqa: E402


def _git(*args: str) -> str:
    done = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else ""


def provenance() -> dict:
    choice = resolve_engine_choice()
    status = _git("status", "--porcelain")
    return {
        "provider": getattr(choice, "provider", ""),
        "model": getattr(choice, "model", ""),
        "api_url": getattr(choice, "api_url", ""),
        "commit": _git("rev-parse", "HEAD"),
        "dirty": bool(status),
        "date": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
    }


def _code_shell_workspace() -> tuple[str, str]:
    """A disposable project with one failing test; the matrix never touches a real repo."""
    root = Path(tempfile.mkdtemp(prefix="ephe-bench-code-shell-"))
    (root / "calc.py").write_text(
        "def total(values):\n"
        "    \"\"\"Return the sum of all values.\"\"\"\n"
        "    return values[0] + values[1] + values[2]\n",
        encoding="utf-8",
    )
    (root / "test_calc.py").write_text(
        "from calc import total\n\n\n"
        "def test_total_sums_two_values():\n"
        "    assert total([1, 2]) == 3\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# Bench fixture\n\nA tiny project for the code-shell matrix.\n", encoding="utf-8"
    )
    digest = hashlib.sha256()
    for path in sorted(root.iterdir()):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    subprocess.run(["git", "init", "-q"], cwd=root, check=False)
    subprocess.run(["git", "add", "."], cwd=root, check=False)
    subprocess.run(
        ["git", "-c", "user.name=Bench", "-c", "user.email=bench@example.invalid",
         "commit", "-qm", "fixture"],
        cwd=root,
        check=False,
    )
    return str(root), digest.hexdigest()


def _browser_fixture() -> tuple[http.server.ThreadingHTTPServer, str, str]:
    """A local page for browser actions; no external site is contacted."""
    root = Path(tempfile.mkdtemp(prefix="ephe-bench-browser-"))
    sections = "".join(
        f"<section><h2>Section {index}</h2><p>Local benchmark content.</p></section>"
        for index in range(1, 21)
    )
    (root / "index.html").write_text(
        "<!doctype html><html><body>"
        "<h1>Benchmark Page</h1>"
        "<p>This is a local benchmark page for browser checks.</p>"
        '<p><a href="/next">More information</a></p>'
        '<input type="search" name="q" placeholder="Search">'
        '<form action="/submitted" method="get"><input name="email"><button type="submit">Submit</button></form>'
        + sections
        + "</body></html>",
        encoding="utf-8",
    )
    (root / "next").write_text("<html><body><h1>Next Page</h1></body></html>", encoding="utf-8")
    (root / "submitted").write_text(
        "<html><body><h1>Form submitted</h1></body></html>", encoding="utf-8"
    )
    (root / "login").write_text(
        '<html><body><h1>Login</h1><form action="/submitted"><input name="user">'
        '<input name="password"><button type="submit">Sign in</button></form></body></html>',
        encoding="utf-8",
    )

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, *_args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}", str(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plugin", help="plugin directory name below plugins/")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out", required=True, help="run-scoped report path")
    parser.add_argument("--force", action="store_true", help="replace an existing report")
    parser.add_argument("--case", action="append", default=[], help="only these case ids")
    parser.add_argument("--summary", action="store_true", help="omit raw transcripts from the report")
    parser.add_argument(
        "--fixture",
        choices=("code-shell", "memory", "browser-use"),
        help="run against a disposable workspace fixture instead of the persisted workspace",
    )
    args = parser.parse_args(argv)
    plugin_dir = ROOT / "plugins" / args.plugin
    if not (plugin_dir / "prompts" / "golden.jsonl").is_file():
        parser.error(f"no golden suite below {plugin_dir}")
    if args.fixture == "code-shell" and args.plugin != "code-shell":
        parser.error("--fixture code-shell only applies to the code-shell plugin")
    if args.fixture == "memory" and args.plugin != "memory":
        parser.error("--fixture memory only applies to the memory plugin")
    if args.fixture == "browser-use" and args.plugin != "browser-use":
        parser.error("--fixture browser-use only applies to the browser-use plugin")
    out = Path(args.out)
    if out.exists() and not args.force:
        parser.error(f"{out} exists; pass --force to replace it")
    workspace = ""
    workspace_hash = ""
    config_isolation = ""
    browser_server = None
    browser_origin = ""
    browser_root = ""
    previous = os.environ.get("EPHE_WORKSPACE")
    previous_config = os.environ.get("EPHE_CONFIG_DIR")
    choice = resolve_engine_choice() if args.fixture == "memory" else None
    try:
        if args.fixture == "code-shell":
            workspace, workspace_hash = _code_shell_workspace()
            os.environ["EPHE_WORKSPACE"] = workspace
            _, tools = plugin_golden.plugin_prompt(plugin_dir)
            report = plugin_golden.measure_matrix(
                plugin_dir,
                runs=args.runs,
                approval_policy=plugin_golden.bench_policy(tools, workspace=workspace),
                case_ids=args.case or None,
            )
        elif args.fixture == "browser-use":
            browser_server, browser_origin, browser_root = _browser_fixture()
            _, tools = plugin_golden.plugin_prompt(plugin_dir)
            report = plugin_golden.measure_matrix(
                plugin_dir,
                runs=args.runs,
                approval_policy=plugin_golden.bench_policy(tools),
                case_ids=args.case or None,
                input_transform=lambda text: text.replace("http://bench.local", browser_origin),
            )
        elif args.fixture == "memory":
            config_isolation = tempfile.mkdtemp(prefix="ephe-bench-memory-config-")
            os.environ["EPHE_CONFIG_DIR"] = config_isolation
            _, tools = plugin_golden.plugin_prompt(plugin_dir)
            runner = lambda case, **kwargs: plugin_golden.run_measured(case, choice, **kwargs)
            report = plugin_golden.measure_matrix(
                plugin_dir,
                runs=args.runs,
                runner=runner,
                approval_policy=plugin_golden.bench_policy(tools),
                case_ids=args.case or None,
            )
        else:
            report = plugin_golden.measure_matrix(
                plugin_dir, runs=args.runs, case_ids=args.case or None
            )
    finally:
        if previous is None:
            os.environ.pop("EPHE_WORKSPACE", None)
        else:
            os.environ["EPHE_WORKSPACE"] = previous
        if previous_config is None:
            os.environ.pop("EPHE_CONFIG_DIR", None)
        else:
            os.environ["EPHE_CONFIG_DIR"] = previous_config
        if workspace:
            shutil.rmtree(workspace, ignore_errors=True)
        if config_isolation:
            shutil.rmtree(config_isolation, ignore_errors=True)
        if browser_server is not None:
            browser_server.shutdown()
            browser_server.server_close()
        if browser_root:
            shutil.rmtree(browser_root, ignore_errors=True)
    report["provenance"] = provenance()
    if args.summary:
        for row in report["cases"]:
            for rep in row["reps"]:
                rep.pop("transcript", None)
        report["transcript_policy"] = "raw transcripts withheld; per-rep verdicts retained"
    if workspace_hash:
        report["provenance"]["workspace_fixture"] = args.fixture
        report["provenance"]["workspace_sha256"] = workspace_hash
    if config_isolation:
        report["provenance"]["config_isolation"] = "temporary"
    if browser_origin:
        report["provenance"]["browser_fixture"] = "local-http"
        report["provenance"]["browser_origin"] = browser_origin
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for row in report["cases"]:
        print(f"  {'PASS' if row['pass3'] else 'FAIL'} {row['id']}: {row['passes']}/{report['runs']}")
    print(
        f"matrix: {report['plugin']} {report['pass3_rate']:.0%} pass3 "
        f"({sum(1 for row in report['cases'] if row['pass3'])}/{len(report['cases'])}) "
        f"on {report['provenance']['provider']}/{report['provenance']['model']} "
        f"commit {report['provenance']['commit'][:12]} -> {out}"
    )
    return 0 if report["pass3_rate"] >= 0.9 else 1


if __name__ == "__main__":
    sys.exit(main())
