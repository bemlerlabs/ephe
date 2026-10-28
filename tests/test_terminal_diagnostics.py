"""Failure classes that get one repair sentence appended to the tool result."""
from __future__ import annotations

from core.terminal_diagnostics import diagnose, annotate, annotate_tool_result


def test_missing_python_package_names_the_package() -> None:
    found = diagnose("Traceback...\nModuleNotFoundError: No module named 'yaml'")
    assert found is not None
    assert found.code == "missing-python-package"
    assert "pip install yaml" in found.hint


def test_missing_import_name_names_both_sides() -> None:
    found = diagnose("ImportError: cannot import name 'load' from 'core.config'")
    assert found is not None
    assert found.code == "missing-import-name"
    assert "core.config" in found.hint and "load" in found.hint


def test_missing_node_module_suggests_npm_install() -> None:
    found = diagnose('Error [ERR_MODULE_NOT_FOUND]: Cannot find module "left-pad"')
    assert found is not None
    assert found.code == "missing-node-module"
    assert "npm install" in found.hint


def test_command_not_found_names_the_binary() -> None:
    found = diagnose("zsh: command not found: ripgrep")
    assert found is not None
    assert found.code == "command-not-found"
    assert "ripgrep" in found.hint


def test_port_conflict_reads_the_port() -> None:
    found = diagnose("Error: listen EADDRINUSE: address already in use :::3000")
    assert found is not None
    assert found.code == "port-in-use"
    assert "3000" in found.hint
    assert "lsof" in found.hint

    other = diagnose("OSError: [Errno 48] address already in use :8080")
    assert other is not None and "8080" in other.hint


def test_sandbox_refusal_is_named() -> None:
    found = diagnose("sandbox-exec: deny file-write-data /etc/hosts")
    assert found is not None
    assert found.code == "sandbox-denied"
    assert "workspace" in found.hint


def test_plain_output_gets_no_diagnosis() -> None:
    result = "total 8\ndrwxr-xr-x 2 sanji staff 64"
    assert diagnose(result) is None
    assert annotate(result, "ls -la") is result


def test_annotation_is_appended_once() -> None:
    result = "ModuleNotFoundError: No module named 'httpx'"
    first = annotate(result, "python app.py")
    assert first.startswith(result)
    assert "[diagnosis missing-python-package]" in first
    assert "after `python app.py`" in first
    assert annotate(first, "python app.py") == first


def test_registry_hook_only_touches_shell_results() -> None:
    result = "ModuleNotFoundError: No module named 'httpx'"
    assert annotate_tool_result("read_file", {"path": "a.py"}, result) == result
    shell = annotate_tool_result("run_shell", {"command": "python app.py"}, result)
    assert "[diagnosis missing-python-package]" in shell
    alias = annotate_tool_result("bash", {"command": "python app.py"}, result)
    assert "[diagnosis missing-python-package]" in alias
