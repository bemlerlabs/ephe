"""Marketplace facade: listing resolution and the staging installer."""
from __future__ import annotations

from core.plugin_admin import (
    _audit_install,
    _installed_version,
    _register_installed,
    _version_key,
)
from core.plugin_install import (
    _default_fetcher,
    _install_from_marketplace,
    _safe_extract,
    install_from_marketplace,
)
from core.plugin_listing import (
    MARKETPLACE_FILENAME,
    MARKETPLACE_VERSION,
    load_marketplace,
    marketplace_path,
    resolve_entry,
)

__all__ = [
    "MARKETPLACE_FILENAME",
    "MARKETPLACE_VERSION",
    "_audit_install",
    "_default_fetcher",
    "_install_from_marketplace",
    "_installed_version",
    "_register_installed",
    "_safe_extract",
    "_version_key",
    "install_from_marketplace",
    "load_marketplace",
    "marketplace_path",
    "resolve_entry",
]
