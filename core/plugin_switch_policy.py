"""The read-only brake on the plugin switch surface (O-10, 2026-10-21).

One setting, one read, one refusal audit. The brake blocks switch mutations; it
does not disable a plugin and it never restores the retired ``master_enabled``
gating bypass.
"""

from __future__ import annotations

READ_ONLY_CODE = "plugin_lifecycle_read_only"


def read_only() -> bool:
    """Read at request time; the operator may flip it without a restart."""
    from core.settings_schema import deep_bool

    return deep_bool("plugins.plugin_lifecycle_read_only")


def audit_refusal(*, action: str, plugin: str = "", scope: str = "") -> None:
    from core.audit_log import audit_event

    audit_event(
        "plugin_lifecycle",
        tool=plugin,
        decision="read_only_refused",
        status="refused",
        detail=f"action={action} scope={scope} reason={READ_ONLY_CODE}",
    )
