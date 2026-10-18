"""A keyed engine has to say where its token comes from, in the code and in the docs.

The measured start of this file (2026-10-10, installed desktop build): an app opened from
the Dock spawns its own backend, and that backend process carried 36 environment variables
with no `EPHE_` among them. So `export EPHE_OPENAI_COMPAT_API_KEY=… && ephe start`
authenticates a keyed endpoint, and the icon-launched app cannot be reached by that export at
all. `~/.ephe/engine.key` (owner-only, written by the user) is the file equivalent of that
export: `app/src-tauri/src/backend.rs` feeds it to the process it spawns, and since the
opencode fallback was removed on 2026-10-10 `core/engine_config.py` reads it for every other
start. docs/SECURITY_THREAT_MODEL.md §1a is the copy that promises both.

These tests keep the promise and the code from drifting apart: the variable and file names the
spawn uses, the places a token is explicitly not stored, every source the resolver actually
consults, and the endpoint rule that decides which engine needs a token at all. No test here
reads or prints a token value — names, fields and existence only.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BACKEND_RS = ROOT / "app" / "src-tauri" / "src" / "backend.rs"
THREAT_MODEL = ROOT / "docs" / "SECURITY_THREAT_MODEL.md"

#: every source the token resolver consults -> the phrase §1a has to name it with
MUST_BE_NAMED = {
    "EPHE_OPENAI_COMPAT_API_KEY": "EPHE_OPENAI_COMPAT_API_KEY",
    "engine.key": "engine.key",
}


@pytest.fixture(scope="module")
def backend_source() -> str:
    return BACKEND_RS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def threat_model() -> str:
    return THREAT_MODEL.read_text(encoding="utf-8")


def _const(source: str, name: str) -> str:
    match = re.search(rf'pub const {name}: &str = "([^"]+)"', source)
    assert match, f"backend.rs declares no {name}"
    return match.group(1)


def test_spawn_hands_the_one_declared_variable_to_the_backend(backend_source):
    """The desktop bridge sets the variable the engine already reads, and no other."""
    assert _const(backend_source, "KEY_ENV") == "EPHE_OPENAI_COMPAT_API_KEY"
    literals = [
        name
        for name in re.findall(r'\.env\(\s*"([^"]+)"', backend_source)
        if name not in {"EPHE_BACKEND_OWNER", "EPHE_PARENT_PID"}
    ]
    assert literals == [], f"hardcoded env names beside the declared one: {literals}"
    assert backend_source.count("cmd.env(") == 1, "a second env injection point appeared"


def test_declared_key_file_is_named_where_the_user_reads_it(backend_source, threat_model):
    """A path only the source knows is not a surface: the docs have to spell it out."""
    file_name = _const(backend_source, "KEY_FILE")
    assert f"~/.ephe/{file_name}" in threat_model, (
        f"backend.rs reads ~/.ephe/{file_name}, the security doc does not name it"
    )
    assert "0600" in threat_model, "the owner-only rule the read enforces is unexplained"


def test_the_reuse_branch_reads_fields_the_backend_actually_answers(backend_source):
    """The seam between the shell and the route runs across two languages.

    `statement()` decides the desktop reuse branch from two keys of `GET /api/health`, and a
    missing key makes it answer `None` — which reads back as "no Ephe backend on this port",
    the exact guess this branch replaced. Rename a field on either side and this fails; the
    two-process behaviour is pinned in `tests/test_engine_reuse_statement.py`.
    """
    from server.routes.health import HealthResponse

    match = re.search(r"pub fn statement\(port: u16\).*?\n}\n", backend_source, re.S)
    assert match, "backend.rs declares no statement() — re-read the reuse branch"
    parsed = set(re.findall(r'\.get\("([a-z_]+)"\)', match.group(0)))
    assert parsed, "statement() no longer reads a field by name"
    answered = set(HealthResponse.model_fields)
    missing = sorted(parsed - answered)
    assert not missing, f"the shell parses {missing}, /api/health does not answer them"


def test_the_engine_config_has_no_place_for_a_key(tmp_path):
    """`engine.json` and `desktop.json` stay secret-free, whatever the spawn does with one."""
    from core.engine_config import EngineChoice
    from ephe_cli import _schreibe_desktop_konfig

    home = tmp_path / "home"
    _schreibe_desktop_konfig(ROOT, "/usr/bin/python3", home=home)
    line = json.loads((home / ".ephe" / "desktop.json").read_text(encoding="utf-8"))
    assert sorted(line) == ["port", "project_root", "python"]

    choice = EngineChoice("openai_compatible", "m", "https://api.example-gateway.test/v1")
    secret_fields = [
        name
        for name in vars(choice)
        if re.search(r"key|token|secret|credential", name, re.I)
    ]
    assert secret_fields == []


def _resolver_source() -> str:
    """The three functions the resolver is made of, read out of the module file.

    AST instead of `inspect.getsource`: an autouse fixture makes the key-file path hermetic for
    every test, and `inspect` would then describe the fixture rather than the code under review.
    """
    text = (ROOT / "core" / "engine_config.py").read_text(encoding="utf-8")
    wanted = {"engine_api_key_for", "_key_file", "key_file_path"}
    tree = ast.parse(text)
    bodies = [
        ast.get_source_segment(text, node)
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    assert len(bodies) == len(wanted), f"the resolver is no longer these three functions: {bodies}"
    return "\n".join(b for b in bodies if b)


def test_every_source_the_resolver_reads_is_declared_in_the_doc(threat_model):
    """A silent third key source is the exact defect this product forbids.

    The check runs over the resolver's own source: whoever adds a variable or a credential
    file there has to add the same name to §1a before this passes, so the list of places a
    token can enter the engine stays maintainable in one glance.

    The file scan covers `.json` and `.key` — a store named after what it holds is exactly how
    the old opencode fallback hid from a `.json`-only pattern.
    """
    source = _resolver_source()
    env_names = set(re.findall(r'environ(?:\.get\()?["\[]?(EPHE_[A-Z_]+)', source))
    files = set(re.findall(r'"([\w.]+\.(?:json|key))"', source))
    consulted = env_names | files
    assert consulted == set(MUST_BE_NAMED), (
        f"the resolver's sources and §1a's list differ: reads {sorted(consulted)}, "
        f"declared {sorted(MUST_BE_NAMED)}"
    )

    missing = [name for name in consulted if MUST_BE_NAMED[name] not in threat_model]
    assert not missing, f"§1a no longer names: {sorted(missing)}"


def test_the_key_file_rules_match_the_desktop_spawn(tmp_path):
    """The Python reader refuses what the Rust reader refuses, for the same reason.

    Owner-only, exactly one non-empty line, a regular file. Anything looser is a file the
    machine leaks to more processes than its owner, and a resolver that "helpfully" trims a
    multi-line file would be choosing between two secrets the user did not choose for it.
    """
    from core.engine_config import _key_file

    home = tmp_path / "home"
    (home / ".ephe").mkdir(parents=True)
    real = home / ".ephe" / "engine.key"

    def write(text: str, mode: int = 0o600) -> None:
        real.write_text(text, encoding="utf-8")
        real.chmod(mode)

    assert _key_file(home=home) == ""  # a machine that never stored a token is the normal state
    write("  token-value \n")
    assert _key_file(home=home) == "token-value", "surrounding whitespace is not part of a token"
    write("token-value\n", mode=0o644)
    assert _key_file(home=home) == "", "a world-readable token is refused"
    write("one\ntwo\n")
    assert _key_file(home=home) == "", "two lines are two tokens, and the resolver may not pick"
    write("")
    assert _key_file(home=home) == "", "an empty file is no token"
    real.unlink()
    (home / "other").write_text("token-value", encoding="utf-8")
    real.symlink_to(home / "other")
    assert _key_file(home=home) == "", "a symlink is refused, so the check cannot be redirected"


def test_the_keyed_endpoint_class_is_the_public_host(monkeypatch):
    """Needing a token is a property of the host, not of the provider label.

    The free cloud candidate is a public host and therefore keyed; a Tailnet engine is not.
    The failure text of the keyed case is pinned because the surface quotes that sentence.
    """
    from core.model_provider import (
        ModelProviderConfig,
        ProviderSetupError,
        _endpoint_requires_api_key,
        ensure_provider_ready,
    )

    monkeypatch.delenv("EPHE_OPENAI_COMPAT_API_KEY", raising=False)
    assert _endpoint_requires_api_key("https://openrouter.ai/api/v1") is True
    assert _endpoint_requires_api_key("http://host-one.example.ts.net:8888/v1") is False

    keyed = ModelProviderConfig(
        provider="openai_compatible",
        model="m",
        base_url="https://api.example-gateway.test/v1",
        label="OpenAI-compatible API",
        offline_capable=False,
        requires_internet=True,
        requires_api_key=True,
        api_key_configured=False,
    )
    with pytest.raises(ProviderSetupError) as raised:
        ensure_provider_ready(keyed)
    assert "EPHE_OPENAI_COMPAT_API_KEY" in str(raised.value)


def test_no_token_file_is_tracked_by_git():
    """Never in a commit: the repo tracks no key file, and the ignore rule covers one."""
    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert [p for p in tracked if p.endswith(".key")] == []
    ignored = subprocess.run(
        ["git", "-C", str(ROOT), "check-ignore", "engine.key"],
        capture_output=True,
        text=True,
    )
    assert ignored.returncode == 0, "*.key is not ignored — a key file could be committed"
