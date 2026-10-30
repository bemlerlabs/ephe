from __future__ import annotations

import argparse
import os
import builtins
import sys
from typing import Any
from core._cli_common import EngineChoice, LOCAL_OLLAMA, OPENAI_COMPAT, _ask_url, _emit_error, _fetch_served_models, save_engine_config
from core._cli_ollama import _local_ollama_detected

def _run_engine_onboarding(
    input_fn=builtins.input, config_path=None
) -> Any:
    """Interactive engine choice (onboarding) for `ephe configure`/`tui`.

    The user picks their engine once (local Ollama / their own Ollama or vLLM
    engine / their own OpenAI-compatible endpoint such as DGX Spark /
    OpenAI-compatible API). The choice is stored in ~/.ephe/engine.json and
    reused on every start. The API key is kept in the OS keychain (0600 key file
    when no backend is available), never in engine.json.

    W18: no silent default any more — an abort (Ctrl+C/EOF) does NOT secretly
    pick local Ollama, it aborts fail-closed.
    """
    from core.engine_config import ENGINE_PRESETS, EngineNotConfigured, store_engine_api_key

    local_preset, remote_preset, compat_preset = ENGINE_PRESETS[0], ENGINE_PRESETS[1], ENGINE_PRESETS[2]

    print("◑ Ephe – engine setup (asked once, then stored)")
    print("  Every user picks their own engine — there is no silent default:")
    print(f"  [1] Local Ollama on this machine ({local_preset.example_url})")
    print("  [2] Your own Ollama / vLLM (remote URL)")
    print("  [3] Your own OpenAI-compatible endpoint (DGX Spark / vLLM)")
    print("  [4] OpenAI-compatible cloud API (e.g. Mistral / OpenAI, with a key)")

    if _local_ollama_detected():
        print(f"  ✓ Local Ollama engine detected ({local_preset.example_url})")
    else:
        print("  ⚠ No local engine detected – please choose the engine and, if needed, the URL")

    pending_key = ""
    while True:
        try:
            raw = (input_fn("Engine [1/2/3/4, no default]: ") or "").strip()
            if raw in ("1", "local", "local_ollama"):
                provider = "local_ollama"
                default_model = local_preset.seed_model()
                api_url = None
            elif raw in ("2", "custom", "custom_ollama"):
                provider = "custom_ollama"
                default_model = remote_preset.seed_model()
                api_url = _ask_url(
                    input_fn,
                    f"Engine base URL (e.g. {remote_preset.example_url}): ",
                    required=True,
                    prefill=remote_preset.seed_url(),
                )
                if api_url:
                    served = _fetch_served_models(api_url)
                    if served:
                        default_model = served[0]
                        print(f"  ✓ Served models: {', '.join(served[:8])}")
                    else:
                        print(f"  ⚠ Engine {api_url} does not answer – please check the model name.")
            elif raw in ("3", "dgx", "spark", "vllm", "openai_compatible"):
                # Preset: an own OpenAI-compatible endpoint (DGX Spark / vLLM).
                # The URL comes from the user or from the env — never from the code.
                provider = OPENAI_COMPAT
                default_model = compat_preset.seed_model() or "custom-model"
                api_url = _ask_url(
                    input_fn,
                    f"OpenAI-compatible base URL (e.g. {compat_preset.example_url}): ",
                    required=True,
                    prefill=compat_preset.seed_url(),
                )
                if api_url:
                    served = _fetch_served_models(api_url)
                    if served:
                        default_model = served[0]
                        print(f"  ✓ Served models: {', '.join(served[:8])}")
                    else:
                        print(f"  ⚠ Engine {api_url} does not answer – please check the model name.")
                key = (input_fn("API key (optional, kept in the OS keychain): ") or "").strip()
                if key:
                    os.environ["EPHE_OPENAI_COMPAT_API_KEY"] = key
                    pending_key = key
            elif raw in ("4", "api", "cloud"):
                provider = OPENAI_COMPAT
                default_model = "custom-model"
                api_url = _ask_url(
                    input_fn,
                    "OpenAI-compatible base URL (e.g. https://api.mistral.ai/v1): ",
                    required=True,
                )
                key = (input_fn("API key (optional, kept in the OS keychain): ") or "").strip()
                if key:
                    os.environ["EPHE_OPENAI_COMPAT_API_KEY"] = key
                    pending_key = key
            else:
                print(f"  Unknown choice: {raw!r} — enter 1/2/3/4.")
                continue
            break
        except (EOFError, KeyboardInterrupt):
            # W18 fail-closed: no silent Ollama fallback when the user aborts.
            print("\n  Aborted – no engine selected.")
            raise EngineNotConfigured("Engine selection aborted.")


    # A tag is shown as the default only when the user seeded one (EPHE_MODEL).
    # Nothing here supplies it: an empty answer asks again, an abort names no model.
    while True:
        label = f"Model [default {default_model}]: " if default_model else "Model: "
        try:
            answer = (input_fn(label) or "").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Aborted – no engine selected.")
            raise EngineNotConfigured("Engine selection aborted.")
        model = answer or default_model
        if model:
            break
        print("  No tag, no engine — enter a model your engine actually serves.")

    choice = EngineChoice(provider=provider, model=model, api_url=api_url)
    saved = save_engine_config(choice, config_path)
    if pending_key and provider == OPENAI_COMPAT:
        store_engine_api_key(pending_key, engine=choice)
    print(f"  → Engine stored: {provider} / {model}"
          + (f" @ {api_url}" if api_url else ""))
    if not saved:
        print("  ⚠  The config could not be written – the selection only applies to this start.")
    return choice


def resolve_engine_choice(config_path=None, configure: bool = False, args=None) -> Any:
    """Resolve the engine choice for ``tui``/``start`` (W18, fail-closed).

    Delegates to the shared resolver ``core.engine_config
    .resolve_engine_choice`` — the same source that ``run_server.py`` uses.
    Priority: persisted ``engine.json`` → explicit engine env → interactive
    onboarding → ``EngineNotConfigured``.

    There is NO silent default any more: without a config and without env it
    aborts (with instructions) instead of falling back to local Ollama or a
    remote host. ``configure`` forces the onboarding, and a TTY on stdin triggers
    it too (a human is sitting in front of it).
    """
    from core.engine_config import (
        EngineNotConfigured,
        resolve_engine_choice as _resolve_engine_choice,
        stdin_is_interactive,
    )

    interactive = bool(configure) or stdin_is_interactive()
    try:
        return _resolve_engine_choice(
            config_path,
            allow_prompt=interactive,
            prompt_fn=_run_engine_onboarding,
        )
    except EngineNotConfigured as exc:
        if args is not None:
            _emit_error(args, 1, str(exc), getattr(exc, "hint", ""))
            raise SystemExit(1) from exc
        raise


def engine_for_headless_run(args=None, model_override: str | None = None) -> Any:
    """The engine for a headless run (`ephe code`/`ephe goal`/`ephe serve`).

    The same source as the TUI and the server: ``engine.json`` → engine env →
    onboarding → abort with instructions. The rest is the absence of exceptions:
    up to I2-2 an agent run that had not chosen an engine ran against
    ``http://localhost:11434`` with a guessed model — the rule that holds for
    `tui` applied to it only on paper.

    ``model_override`` (the `--model` flag) picks the model *inside* the chosen
    engine. A model name names no endpoint, which is exactly why it is no engine
    choice: without a chosen engine the abort stays, override or not.
    """
    choice = resolve_engine_choice(args=args)
    override = (model_override or "").strip()
    if override and override != choice.model:
        from dataclasses import replace

        choice = replace(choice, model=override)
    choice.apply_env()
    return choice


def cmd_configure(args: argparse.Namespace, config_path=None) -> int:
    """`ephe configure` — store the engine choice interactively (W18).

    This is the way out of the fail-closed abort: WITHOUT a persisted
    engine.json (and without engine env) neither `ephe start` nor the server
    starts — the error message points exactly at this command. The choice lands
    in ~/.ephe/engine.json; keys are never persisted.
    """
    from core.engine_config import EngineNotConfigured, load_engine_config

    existing = load_engine_config(config_path)
    if existing is not None and not existing.is_complete():
        # A half-written config is not a decision, and the command whose whole job
        # is to write one must not answer "already configured" over it.
        existing = None
    if existing is not None and not args.force:
        where = f" @ {existing.api_url}" if existing.api_url else ""
        print(f"  → Engine already configured: {existing.provider} / {existing.model}{where}")
        print("  → Change it with: ephe configure --force")
        return 0

    try:
        choice = _run_engine_onboarding(config_path=config_path)
    except EngineNotConfigured as exc:
        _emit_error(args, 1, str(exc), getattr(exc, "hint", ""))
        return 1
    choice.apply_env()
    print("  → Start the app with: ephe start")
    _print_code_exec_runtime()
    return 0


def _print_code_exec_runtime() -> None:
    """Wave E1: the second runtime decision does not stay in the server log.

    After the engine choice, `ephe configure` says what carries model Python —
    the verified CPython cell or the kernel with full host access. Pure
    information: an error here must not abort the configuration.
    """
    try:
        from core import cpython_cell

        refused = cpython_cell.exec_choice_error()
        if refused:
            print(f"  → Code execution: {refused}")
        elif cpython_cell.exec_runtime() == cpython_cell.RUNTIME_CELL:
            version = cpython_cell.guest_state()["version"]
            print(f"  → Code execution: CPython cell (Python {version}), sandboxed "
                  "— fuel/memory/disk ceilings apply, no network")
        else:
            print("  → Code execution: kernel — UNSANDBOXED, full host access")
            print("     opt in to the cell with: pip install 'ephe[sandbox]' "
                  "&& python3 build_cpython_guest.py")
    except Exception:  # noqa: BLE001 — an info line is no reason to abort
        pass


def cmd_tui(args: argparse.Namespace, config_path=None) -> int:
    import ephe

    # W4-10 (R15 hole H2): a bare --model names no endpoint — it picks the model
    # *inside* the chosen engine and may not swap it. Route it through the same
    # resolver the headless runs use (engine.json → env → onboarding → abort), so
    # a persisted remote engine survives `ephe tui --model <tag>` and a missing
    # engine fails closed instead of falling back to local Ollama.
    if args.model and not args.api_url:
        choice = engine_for_headless_run(args, args.model)
    # Explicit engine flag (--api-url) → no onboarding needed. W4-11 owns this
    # branch (R15 hole H3).
    elif args.model or args.api_url:
        # H3 (fail-closed): `--api-url` names an engine ENDPOINT but not a model.
        # A model name is not an engine choice, and an endpoint is not a model:
        # the provider resolver reads the tag from EPHE_OPENAI_COMPAT_MODEL, so an
        # explicit endpoint without a tag aborts NAMING that variable — instead of
        # letting `EngineChoice(model=None)` crash with a bare AttributeError
        # (`None.strip()` in __post_init__) that named nothing and helped nobody.
        if args.api_url and not (args.model or "").strip():
            from core.engine_config import (
                ENGINE_SETUP_HINT,
                ENV_MODEL,
                EngineNotConfigured,
            )

            raise EngineNotConfigured(
                "--api-url names an engine endpoint, but the model tag is "
                "missing (pass --model <tag>, or set "
                f"{ENV_MODEL[OPENAI_COMPAT]}).",
                hint=ENGINE_SETUP_HINT,
            )
        choice = EngineChoice(
            provider=OPENAI_COMPAT if args.api_url else LOCAL_OLLAMA,
            model=args.model,
            api_url=args.api_url,
        )
    else:
        # Without the model flag: engine.json → env. No engine is not an abort any
        # more (owner order 2026-10-29): the terminal app opens and offers the
        # engine setup in its own surface. The rule that survives is the stricter
        # half — nothing leaves until a choice exists, so no request runs against
        # an engine the user never named.
        try:
            if args.configure:
                choice = resolve_engine_choice(
                    config_path=config_path, configure=True, args=None
                )
            else:
                from core.engine_config import resolve_engine_choice as _persisted_choice

                choice = _persisted_choice(config_path, allow_prompt=False)
        except Exception:  # EngineNotConfigured and a damaged config alike
            choice = None

    if choice is not None and not choice.is_complete():
        choice = None
    if choice is not None:
        choice.apply_env()
        forwarded = ["ephe"] + choice.to_flags()
    else:
        forwarded = ["ephe"]
    if args.reset:
        forwarded.append("--reset")

    # P0-1 E1: hand the approval flags through to the TUI
    if args.dry_run:
        forwarded.append("--dry-run")
    if args.yes:
        forwarded.append("--yes")
    if args.no:
        forwarded.append("--no")

    old_argv = sys.argv
    try:
        sys.argv = forwarded
        ephe.main()
    finally:
        sys.argv = old_argv
    return 0
