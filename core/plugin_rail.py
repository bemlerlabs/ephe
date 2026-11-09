"""Ephe — which rail a bundle actually runs on.

core/plugin_rail.py

The Extensions surface says what a plugin is switched on. It did not say *how* it runs, and
the two facts come apart in this product: a version 1 bundle lists names of tools the host
already implements, so the bundle is a switch, while a version 2 bundle carries its own
entry — a file inside its directory that the confined worker (#9) resolves and runs. A
reader who is told both are "a plugin" is being told something untrue, and the difference is
exactly what the platform ruling A1 was about: nothing in the host process imports a plugin.

Three rails, and the choice is made from the manifest the same way `tool_claims` reads it, so
the surface and the mount cannot disagree about the same bundle:

  `declarative`  no tool at all. The host reads the bundle's components as data — skills,
                 commands, instructions — and executes nothing of it.
  `kernel`       version 1 `components.tools`: bare names of kernel tools this bundle
                 activates. The code that runs is Ephe's, and the bundle is the switch.
  `worker`       version 2 `components.tools`: one entry per tool, resolved inside the plugin
                 directory and run in the confined child process, behind the signature gate
                 and the per-family approval rule.

The rail is a property of what is declared, not of what is enabled: a disabled worker bundle
still names its own entries, and the surface says so. Whether a given tool answered today is
the mount's record (`plugin_lifecycle_mount.mount_records`), and that is a different column.
"""
from __future__ import annotations

from typing import Any

RAIL_DECLARATIVE = "declarative"
RAIL_KERNEL = "kernel"
RAIL_WORKER = "worker"

RAILS = (RAIL_DECLARATIVE, RAIL_KERNEL, RAIL_WORKER)


def rail_of(manifest: dict[str, Any] | None) -> str:
    """The one rail a bundle's own manifest puts it on."""
    return rail_fact(manifest)["rail"]


def rail_fact(manifest: dict[str, Any] | None) -> dict[str, Any]:
    """The rail and the two counts that decided it, so a surface can show its work.

    `contributed` counts version 2 entries the bundle carries itself, `activated` counts the
    kernel names a version 1 list turns on. A manifest that never validated reaches this
    function as nothing at all, and nothing is `declarative`: declaring no tool is a fact
    about the bundle, while an unreadable manifest is a fact about the reader, and the second
    one belongs in the notice beside this column.
    """
    if not isinstance(manifest, dict):
        return {"rail": RAIL_DECLARATIVE, "contributed": 0, "activated": 0}

    from core.plugin_tools_contract import tool_claims

    claims = tool_claims(manifest)
    contributed = sum(1 for claim in claims if claim.contributed)
    activated = sum(1 for claim in claims if not claim.contributed)
    if contributed:
        rail = RAIL_WORKER
    elif activated:
        rail = RAIL_KERNEL
    else:
        rail = RAIL_DECLARATIVE
    return {"rail": rail, "contributed": contributed, "activated": activated}
