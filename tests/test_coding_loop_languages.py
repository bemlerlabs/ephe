"""Language coverage of the edit-time checker."""
from __future__ import annotations

from pathlib import Path

import pytest

from core import coding_loop
from tests.support.capabilities import requires_rustc


def _fake_which(monkeypatch: pytest.MonkeyPatch, present: set[str]) -> None:
    monkeypatch.setattr(
        coding_loop.shutil,
        "which",
        lambda name: f"/opt/tools/{name}" if name in present else None,
    )


def test_tsx_uses_the_tsx_loader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_which(monkeypatch, {"esbuild"})
    path = tmp_path / "view.tsx"
    path.write_text("export const x = 1\n", encoding="utf-8")
    command = coding_loop.verification_command(path)
    assert command == ["/opt/tools/esbuild", str(path), "--loader=tsx", "--log-level=silent"]


def test_ts_uses_the_ts_loader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_which(monkeypatch, {"esbuild"})
    path = tmp_path / "util.ts"
    path.write_text("export const x = 1\n", encoding="utf-8")
    command = coding_loop.verification_command(path)
    assert "--loader=ts" in command


def test_local_esbuild_binary_is_used_when_path_has_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_which(monkeypatch, set())
    binary = tmp_path / "node_modules" / ".bin" / "esbuild"
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")
    path = tmp_path / "src" / "app.ts"
    path.parent.mkdir()
    path.write_text("export const x = 1\n", encoding="utf-8")
    command = coding_loop.verification_command(path)
    assert command[0] == str(binary)


def test_rust_uses_metadata_emission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_which(monkeypatch, {"rustc"})
    path = tmp_path / "lib.rs"
    path.write_text("pub fn a() {}\n", encoding="utf-8")
    command = coding_loop.verification_command(path)
    assert command[:4] == ["/opt/tools/rustc", "--emit=metadata", "--crate-type=lib", str(path)]
    assert command[-2] == "-o"
    assert command[-1].endswith(".check.rmeta")


def test_missing_toolchain_means_no_checker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_which(monkeypatch, set())
    for name in ("a.ts", "a.tsx", "a.rs"):
        path = tmp_path / name
        path.write_text("", encoding="utf-8")
        assert coding_loop.verification_command(path) is None


@requires_rustc
def test_rust_repair_loop_reads_a_real_compile_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(coding_loop, "_esbuild", coding_loop._esbuild)
    coding_loop.reset_turn()
    broken = tmp_path / "broken.rs"
    broken.write_text("pub struct Broken {\n", encoding="utf-8")
    verdict = coding_loop.verify(broken, timeout=60)
    assert verdict is not None and verdict.ok is False
    assert "unclosed" in verdict.output.lower() or "error" in verdict.output.lower()

    coding_loop.reset_turn()
    fixed = tmp_path / "fixed.rs"
    fixed.write_text("pub struct Fixed {\n    pub a: u8,\n}\n", encoding="utf-8")
    verdict = coding_loop.verify(fixed, timeout=60)
    assert verdict is not None and verdict.ok is True


@requires_rustc
def test_the_rust_checker_is_the_compiler_the_capability_probe_finds(tmp_path: Path) -> None:
    """One authority: the loop runs the compiler the probe proved, not a path of its own.

    Both resolve through PATH, so both name the same binary; the public CI failure was
    not a second resolver — it was the sandbox hiding the one path both had agreed on.
    This pin keeps a future "just use ~/.cargo/bin/rustc" from splitting the two answers
    again, because such a guess would still be a path nobody probed.
    """
    from tests.support.capabilities import rustc_path

    path = tmp_path / "lib.rs"
    path.write_text("pub fn a() {}\n", encoding="utf-8")
    command = coding_loop.verification_command(path)
    assert command is not None
    assert command[0] == str(rustc_path())
