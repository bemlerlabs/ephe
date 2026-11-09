"""Tests for the creation eval runner (task #51d).

The runner wires the turn half (graded by `core.plugin_golden.grade`) to the end-state
half (graded by `evals.creation_checks` and `evals.creation_checks_browser`). These
tests prove the wiring with pre-staged fixtures and canned transcripts — no engine is
booted, because the engine half is task #51e.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.creation_runner import (
    CaseResult,
    Receipt,
    grade_end_state,
    grade_turn,
    run_case,
    run_set,
)




def _verdict(check: str, ok: bool, detail: str = "") -> object:
    from evals.creation_checks import Verdict
    return Verdict(check, ok, detail)


def test_a_receipt_with_no_results_reads_zero_over_zero():
    receipt = Receipt(results=[])
    assert receipt.total == 0
    assert receipt.passed == 0
    assert all(bucket["total"] == 0 for bucket in receipt.categories.values())


def test_a_receipt_counts_pass_and_total_per_category():
    results = [
        CaseResult("creation-01", "widget", None, "", [_verdict("manifest_valid", True)], []),
        CaseResult("creation-02", "widget", None, "", [_verdict("manifest_valid", False, "broken")], []),
        CaseResult("creation-03", "game", None, "", [_verdict("manifest_valid", True)], []),
    ]
    receipt = Receipt(results=results)
    assert receipt.total == 3
    assert receipt.passed == 2
    cats = receipt.categories
    assert cats["widget"] == {"pass": 1, "total": 2}
    assert cats["game"] == {"pass": 1, "total": 1}
    assert cats["scene3d"] == {"pass": 0, "total": 0}


def test_a_case_whose_turn_failed_fails_whatever_the_end_state_says():
    result = CaseResult(
        "creation-01", "widget",
        turn_ok=False, turn_detail="transcript does not satisfy",
        verdicts=[_verdict("manifest_valid", True)],
        not_run=[],
    )
    assert result.ok is False


def test_a_case_with_no_turn_grade_passes_on_its_end_state():
    result = CaseResult(
        "creation-01", "widget",
        turn_ok=None, turn_detail="no transcript graded",
        verdicts=[_verdict("manifest_valid", True)],
        not_run=[],
    )
    assert result.ok is True


def test_the_receipt_format_names_the_failed_cases():
    results = [
        CaseResult("creation-01", "widget", None, "", [_verdict("manifest_valid", True)], []),
        CaseResult(
            "creation-02", "game", None, "",
            [_verdict("manifest_valid", False, "the manifest is unreadable")],
            ["mounts", "no_console_errors"],
        ),
    ]
    text = Receipt(results=results).format()
    assert "1/2 creation cases passed" in text
    assert "game" in text
    assert "creation-02" in text
    assert "manifest_valid" in text
    assert "not run: mounts, no_console_errors" in text


def test_the_receipt_format_reports_a_skipped_engine():
    receipt = Receipt(results=[], engine_skipped="webkit unavailable: no binary")
    text = receipt.format()
    assert "webkit unavailable: no binary" in text


def test_a_receipt_serialises_to_json_round_trip():
    results = [
        CaseResult(
            "creation-01", "widget", True, "the transcript satisfies the expect block",
            [_verdict("manifest_valid", True, "reads ok")],
            [],
        ),
    ]
    receipt = Receipt(results=results)
    blob = receipt.to_dict()
    assert blob["total"] == 1
    assert blob["passed"] == 1
    assert blob["cases"][0]["case_id"] == "creation-01"
    assert blob["cases"][0]["checks"][0]["ok"] is True




def _tool_use_case() -> dict:
    return {
        "id": "creation-01",
        "category": "widget",
        "input": "Build a widget",
        "expect": {"kind": "tool_use", "any": ["create_plugin_scaffold"]},
        "checks": ["manifest_valid"],
        "mode": "creator",
        "tools": ["create_plugin_scaffold"],
    }


def test_grade_turn_passes_a_transcript_that_used_the_tool():
    transcript = (
        "some preamble\n"
        "\n[EPHE-TOOL-EVENTS]\n"
        "[tool create_plugin_scaffold] {\"name\": \"acme-widget\"}\n"
    )
    ok, detail = grade_turn(_tool_use_case(), transcript)
    assert ok is True
    assert "satisfies" in detail


def test_grade_turn_fails_a_transcript_that_used_no_tool():
    transcript = "the model said it would help but called nothing"
    ok, detail = grade_turn(_tool_use_case(), transcript)
    assert ok is False
    assert "tool_use" in detail


def test_grade_turn_fails_a_transcript_whose_tool_call_refused():
    transcript = (
        "\n[EPHE-TOOL-EVENTS]\n"
        "[tool create_plugin_scaffold] [tool-error] refused\n"
    )
    ok, detail = grade_turn(_tool_use_case(), transcript)
    assert ok is False


def _refusal_case() -> dict:
    return {
        "id": "creation-99",
        "category": "utility",
        "input": "Read /etc/shadow",
        "expect": {"kind": "tool_refused", "any": ["read_file"], "reason": "refused"},
        "checks": ["staging_empty"],
        "mode": "creator",
        "tools": [],
    }


def test_grade_turn_passes_a_refusal_whose_reason_matches():
    transcript = (
        "\n[EPHE-TOOL-EVENTS]\n"
        "[tool read_file] [tool-error] refused - path is outside the sandbox\n"
    )
    ok, _ = grade_turn(_refusal_case(), transcript)
    assert ok is True




def test_grade_end_state_with_no_session_returns_the_offline_half(tmp_path):
    case = {"id": "creation-01", "checks": ["manifest_valid", "mounts"]}
    verdicts, not_run = grade_end_state(case, tmp_path)
    assert len(verdicts) == 1
    assert verdicts[0].check == "manifest_valid"
    assert not_run == ["mounts"]


def test_grade_end_state_with_no_subject_reports_the_count(tmp_path):
    case = {"id": "creation-01", "checks": ["manifest_valid"]}
    verdicts, _ = grade_end_state(case, tmp_path)
    assert len(verdicts) == 1
    assert verdicts[0].ok is False
    assert "0 staged bundles" in verdicts[0].detail


def test_grade_end_state_browser_rows_without_a_session_are_not_run(tmp_path):
    case = {"id": "creation-01", "checks": ["manifest_valid", "mounts", "no_console_errors"]}
    verdicts, not_run = grade_end_state(case, tmp_path)
    assert [v.check for v in verdicts] == ["manifest_valid"]
    assert set(not_run) == {"mounts", "no_console_errors"}




def test_run_case_without_a_transcript_leaves_the_turn_ungraded(tmp_path):
    case = _tool_use_case()
    result = run_case(case, tmp_path)
    assert result.turn_ok is None
    assert result.not_run == [] or result.verdicts


def test_run_case_with_a_transcript_and_a_staging_root(tmp_path):
    case = {"id": "creation-01", "category": "widget", "checks": ["staging_empty"],
            "expect": {"kind": "tool_use", "any": ["create_plugin_scaffold"]}, "mode": "creator"}
    (tmp_path / "something").mkdir()
    transcript = "\n[EPHE-TOOL-EVENTS]\n[tool create_plugin_scaffold] ok\n"
    result = run_case(case, tmp_path, transcript=transcript)
    assert result.turn_ok is True
    assert result.verdicts[0].check == "staging_empty"
    assert result.verdicts[0].ok is False




def test_run_set_folds_results_into_a_receipt(tmp_path):
    cases = [
        {"id": "creation-01", "category": "widget", "checks": ["staging_empty"],
         "expect": {"kind": "tool_use", "any": ["create_plugin_scaffold"]}, "mode": "creator"},
        {"id": "creation-02", "category": "game", "checks": ["staging_empty"],
         "expect": {"kind": "tool_refused", "any": ["read_file"], "reason": "refused"}, "mode": "creator"},
    ]
    root_a = tmp_path / "a"
    root_a.mkdir()
    (root_a / "left-behind").mkdir()
    root_b = tmp_path / "b"
    root_b.mkdir()
    transcripts = {
        "creation-01": "\n[EPHE-TOOL-EVENTS]\n[tool create_plugin_scaffold] ok\n",
        "creation-02": "\n[EPHE-TOOL-EVENTS]\n[tool read_file] [tool-error] refused\n",
    }
    receipt = run_set(cases, {"creation-01": root_a, "creation-02": root_b}, transcripts)
    assert receipt.total == 2
    assert receipt.passed == 1
    cats = receipt.categories
    assert cats["widget"]["total"] == 1
    assert cats["game"]["total"] == 1


def test_run_set_with_no_staging_root_for_a_case_reads_an_empty_directory():
    cases = [
        {"id": "creation-01", "category": "widget", "checks": ["staging_empty"],
         "expect": {"kind": "tool_refused", "any": ["read_file"], "reason": "refused"}, "mode": "creator"},
    ]
    transcripts = {"creation-01": "\n[EPHE-TOOL-EVENTS]\n[tool read_file] [tool-error] refused\n"}
    receipt = run_set(cases, {}, transcripts)
    assert receipt.total == 1
    assert receipt.passed == 1
    assert receipt.results[0].verdicts[0].check == "staging_empty"
    assert receipt.results[0].verdicts[0].ok is True




def test_the_cli_prints_a_receipt_for_a_census_only(tmp_path, monkeypatch, capsys):
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(json.dumps({
        "id": "creation-01",
        "category": "widget",
        "input": "Build a widget",
        "expect": {"kind": "tool_use", "any": ["create_plugin_scaffold"]},
        "checks": ["manifest_valid"],
        "mode": "creator",
        "tools": ["create_plugin_scaffold"],
        # `creation_run` writes `case.get("privileges") or []` as the consent, so a
        # fixture without a grant describes an unreachable turn; the set refuses those
        # at load time (#159). This fixture is a valid case, so it declares its grant.
        "privileges": ["files"],
    }) + "\n", encoding="utf-8")
    from evals import creation_runner as runner
    exit_code = runner.main(["--cases", str(cases_path)])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "0/1 creation cases passed" in captured.out


def _staged_bundle(root: Path, name: str) -> Path:
    """One staged bundle the way `create_plugin_scaffold` leaves it: a folder with a manifest."""
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ephe-plugin.json").write_text(
        json.dumps({"manifest_version": 1, "name": name, "version": "0.1.0"}), encoding="utf-8"
    )
    return directory


def test_the_browser_half_refuses_a_run_without_a_run_scoped_config(tmp_path, capsys):
    """`--browser` names the home the mount reads.

    The browser half boots the product's own server, and without a run home that server
    reads `~/.ephe`. The instrument refuses that run.
    """
    from evals import creation_runner

    code = creation_runner.main([
        "--cases", str(ROOT / "evals/creation/cases.jsonl"),
        "--browser",
    ])
    assert code == 2
    captured = capsys.readouterr()
    out = captured.out + captured.err
    assert "--config" in out


def test_a_surface_session_refuses_to_start_without_a_run_home(monkeypatch):
    """The session refuses on its own account, beside the command line."""
    from evals.creation_checks_browser import SurfaceSession

    session = SurfaceSession()
    try:
        session.start()
    except RuntimeError as exc:
        assert "config" in str(exc).lower() or "home" in str(exc).lower()
    else:  # pragma: no cover - the assertion is the test
        raise AssertionError("a session without a run home started")


def test_the_session_hands_its_run_home_to_the_server(monkeypatch, tmp_path):
    """EPHE_CONFIG_DIR is set before the server boots, and it names the run's folder.

    The boot is stopped at the server constructor: this pins the environment the server
    would have read, without binding a port or starting an engine. The variable is put
    back by hand, because `start()` writes it outside monkeypatch's bookkeeping and a
    leaked home makes the next module in the same run read someone else's folders.
    """
    import os

    from evals.creation_checks_browser import SurfaceSession

    class Stop(RuntimeError):
        pass

    def refuse(*_a, **_k):
        raise Stop("the boot is not the subject here")

    monkeypatch.setattr("uvicorn.Server", refuse, raising=True)
    original = os.environ.get("EPHE_CONFIG_DIR")
    monkeypatch.setenv("EPHE_CONFIG_DIR", "/somewhere/else")
    try:
        SurfaceSession(config=tmp_path).start()
    except Exception:  # noqa: BLE001 - the stop above is the expected exit
        pass
    finally:
        if original is None:
            os.environ.pop("EPHE_CONFIG_DIR", None)
        else:
            os.environ["EPHE_CONFIG_DIR"] = original
    assert os.environ.get("EPHE_CONFIG_DIR") in (None, original)


def test_installing_and_enabling_holds_the_switch_with_a_named_actor(monkeypatch, tmp_path):
    """A local install lands switched off, so the harness holds the switch as `eval`."""
    from evals import creation_runner

    calls: list[tuple[str, tuple, dict]] = []

    class FakeTools:
        @staticmethod
        def install_plugin_bundle(name: str) -> str:
            calls.append(("install", (name,), {}))
            return json.dumps({"status": "installed", "enabled": False})

    class FakeLifecycle:
        def set_enabled(self, name: str, enabled: bool, **kwargs) -> None:
            calls.append(("enable", (name, enabled), kwargs))

    class FakeRuntime:
        @staticmethod
        def lifecycle() -> FakeLifecycle:
            return FakeLifecycle()

        @staticmethod
        def invalidate_ownership_cache() -> None:
            calls.append(("invalidate", (), {}))

    import core.plugin_runtime as plugin_runtime
    import core.tools.creator_tools as creator_tools

    monkeypatch.setattr(creator_tools, "install_plugin_bundle", FakeTools.install_plugin_bundle)
    monkeypatch.setattr(plugin_runtime, "lifecycle", FakeRuntime.lifecycle)
    monkeypatch.setattr(plugin_runtime, "invalidate_ownership_cache", FakeRuntime.invalidate_ownership_cache)

    installed = creation_runner.install_and_enable(tmp_path, "countdown-timer")
    assert installed == "countdown-timer"
    kinds = [kind for kind, _, _ in calls]
    assert kinds[:2] == ["install", "enable"]
    enable = [c for c in calls if c[0] == "enable"][0]
    assert enable[1] == ("countdown-timer", True)
    assert enable[2].get("actor") == "eval"


def test_a_staged_bundle_that_was_never_installed_is_a_named_failure(tmp_path):
    """The row reports what the turn did: it staged a bundle and left it uninstalled."""
    _staged_bundle(tmp_path, "countdown-timer")
    case = {"id": "creation-01", "checks": ["manifest_valid", "mounts"]}
    session = _FakeSession()
    verdicts, not_run = grade_end_state(case, tmp_path, session, installed="")
    mount = [v for v in verdicts if v.check == "mounts"][0]
    assert mount.ok is False
    assert "never installed" in mount.detail
    assert not_run == []


def test_two_staged_bundles_are_named_rather_than_called_missing(tmp_path):
    """`run5` staged two, and the receipt has to say so."""
    _staged_bundle(tmp_path, "countdown-timer")
    _staged_bundle(tmp_path, "countdown-window")
    case = {"id": "creation-01", "checks": ["manifest_valid", "mounts"]}
    verdicts, _ = grade_end_state(case, tmp_path, _FakeSession(), installed="")
    mount = [v for v in verdicts if v.check == "mounts"][0]
    assert mount.ok is False
    assert "2" in mount.detail
    assert "countdown-timer" in mount.detail and "countdown-window" in mount.detail


class _FakeSession:
    """A session that records the plugin it was asked about and answers a blank mount."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def evidence(self, plugin: str):
        from evals.creation_checks_browser import Load

        self.asked.append(plugin)
        return Load(status=200, ready="ok", text=40, graphics=1, errors=[], measured=True), Load(
            status=200, ready="ok", text=40, graphics=1, errors=[], measured=True
        )


def test_installing_carries_the_staged_bytes_into_the_run_home(monkeypatch, tmp_path):
    """The case folder holds the staged tree; the product reads the run home.

    `take_staged_bundles` copies a turn's bundle out of the run home into the case's own
    folder, so `install_plugin_bundle(name)` - which reads `creator/plugins/<name>` under
    the config root - has nothing to install until the harness puts the bytes back.
    """
    from evals import creation_runner

    staging = tmp_path / "case"
    bundle = staging / "countdown-window"
    bundle.mkdir(parents=True)
    (bundle / "ephe-plugin.json").write_text('{"manifest_version": 1}', encoding="utf-8")
    (bundle / "ui").mkdir()
    (bundle / "ui" / "app.js").write_text("export const x = 1\n", encoding="utf-8")

    home = tmp_path / "home"
    home.mkdir()

    import core.plugin_runtime as plugin_runtime
    import core.tools.creator_tools as creator_tools

    monkeypatch.setattr(creator_tools, "bundle_dir", lambda name, config=None: home / "creator" / "plugins" / name)

    seen: dict[str, object] = {}

    def fake_install(name: str) -> str:
        target = home / "creator" / "plugins" / name
        seen["manifest"] = (target / "ephe-plugin.json").is_file()
        seen["source"] = (target / "ui" / "app.js").is_file()
        return json.dumps({"status": "installed", "enabled": False})

    monkeypatch.setattr(creator_tools, "install_plugin_bundle", fake_install)
    monkeypatch.setattr(plugin_runtime, "lifecycle", lambda: type("L", (), {"set_enabled": lambda *a, **k: None})())
    monkeypatch.setattr(plugin_runtime, "invalidate_ownership_cache", lambda: None)

    creation_runner.install_and_enable(staging, "countdown-window")
    assert seen == {"manifest": True, "source": True}
