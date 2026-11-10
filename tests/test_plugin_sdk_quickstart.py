"""The SDK guide opens with a quickstart that is ten lines and actually runs.

A guide that opens with a mental model and closes with a checklist still leaves the author
to assemble the first plugin themselves. `docs/PLUGIN_SDK.md` therefore opens with the
shortest real path: create the folder, write the manifest, ship the document it declares,
look, switch it on. This test holds the block to its promises — ten lines at most, every
`ephe` word a parser choice, and the block executed in a throwaway home, so the reader can
copy it.

Nothing in the block touches the developer's own device state: `HOME` points at a temporary
directory and the `ephe` on `PATH` is a shim around this checkout.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import ephe_cli

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "PLUGIN_SDK.md"
SECTION = "## Quickstart"
FENCE = re.compile(r"```(?:bash|sh)\n(.*?)```", re.DOTALL)
_COMMAND = re.compile(r"^\s*ephe\s+([a-z][a-z0-9-]*)(?:\s+([a-z][a-z0-9-]*))?")


def _block() -> str:
    text = GUIDE.read_text(encoding="utf-8")
    start = text.index(SECTION)
    rest = text[start:]
    match = FENCE.search(rest)
    assert match, "the quickstart section carries no shell block"
    return match.group(1)


def _lines() -> list[str]:
    return [line.rstrip() for line in _block().splitlines()]


def _command_lines() -> list[str]:
    return [
        line.strip()
        for line in _lines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_the_quickstart_is_ten_lines_of_real_commands():
    """GIVEN the opening quickstart
    WHEN its shell lines are counted
    THEN it holds ten at most — the point is a path a reader can hold in the head."""
    commands = _command_lines()

    assert commands, "the quickstart has no command"
    assert len(commands) <= 10, f"the quickstart is {len(commands)} lines: {commands}"
    assert commands[0].startswith("mkdir -p ~/.ephe/plugins/")


def test_every_ephe_word_in_the_quickstart_is_a_parser_choice():
    parser = ephe_cli.build_parser()
    parents: dict[str, object] = {}
    for action in parser._actions:
        if hasattr(action, "choices") and action.choices:
            parents = dict(action.choices)
    for line in _command_lines():
        match = _COMMAND.match(line)
        if not match:
            continue
        parent, child = match.group(1), match.group(2)
        assert parent in parents, f"`ephe {parent}` is not a command"
        if child:
            children = [
                name
                for action in parents[parent]._actions
                if hasattr(action, "choices") and action.choices
                for name in action.choices
            ]
            assert child in children, f"`ephe {parent} {child}` is not an action"


def test_the_quickstart_names_the_folder_the_manifest_and_the_switch():
    text = _block()
    assert "~/.ephe/plugins/" in text
    assert "ephe-plugin.json" in text
    assert "ephe plugin list" in text
    assert "ephe plugin enable" in text


def test_the_quickstart_runs_in_a_throwaway_home(tmp_path):
    """GIVEN the quickstart block, copied as written
    WHEN it runs against a temporary home and this checkout's CLI
    THEN it ends on a bundle the scanner lists, with no refusal on the way."""
    home = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    (home / ".ephe").mkdir(parents=True)
    bin_dir.mkdir()
    shim = bin_dir / "ephe"
    shim.write_text(
        "#!/bin/sh\n"
        f'exec "{sys.executable}" -m ephe_cli "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    # The block uses the default device root under HOME; an inherited override would
    # split the two, so the two names that could are removed from the child's environment.
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"EPHE_CONFIG_DIR", "EPHE_PLUGINS_ROOT"}
    }
    env.update(
        {
            "HOME": str(home),
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "PYTHONPATH": str(ROOT),
        }
    )

    result = subprocess.run(
        ["/bin/bash", "-e", "-c", _block()],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, result.stderr
    listing = subprocess.run(
        [str(shim), "plugin", "list"],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert listing.returncode == 0, listing.stderr
    assert "hello-card" in listing.stdout
    assert "0.1.0" in listing.stdout
    assert "invalid" not in listing.stdout
    # the enable step is the last line and it answered for the bundle
    assert "hello-card: enabled" in result.stdout
    assert (home / ".ephe" / "plugins" / "hello-card" / "ephe-plugin.json").is_file()


def test_the_guide_states_what_installed_means():
    """The word "installed" is the one a reader must not have to guess: folder presence
    under the plugins root is what makes a bundle loadable."""
    text = GUIDE.read_text(encoding="utf-8")
    quickstart = text[text.index(SECTION):]
    assert "plugins root" in quickstart.lower() or "scanner" in quickstart.lower()
