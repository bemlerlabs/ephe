"""The heads an agent needs to do its work, and the flag that turns each one
into something the head check cannot see.

The command-policy audit of 2026-11-18 found the whitelist missing the tools a
build actually calls (jq, rg, sed, tar, sips, afconvert, pnpm) while the
substring table refused commands that used them. Widening a head is only half
the change: `sed -i` rewrites a file, `rg --pre` runs a program per file, `tar
--to-command` runs anything, `sysctl -w` writes kernel state. Those are refused
by flag, which is where the action lives.
"""
from __future__ import annotations

import pytest

from core.tools.base import ALLOWED_COMMANDS
from core.tools.shell_tools import validate_shell_command
from core.tools._shell_validate import (
    _FILE_HEADS,
    _FLAG_PATHS,
    _FLAG_VALUES,
    _PER_HEAD_BLOCKED_FLAGS,
    _PER_HEAD_REFUSALS,
    _PROGRAM_HEADS,
    _WRITE_HEADS,
)


class TestAddedHeadsRunTheirWork:
    """Each head is allowed for the thing it is installed for, with the sandbox
    on — the sandbox is what makes the exec itself bounded, the door still reads
    its operands."""

    @pytest.mark.parametrize("command", [
        'jq -c ".foo" data.json',
        'rg "TODO" src',
        'sed -n "1,5p" notes.txt',
        'awk -F: \'{print $1}\' people.txt',
        'printf "%s\\n" hello',
        "tee build.log",
        "shasum -a 256 dist/app.tar.gz",
        "tar -czf site.tgz dist",
        "tar -tzf site.tgz",
        "zip -r site.zip dist",
        "unzip -l site.zip",
        "ditto src build",
        "afinfo in.aiff",
        "afconvert -f wav -d pcm in.aiff out.wav",
        'say -o hello.aiff "Hallo Welt"',
        "sw_vers",
        "sysctl hw.memsize",
        "pnpm test",
    ])
    def test_given_an_added_head_then_its_work_is_allowed(self, command, tmp_path):
        assert validate_shell_command(command, sandboxed=True, root=str(tmp_path)) is None


class TestAddedHeadGuards:
    """The argv carries what the head cannot show: a flag that runs a program or
    rewrites a file. Refused by the flag, so the message names the action."""

    @pytest.mark.parametrize(("command", "marker"), [
        ('sed -i "s/a/b/" notes.txt', "edit_file"),
        ('sed --in-place s/a/b/ notes.txt', "edit_file"),
        ("awk -W prog.awk", "runs a program"),
        ("awk --file prog.awk", "runs a program"),
        ("rg --pre gzip foo", "runs a program"),
        ("rg --hostname-bin foo bar", "runs a program"),
        ("tar --to-command sh -cf a.tar dist", "arbitrary program"),
        ("tar --use-compress-program pigz -cf a.tar dist", "arbitrary program"),
        ('zip -TT "echo x" a.zip dist', "test command"),
        ("sysctl -w kern.hostname=x", "writes kernel state"),
    ])
    def test_given_a_flag_that_performs_the_action_then_named(
        self, command, marker, tmp_path
    ):
        reason = validate_shell_command(command, sandboxed=True, root=str(tmp_path))
        assert reason is not None, command
        assert marker in reason, reason


class TestProgramOperandIsData:
    """A jq filter, a sed script and an awk program are the language, not a path.
    Their `$1` and `..` are what made the file door refuse `awk '{print $1}' f`."""

    @pytest.mark.parametrize("command", [
        'awk \'{print $1, $2}\' people.txt',
        "sed 's/a\\./b./' notes.txt",
        'jq \'.foo | .[0]\' data.json',
        "sed -e 's/a/b/' notes.txt other.txt",
    ])
    def test_given_a_program_operand_then_the_files_still_get_checked(
        self, command, tmp_path
    ):
        assert validate_shell_command(command, sandboxed=True, root=str(tmp_path)) is None

    @pytest.mark.parametrize("command", [
        "awk '{print $1}' ~/.ssh/id_rsa",
        "jq . ~/Documents/../../.config/gcloud/credentials",
        "sed -e s/a/b/ ~/.aws/credentials",
    ])
    def test_given_the_operand_after_the_program_then_the_door_still_binds(
        self, command, tmp_path
    ):
        reason = validate_shell_command(command, sandboxed=True, root=str(tmp_path))
        assert reason is not None, command
        assert "file-tool roots" in reason, reason


class TestPolicyTablesAreLive:
    """A head in a rule table that the whitelist never lets through is a dead
    entry: it reads as a guard and checks nothing, because the command died two
    lines earlier. Every table keys on an allowed head."""

    def test_given_every_rule_table_then_its_heads_are_whitelisted(self):
        tables = {
            "FILE_HEADS": _FILE_HEADS,
            "WRITE_HEADS": _WRITE_HEADS,
            "FLAG_VALUES": _FLAG_VALUES,
            "FLAG_PATHS": _FLAG_PATHS,
            "PER_HEAD_BLOCKED_FLAGS": _PER_HEAD_BLOCKED_FLAGS,
            "PER_HEAD_REFUSALS": _PER_HEAD_REFUSALS,
            "PROGRAM_HEADS": _PROGRAM_HEADS,
        }
        for name, table in tables.items():
            stray = set(table) - ALLOWED_COMMANDS
            assert not stray, f"{name} carries heads the whitelist refuses anyway: {stray}"

    def test_given_a_head_that_puts_bytes_on_disk_then_the_write_set_knows_it(self):
        # A declared data root is a read grant; membership here is what keeps it read-only.
        writers = {"tee", "tar", "zip", "unzip", "ditto", "sips", "afconvert", "qlmanage"}
        assert writers <= _WRITE_HEADS, writers - _WRITE_HEADS

    def test_given_a_guarded_head_then_it_has_its_own_sentence(self):
        assert set(_PER_HEAD_BLOCKED_FLAGS) == set(_PER_HEAD_REFUSALS)

    def test_given_no_network_binary_then_the_deliberate_absence_holds(self):
        for head in ("curl", "wget", "osascript", "launchctl", "defaults", "codesign"):
            assert head not in ALLOWED_COMMANDS, head
