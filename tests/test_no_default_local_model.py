"""D2 (#94): the product names no model on the user's behalf.

Ollama stays a first-class, fully offline engine class; which tag runs inside it is
the user's choice. A tag that ships as a default is a model the product picked, so
these pins hold two facts: no source a user inherits names a model, and every path
that used to fill one in refuses with the env name instead.

Written before the code that makes them pass (owner decision 2026-10-11).
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Sources whose literals reach a user who never configured anything: parser defaults,
#: env fallbacks, onboarding seeds, the example templates, and the register surface that
#: offers the choice. A tag inside a test fixture is a made-up name; a tag here is a model
#: the product picked.
SHIPPED_DEFAULT_SOURCES = (
    "core/model_config.py",
    "core/model_provider.py",
    "core/engine_config.py",
    "core/_cli_common.py",
    "core/_cli_onboarding.py",
    "core/_cli_ollama.py",
    "core/model_router.py",
    "core/scheduler.py",
    "core/skills.py",
    "core/swarm.py",
    "core/swarm_v2.py",
    "core/vision.py",
    "core/tools/system_tools.py",
    "server/openai.py",
    "ephe.py",
    "ephe_cli.py",
    "ui/app.py",
    ".env.example",
    "engine.example.json",
    "app/src/lib/contextMeter.ts",
)

#: A whole surface rather than a file list, because the register is where a shipped tag
#: reappears first: the picker that answers for an engine which did not reply. Test files
#: are out of scope for the same reason the core fixtures are — a tag there is invented
#: data, not a default.
SHIPPED_DEFAULT_GLOBS = (
    ("app/src/components/dashboard/settings/model", "*.ts"),
    ("app/src/components/dashboard/settings/model", "*.tsx"),
)


def _scanned_sources() -> list[str]:
    found = list(SHIPPED_DEFAULT_SOURCES)
    for directory, pattern in SHIPPED_DEFAULT_GLOBS:
        for path in sorted((ROOT / directory).glob(pattern)):
            if ".test." in path.name:
                continue
            found.append(f"{directory}/{path.name}")
    return found


MODEL_TAG = re.compile(
    r"\b(?:gemma|qwen|llama|mistral|minicpm|phi|deepseek|codellama|ds)[a-z0-9._-]*:[a-z0-9._-]+",
    re.IGNORECASE,
)


def test_given_default_shipping_sources_when_scanned_then_none_names_a_model():
    offenders = []
    for rel in _scanned_sources():
        text = (ROOT / rel).read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for tag in MODEL_TAG.findall(line):
                offenders.append(f"{rel}:{line_no} names {tag}")
    assert offenders == []


def test_the_register_surface_is_actually_scanned():
    """A glob that matched nothing would turn the scan above into a pass by absence, so the
    two files this wave found tags in are named here. Test files stay out by rule."""
    scanned = [rel for rel in _scanned_sources() if rel.startswith("app/src/components/")]
    model_dir = "app/src/components/dashboard/settings/model/"
    for name in ("useSettingsCore.ts", "useSettingsSave.ts"):
        assert model_dir + name in scanned, scanned
    assert not [p for p in scanned if ".test." in p], scanned
    assert len(scanned) > 10, scanned


def _tags_in(text: str) -> list[tuple[int, str]]:
    return [
        (line_no, tag)
        for line_no, line in enumerate(text.splitlines(), start=1)
        for tag in MODEL_TAG.findall(line)
    ]


def test_given_a_lane_committed_a_half_state_when_head_is_scanned_then_it_is_complete():
    """A shared worktree lets a partial commit carry whatever the file holds at that
    moment, so this reads HEAD — the blob a CI checkout gets — beside the working copy."""
    import subprocess

    head = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True
    )
    if head.returncode != 0:
        pytest.skip("no commit to read")

    offenders = []
    for rel in _scanned_sources():
        blob = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"HEAD:{rel}"], capture_output=True, text=True
        )
        if blob.returncode != 0:
            continue  # a path not in this commit ships nothing
        offenders += [f"HEAD:{rel}:{n} names {t}" for n, t in _tags_in(blob.stdout)]
    assert offenders == []


def test_no_env_lookup_in_the_shipped_code_carries_a_model_default():
    """A two-argument `os.environ.get` whose fallback is a model tag is a shipped default
    in its most compact form; `core/`, `ui/`, our own /v1 surface and the chat/vision
    route modules may not carry one."""
    env_default = re.compile(r"""os\.environ\.get\(\s*["'][A-Z0-9_]+["']\s*,\s*["']([^"']+)["']""")
    paths = sorted((ROOT / "core").rglob("*.py")) + sorted((ROOT / "ui").rglob("*.py"))
    # The chat/vision request `model` defaults are sentinels — empty while EPHE_MODEL
    # is unset — so a fallback tag in these two files is the exact shipped default
    # this test exists to catch (D2 residual).
    paths += [
        ROOT / "ephe.py",
        ROOT / "ephe_cli.py",
        ROOT / "server" / "openai.py",
        ROOT / "server" / "routes" / "chat.py",
        ROOT / "server" / "routes" / "vision.py",
    ]

    offenders = []
    for path in paths:
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = env_default.search(line)
            if match and MODEL_TAG.search(match.group(1)):
                offenders.append(f"{path.relative_to(ROOT)}:{line_no} defaults to {match.group(1)}")
    assert offenders == []


@pytest.mark.parametrize(
    ("module", "attr"),
    [
        ("core.model_config", "recommended_fast_model"),
        ("core.model_provider", "DEFAULT_LOCAL_MODEL"),
        ("core.engine_config", "DEFAULT_LOCAL_MODEL"),
        ("core._cli_common", "DEFAULT_MODEL"),
    ],
)
def test_given_a_removed_picker_when_the_module_loads_then_the_name_is_gone(module, attr):
    assert not hasattr(importlib.import_module(module), attr)


def test_local_ollama_env_without_a_tag_refuses_with_the_env_name(monkeypatch):
    from core.engine_config import EngineNotConfigured, engine_choice_from_env

    monkeypatch.setenv("EPHE_MODEL_PROVIDER", "local_ollama")
    monkeypatch.delenv("EPHE_MODEL", raising=False)

    with pytest.raises(EngineNotConfigured) as exc:
        engine_choice_from_env()
    assert "EPHE_MODEL" in str(exc.value)
    assert "ephe configure" in exc.value.hint


def test_local_ollama_env_with_a_tag_keeps_it(monkeypatch):
    from core.engine_config import engine_choice_from_env

    monkeypatch.setenv("EPHE_MODEL_PROVIDER", "local_ollama")
    monkeypatch.setenv("EPHE_MODEL", "mine:work")

    assert engine_choice_from_env().model == "mine:work"


def test_provider_without_a_tag_names_no_model(monkeypatch):
    """The engine class is chosen (Ollama on this machine), the tag is not. An active
    model nobody named used to read back as a shipped default on every surface."""
    import core.model_provider as provider

    monkeypatch.delenv("EPHE_MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("EPHE_MODEL", raising=False)
    monkeypatch.setattr(provider, "_ACTIVE_OVERRIDE", None, raising=False)

    active = provider.get_active_provider()
    assert active.provider == "local_ollama"
    assert active.model == ""


def test_provider_options_offer_no_tag():
    """The two Ollama classes are the ones that used to ship a local tag; the
    openai_compatible entry keeps its neutral 'custom-model' placeholder, which names
    no model of ours and is pinned by the provider-switch tests."""
    import core.model_provider as provider

    for option in provider.list_provider_options():
        if option["provider"] in ("local_ollama", "custom_ollama"):
            assert option["model"] == "", option["provider"]


def test_chosen_model_takes_the_tag_the_env_named(monkeypatch):
    from core.model_provider import chosen_model

    monkeypatch.setenv("EPHE_MODEL", "mine:work")
    assert chosen_model("a scheduled job") == "mine:work"


def test_chosen_model_uses_the_tag_of_the_chosen_engine(monkeypatch):
    """EPHE_MODEL is one source of the tag; the chosen engine is another, and it answers
    here too — the scheduler, the skill test and the vision call run the user's own
    choice."""
    import core.model_provider as provider
    from core.model_provider import ModelProviderConfig, chosen_model

    monkeypatch.delenv("EPHE_MODEL", raising=False)
    monkeypatch.setattr(provider, "_ACTIVE_OVERRIDE", ModelProviderConfig(
        provider="local_ollama",
        model="mine:from-engine",
        base_url="http://localhost:11434",
        label="Local Ollama",
        offline_capable=True,
        requires_internet=False,
    ), raising=False)
    assert chosen_model() == "mine:from-engine"


def test_chosen_model_refuses_instead_of_sending_an_empty_tag(monkeypatch):
    import core.model_provider as provider
    from core.engine_config import EngineNotConfigured
    from core.model_provider import chosen_model

    monkeypatch.delenv("EPHE_MODEL", raising=False)
    monkeypatch.delenv("EPHE_MODEL_PROVIDER", raising=False)
    monkeypatch.setattr(provider, "_ACTIVE_OVERRIDE", None, raising=False)

    with pytest.raises(EngineNotConfigured, match="No model chosen for the vision call"):
        chosen_model("the vision call")


def test_tiers_carry_no_name_until_the_user_configures_one():
    import core.model_config as model_config

    with patch.dict("os.environ", {}, clear=True):
        built = model_config._build_tier_map()
    assert [cfg.name for cfg in built.values()] == ["", "", ""]


def test_tiers_read_the_tags_the_user_configured():
    import core.model_config as model_config

    env = {
        "EPHE_OFFLINE_MODEL": "mine:tiny",
        "EPHE_FAST_MODEL": "mine:work",
        "EPHE_POWER_MODEL": "mine:big",
    }
    with patch.dict("os.environ", env, clear=True):
        names = {cfg.name for cfg in model_config._build_tier_map().values()}
    assert names == set(env.values())


def test_an_unnamed_tier_matches_no_window(monkeypatch):
    """Prefix matching over an empty tier name would hand every unnamed model the
    tier's window; the table may only answer for a tag that was actually configured."""
    import core.model_config as model_config
    from core.model_config import ModelConfig, ModelTier

    monkeypatch.setattr(
        model_config,
        "TIER_MAP",
        {tier: ModelConfig(name="", tier=tier) for tier in ModelTier},
    )
    assert model_config.context_window_for_model("") is None
    assert model_config.context_window_for_model("mine:work") is None


def test_onboarding_prompts_with_no_default_and_stores_what_was_typed(tmp_path, monkeypatch):
    """The Ollama branch used to print `Modell [Default <tag>]:` and store that tag on (language-gate: ignore — quoted CLI output under test)
    an empty Enter. With nothing seeded it asks, and an empty answer asks again."""
    import ephe_cli as cli

    monkeypatch.delenv("EPHE_MODEL", raising=False)
    prompts: list[str] = []

    def input_fn(prompt: str) -> str:
        prompts.append(prompt)
        if len(prompts) == 1:
            return "1"
        if len(prompts) == 2:
            return ""
        return "mine:chosen"

    choice = cli._run_engine_onboarding(
        input_fn=input_fn, config_path=tmp_path / "engine.json"
    )

    assert "Default" not in prompts[1], prompts
    assert choice.provider == "local_ollama"
    assert choice.model == "mine:chosen"


def test_onboarding_aborted_at_the_model_prompt_stores_nothing(tmp_path, monkeypatch):
    import ephe_cli as cli
    from core.engine_config import EngineNotConfigured

    monkeypatch.delenv("EPHE_MODEL", raising=False)

    def input_fn(prompt: str) -> str:
        if "Engine" in prompt:
            return "1"
        raise EOFError

    with pytest.raises(EngineNotConfigured):
        cli._run_engine_onboarding(input_fn=input_fn, config_path=tmp_path / "engine.json")
    assert not (tmp_path / "engine.json").exists()


def test_onboarding_keeps_an_env_seeded_tag_as_the_shown_choice(tmp_path, monkeypatch):
    """EPHE_MODEL is an explicit choice, so the prompt may show it — this is the one
    side that must not have been thrown out with the shipped default."""
    import ephe_cli as cli

    monkeypatch.setenv("EPHE_MODEL", "mine:from-env")

    def input_fn(prompt: str) -> str:
        return "1" if "Engine" in prompt else ""

    choice = cli._run_engine_onboarding(
        input_fn=input_fn, config_path=tmp_path / "engine.json"
    )
    assert choice.model == "mine:from-env"


def test_ephe_start_without_an_engine_leaks_no_engine_env(capsys, monkeypatch):
    """H4: the placeholder used to be applied into the child env, so the spawned
    server saw a configured local_ollama plus a tag nobody picked, and the chat's
    fail-closed gate stayed disarmed. The hand-off belongs to run_server.py."""
    import ephe_cli
    from core.engine_config import EngineNotConfigured

    captured: dict = {}

    def _fake_run(cmd, env=None):
        captured["env"] = env
        return type("Proc", (), {"returncode": 0})()

    monkeypatch.setattr(ephe_cli, "ensure_pwa_built", lambda: None)
    monkeypatch.setattr(ephe_cli, "_run", _fake_run)
    monkeypatch.setattr(
        ephe_cli,
        "resolve_engine_choice",
        lambda **_kw: (_ for _ in ()).throw(EngineNotConfigured("No engine configured.")),
    )
    args = ephe_cli.build_parser().parse_args(["start", "--skip-model-check"])

    assert ephe_cli.cmd_start(args) == 0

    for var in ("EPHE_MODEL_PROVIDER", "EPHE_MODEL"):
        assert captured["env"].get(var) in (None, ""), var
    assert "No engine configured" in capsys.readouterr().out


def test_ephe_start_with_a_chosen_engine_still_applies_it(tmp_path, monkeypatch):
    import ephe_cli as cli
    from core.engine_config import EngineChoice, save_engine_config

    cfg = tmp_path / "engine.json"
    save_engine_config(EngineChoice(provider="local_ollama", model="mine:work"), cfg)
    captured: dict = {}

    monkeypatch.setattr(cli, "ensure_pwa_built", lambda: None)
    monkeypatch.setattr(
        cli,
        "_run",
        lambda cmd, env=None: captured.update(env=env) or type("P", (), {"returncode": 0})(),
    )
    monkeypatch.setattr("core.engine_config.stdin_is_interactive", lambda: False)
    args = cli.build_parser().parse_args(["start", "--skip-model-check"])

    assert cli.cmd_start(args, config_path=cfg) == 0
    assert captured["env"]["EPHE_MODEL"] == "mine:work"
    assert captured["env"]["EPHE_MODEL_PROVIDER"] == "local_ollama"


def test_ephe_start_lan_without_an_engine_reaches_the_server_as_a_refusal(monkeypatch):
    """The same leak closed a second hole: with the placeholder applied, the spawned
    server saw a configured engine and bound 0.0.0.0 without one. Now the child gets
    EPHE_HOST=0.0.0.0 and no provider, which is exactly the input
    `test_w19_setup_start.py::test_ephe_spawn_env_without_engine_fails_closed`
    proves the server refuses."""
    import ephe_cli
    from core.engine_config import EngineNotConfigured

    captured: dict = {}
    monkeypatch.setattr(ephe_cli, "ensure_pwa_built", lambda: None)
    monkeypatch.setattr(
        ephe_cli, "_run",
        lambda cmd, env=None: captured.update(env=env, cmd=cmd) or type("P", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(
        ephe_cli, "resolve_engine_choice",
        lambda **_kw: (_ for _ in ()).throw(EngineNotConfigured("No engine configured.")),
    )
    args = ephe_cli.build_parser().parse_args(["start", "--lan", "--skip-model-check"])

    ephe_cli.cmd_start(args)

    assert captured["env"]["EPHE_HOST"] == "0.0.0.0"
    assert captured["env"].get("EPHE_MODEL_PROVIDER") in (None, "")


def test_cli_model_flags_default_to_nothing(monkeypatch):
    """`doctor`/`update` inherited a tag from the parser while `code`/`goal` already
    read the env or nothing. One rule for all of them now."""
    import ephe_cli

    monkeypatch.delenv("EPHE_MODEL", raising=False)
    for argv in (["doctor"], ["update"]):
        assert ephe_cli.build_parser().parse_args(argv).model is None, argv

    monkeypatch.setenv("EPHE_MODEL", "mine:work")
    assert ephe_cli.build_parser().parse_args(["doctor"]).model == "mine:work"


def test_doctor_without_a_chosen_tag_reports_the_absence(capsys, tmp_path, monkeypatch):
    """Hermetic on purpose: `doctor` falls back to the persisted choice, and a
    developer's own ~/.ephe would decide the answer without the isolated config dir."""
    import core.engine_config as ec
    import ephe_cli

    monkeypatch.setattr(ec, "CONFIG_DIR", tmp_path / "config")
    args = ephe_cli.build_parser().parse_args(["doctor"])
    installed = MagicMock()
    with patch.object(ephe_cli, "_ollama_binary", lambda: "/usr/local/bin/ollama"), \
         patch.object(ephe_cli, "_json_get", lambda *_a, **_kw: None), \
         patch.object(ephe_cli, "_model_installed", installed):
        code = args.func(args)

    out = capsys.readouterr().out
    # No engine and no tag is a state the app resolves in its own setup
    # (owner order 2026-10-29), so the row informs and the run stays green.
    assert code == 0
    installed.assert_not_called()
    assert "none chosen yet" in out


def test_doctor_probes_the_persisted_local_tag_without_a_flag(tmp_path, monkeypatch, capsys):
    """The absence is only reported when there is really no choice: a user who
    configured local Ollama gets that tag probed, and the parser never hands one over."""
    import core.engine_config as ec
    import ephe_cli

    isolated = tmp_path / "config"
    monkeypatch.setattr(ec, "CONFIG_DIR", isolated)
    ec.save_engine_config(ec.EngineChoice(provider=ec.LOCAL_OLLAMA, model="mine:work"),
                          isolated / "engine.json")
    args = ephe_cli.build_parser().parse_args(["doctor"])
    probe = MagicMock(return_value=(True, "ok"))
    tags = {"models": [{"name": "mine:work"}]}
    with patch.object(ephe_cli, "_ollama_binary", lambda: "/usr/local/bin/ollama"), \
         patch.object(ephe_cli, "_json_get",
                      lambda url, *_a, **_kw: tags if url.endswith("/api/tags") else None), \
         patch.object(ephe_cli, "_model_installed", lambda _m: True), \
         patch.object(ephe_cli, "_model_loadable", probe):
        ephe_cli.cmd_doctor(args)

    out = capsys.readouterr().out
    assert "Model mine:work" in out
    probe.assert_called_once_with("mine:work")


def test_tui_entry_passes_no_tag_to_the_app(monkeypatch):
    """`ephe-app` (ephe.py) carried the tag in its own parser default."""
    import ephe

    seen: dict = {}

    class _FakeApp:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        def run(self):
            return None

    monkeypatch.setitem(sys.modules, "ui.app", MagicMock(EpheApp=_FakeApp))
    monkeypatch.setattr(sys, "argv", ["ephe-app"])

    ephe.main()

    assert seen["model"] is None


def test_ollama_variant_probe_generalises_over_the_users_tag():
    """The MLX/nvfp4 readiness probe was keyed to one shipped tag, so it stopped
    applying to any model the user actually runs."""
    from core._cli_ollama import _ollama_model_candidates

    if sys.platform != "darwin":
        pytest.skip("the MLX variant probe is macOS-only")
    assert _ollama_model_candidates("mine:work") == [
        "mine:work",
        "mine:work-mlx",
        "mine:work-nvfp4",
    ]


@pytest.mark.asyncio
async def test_chat_loop_does_not_swap_the_model_under_memory_pressure(monkeypatch):
    """`core/chat.py` used to rerun the user's turn on `qwen3:4b` when the primary model
    reported it needed more RAM — a second model, chosen by the product, mid-conversation.
    Without `EPHE_FALLBACK_MODEL` the error reaches the caller and one request goes out."""
    from unittest.mock import AsyncMock

    from core.chat import chat_with_tools

    monkeypatch.delenv("EPHE_FALLBACK_MODEL", raising=False)
    with patch("core.chat.ollama.AsyncClient") as MockClient:
        client = AsyncMock()
        client.chat = AsyncMock(side_effect=Exception(
            "model requires more system memory (9.8 GiB) than is available (8.6 GiB)"
        ))
        MockClient.return_value = client

        with pytest.raises(Exception, match="requires more system memory"):
            await chat_with_tools(
                model="mine:work",
                history=[{"role": "user", "content": "Hallo"}],
                on_chunk=lambda c: None,
            )
        assert client.chat.await_count == 1
