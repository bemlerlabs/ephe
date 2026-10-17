"""The usage seam: every branch behind a parse failure answers on the channel the caller asked for.

`ephe doctor --bogus` must not print the root usage line, and `--json` must not turn into
argparse prose. Both halves live in `_parse_args` and its three helpers, so they are exercised
here in-process: a test that shells out measures the subprocess and leaves the seam itself
unreached in the traced run, which is what the coverage floor counts.
"""
from __future__ import annotations

import contextlib
import io
import sys

import pytest

import ephe_cli


def _parser():
    return ephe_cli.build_parser()


class TestNamedSubparser:
    def test_no_words_names_no_command(self):
        assert ephe_cli._named_subparser(_parser(), []) is None

    def test_a_known_verb_names_its_own_parser(self):
        sub = ephe_cli._named_subparser(_parser(), ["doctor", "--bogus"])
        assert sub is not None
        assert "doctor" in sub.prog

    def test_an_unknown_word_names_nothing(self):
        assert ephe_cli._named_subparser(_parser(), ["nonsense"]) is None

    def test_a_parser_without_subcommands_names_nothing(self):
        """The loop found no subcommand table at all, which is not the same as an unknown word."""
        doctor = ephe_cli._named_subparser(_parser(), ["doctor"])
        assert doctor is not None
        assert ephe_cli._named_subparser(doctor, ["doctor"]) is None


class TestUsageText:
    def test_a_named_command_gets_its_own_usage_line(self):
        """The named subparser is re-run so argparse writes the line that belongs to it."""
        text = ephe_cli._usage_text(_parser(), ["doctor", "--bogus"], "captured-root-usage")
        assert "ephe doctor" in text
        assert text != "captured-root-usage"

    def test_words_that_name_no_command_keep_what_the_root_captured(self):
        assert ephe_cli._usage_text(_parser(), ["nonsense"], "root-usage") == "root-usage"

    def test_a_named_command_that_succeeds_keeps_the_captured_text(self):
        """A subparser that parses cleanly writes nothing, so the captured text is the answer."""
        assert ephe_cli._usage_text(_parser(), ["doctor"], "root-usage") == "root-usage"


class TestUsageMessage:
    def test_argparses_diagnostic_line_loses_its_program_prefix(self):
        text = "usage: ephe doctor [-h]\nephe doctor: error: unrecognized arguments: --bogus\n"
        assert ephe_cli._usage_message(text) == "unrecognized arguments: --bogus"

    def test_a_line_without_the_marker_is_the_message(self):
        assert ephe_cli._usage_message("something went wrong") == "something went wrong"

    def test_empty_text_says_something(self):
        assert ephe_cli._usage_message("   \n\n") == "invalid arguments"


class TestParseArgsChoosesTheChannel:
    def _run_main(self, argv, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["ephe", *argv])
        with pytest.raises(SystemExit) as caught:
            ephe_cli.main()
        out, err = capsys.readouterr()
        return caught.value.code, out, err

    def test_json_was_asked_for_so_the_envelope_carries_the_failure(self, monkeypatch, capsys):
        code, out, err = self._run_main(["doctor", "--bogus", "--json"], monkeypatch, capsys)
        assert code == 2
        assert err == ""
        assert '"code_id": "usage_error"' in out
        assert "See `ephe doctor --help`" in out

    def test_without_json_argparses_own_text_names_the_typed_command(self, monkeypatch, capsys):
        code, out, err = self._run_main(["doctor", "--bogus"], monkeypatch, capsys)
        assert code == 2
        assert "usage: ephe doctor" in err
        assert "usage: ephe [-h] [--version] {start,web" not in err

    def test_an_unknown_command_answers_on_the_root_usage(self, monkeypatch, capsys):
        code, out, err = self._run_main(["nonsense"], monkeypatch, capsys)
        assert code == 2
        assert "usage: ephe [-h] [--version]" in err

    def test_help_still_answers_on_stdout_with_zero(self, monkeypatch, capsys):
        code, out, err = self._run_main(["--help"], monkeypatch, capsys)
        assert code == 0
        assert "usage: ephe" in out
        assert err == ""

    def test_version_still_answers_on_stdout_with_zero(self, monkeypatch, capsys):
        code, out, err = self._run_main(["--version"], monkeypatch, capsys)
        assert code == 0
        assert out.strip()
        assert err == ""


class TestAvailableToolNames:
    def test_a_registry_that_cannot_be_read_yields_no_names(self, monkeypatch):
        """The help still renders when the registry is unavailable, so the failure is silent."""
        import core.tools.registry as registry

        def refuse():
            raise RuntimeError("the registry cannot be read here")

        monkeypatch.setattr(registry, "get_tool_schemas", refuse)
        assert ephe_cli.available_tool_names() == []

    def test_a_readable_registry_yields_sorted_names(self):
        names = ephe_cli.available_tool_names()
        assert names, "the execution path offers tools, so the help must name them"
        assert names == sorted(names)
