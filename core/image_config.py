"""Ephe – image_config: persistent image-endpoint setting (R16).

One source: ~/.ephe/image.json (respects EPHE_CONFIG_DIR). The
settings UI writes here, `generate_image` reads from it — priority in the tool:
env (EPHE_IMAGE_*) > image.json > active chat engine.

Deliberately NOT in engine.json: save_engine_config persists asdict(EngineChoice)
and would discard foreign keys; image.json is also separate in content (the
API key is a secret and gets 0600, atomic write like engine.json).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

# Read dynamically through the module (engine_config.CONFIG_DIR) so tests can
# redirect the config dir by monkeypatching it — a `from … import CONFIG_DIR`
# would freeze the binding and write into the real HOME in tests.
from core import engine_config


@dataclass
class ImageConfig:
    base_url: str = ""
    api_key: str = field(repr=False, default="")
    model: str = ""


def image_config_path():
    return engine_config.CONFIG_DIR / "image.json"


def _validate_base_url(base_url: str) -> str:
    cleaned = (base_url or "").strip().rstrip("/")
    if cleaned and not cleaned.startswith(("http://", "https://")):
        raise ValueError("base_url must start with http:// or https://.")
    return cleaned


def load_image_config() -> ImageConfig:
    try:
        raw = json.loads(image_config_path().read_text(encoding="utf-8"))
        return ImageConfig(
            base_url=str(raw.get("base_url", "") or ""),
            api_key=str(raw.get("api_key", "") or ""),
            model=str(raw.get("model", "") or ""),
        )
    except Exception:
        # Damaged/unreadable → treat as not configured, never crash.
        return ImageConfig()


def save_image_config(
    base_url: str = "",
    api_key: str | None = None,
    model: str = "",
    path=None,
) -> ImageConfig:
    """Atomic write (0600). api_key=None = keep the existing key,
    api_key="" = delete the key (settings-UI semantics)."""
    existing = load_image_config()
    cfg = ImageConfig(
        base_url=_validate_base_url(base_url),
        api_key=(existing.api_key if api_key is None else api_key),
        model=(model or "").strip(),
    )
    target = path or image_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.parent.chmod(0o700)
    except OSError:
        pass
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return cfg
