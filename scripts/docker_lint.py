#!/usr/bin/env python3
"""hadolint and shellcheck counts against a committed baseline, in one gate.

`docs/CI_HYBRID_CAPACITY_2026-10-11.md` row 12 of the residue refuses a docker-lint job that assumes
the two binaries exist, and this repository's history says a gate that silently finds nothing because
its tool was missing is worse than no gate. So the instrument resolves both, refuses naming the tool
that did not resolve, and compares what they report against `scripts/docker-lint-baseline.json`:

* a rule code that is new counts as a regression, whatever its severity;
* a code whose count rose counts as a regression;
* a count below baseline is reported as a lowering the owner can bank with `--update`.

No ignore flags are passed to either tool, so the baseline is the whole veto list rather than a set of
taste exclusions chosen here. That is also why the pinned versions are part of the record: shellcheck
renumbers and re-levels codes between releases, and a gate whose counts move because the tool moved
would be measuring the toolchain.

Measured 2026-10-11 with hadolint 2.15.1 and shellcheck 0.11.0 over this tree: the Dockerfile reports
DL3008 twice and DL3025 once; the 13 tracked shell scripts report 21 findings at warning-and-above
(SC2155 12, SC2034 5, SC2164 1, SC2148 cleared by the shell directive in `scripts/lint_policy.sh`) plus
the info and style tier.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_DEFAULT = ROOT / "scripts" / "docker-lint-baseline.json"
POLICY = "docker-lint-ratchet"
VERSION = 1
#: The two tools the gate needs, with the release asset names the CI leg downloads. Kept here so the
#: refusal message can name what to install rather than just saying "not found".
TOOLS = {
    "hadolint": "hadolint v2.15.1 (hadolint-linux-arm64, digest pinned in .github/workflows/docklint.yml)",
    "shellcheck": "shellcheck v0.11.0 (shellcheck-v0.11.0.linux.aarch64.tar.xz, digest pinned there)",
}
DOCKERFILE = "Dockerfile"


class ToolError(RuntimeError):
    pass


def resolve(tool: str) -> str:
    """The binary this run uses: EPHE_<TOOL>_BIN, then PATH, then a refusal that names it.

    The env override exists because the CI leg installs both tools into `RUNNER_TEMP` and must not
    depend on a listener happening to carry them.
    """
    env_name = f"EPHE_{tool.upper()}_BIN"
    candidate = os.environ.get(env_name) or shutil.which(tool)
    if not candidate:
        raise ToolError(f"{tool} did not resolve ({env_name} unset, nothing on PATH; expected: {TOOLS[tool]})")
    path = Path(candidate)
    if not path.is_file() or not path.stat().st_mode & 0o111:
        raise ToolError(f"{tool} resolves to {candidate}, which is not an executable file")
    return str(path)


def tool_version(binary: str, tool: str) -> str:
    done = subprocess.run([binary, "--version"], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise ToolError(f"{binary} --version exited {done.returncode}: {done.stderr.strip()}")
    match = re.search(r"version:\s*([0-9][\w.]+)|(\d+\.\d+\.\d+)", done.stdout)
    if not match:
        raise ToolError(f"cannot read a version out of `{binary} --version`: {done.stdout[:120]!r}")
    return match.group(1) or match.group(2)


def tracked_shell_scripts() -> list[str]:
    done = subprocess.run(["git", "ls-files", "-z", "*.sh"], capture_output=True, check=True, text=True)
    return sorted(p for p in done.stdout.split("\0") if p)


def hadolint_findings(binary: str, paths: list[str]) -> list[dict]:
    done = subprocess.run([binary, "--format", "json", *paths], capture_output=True, text=True,
                          check=False)
    if done.returncode not in (0, 1):
        raise ToolError(f"hadolint exited {done.returncode}: {done.stderr.strip()[:200]}")
    payload = json.loads(done.stdout or "[]")
    return [
        {"code": str(item["code"]), "file": item.get("file", DOCKERFILE), "line": item["line"],
         "level": item["level"], "message": item["message"]}
        for item in payload
    ]


def shellcheck_findings(binary: str, paths: list[str]) -> list[dict]:
    if not paths:
        return []
    done = subprocess.run([binary, "--format", "json", *paths], capture_output=True, text=True,
                          check=False)
    # shellcheck exits 1 when it reports anything, so a non-zero status is the normal case here; the
    # JSON is empty and the truth is the count, not the code.
    payload = json.loads(done.stdout or "[]")
    return [
        {"code": f"SC{item['code']}", "file": item["file"], "line": item["line"],
         "level": item["level"], "message": item["message"]}
        for item in payload if isinstance(item, dict)
    ]


def load_baseline(path: Path) -> dict:
    if not path.exists():
        raise ToolError(f"no baseline at {path.name} (looked in {path.parent}); it is a tracked file, restore it from the repository")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("policy") != POLICY or raw.get("version") != VERSION:
        raise ToolError(
            f"baseline {path.name} is policy {raw.get('policy')!r} version {raw.get('version')!r}; "
            f"this gate speaks {POLICY!r} version {VERSION}"
        )
    if not isinstance(raw.get("rules"), dict):
        raise ToolError(f"baseline {path.name} has no `rules` mapping")
    return raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", type=Path, default=BASELINE_DEFAULT)
    parser.add_argument("--update", action="store_true", help="lower the baseline to this tree")
    parser.add_argument("--json", type=Path, help="write the finding list here")
    parser.add_argument("--show-findings", type=int, default=30, help="how many finding lines to print")
    args = parser.parse_args(argv)

    hadolint = resolve("hadolint")
    shellcheck = resolve("shellcheck")
    had_version = tool_version(hadolint, "hadolint")
    sc_version = tool_version(shellcheck, "shellcheck")

    docker_paths = [p for p in (DOCKERFILE,) if (ROOT / p).is_file()]
    shell_paths = tracked_shell_scripts()
    findings = hadolint_findings(hadolint, docker_paths) + shellcheck_findings(shellcheck, shell_paths)
    counts = collections.Counter(item["code"] for item in findings)

    print(f"docker-lint: hadolint {had_version}, shellcheck {sc_version}")
    print(f"  inputs: {len(docker_paths)} containerfile(s), {len(shell_paths)} tracked shell script(s)")
    print(f"  {len(findings)} finding(s) across {len(counts)} rule code(s)")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(findings, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    baseline = None if args.update else load_baseline(args.baseline)
    if args.update:
        existing = load_baseline(args.baseline)
        proposed = {code: counts.get(code, 0) for code, ceiling in existing["rules"].items()}
        proposed = {code: count for code, count in proposed.items() if count}
        raise_list = [
            f"{code}: {counts.get(code, 0)} against the recorded {ceiling}"
            for code, ceiling in existing["rules"].items()
            if counts.get(code, 0) > ceiling
        ]
        new_codes = sorted(set(counts) - set(existing["rules"]))
        if raise_list or new_codes:
            for line in raise_list:
                print(f"  REFUSED {line}")
            for code in new_codes:
                print(f"  REFUSED {code}: {counts[code]} finding(s) of a rule the baseline never recorded")
            print("  --update lowers this file and cannot widen it: fix the finding, or record the "
                  "decision in .github/workflows/docklint.yml and raise the ceiling by hand")
            return 1
        payload = {
            "policy": POLICY, "version": VERSION, "instrument": "scripts/docker_lint.py",
            "hadolint_version": had_version, "shellcheck_version": sc_version,
            "measured_at": existing.get("measured_at", ""), "rules": dict(sorted(proposed.items())),
        }
        if payload["rules"] == existing["rules"]:
            print("  nothing to lower: the tree already matches the recorded ceilings")
            return 0
        payload["measured_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        args.baseline.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        retired = len(existing["rules"]) - len(proposed)
        print(f"  lowered {args.baseline.name}: {retired} code(s) gone, counts follow the tree")
        return 0

    if baseline is None:
        return 0
    if baseline.get("hadolint_version") != had_version:
        print(f"  FAIL tool drift: baseline was written with hadolint "
              f"{baseline.get('hadolint_version')}, this run has {had_version}")
        return 1
    if baseline.get("shellcheck_version") != sc_version:
        print(f"  FAIL tool drift: baseline was written with shellcheck "
              f"{baseline.get('shellcheck_version')}, this run has {sc_version}")
        return 1

    allowed = {k: v for k, v in baseline["rules"].items()}
    regressions = []
    lowered = []
    for code, count in sorted(counts.items()):
        ceiling = allowed.get(code)
        if ceiling is None:
            regressions.append(f"{code}: {count} finding(s) of a rule the baseline never recorded")
        elif count > ceiling:
            regressions.append(f"{code}: {count} finding(s) over the recorded {ceiling}")
        elif count < ceiling:
            lowered.append(f"{code}: {ceiling} -> {count}")
    for code, ceiling in sorted(allowed.items()):
        if code not in counts and ceiling:
            lowered.append(f"{code}: {ceiling} -> 0")

    for finding in findings[: args.show_findings]:
        print(f"  {finding['file']}:{finding['line']} {finding['level']} {finding['code']} "
              f"{finding['message'][:90]}")
    if len(findings) > args.show_findings:
        print(f"  ... {len(findings) - args.show_findings} more finding(s) in the json")

    if lowered:
        print("  below baseline, the ratchet can be lowered: " + ", ".join(lowered))
    for line in regressions:
        print(f"  FAIL {line}")
    if regressions:
        return 1
    print("docker-lint: pass -- no new rule code and no count above its recorded ceiling")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except ToolError as exc:
        # A refusal the CI log can read: the message names the tool and what was expected, and the
        # exit code says the gate never ran, which is not the same finding as a lint failure.
        print(f"docker-lint: FAIL {exc}")
        sys.exit(2)
