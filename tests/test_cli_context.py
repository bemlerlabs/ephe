"""`ephe context` is the terminal half of the context report.

The resolver in ``core.workspace_rules`` already knows which workspace file the prompt
received, which one it cut and which one it refused; the CLI could name none of that. The
structured explanation lands with the context contract, so this file runs both seams: the
report the tree carries now, and the documented shape when it arrives.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest

import ephe_cli
from core import _cli_context

#: The canonical rule-file names come from the resolver, so a rename cannot drift here.
from core.workspace_rules import (
    RULE_FILE_MAX,
    RULES_DIR,
    RULES_NAME,
    WORKSPACE_RULES_MAX,
)


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """A workspace the resolver reads, and no structured report to read instead."""
    wd = tmp_path / "ws"
    wd.mkdir()
    monkeypatch.setenv("EPHE_WORKSPACE", str(wd))
    monkeypatch.setattr(_cli_context, "_explain_workspace_context", None)
    return wd


def _run(*argv: str) -> int:
    return ephe_cli.cmd_context(ephe_cli.build_parser().parse_args(["context", *argv]))


def _subparser(verb: str) -> argparse.ArgumentParser:
    parser = ephe_cli.build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices[verb]
    raise AssertionError(f"build_parser() registers no `{verb}` subparser")


def _rules_dir(workspace: Path) -> Path:
    rules = workspace / RULES_DIR
    rules.mkdir(parents=True)
    return rules


def test_it_names_every_file_with_the_status_the_reader_gave_it(workspace, capsys):
    (workspace / RULES_NAME).write_text("Use rg for search.\n", encoding="utf-8")
    (_rules_dir(workspace) / "10-team.md").write_text("rule\n" * 2_000, encoding="utf-8")

    code = _run()

    out = capsys.readouterr().out
    assert code == 0
    assert str(workspace.resolve()) in out
    assert RULES_NAME in out
    assert ".ephe/rules/10-team.md" in out
    assert "included" in out
    assert "truncated" in out


def test_the_header_names_the_caps_and_the_workspace_root(workspace, capsys):
    (workspace / RULES_NAME).write_text("a rule", encoding="utf-8")

    _run()

    out = capsys.readouterr().out
    assert f"{WORKSPACE_RULES_MAX} chars total" in out
    assert f"{RULE_FILE_MAX} per file" in out
    assert str(workspace.resolve()) in out


def test_an_empty_workspace_is_one_honest_line(workspace, capsys):
    code = _run()

    out = capsys.readouterr().out
    assert code == 0
    assert "No context files under" in out
    assert str(workspace.resolve()) in out
    assert "included" not in out


def test_a_file_outside_the_root_is_named_as_denied_with_its_reason(workspace, tmp_path, capsys):
    secret = tmp_path / "outside.md"
    secret.write_text("outside-body", encoding="utf-8")
    (_rules_dir(workspace) / "escape.md").symlink_to(secret)

    _run()

    out = capsys.readouterr().out
    assert "escape.md" in out
    assert "denied (outside-root)" in out
    assert "outside-body" not in out


def test_the_json_report_carries_the_layers_the_caps_and_the_counts(workspace, capsys):
    body = "Use rg for search."
    (workspace / RULES_NAME).write_text(body + "\n", encoding="utf-8")

    _run("--json")

    payload = json.loads(capsys.readouterr().out)
    assert payload["workspace"] == str(workspace.resolve())
    assert payload["source"] == "read_workspace_rules"
    assert payload["caps"] == {"total": WORKSPACE_RULES_MAX, "per_file": RULE_FILE_MAX}
    assert [row["file"] for row in payload["layers"]] == [RULES_NAME]
    assert payload["layers"][0]["status"] == "included"
    assert payload["total_chars"] == len(body)
    assert payload["counts"] == {"included": 1}


def test_the_structured_report_is_printed_when_it_carries_the_documented_fields(
    workspace, monkeypatch, capsys
):
    monkeypatch.setattr(
        _cli_context,
        "_explain_workspace_context",
        lambda: {
            "layers": [
                {
                    "name": "soul",
                    "file": "SOUL.md",
                    "chars": 120,
                    "status": "included",
                    "reason": "",
                    "scope": "workspace",
                },
                {
                    "name": "user",
                    "file": "USER.md",
                    "chars": 0,
                    "status": "denied",
                    "reason": "protected-root",
                    "scope": "private",
                },
            ],
            "caps": {"total": 24_000, "per_file": 4_000},
            "total_chars": 120,
        },
    )

    _run()
    out = capsys.readouterr().out

    assert "SOUL.md" in out and "USER.md" in out
    assert "denied (protected-root)" in out
    assert "24000 chars total, 4000 per file" in out

    _run("--json")
    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "explain_workspace_context"
    assert [row["layer"] for row in payload["layers"]] == ["soul", "user"]
    assert [row["scope"] for row in payload["layers"]] == ["workspace", "private"]


def _broken_report():
    raise RuntimeError("the structured report is broken")


@pytest.mark.parametrize(
    "explainer",
    [_broken_report, lambda: {"layers": "not a list"}, lambda: {"layers": [{"chars": 4}]}],
    ids=["raises", "layers-not-a-list", "row-without-file-or-status"],
)
def test_a_report_that_does_not_fit_the_shape_falls_back_to_the_resolver(
    workspace, monkeypatch, capsys, explainer
):
    (workspace / RULES_NAME).write_text("a rule", encoding="utf-8")
    monkeypatch.setattr(_cli_context, "_explain_workspace_context", explainer)

    _run("--json")

    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "read_workspace_rules"
    assert [row["file"] for row in payload["layers"]] == [RULES_NAME]


def test_the_doctor_row_counts_loaded_capped_and_refused_files(workspace):
    (workspace / RULES_NAME).write_text("a rule", encoding="utf-8")
    (_rules_dir(workspace) / "10-team.md").write_text(
        "x" * (RULE_FILE_MAX + 10), encoding="utf-8"
    )

    detail = _cli_context.doctor_row()

    assert "1 included" in detail
    assert "1 truncated" in detail
    assert "0 denied" in detail
    assert "ephe context" in detail


def test_the_doctor_row_says_none_when_the_workspace_carries_no_context_file(workspace):
    detail = _cli_context.doctor_row()

    assert detail.startswith("none in ")
    assert "ephe context" in detail


def test_help_names_the_statuses_and_the_flag():
    help_text = _subparser("context").format_help()

    assert "--json" in help_text
    for status in ("included", "truncated", "denied"):
        assert status in help_text
    assert "context" in ephe_cli._completion_subcommands()


def test_the_command_dispatches_through_main(workspace, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["ephe", "context"])

    with pytest.raises(SystemExit) as exit_info:
        ephe_cli.main()

    assert exit_info.value.code == 0
    assert "Workspace" in capsys.readouterr().out
