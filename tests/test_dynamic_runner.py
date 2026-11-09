"""Task #9: the confined dynamic-tool runner — a plugin tool executes in a child, never here.

Every test drives a real confined child through `core.sandbox.run_worker` on this
machine's boundary (Seatbelt on macOS, the same rail #47 proved live). The subject
is the boundary, so the assertions are about where code ran and what could not:
the plugin module loaded in the child and not in this process, the writable root
and the refusals around it, and the answer when confinement is missing.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core import mcp_sandbox, plugin_manifest
from core.sandbox.runner import (
    RunResult,
    resolve_entry_file,
    resolve_plugin_dir,
    run_plugin_tool,
)
from core.tools.dynamic_registry import ToolDescriptor, fingerprint_for, served_tool_name


def _descriptor(plugin_id: str, tool: str, entry: str, *, required=("unit",)) -> ToolDescriptor:
    name = served_tool_name(plugin_id, tool)
    schema = {
        "type": "function",
        "function": {
            "name": name,
            "description": "A confined fixture tool.",
            "parameters": {
                "type": "object",
                "properties": {"unit": {"type": "string"}},
                "required": list(required),
            },
        },
    }
    return ToolDescriptor(
        name=name,
        plugin_id=plugin_id,
        schema=schema,
        transport="plugin",
        entry=entry,
        tool_family="read",
        fingerprint=fingerprint_for(schema),
    )


def _plugin(tmp_path: Path, body: str, module: str = "handlers") -> Path:
    root = tmp_path / "plugin"
    root.mkdir(exist_ok=True)
    (root / f"{module}.py").write_text(body, encoding="utf-8")
    return root


def _run(tmp_path, body, arguments, *, plugin_id="w9", module="handlers", **kw) -> RunResult:
    descriptor = _descriptor(plugin_id, "tick", f"{module}:run")
    root = _plugin(tmp_path, body, module)
    return run_plugin_tool(descriptor, arguments, root, **kw)


WRITE_DENIED_BODY = """
def run(arguments, state_dir):
    import os
    inside = os.path.join(state_dir, "inside.txt")
    with open(inside, "w") as handle:
        handle.write("inside-ok")
    escape = arguments["escape"]
    refused = None
    try:
        with open(escape, "w") as handle:
            handle.write("should-never-exist")
    except OSError as exc:
        refused = type(exc).__name__
    return {"inside": os.path.exists(inside), "refused": refused,
            "escape_exists": os.path.exists(escape)}
"""


def test_a_tool_runs_in_the_child_and_not_here(tmp_path):
    body = (
        "def run(arguments, state_dir):\n"
        "    import os, sys\n"
        "    return {\n"
        "        'pid': os.getpid(),\n"
        "        'module': __name__,\n"
        "        'main_file': getattr(sys.modules['__main__'], '__file__', ''),\n"
        "        'unit': arguments.get('unit'),\n"
        "    }\n"
    )
    result = _run(tmp_path, body, {"unit": "seconds"})
    assert result.kind == "result", result.text
    payload = json.loads(result.text)
    assert payload["unit"] == "seconds"
    # The proof the import happened in the child: a different pid, the plugin
    # module named in the child, and the launcher as __main__ — never this process.
    assert payload["pid"] != os.getpid()
    assert payload["module"] == "plugin_entry"
    assert "worker_launcher.py" in payload["main_file"]
    # Nothing of the plugin crossed into the backend process (ruling A1).
    assert "plugin_entry" not in sys.modules


def test_writes_land_in_the_data_root_and_nowhere_else(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    escape = str(Path.home() / ".w9_escape_probe")
    Path(escape).unlink(missing_ok=True)
    result = _run(tmp_path, WRITE_DENIED_BODY, {"unit": "s", "escape": escape})
    assert result.kind == "result", result.text
    payload = json.loads(result.text)
    assert payload["inside"] is True
    assert payload["refused"] == "PermissionError"
    assert payload["escape_exists"] is False
    assert not Path(escape).exists(), "the confined child wrote outside its data root"


def test_a_slow_tool_times_out_and_leaves_no_process(tmp_path):
    marker = "w9sloworphanmarker42"
    body = (
        "def run(arguments, state_dir):\n"
        "    import subprocess, sys, time\n"
        "    subprocess.Popen([sys.executable, '-c',\n"
        "        'import time; time.sleep(30) #%s' % arguments['marker']])\n"
        "    time.sleep(30)\n"
    )
    result = _run(tmp_path, body, {"unit": "s", "marker": marker}, timeout_seconds=1.0)
    assert result.kind == "error"
    assert "timed out" in result.text
    assert "/Users/" not in result.text and str(tmp_path) not in result.text
    probe = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True)
    assert probe.stdout.strip() == "", f"orphan survived: {probe.stdout}"


def test_an_escaping_entry_is_refused_before_any_spawn(tmp_path):
    root = _plugin(tmp_path, "def run(a, s):\n    return 1\n")
    marker = root / "RAN"
    for hostile in ("../evil:run", "/etc/passwd:run"):
        entry_file, error = resolve_entry_file(root, hostile)
        assert entry_file is None and error, hostile
    # A symlink that points out of the plugin directory is refused too.
    outside = tmp_path / "outside_target.py"
    outside.write_text("def run(a, s):\n    return 1\n", encoding="utf-8")
    (root / "evil.py").symlink_to(outside)
    entry_file, error = resolve_entry_file(root, "evil:run")
    assert entry_file is None and "outside" in error
    assert not marker.exists(), "an escaping entry reached the child"


def test_no_confinement_refuses_and_the_child_never_starts(tmp_path, monkeypatch):
    marker = tmp_path / "plugin" / "RAN"
    body = f"def run(a, s):\n    import pathlib; pathlib.Path({str(marker)!r}).write_text('x')\n    return 1\n"
    monkeypatch.setattr(mcp_sandbox, "platform_boundary", lambda: "unavailable")
    result = _run(tmp_path, body, {"unit": "s"})
    assert result.kind == "refusal"
    assert result.code == "sandbox_unavailable"
    assert "not spawned" in result.text or "not run" in result.text
    assert not marker.exists(), "the child ran even though confinement was missing"
    assert "/Users/" not in result.text


def test_oversized_stderr_is_capped_with_the_tail(tmp_path):
    body = (
        "def run(a, s):\n"
        "    import sys\n"
        "    sys.stderr.write('x' * 20000)\n"
        "    sys.stderr.write('TAILMARK\\n')\n"
        "    raise RuntimeError('tool failed')\n"
    )
    result = _run(tmp_path, body, {"unit": "s"}, output_cap_bytes=600)
    assert result.kind == "error"
    assert "TAILMARK" in result.text
    assert "cap 600" in result.text
    assert len(result.text) < 4000


def test_crash_and_nonzero_are_distinct_and_sanitised(tmp_path):
    crash = _run(
        tmp_path,
        "def run(a, s):\n    import os, signal\n    os.kill(os.getpid(), signal.SIGTERM)\n",
        {"unit": "s"},
    )
    nonzero = _run(
        tmp_path,
        "def run(a, s):\n    import sys\n    sys.exit(7)\n",
        {"unit": "s"},
    )
    raised = _run(
        tmp_path,
        "def run(a, s):\n    raise ValueError('bad input')\n",
        {"unit": "s"},
    )
    assert crash.status == "crashed" and "signal 15" in crash.text
    assert nonzero.status == "nonzero" and "7" in nonzero.text
    assert raised.status == "tool_error" and "ValueError" in raised.text
    for result in (crash, nonzero, raised):
        assert result.kind == "error"
        assert result.text.startswith("[TOOL-ERROR]")
        assert "/Users/" not in result.text and str(tmp_path) not in result.text


async def test_bad_arguments_never_spawn_a_child(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    body = (
        "def run(a, s):\n"
        "    import pathlib\n"
        f"    pathlib.Path({str(tmp_path / 'CHILD')!r}).write_text('ran')\n"
        "    return 1\n"
    )
    descriptor = _descriptor("w9", "tick", "handlers:run", required=("unit",))
    _plugin(tmp_path, body)
    from core.tools.dynamic_registry import default_registry
    from core.tools.dynamic_wiring import dispatch_dynamic_call

    assert default_registry().register(descriptor).ok
    try:
        # A missing required argument is refused by the kernel validator before the
        # transport is reached, so no worker is started at all.
        answer = await dispatch_dynamic_call(descriptor.name, {})
    finally:
        default_registry().unregister_plugin("w9")
    assert answer is not None and "[TOOL-ERROR]" in answer
    assert not (tmp_path / "CHILD").exists(), "a child started despite bad arguments"


def test_resolution_resolves_inside_the_plugin_dir(tmp_path):
    root = _plugin(tmp_path, "def run(a, s):\n    return 1\n")
    entry_file, error = resolve_entry_file(root, "handlers:run")
    assert error == ""
    assert entry_file is not None
    assert str(entry_file).startswith(str(Path(root).resolve()))


def test_resolve_plugin_dir_finds_a_scanned_manifest(tmp_path, monkeypatch):
    plugins = tmp_path / "plugins" / "w9found"
    plugins.mkdir(parents=True)
    (plugins / "ephe-plugin.json").write_text(
        json.dumps({
            "manifest_version": 1,
            "name": "w9found",
            "version": "0.1.0",
            "description": "A scanned fixture plugin.",
            "permissions": {"tool_families": ["read"], "data_roots": []},
            "components": {},
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", tmp_path / "plugins")
    assert resolve_plugin_dir("w9found") == plugins
    assert resolve_plugin_dir("w9missing") is None


def _mount(tmp_path, monkeypatch, plugin_id: str, body: str) -> Path:
    """Put a resolvable plugin with one tool module under the scan root."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    root = tmp_path / "plugins" / plugin_id
    root.mkdir(parents=True)
    (root / "ephe-plugin.json").write_text(
        json.dumps({
            "manifest_version": 1, "name": plugin_id, "version": "0.1.0",
            "description": "A confined fixture plugin.",
            "permissions": {"tool_families": ["read"], "data_roots": []},
            "components": {},
        }),
        encoding="utf-8",
    )
    (root / "handlers.py").write_text(body, encoding="utf-8")
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", tmp_path / "plugins")
    return root


@pytest.mark.asyncio
async def test_a_plugin_descriptor_runs_through_the_transport(tmp_path, monkeypatch):
    from core.tools.dynamic_registry import default_registry
    from core.tools.registry import execute_tool, invalidate_tool_schema_cache

    _mount(tmp_path, monkeypatch, "w9e2e", (
        "def run(arguments, state_dir):\n"
        "    import os\n"
        "    return {'pid': os.getpid(), 'unit': arguments.get('unit')}\n"
    ))
    descriptor = _descriptor("w9e2e", "tick", "handlers:run")
    assert default_registry().register(descriptor).ok
    invalidate_tool_schema_cache()
    try:
        result = await execute_tool(descriptor.name, {"unit": "seconds"})
    finally:
        default_registry().unregister_plugin("w9e2e")
    payload = json.loads(str(result))
    assert payload["unit"] == "seconds"
    assert payload["pid"] != os.getpid()
    # The post-hook returned a plain result string, and no plugin code is in this process.
    assert "plugin_entry" not in sys.modules


@pytest.mark.asyncio
async def test_an_unresolvable_plugin_still_answers_not_available(tmp_path, monkeypatch):
    from core.tools.dynamic_registry import default_registry
    from core.tools.registry import execute_tool

    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", tmp_path / "empty-plugins")
    descriptor = _descriptor("w9ghost", "tick", "handlers:run")
    assert default_registry().register(descriptor).ok
    try:
        result = await execute_tool(descriptor.name, {"unit": "seconds"})
    finally:
        default_registry().unregister_plugin("w9ghost")
    assert "is not available" in str(result)
    assert getattr(result, "code", "") == "tool_not_available"
