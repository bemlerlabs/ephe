"""The engine setup the terminal app opens when no engine is configured.

Two surfaces: a provider list and the form behind it. Nothing here picks a
provider on its own. The user names one, the form asks for the endpoint and the
key only when that provider needs them, and the model comes from what the
endpoint actually serves.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from core.engine_config import (
    CUSTOM_OLLAMA,
    LOCAL_OLLAMA,
    OPENAI_COMPAT,
    EngineChoice,
    load_engine_config,
    save_engine_config,
    store_engine_api_key,
)
from ui.palette import ACCENT, DIM, TEXT

LOCAL_OLLAMA_URL = "http://127.0.0.1:11434"


@dataclass(frozen=True)
class Provider:
    """One entry of the setup list: a provider and the endpoint it starts from."""

    key: str
    label: str
    provider: str
    start_url: str = ""
    editable_url: bool = True
    asks_key: bool = False
    key_required: bool = False


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        key="local",
        label="Local Ollama on this machine",
        provider=LOCAL_OLLAMA,
        start_url=LOCAL_OLLAMA_URL,
        editable_url=False,
    ),
    Provider(
        key="ollama",
        label="Your own Ollama / vLLM server",
        provider=CUSTOM_OLLAMA,
        start_url="",
    ),
    Provider(
        key="openai",
        label="OpenAI-compatible endpoint (vLLM, SGLang, DGX)",
        provider=OPENAI_COMPAT,
        start_url="",
        asks_key=True,
    ),
    Provider(
        key="openrouter",
        label="OpenRouter",
        provider=OPENAI_COMPAT,
        start_url="https://openrouter.ai/api/v1",
        asks_key=True,
        key_required=True,
    ),
)


def provider_by_key(key: str) -> Provider | None:
    for provider in PROVIDERS:
        if provider.key == key:
            return provider
    return None


def validate_setup(provider: Provider, url: str, model: str, key: str) -> str | None:
    """Why this form cannot be saved yet, or None when it can."""
    if provider.provider == LOCAL_OLLAMA:
        if not model.strip():
            return "Pick a model this machine serves."
        return None
    if not url.strip():
        return "The endpoint is part of the choice: enter its base URL (…/v1)."
    if provider.key_required and not key.strip():
        return f"{provider.label} needs an API key."
    if not model.strip():
        return "Pick a model the endpoint serves, or type its tag."
    return None


def _model_ids(target: str, key: str, timeout: float) -> list[str]:
    headers = {"Accept": "application/json"}
    if key.strip():
        headers["Authorization"] = f"Bearer {key.strip()}"
    try:
        request = urllib.request.Request(target, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    ids = [
        str(entry.get("id") or "")
        for entry in payload.get("data", [])
        if isinstance(entry, dict) and entry.get("id")
    ]
    if not ids:
        ids = [
            str(entry.get("name") or "")
            for entry in payload.get("models", [])
            if isinstance(entry, dict) and entry.get("name")
        ]
    return [model for model in ids if model]


def list_models(provider: Provider, url: str, key: str = "", timeout: float = 6.0) -> list[str]:
    """The model ids the endpoint lists, or an empty list when it does not answer.

    Both shapes are tried: the OpenAI-compatible route first for a remote
    endpoint, the native tag route for a local one, the other one as fallback.
    """
    base = (url or provider.start_url).strip().rstrip("/")
    if not base:
        return []
    root = base.removesuffix("/v1")
    compatible = f"{base if base.endswith('/v1') else base + '/v1'}/models"
    tags = f"{root}/api/tags"
    targets = (tags, compatible) if provider.provider == LOCAL_OLLAMA else (compatible, tags)
    for target in targets:
        models = _model_ids(target, key, timeout)
        if models:
            return models
    return []


def save_engine_setup(provider: Provider, url: str, model: str, key: str) -> EngineChoice:
    """Persist the choice the way every other surface reads it, and apply it here.

    The endpoint is dropped for a local engine on purpose: a stale remote URL in
    the config comes back wrong on the next start.
    """
    existing = load_engine_config()
    api_url = None if provider.provider == LOCAL_OLLAMA else url.strip().rstrip("/")
    choice = EngineChoice(provider=provider.provider, model=model.strip(), api_url=api_url)
    if existing is not None:
        choice.output_dir = existing.output_dir
        choice.workspace_dir = existing.workspace_dir
        choice.brand = existing.brand
        choice.pricing = existing.pricing
        choice.generation = existing.generation
    save_engine_config(choice)
    if key.strip() and provider.provider == OPENAI_COMPAT:
        store_engine_api_key(key.strip(), engine=choice)
        os.environ["EPHE_OPENAI_COMPAT_API_KEY"] = key.strip()
    choice.apply_env()
    return choice


class ProviderPicker(ModalScreen[Provider | None]):
    """The provider list: arrows move, Enter opens the form behind the entry."""

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
        Binding("up", "previous", "Up", show=False, priority=True),
        Binding("down", "next", "Down", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._index = 0

    def compose(self) -> ComposeResult:
        with Vertical(classes="overlay-card"):
            yield Static(
                f"[bold {TEXT}]Engine setup[/bold {TEXT}]", classes="overlay-title"
            )
            yield Static("", id="provider-list", markup=True)
            yield Static(f"[{DIM}]Enter choose · Esc close[/{DIM}]", id="provider-hint")

    def on_mount(self) -> None:
        self._render_list()

    def action_close(self) -> None:
        self.dismiss(None)

    def action_next(self) -> None:
        self._index = (self._index + 1) % len(PROVIDERS)
        self._render_list()

    def action_previous(self) -> None:
        self._index = (self._index - 1) % len(PROVIDERS)
        self._render_list()

    def on_key(self, event: object) -> None:
        from textual.events import Key

        if isinstance(event, Key) and event.key == "enter":
            event.prevent_default()
            self.dismiss(PROVIDERS[self._index])

    def _render_list(self) -> None:
        rows = []
        for position, provider in enumerate(PROVIDERS):
            marker = (
                f"[bold {ACCENT}]›[/bold {ACCENT}]" if position == self._index else " "
            )
            detail = f"  [{DIM}]{provider.start_url}[/{DIM}]" if provider.start_url else ""
            rows.append(f"{marker} {provider.label}{detail}")
        self.query_one("#provider-list", Static).update("\n".join(rows))


class EngineForm(ModalScreen[EngineChoice | None]):
    """Endpoint, key and model for the picked provider; Ctrl+S lists the models."""

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
        Binding("ctrl+s", "connect", "List models", priority=True),
    ]

    def __init__(self, provider: Provider) -> None:
        super().__init__()
        self._provider = provider

    def compose(self) -> ComposeResult:
        with Vertical(classes="overlay-card"):
            yield Static(
                f"[bold {TEXT}]{self._provider.label}[/bold {TEXT}]",
                classes="overlay-title",
            )
            if self._provider.editable_url:
                yield Input(
                    placeholder="Base URL, e.g. http://host:8000/v1",
                    value=self._provider.start_url,
                    id="setup-url",
                )
            if self._provider.asks_key:
                yield Input(
                    placeholder="API key (kept in the OS keychain)",
                    password=True,
                    id="setup-key",
                )
            yield Static("", id="setup-status", markup=True)
            yield Input(placeholder="Model tag", id="setup-model")
            yield Static("", id="setup-models", markup=True)
            yield Static(
                f"[{DIM}]Ctrl+S list models · Enter save · Esc back[/{DIM}]",
                id="setup-hint",
            )

    def on_mount(self) -> None:
        if self._provider.provider == LOCAL_OLLAMA:
            self.query_one("#setup-model", Input).focus()
            self.action_connect()
        elif self._provider.editable_url:
            self.query_one("#setup-url", Input).focus()
        else:
            self.query_one("#setup-model", Input).focus()

    def action_close(self) -> None:
        self.dismiss(None)

    def _status(self, text: str) -> None:
        self.query_one("#setup-status", Static).update(text)

    def _url(self) -> str:
        try:
            return self.query_one("#setup-url", Input).value.strip()
        except Exception:
            return self._provider.start_url

    def _key(self) -> str:
        try:
            return self.query_one("#setup-key", Input).value.strip()
        except Exception:
            return ""

    def action_connect(self) -> None:
        self._status(f"[{DIM}]Listing models…[/{DIM}]")
        self.run_worker(self._list_worker(), group="engine-setup", exclusive=True)

    async def _list_worker(self) -> None:
        import asyncio

        models = await asyncio.to_thread(
            list_models, self._provider, self._url(), self._key()
        )
        if not models:
            self._status(
                f"[{ACCENT}]No models listed — check the URL, the key and that the "
                f"engine runs.[/{ACCENT}]"
            )
            return
        field = self.query_one("#setup-model", Input)
        if not field.value.strip():
            field.value = models[0]
        shown = ", ".join(models[:8]) + ("…" if len(models) > 8 else "")
        self.query_one("#setup-models", Static).update(f"[{DIM}]{shown}[/{DIM}]")
        self._status(f"[{DIM}]{len(models)} model(s) served.[/{DIM}]")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._save()

    def _save(self) -> None:
        model = self.query_one("#setup-model", Input).value
        problem = validate_setup(self._provider, self._url(), model, self._key())
        if problem is not None:
            self._status(f"[{ACCENT}]{problem}[/{ACCENT}]")
            return
        try:
            choice = save_engine_setup(self._provider, self._url(), model, self._key())
        except Exception as exc:
            self._status(f"[{ACCENT}]Could not store the engine: {exc}[/{ACCENT}]")
            return
        self.dismiss(choice)


__all__ = [
    "PROVIDERS",
    "EngineForm",
    "Provider",
    "ProviderPicker",
    "list_models",
    "provider_by_key",
    "save_engine_setup",
    "validate_setup",
]
