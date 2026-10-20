"""
◑ Ephe – Engine Configuration Persistence
core/engine_config.py

Persists the engine choice of the CLI/TUI (`ephe tui`) so a user selects an
engine (local Ollama / own Ollama or vLLM engine / own OpenAI-compatible
endpoint such as DGX Spark) once and every later start reuses it without a
model flag ("stored").

Convention:
- Provider enum: local_ollama | custom_ollama | openai_compatible
  (matching core/model_provider.py exactly).
- API keys are NEVER written to ~/.ephe/engine.json. The provider system reads one
  variable, ``EPHE_OPENAI_COMPAT_API_KEY``, which gets its value from two places and no
  more: the user's shell export or the key field of onboarding/settings (the latter lives
  only in the running server process), and ``~/.ephe/engine.key`` — one owner-only line the
  user writes, read by the desktop spawn (``app/src-tauri/src/backend.rs``) and by this
  module for every other start, because an app opened from the Dock inherits no shell
  environment. A group- or world-readable, symlinked, empty or multi-line key file is
  refused, never used. A key the user stores through this module prefers the OS keychain
  (entry ``ephe/engine_api_key``) and writes ``~/.ephe/engine.key`` only when no keyring
  backend is importable; the channel bot token uses the same vault under its own entry
  (``core/channels/pairing.py``). No other program's credential store is read: that fallback
  existed until 2026-10-10 and is measured away in tests/test_desktop_engine_key.py.
- api_url is the full OpenAI-compatible base URL (e.g. http://10.0.0.5:8000/v1).

W18 (audit, fail-closed): there is NO silent engine default any more. The code
holds neither a private hostname nor a key literal. The engine choice belongs to
the user and comes from exactly two sources:

1. the persisted ``~/.ephe/engine.json`` (onboarding: `ephe configure`),
2. an explicit engine env (``EPHE_MODEL_PROVIDER`` + endpoint variable).

If neither is set, startup aborts with an actionable instruction
(``EngineNotConfigured``) instead of falling back to an engine silently —
``resolve_engine_choice()`` is the shared resolver of CLI and server (one source
of truth). DGX Spark / vLLM stay first-class: as a chosen preset
(``ENGINE_PRESETS``) and as a template (``engine.example.json``,
``.env.example``), not as a hardcoded default.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import json
import os
import stat
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

# Provider constants (matching core/model_provider.py exactly)
LOCAL_OLLAMA = "local_ollama"
CUSTOM_OLLAMA = "custom_ollama"
OPENAI_COMPAT = "openai_compatible"

VALID_PROVIDERS = (LOCAL_OLLAMA, CUSTOM_OLLAMA, OPENAI_COMPAT)

# Engine env (explicit configuration without engine.json)
ENV_PROVIDER = "EPHE_MODEL_PROVIDER"
ENV_BASE_URL = {
    LOCAL_OLLAMA: "EPHE_LOCAL_OLLAMA_BASE_URL",
    CUSTOM_OLLAMA: "EPHE_CUSTOM_OLLAMA_BASE_URL",
    OPENAI_COMPAT: "EPHE_OPENAI_COMPAT_BASE_URL",
}
ENV_MODEL = {
    LOCAL_OLLAMA: "EPHE_MODEL",
    CUSTOM_OLLAMA: "EPHE_MODEL",
    OPENAI_COMPAT: "EPHE_OPENAI_COMPAT_MODEL",
}

# Fixed line for every fail-closed path (identical in CLI and server).
ENGINE_SETUP_HINT = (
    "Run `ephe configure` and pick your engine (saved to ~/.ephe/engine.json), "
    f"or set it explicitly via env: {ENV_PROVIDER}=local_ollama|custom_ollama|openai_compatible "
    "plus EPHE_LOCAL_OLLAMA_BASE_URL / EPHE_CUSTOM_OLLAMA_BASE_URL / EPHE_OPENAI_COMPAT_BASE_URL "
    "(and EPHE_MODEL)."
)


class EngineNotConfigured(RuntimeError):
    """Fail-closed: no engine chosen (neither engine.json nor engine env).

    ``hint`` is the actionable instruction (the fixed line) for the surface.
    """

    def __init__(self, message: str | None = None, hint: str | None = None) -> None:
        super().__init__(message or "No engine configured.")
        self.hint = ENGINE_SETUP_HINT if hint is None else hint


# Presets (onboarding templates)
# A preset describes an engine CLASS (local Ollama, remote Ollama, own
# OpenAI-compatible endpoint) — never a private host. The example value is a
# neutral placeholder; the seed comes from the env.
# No preset names a model either (2026-10-09): a template cannot size this machine,
# and onboarding shows `Modell [Default x]` and stores x.  # language-gate: ignore (quoted German surface label of the model field, app/src/locales/de.json:312)
# Since 2026-10-11 x only exists when the user named it (EPHE_MODEL): the product
# stopped sizing a tag from this machine's RAM, so an unset model asks instead of
# storing one. Before, an 8 GB machine was offered a 12B model it cannot load.

@dataclass(frozen=True)
class EnginePreset:
    """Selectable engine template for onboarding (no default, no secret)."""

    id: str
    label: str
    provider: str
    needs_url: bool
    example_url: str
    default_model: str = ""
    env_url: str = ""
    env_model: str = ""

    def seed_url(self) -> str:
        """Pre-fill from the env (empty = the user types it themselves)."""
        return (os.environ.get(self.env_url) or "").strip() if self.env_url else ""

    def seed_model(self) -> str:
        if self.env_model and os.environ.get(self.env_model, "").strip():
            return os.environ[self.env_model].strip()
        return self.default_model


ENGINE_PRESETS: tuple[EnginePreset, ...] = (
    EnginePreset(
        id=LOCAL_OLLAMA,
        label="Local Ollama (this machine)",
        provider=LOCAL_OLLAMA,
        needs_url=False,
        example_url="http://127.0.0.1:11434",
        default_model="",
        env_model="EPHE_MODEL",
    ),
    EnginePreset(
        id=CUSTOM_OLLAMA,
        label="Your own Ollama / vLLM (remote URL)",
        provider=CUSTOM_OLLAMA,
        needs_url=True,
        example_url="http://192.168.1.50:11434",
        default_model="",
        env_url=ENV_BASE_URL[CUSTOM_OLLAMA],
        env_model="EPHE_MODEL",
    ),
    EnginePreset(
        id="dgx_spark_vllm",
        label="Your own OpenAI-compatible endpoint (DGX Spark / vLLM)",
        provider=OPENAI_COMPAT,
        needs_url=True,
        example_url="http://gpu-host.example:8000/v1",
        default_model="",
        env_url=ENV_BASE_URL[OPENAI_COMPAT],
        env_model=ENV_MODEL[OPENAI_COMPAT],
    ),
)


def engine_preset(preset_id: str) -> EnginePreset | None:
    """Preset by ID (None when unknown)."""
    key = (preset_id or "").strip().lower()
    for preset in ENGINE_PRESETS:
        if preset.id == key:
            return preset
    return None


def ensure_default_engine_api_key(base_url: str | None) -> None:
    """DEPRECATED (W18): there is no hardcoded access token any more.

    Previously this function put a key stored in the code into the env as soon
    as the URL matched the standard engine. The access token now comes
    exclusively from ``EPHE_OPENAI_COMPAT_API_KEY`` (or from the user input in
    onboarding/settings, which writes into that same env variable).

    The function stays as a no-op for legacy callers and deliberately writes
    nothing: a guessed key was exactly the silent default that was removed here.
    """
    return None


# Engine key vault (P0-1): the OS keychain first, the 0600 file as fallback.
# Same keyring service as the channel bot token, one entry per secret
# (`core/channels/pairing.py`).

ENGINE_KEYRING_SERVICE = "ephe"
ENGINE_KEYRING_USERNAME = "engine_api_key"


def _store_engine_keyring(token: str) -> bool:
    """Writes the token into the OS keychain (macOS Keychain / Linux SecretService).

    False when no keyring backend is importable or it refuses the write, so the
    caller knows to fall back to the 0600 key file.
    """
    try:
        import keyring
    except ImportError:
        return False
    try:
        keyring.set_password(ENGINE_KEYRING_SERVICE, ENGINE_KEYRING_USERNAME, token)
        return True
    except Exception:
        return False


def _load_engine_keyring() -> str:
    """The stored token, or "" when no backend answers, no entry is held, or the read fails."""
    try:
        import keyring
    except ImportError:
        return ""
    try:
        return keyring.get_password(ENGINE_KEYRING_SERVICE, ENGINE_KEYRING_USERNAME) or ""
    except Exception:
        return ""


def _delete_engine_keyring() -> None:
    """Best effort: a missing backend or a missing entry is not an error here."""
    try:
        import keyring
    except ImportError:
        return
    try:
        keyring.delete_password(ENGINE_KEYRING_SERVICE, ENGINE_KEYRING_USERNAME)
    except Exception:
        pass


def key_file_path(home: "Path | None" = None) -> Path:
    return (Path(home) if home is not None else Path.home()) / ".ephe" / "engine.key"


def _key_file(home: "Path | None" = None) -> str:
    """The stored token: one owner-only line in ``~/.ephe/engine.key``, or nothing.

    The rules are the desktop spawn's rules (`app/src-tauri/src/backend.rs::key_from_file`)
    because the file is one promise and every surface has to keep it: a mode that lets group or
    other read it, a symlink, an empty file or more than one line is a file the machine leaks,
    not a secret the user stored, so it is refused rather than used.
    """
    path = key_file_path(home)
    try:
        meta = os.lstat(path)
    except OSError:
        return ""
    if not stat.S_ISREG(meta.st_mode) or stat.S_IMODE(meta.st_mode) & 0o077:
        return ""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""
    return "" if not text or "\n" in text else text


def engine_api_key_for(url: str | None, home: "Path | None" = None) -> str:
    """Effective access token of an engine: the env variable, else the keychain, else the key file.

    No literal default, and no third source. ``EPHE_OPENAI_COMPAT_API_KEY`` wins wherever it is
    set — an inherited value names what whoever started this process chose, and a stored secret
    never replaces it quietly. The keychain entry (``ephe/engine_api_key``, written by
    ``store_engine_api_key``) comes next, then ``~/.ephe/engine.key``. The file exists because the
    env cannot reach an icon-launched app (measured: that backend carried no ``EPHE_`` variable at
    all), and it now covers every start, the desktop one included: `core/model_provider.py` has
    been sending users to that path on surfaces that never read it.

    Until 2026-10-10 an empty env fell back to another tool's credential store
    (``~/.local/share/opencode/auth.json``), which AGENTS.md did not name as a key source. It is
    gone because the reason it was kept measured false: the token it resolved answered
    ``401`` at the issuer, and the same function returned nothing for the ``http://`` spelling of
    the same host. Both halves are pinned in tests/test_desktop_engine_key.py.

    ``url`` stays in the signature because twelve call sites pass an endpoint with it, and a
    per-endpoint token store would start here. The token is not selected by host today: one
    variable, one file, and the endpoint decides only whether a token is needed at all
    (`core/model_provider.py::endpoint_requires_api_key`).
    """
    key = (os.environ.get("EPHE_OPENAI_COMPAT_API_KEY") or "").strip()
    return key or _load_engine_keyring() or _key_file(home=home)


def store_engine_api_key(token: str, home: "Path | None" = None) -> str:
    """Stores the engine token: OS keychain preferred, else the 0600 key file.

    The return value is the storage mode used (``"keyring"`` / ``"file_0600"``).
    An empty token is refused, so no call clears a stored key by accident, and the
    file path written is the one ``_key_file`` reads back.

    A multi-line token is refused for the same reason: the reader refuses a
    two-line file (``_key_file``, matching the desktop spawn), so persisting one
    would report success on a key the resolver never finds.
    """
    if not token or not token.strip():
        raise ValueError("engine API key is empty — store refused (fail-closed).")
    value = token.strip()
    if "\n" in value or "\r" in value:
        raise ValueError(
            "engine API key must be one line — store refused (fail-closed)."
        )
    if _store_engine_keyring(value):
        return "keyring"
    path = key_file_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    # The engine key is the stored secret: one owner-only 0600 line in the user's
    # ~/.ephe/engine.key, written only where no keyring holds it. The mode is set on
    # the open, so the file is owner-only from its first byte and a crash leaves no
    # readable half-written one behind.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (value + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    # The call is `os.replace` so that a caller watching the rename sees it on every
    # interpreter: pathlib's `Path.replace` goes through an accessor bound at import, and
    # the py3.10 leg reads this temporary file's mode through that watch.
    os.replace(tmp, path)
    return "file_0600"


def delete_engine_api_key(home: "Path | None" = None) -> None:
    """Revokes the stored token: the keychain entry and the key file, both best effort."""
    _delete_engine_keyring()
    try:
        key_file_path(home).unlink(missing_ok=True)
    except OSError:
        pass


CONFIG_DIR = Path(os.environ.get("EPHE_CONFIG_DIR") or str(Path.home() / ".ephe"))
CONFIG_FILE = "engine.json"


def config_root() -> Path:
    """The per-device folder as the single root (W6): env override or ~/.ephe.

    Resolved at call time so test harnesses can set the root through the env
    before the module is reloaded.
    """
    return Path(os.environ.get("EPHE_CONFIG_DIR") or str(Path.home() / ".ephe"))


def config_subdir(name: str) -> Path:
    """Subfolder of the device folder, e.g. config_subdir("sessions")."""
    return config_root() / name


@dataclass
class EngineChoice:
    """Immutable, persistable engine choice."""

    provider: str  # local_ollama | custom_ollama | openai_compatible
    model: str
    api_url: str | None = None
    # R44 (P4) / R4-A1: output path — since the workbench this is NO LONGER the
    # birth place (that is ~/.ephe/artifacts/<session>), but the remembered
    # target of an adoption.
    output_dir: str | None = None
    # Workspace (F: project folder as in leading AI clients) — the Shell/File
    # tools resolve relative paths against it and start inside it. None = server cwd.
    workspace_dir: str | None = None
    # Wave 11 (P1-4): optional brand kit (name/primary/secondary) for decks.
    # Empty value = no override; the deck tools fall back to the generic theme.
    brand: dict | None = None
    # N8b: price table per model (USD per 1M tokens) — persisted so that the
    # USD accounting of the bench follows a model change instead of hanging on an
    # env default. Form: {"in_per_m": 0.05, "out_per_m": 0.40}.
    pricing: dict | None = None
    # Wave 5 (settings depth): generation parameters as the persisted
    # source-of-truth (temperature, top_p, max_tokens, tool_budget,
    # context_window, memory_max_entries). None = nothing set (env/default
    # applies). The read path applies env precedence (read_generation_values).
    generation: dict | None = None

    def __post_init__(self) -> None:
        if self.provider not in VALID_PROVIDERS:
            raise ValueError(f"Unknown provider: {self.provider!r}")
        if not self.model.strip():
            raise ValueError("Model name must not be empty.")

    def to_flags(self) -> list[str]:
        """CLI flags for `ephe main()` — model and engine URL."""
        flags = ["--model", self.model]
        if self.api_url:
            flags += ["--api-url", self.api_url]
        return flags

    def apply_env(self) -> None:
        """Sets the session env variables that the provider system reads.

                ``EPHE_MODEL_PROVIDER`` is set according to ``self.provider``
        so the server resolver (core.model_provider._provider_from_env) looks up
        the configured engine — instead of silently falling back to
        ``local_ollama``. Without this key the PWA never used the configured
        engine (e.g. Qwen-DGX), always the local Ollama.
        """
        os.environ["EPHE_MODEL_PROVIDER"] = self.provider
        os.environ["EPHE_MODEL"] = self.model
        # The provider-specific model key is not conditional on the endpoint: the
        # resolver reads it for every openai_compatible call, and a missing URL is a
        # separate field that is refused below with its own name.
        os.environ[ENV_MODEL[self.provider]] = self.model
        if self.provider == OPENAI_COMPAT:
            if not self.api_url:
                raise EngineNotConfigured(
                    f"Engine config for {OPENAI_COMPAT} is missing field: api_url. "
                    "The endpoint is part of the choice; no default is assumed."
                )
            os.environ["EPHE_OPENAI_COMPAT_BASE_URL"] = self.api_url
            # W18: NO implicit access token any more. The key comes from
            # EPHE_OPENAI_COMPAT_API_KEY (shell export, the settings key field, or the
            # desktop key file) — when a public endpoint needs one and none is there,
            # ensure_provider_ready refuses before any request leaves and the chat
            # route answers 503 with that instruction (measured 2026-10-10).
        elif self.provider == CUSTOM_OLLAMA and self.api_url:
            os.environ["EPHE_CUSTOM_OLLAMA_BASE_URL"] = self.api_url


def default_config_path() -> Path:
    """Canonical storage location of the engine choice."""
    return CONFIG_DIR / CONFIG_FILE


def load_engine_config(path: Path | None = None) -> EngineChoice | None:
    """Loads the persisted engine choice. None when no config exists."""
    cfg_path = path or default_config_path()
    try:
        if not cfg_path.exists():
            return None
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        return EngineChoice(
            provider=raw["provider"],
            model=raw["model"],
            api_url=raw.get("api_url"),
            output_dir=(str(raw.get("output_dir") or "").strip() or None),
            workspace_dir=raw.get("workspace_dir"),
            brand=(raw.get("brand") or None),
            pricing=(raw.get("pricing") or None),
            generation=(raw.get("generation") or None),
        )
    except Exception:
        # Damaged or unreadable config → treat as none, never crash.
        return None


# Wave 5: generation parameters (settings depth, one source)
#
# Order in the read path (read_generation_values):
#   1. env override (EPHE_TEMPERATURE, EPHE_TOP_P, EPHE_MAX_TOKENS,
#      EPHE_TOOL_BUDGET, EPHE_CONTEXT_WINDOW, EPHE_MEMORY_MAX_ENTRIES,
#      EPHE_SWARM_MAX_PARALLEL),
#   2. the persisted generation block from engine.json,
#   3. the hard default within the bounds below (clamp).
# The env is read-only precedence — it never changes the file.

#: (default, min, max) per key; max=None => no upper bound.
#: A default of None = "cannot be set" — the key stays None when no value is
#: configured (top_p/max_tokens/context_window are optional per model).
GENERATION_BOUNDS: dict[str, tuple[float | int | None, float | int, float | int | None]] = {
    "temperature": (0.0, 0.0, 2.0),
    "top_p": (None, 0.0, 1.0),
    "max_tokens": (None, 1, None),
    "tool_budget": (10, 1, 40),
    "context_window": (None, 1, None),
    "memory_max_entries": (1000, 1, None),
    # How many swarm agents of one wave may run at the same time.
    "swarm_max_parallel": (8, 1, None),
}

#: Env names per key (precedence level 1).
GENERATION_ENV_KEYS: dict[str, str] = {
    "temperature": "EPHE_TEMPERATURE",
    "top_p": "EPHE_TOP_P",
    "max_tokens": "EPHE_MAX_TOKENS",
    "tool_budget": "EPHE_TOOL_BUDGET",
    "context_window": "EPHE_CONTEXT_WINDOW",
    "memory_max_entries": "EPHE_MEMORY_MAX_ENTRIES",
    "swarm_max_parallel": "EPHE_SWARM_MAX_PARALLEL",
}

# Non-thinking passthrough (2026-10-11): two NON-numeric generation options on
# the same ladder (env → engine.json generation block → unset). They exist
# because DeepSeek's OpenAI-compatible API defaults thinking ON — the reasoning
# text is billed against max_tokens and can consume the whole budget unless the
# request carries {"type": "disabled"}. The default for both is None ("not
# configured"): the request path sends the field only when it is set, so an
# installation that configures nothing keeps the body it always sent.

#: Env names per option key (precedence level 1).
GENERATION_OPTION_ENV_KEYS: dict[str, str] = {
    "thinking": "EPHE_THINKING",
    "reasoning_effort": "EPHE_REASONING_EFFORT",
}


def normalize_thinking(value: object) -> dict | None:
    """thinking option → the object the API expects, or None (= unset).

    An object travels as written ({"type": "disabled"}); a bare mode string —
    the shape the env gives, EPHE_THINKING=disabled — is wrapped into
    {"type": <mode>}. Malformed input (numbers, lists, broken JSON leftovers)
    is unset, never a nonsense type token: a bad value must not become a 400.
    """
    if isinstance(value, dict):
        return dict(value) or None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            if raw[:1] in ("{", "["):
                return None  # broken JSON — do not wrap it into a type token
            return {"type": raw}
        if isinstance(parsed, dict):
            return parsed or None
        if isinstance(parsed, str) and parsed.strip():
            return {"type": parsed.strip()}
    return None


def normalize_reasoning_effort(value: object) -> str | None:
    """reasoning_effort option → the string as the engine spells it, or None.

    Pass-through on purpose: the vocabulary (none/low/medium/high, plus
    engine-specific extras) is the engine's own set.
    """
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


#: Validators per option key — the non-numeric counterpart of GENERATION_BOUNDS,
#: same presence semantics (None = not configured).
GENERATION_OPTION_NORMALIZERS: dict[str, Callable[[object], dict | str | None]] = {
    "thinking": normalize_thinking,
    "reasoning_effort": normalize_reasoning_effort,
}


# Registry coherence: the readers index GENERATION_ENV_KEYS by a key of
# GENERATION_BOUNDS (read_generation_explicit, read_generation_values) and
# GENERATION_OPTION_ENV_KEYS by a key of GENERATION_OPTION_NORMALIZERS
# (read_generation_options); validate_generation writes both registers into one
# generation block. A key without its env entry is a KeyError at read time, a key in
# both registers is written twice, a repeated env name makes two keys read one
# variable — all three drift without a symptom here, so the contract is checked at
# import and pinned in tests/test_generation_registry_coherence.py.


def generation_registry_inconsistencies() -> list[str]:
    """Every way the four generation registers disagree; empty means coherent."""
    problems: list[str] = []
    pairs = list(GENERATION_ENV_KEYS.items()) + list(GENERATION_OPTION_ENV_KEYS.items())
    for label, keys, env_names in (
        ("bounds", GENERATION_BOUNDS, GENERATION_ENV_KEYS),
        ("options", GENERATION_OPTION_NORMALIZERS, GENERATION_OPTION_ENV_KEYS),
    ):
        for key in sorted(set(keys) - set(env_names)):
            problems.append(f"{label} key {key!r} has no env name")
        for key in sorted(set(env_names) - set(keys)):
            problems.append(f"{label} env name for {key!r} has no key")
    for key in sorted(set(GENERATION_BOUNDS) & set(GENERATION_OPTION_NORMALIZERS)):
        problems.append(f"{key!r} sits in both registers")
    owner: dict[str, str] = {}
    for key, env_name in pairs:
        previous = owner.setdefault(env_name, key)
        if previous != key:
            problems.append(f"env name {env_name} is read by {previous!r} and {key!r}")
        if env_name != f"EPHE_{key.upper()}":
            problems.append(f"env name {env_name} for {key!r} is not EPHE_{key.upper()}")
    return problems


_coherence_problems = generation_registry_inconsistencies()
if _coherence_problems:  # pragma: no cover — a drifted register is a code defect, never a runtime state
    raise RuntimeError("generation registry incoherent: " + "; ".join(_coherence_problems))


def clamp_generation_value(key: str, value: object) -> float | int:
    """Clamps a value to the bounds; invalid/None → default.

    Integer keys (max_tokens, tool_budget, context_window,
    memory_max_entries, swarm_max_parallel) return int, float keys
    (temperature, top_p) return float. 0 is lifted to the lower bound
    (0 tokens / 0 parallel slots make no sense).
    """
    default, low, high = GENERATION_BOUNDS.get(key, (0, 0, None))
    if value is None:
        return default
    try:
        num = float(value) if isinstance(value, str) else value
        num = float(num)
    except (TypeError, ValueError):
        return default
    if num != num:  # NaN
        return default
    if num < low:
        num = float(low)
    if high is not None and num > high:
        num = float(high)
    if key in ("temperature", "top_p"):
        return round(num, 4)
    return int(num)


def normalize_generation(raw: dict | None) -> dict[str, float | int]:
    """Raw (not nulled) generation block → complete, clamped block."""
    src = raw if isinstance(raw, dict) else {}
    return {k: clamp_generation_value(k, src.get(k)) for k in GENERATION_BOUNDS}


def validate_generation(raw: dict | None) -> dict[str, float | int | str | dict]:
    """Validates the generation block in the WRITE path — and writes only what
    somebody actually set.

    Unlike the read path (which clamps quietly), write presence is strict: a
    value outside the hard bounds is a configuration error and raises
    ``ValueError`` (route → 422) — otherwise parameters that silently take
    effect but are broken would be created (e.g. tool_budget=999 blows up the
    iteration limit).

    I3-8: no more default back-filling. Earlier all six keys ended up in
    engine.json even when only one had been touched — that made 'did the user
    set this?' indistinguishable, and a consumer with its own decision (chat
    rounds 25, context window from the model table, memory cap 1000) would have
    inherited a registry default.

    The non-numeric options (thinking, reasoning_effort) follow the same
    presence rule: a well-formed value is carried, a malformed one raises
    ``ValueError`` instead of being dropped silently.
    """
    src = raw if isinstance(raw, dict) else {}
    out: dict[str, float | int | str | dict] = {}
    for key, (_default, low, high) in GENERATION_BOUNDS.items():
        value = src.get(key)
        if value is None:
            continue
        try:
            num = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"generation.{key}: not a number ({value!r})"
            ) from exc
        if num != num:
            raise ValueError(f"generation.{key}: NaN is not a valid value")
        if num < low or (high is not None and num > high):
            bound = f"{low}..{high}" if high is not None else f">= {low}"
            raise ValueError(
                f"generation.{key}={num} out of range ({bound})"
            )
        out[key] = clamp_generation_value(key, num)
    for key, normalizer in GENERATION_OPTION_NORMALIZERS.items():
        value = src.get(key)
        if value is None:
            continue
        normalized = normalizer(value)
        if normalized is None:
            raise ValueError(
                f"generation.{key}: not a valid option value ({value!r})"
            )
        out[key] = normalized
    return out


def read_generation_explicit(path: Path | None = None) -> dict[str, float | int]:
    """Only what somebody set: the engine.json entry or the env — no defaults.

    For consumers whose own default is a decision. The question 'did the user
    touch tool_budget?' must not be answered with 'yes, because 10 is there'
    when 10 is only the registry default.
    """
    choice = load_engine_config(path)
    stored = choice.generation if choice else None
    src = stored if isinstance(stored, dict) else {}
    out: dict[str, float | int] = {}
    for key in GENERATION_BOUNDS:
        raw = src.get(key)
        env = (os.environ.get(GENERATION_ENV_KEYS[key]) or "").strip()
        candidate = env if env else raw
        if candidate is None or candidate == "":
            continue
        try:
            num = float(candidate)
        except (TypeError, ValueError):
            continue
        if num != num:
            continue
        out[key] = clamp_generation_value(key, num)
    return out


def read_generation_values(path: Path | None = None) -> dict[str, float | int]:
    """Active generation values: env precedence, then engine.json, then default.

    The file stays untouched (the env is purely read-time precedence).
    """
    choice = load_engine_config(path)
    merged = normalize_generation(choice.generation if choice else None)
    for key, env_name in GENERATION_ENV_KEYS.items():
        raw = (os.environ.get(env_name) or "").strip()
        if raw:
            merged[key] = clamp_generation_value(key, raw)
    return merged


def read_generation_options(path: Path | None = None) -> dict[str, dict | str | None]:
    """Active non-numeric generation options: env precedence → engine.json → None.

    The same ladder as read_generation_values(), with the one difference that
    is the point: the default is None for both keys, and None means "not
    configured". The request path (core/model_provider.py) sends a field only
    when it is set — a request without thinking/reasoning_effort is what every
    installation sent before, so nothing changes until somebody configures it.
    """
    choice = load_engine_config(path)
    stored = choice.generation if choice else None
    src = stored if isinstance(stored, dict) else {}
    out: dict[str, dict | str | None] = {}
    for key, normalizer in GENERATION_OPTION_NORMALIZERS.items():
        env_raw = (os.environ.get(GENERATION_OPTION_ENV_KEYS[key]) or "").strip()
        candidate = env_raw if env_raw else src.get(key)
        out[key] = normalizer(candidate)
    return out


# Engine resolution: ONE source for CLI and server (W18, fail-closed)

def stdin_is_interactive() -> bool:
    """True when a TTY is attached to stdin — then onboarding is possible.

    Non-interactive contexts (CI, Docker, pipe, systemd) must NOT wait for
    prompt input: there the fail-closed path with the instruction applies.
    """
    try:
        return bool(sys.stdin and sys.stdin.isatty())
    except Exception:  # pragma: no cover — exotic stdin objects
        return False


def engine_choice_from_env() -> EngineChoice | None:
    """Engine choice from the env — the explicit configuration without engine.json.

    None = ``EPHE_MODEL_PROVIDER`` is not set (nothing chosen).
    An incomplete engine env (provider without endpoint/model) is a configuration
    error and aborts fail-closed — it is NOT covered up by a silent default.
    """
    provider = (os.environ.get(ENV_PROVIDER) or "").strip()
    if not provider:
        return None
    if provider not in VALID_PROVIDERS:
        raise EngineNotConfigured(
            f"Unknown {ENV_PROVIDER}={provider!r}. Allowed: {', '.join(VALID_PROVIDERS)}.",
        )

    url = (os.environ.get(ENV_BASE_URL[provider]) or "").strip() or None
    model = (os.environ.get(ENV_MODEL[provider]) or "").strip()
    if provider != LOCAL_OLLAMA and not url:
        raise EngineNotConfigured(
            f"{ENV_PROVIDER}={provider} is set, but {ENV_BASE_URL[provider]} is missing.",
        )
    # The tag is part of the choice for every engine class, the local one included:
    # Ollama on this machine is the engine, which tag runs inside it is the user's.
    if not model:
        raise EngineNotConfigured(
            f"{ENV_PROVIDER}={provider} is set, but {ENV_MODEL[provider]} is missing.",
        )
    return EngineChoice(provider=provider, model=model, api_url=url)


def resolve_engine_choice(
    config_path: Path | None = None,
    *,
    allow_prompt: bool = False,
    prompt_fn: Callable[..., EngineChoice] | None = None,
) -> EngineChoice:
    """Engine resolution (single source of truth for CLI AND server).

    Order:
      1. persisted ``engine.json`` (user with a valid config: unchanged),
      2. explicit engine env (``EPHE_MODEL_PROVIDER`` + endpoint/model),
      3. interactive onboarding — only with ``allow_prompt`` AND ``prompt_fn``,
      4. otherwise ``EngineNotConfigured`` (fail-closed with the instruction).

    There is no silent default: without a config and without the env this aborts
    instead of falling back to a local Ollama (or a remote host).
    """
    choice = load_engine_config(config_path)
    if choice is not None:
        return choice

    env_choice = engine_choice_from_env()
    if env_choice is not None:
        return env_choice

    if allow_prompt and prompt_fn is not None:
        return prompt_fn(config_path=config_path)

    raise EngineNotConfigured()


def save_engine_config(
    choice: EngineChoice, path: Path | None = None
) -> bool:
    """Persists the engine choice atomically into ~/.ephe/engine.json."""
    cfg_path = path or default_config_path()
    try:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        # Hardening (AppSec/least privilege): config directory only for the owner
        # (0700). Prevents other local processes from reading the engine choice or
        # drawing side channels from the config.
        try:
            cfg_path.parent.chmod(0o700)
        except OSError:
            pass
        payload = asdict(choice)
        tmp = cfg_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(cfg_path)
        # Hardening: engine.json readable/writable only by the owner (0600). The
        # file itself never contains secrets (keys stay in the session env), but
        # least privilege applies to every persisted artifact.
        try:
            cfg_path.chmod(0o600)
        except OSError:
            pass
        return True
    except Exception:
        return False


def clear_engine_config(path: Path | None = None) -> bool:
    """Removes the persisted engine choice."""
    cfg_path = path or default_config_path()
    try:
        if cfg_path.exists():
            cfg_path.unlink()
        return True
    except Exception:
        return False


# Workspace (project folder)
# One source: engine.json. Shell tools start inside it, file tools resolve
# relative paths against it. None/empty = behaviour as before (server cwd).

#: Folders a workspace or an output directory may never be. The value is the owner's own
#: choice and may sit anywhere they work, so this is a refusal list rather than a cage: it
#: holds the places a credential lives, the system roots where a stray write costs the
#: machine, and this product's own state directory, which a workspace inside it would nest
#: in its own data.
REFUSED_DIRS = (
    "~/.ephe", "~/.ssh", "~/.gnupg", "~/Library/Keychains",
    "/etc", "/bin", "/sbin", "/System", "/Library", "/dev", "/proc", "/sys",
)


def _refuse_unsafe_dir(path: Path, what: str) -> None:
    """Refuses a folder the tools must not take as a workspace or an output target.

    Every entry is resolved before the comparison, because on macOS `/etc` is itself a
    symlink and the text of the two sides would otherwise never meet.
    """
    from core.path_guard import within

    if path == path.parent:
        raise ValueError(f"{what} must not be the filesystem root: {path}")
    for entry in REFUSED_DIRS:
        root = Path(entry).expanduser().resolve()
        if path == root or within(path, root):
            raise ValueError(f"{what} must not sit in {root}: {path}")


def validate_workspace_dir(path: str | None) -> str | None:
    """Normalises + validates a workspace path (ValueError when invalid)."""
    if path is None or not str(path).strip():
        return None
    # The workspace directory is the user's own engine setting: the project folder may
    # sit anywhere the user works, so there is no root to jail it to. The only caller is
    # the settings route (server/routes/settings.py:220), where the value arrives as the
    # owner's own folder choice.
    p = Path(str(path).strip()).expanduser()
    if not p.is_absolute():
        raise ValueError("Workspace path must be absolute.")
    # The candidate is the owner's own folder pick, and the refusal list below is what keeps
    # it out of the places that matter.
    p = p.resolve()  # codeql[py/path-injection]
    _refuse_unsafe_dir(p, "Workspace directory")
    if not p.is_dir():
        raise ValueError(f"Workspace directory does not exist: {p}")
    return str(p)


def get_workspace_dir() -> str:
    """Active workspace directory for the shell/file tools.

    Parity with ``workspace_rules.resolve_workspace_dir``: the env
    ``EPHE_WORKSPACE`` wins (tests/power users), otherwise the persisted
    engine.json; on a missing/invalid path we fall back to the server cwd
    (the old behaviour), never crash.
    """
    env = (os.environ.get("EPHE_WORKSPACE") or "").strip()
    if env:
        try:
            p = Path(env).expanduser()
            if p.is_dir():
                return str(p.resolve())
        except Exception:
            pass
    choice = load_engine_config()
    wd = (choice.workspace_dir if choice else "") or ""
    if wd:
        try:
            p = Path(wd).expanduser()
            if p.is_dir():
                return str(p.resolve())
        except Exception:
            pass
    return os.getcwd()


def workspace_hash(path: str | None = None) -> str:
    """W16: 16 hex characters of the SHA256 over the workspace path — SSOT for
    vector scope names (collection + persist subfolder). Deterministic and
    platform-neutral (resolve before hashing)."""
    import hashlib

    target = str(path) if path else get_workspace_dir()
    try:
        target = str(Path(target).expanduser().resolve())
    except Exception:
        pass
    return hashlib.sha256(target.encode("utf-8")).hexdigest()[:16]


def validate_output_dir(path: str | None) -> str | None:
    """Normalises the output path; empty input = no override (None).

    Unlike the workspace the folder is created when needed (level 1 would
    otherwise never exist, level 2 is a fresh target per project).
    """
    if path is None or not str(path).strip():
        return None
    # The output directory is the user's own engine setting, as above: the second
    # folder of the same POST (server/routes/settings.py:225).
    p = Path(str(path).strip()).expanduser()
    if not p.is_absolute():
        raise ValueError("Output dir path must be absolute.")
    # The same folder choice, for the second field of the same POST.
    p = p.resolve()  # codeql[py/path-injection]
    _refuse_unsafe_dir(p, "Output dir")
    p.mkdir(parents=True, exist_ok=True)
    if not p.is_dir():
        raise ValueError(f"Output dir is not a directory: {p}")
    return str(p)


def get_output_dir() -> str | None:
    """Active output path for the document/image tools (R44/P4). None = default.

    As with the workspace: the persisted engine.json is the source. Since R4-A1 the
    value is no longer a birth place — the output tools ask artifact_output_dir();
    this field is only still read by POST /api/artifacts/{id}/adopt.
    """
    choice = load_engine_config()
    if choice and choice.output_dir:
        return choice.output_dir
    # Without a persisted value: respect the env override (CI/container).
    raw = (os.environ.get("EPHE_OUTPUT_DIR") or "").strip()
    return raw or None


def artifact_output_dir() -> Path:
    """The ONE birth place: the workbench, per session (``~/.ephe/artifacts/…``).

    Eleven tools copied the old ladder (output_dir → ~/Downloads) and differed
    from each other — every deviation a location no reviewer knows. Since A1 none
    of these tools asks for ``output_dir`` any more: the field was demoted from
    birth place to **adoption target** (POST /artifacts/{id}/adopt reads it). The
    folder is created when it is asked for, not only when something is written.
    """
    from core.artifact_workbench import artifact_session_dir

    out = artifact_session_dir()
    out.mkdir(parents=True, exist_ok=True)
    return out


def get_brand_kit() -> dict:
    """Optional brand kit from the persisted engine config (wave 11, P1-4).

    Empty dict when no ``brand`` block is set — the deck tools then fall back to
    the generic theme. No default hardcoding: the config is the only source.
    """
    choice = load_engine_config()
    if choice and choice.brand:
        return dict(choice.brand)
    return {}


def persist_engine_choice(
    provider: str,
    model: str,
    base_url: str | None = None,
    generation: dict | None = None,
) -> bool:
    """R20-SSOT: engine persistence for BOTH write paths (POST /api/settings
    and PUT /api/model/provider). api_url is only persisted for remote
    providers — otherwise a locally bound Ollama comes back wrong on restart.

    Wave 5: `generation` (generation parameters) is an optional third
    persistence field. None = inherit the existing block (read-modify-write), so
    a provider change does not silently delete the generation settings.

    Measured 2026-10-09: `brand` and `pricing` were not re-attached, so every
    engine switch dropped them — contradicting this file's own note that pricing
    exists so the USD accounting follows a model change. Both are pure
    read-modify-write inherit: a switch changes provider/model/api_url only.
    """
    # Read-modify-write: the folder settings (path chain) survive a provider
    # persist, otherwise they are lost quietly on an engine change.
    existing = load_engine_config()
    return save_engine_config(
        EngineChoice(
            provider=provider,
            model=model,
            api_url=(
                base_url
                if provider in ("openai_compatible", "custom_ollama") and base_url
                else None
            ),
            output_dir=existing.output_dir if existing else None,
            workspace_dir=existing.workspace_dir if existing else None,
            brand=existing.brand if existing else None,
            pricing=existing.pricing if existing else None,
            generation=(
                generation
                if generation is not None
                else (existing.generation if existing else None)
            ),
        )
    )


# Named-engine context window (W7-6, engine-named)
#
# The tier table in core.model_config keys a window by ROUTING CLASS
# (offline/fast/power) — the model class the router picks, never the engine a
# measurement ran on. On its own it cannot satisfy the wave gate that every
# engine number names its engine, so the engine side lives here: which field a
# live engine writes for its window, who reads it, and a verdict that names the
# engine whether the static row matches the probe or not.
#
# The field names were live-measured, never guessed:
#   context_window      DeepSeek hosted API — GET https://api.deepseek.com/v1/models
#                       (2026-10-12: deepseek-flash and deepseek-v4-pro -> 1048576)
#   max_model_len       vLLM
#   context_length      SGLang and the DGX Spark health surface (2026-10-11)
#   max_context_length  several OpenAI-compatible routers
CONTEXT_WINDOW_FIELDS: tuple[str, ...] = (
    "context_window",
    "max_model_len",
    "context_length",
    "max_context_length",
)


def window_from_model_entry(entry: object) -> int | None:
    """The window of one /v1/models entry from the field the engine wrote, or None.

    An entry without any of CONTEXT_WINDOW_FIELDS leaves the window unknown, so
    the caller owns the fallback. A boolean never counts as a window.
    """
    if not isinstance(entry, dict):
        return None
    for field in CONTEXT_WINDOW_FIELDS:
        value = entry.get(field)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value > 0:
            return value
    return None


def engine_window_name(provider: str, model: str) -> str:
    """The name every engine number has to carry: ``<provider>/<model>``.

    Falls back to whichever half is set; ``"unnamed"`` only when neither is — an
    engine number without a name is what the wave gate forbids.
    """
    provider = (provider or "").strip()
    model = (model or "").strip()
    if provider and model:
        return f"{provider}/{model}"
    return model or provider or "unnamed"


@dataclass(frozen=True)
class WindowReconciliation:
    """Verdict of one tier row against one live probe — the engine always named."""

    engine: str
    verdict: str        # match | table-stale | probe-missing | no-row
    table_window: int | None
    probe_window: int | None
    detail: str


def reconcile_tier_window(
    *,
    provider: str,
    model: str,
    table_window: int | None,
    probe_window: int | None,
) -> WindowReconciliation:
    """Compare a tier-table row with a live probe of the named engine.

    The live probe wins at runtime (``resolve_context_window``: env > engine >
    tier > legacy); this verdict only says out loud whether the static row still
    matches what the engine serves, so a stale row cannot hide behind the probe.
    Every branch names the engine.

    verdict:
      match          probe equals the row — the row still describes the engine,
      table-stale    probe differs — the row no longer matches the named engine,
      probe-missing  the engine named no window (unreachable, or a field it does
                     not write); the tier row is then the effective value and is
                     a different engine's number,
      no-row         the tier table carries no window for this engine at all.
    """
    engine = engine_window_name(provider, model)
    if probe_window is None:
        return WindowReconciliation(
            engine=engine,
            verdict="probe-missing",
            table_window=table_window,
            probe_window=None,
            detail=(
                f"{engine} named no window; the {table_window} tier row is the "
                "effective value and belongs to a different engine"
                if table_window
                else f"{engine} named no window and no tier row exists"
            ),
        )
    if table_window is None:
        return WindowReconciliation(
            engine=engine,
            verdict="no-row",
            table_window=None,
            probe_window=probe_window,
            detail=f"no tier row for {engine}; the live probe {probe_window} is the only number",
        )
    if table_window == probe_window:
        return WindowReconciliation(
            engine=engine,
            verdict="match",
            table_window=table_window,
            probe_window=probe_window,
            detail=f"the tier row equals the live probe of {engine}",
        )
    return WindowReconciliation(
        engine=engine,
        verdict="table-stale",
        table_window=table_window,
        probe_window=probe_window,
        detail=(
            f"the tier row {table_window} is stale next to the live probe "
            f"{probe_window} of {engine}"
        ),
    )
