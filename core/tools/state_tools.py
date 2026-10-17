"""Ephe – stateful agent tools (P3, parity harness).

Two thin agent tools that wire the write path onto the persistent
memory and the skill catalog:

- ``memory``        : 2-tier write path (``user`` = profile, ``memory`` = Chroma).
- ``skill_manage``  : skill catalog care (create/list/delete) via the loader.

Both are deliberately read-/write-poor and use exclusively the existing
single-source-of-truth APIs (``core.memory.Memory``, ``core.profile``,
``core.skills.SkillLoader``) — no second truth, no own cache.
"""

from __future__ import annotations

import os

from core.reason import reason

#: P2-1: a hard write budget per tier, so an agent loop does not fill up the
#: persistent memory. Surplus is trimmed on add (the oldest
#: entry gives way). Deliberately small — injection is retrieval-side
#: capped at max_entries=10 anyway, a larger archive brings the model nothing.
#: Configurable via EPHE_MEMORY_CEILING (fallback 200), 12 per field.
MEMORY_TIER_CEILING = int(os.environ.get("EPHE_MEMORY_CEILING", "200"))
USER_TIER_FIELDS = int(os.environ.get("EPHE_USER_TIER_FIELDS", "12"))


def _enforce_memory_ceiling(mem, ceiling: int = MEMORY_TIER_CEILING) -> int:
    """Keeps the collection <= ceiling; deletes surplus oldest entries.

    ``list_all`` returns newest-first (timestamp desc) — the last element
    is therefore the oldest entry. Returns the number of deleted entries.
    """
    removed = 0
    while mem.count() > ceiling:
        entries = mem.list_all(limit=ceiling + 1)
        if not entries:
            break
        mem.delete(entries[-1]["id"])
        removed += 1
    return removed


# memory (2-Tier)

async def memory(action: str, target: str, content: str = "",
                 old_text: str = "", memory_type: str = "",
                 supersedes: str = "") -> str:
    """2-tier memory: ``user`` (profile) and ``memory`` (fact collection).

    action: add | replace | remove | list
    target: user | memory

    ``memory_type`` (semantic|episodic|procedural) and ``supersedes`` (id of an
    existing fact) belong only to the ``memory`` tier and only to the Kepta brain
    as columns; under Chroma they pass through without effect.
    """
    action = (action or "").strip().lower()
    target = (target or "").strip().lower()
    if action not in {"add", "replace", "remove", "list"}:
        return reason("memory_action_unknown", "[memory] action must be add|replace|remove|list")
    if target not in {"user", "memory"}:
        return reason("memory_target_unknown", "[memory] target must be user|memory")

    # Tier "memory": the fact collection behind the memory facade.
    if target == "memory":
        from core.memory import Memory
        mem = Memory()
        options: dict = {}
        if (memory_type or "").strip():
            options["memory_type"] = memory_type.strip().lower()
        if action == "add":
            if not content.strip():
                return reason("memory_add_needs_content", "[memory] add needs 'content'")
            # P2-1: hard tier budget — the oldest entry gives way, so the
            # collection does not grow unbounded.
            _enforce_memory_ceiling(mem)
            mem.store(content.strip(), metadata={"source": "agent"}, **options)
            return reason("memory_stored", f"[memory] stored ({mem.count()} entries)",
                          count=str(mem.count()))
        if action == "list":
            # Only leading facts: a superseded fact stays queryable (search),
            # but should not stand in the listing as a present-tense claim.
            entries = [
                e for e in mem.list_all(limit=50)
                if not (e.get("metadata") or {}).get("superseded_by")
            ]
            if not entries:
                return reason("memory_empty", "[memory] no entries")
            return "\n".join(f"- {e['text']}" for e in entries)
        if action == "remove":
            if not old_text.strip():
                return reason("memory_remove_needs_old_text",
                              "[memory] remove needs 'old_text' (substring)")
            removed = 0
            for e in mem.list_all(limit=500):
                if old_text.strip() in e["text"]:
                    mem.delete(e["id"])
                    removed += 1
            return reason("memory_removed", f"[memory] removed {removed} entries",
                          count=str(removed))
        # replace = correction. Under Kepta the identified fact is superseded
        # (superseded_by + valid_to, so it stays queryable); Chroma replaces the text
        # in the same id. Both through the same call — core/memory.py:store().
        if not old_text.strip() or not content.strip():
            return reason("memory_replace_needs_fields",
                          "[memory] replace needs 'old_text' and 'content'")
        _enforce_memory_ceiling(mem)
        hit_id = (supersedes or "").strip() or next(
            (e["id"] for e in mem.list_all(limit=500) if old_text.strip() in e["text"]), None
        )
        if hit_id:
            mem.store(content.strip(), metadata={"source": "agent"},
                      supersedes=hit_id, **options)
        else:
            mem.store(content.strip(), metadata={"source": "agent"}, **options)
        return reason("memory_replaced", f"[memory] replaced ({mem.count()} entries)",
                      count=str(mem.count()))

    # Tier "user": structured user profile (JSON, no vector).
    from core.profile import load_profile, save_profile
    profile = load_profile()
    if action == "list":
        return profile.to_context_string() or reason("profile_empty", "[memory] profile empty")
    if action == "add":
        if not content.strip():
            return reason("memory_add_needs_content", "[memory] add needs 'content'")
        # Profile fields are lists/strings; we fill the first free field.
        _apply_profile_field(profile, content.strip())
        save_profile(profile)
        return reason("profile_updated", "[memory] profile updated")
    if action in {"replace", "remove"}:
        if not content.strip():
            return reason("profile_action_needs_content",
                          f"[memory] {action} needs 'content' (field=value)", action=action)
        _apply_profile_field(profile, content.strip())
        save_profile(profile)
        return reason("profile_action_done", f"[memory] profile {action}d", action=action)
    # Unreachable: the action guard above admits exactly the four branches below.
    return "[memory] unknown combination"


def _apply_profile_field(profile, kv: str) -> None:
    """Sets a profile field from 'key=value' (lists separated by comma)."""
    if "=" not in kv:
        # Without '=': append as Topics_of_interest (the most common case).
        profile.topics_of_interest = [
            *profile.topics_of_interest, kv
        ]
        return
    key, _, value = kv.partition("=")
    key, value = key.strip(), value.strip()
    if not hasattr(profile, key):
        return
    current = getattr(profile, key)
    if isinstance(current, list):
        setattr(profile, key, [v.strip() for v in value.split(",") if v.strip()])
    else:
        setattr(profile, key, value)


# skill_manage (catalog care)

async def skill_manage(action: str, name: str = "", trigger: str = "",
                       description: str = "", tools: str = "",
                       system_prompt: str = "", test_input: str = "",
                       test_expect_tool: str = "",
                       test_expect_contains: str = "") -> str:
    """Care for the skill catalog: list | show | create | delete.

    Uses exclusively ``SkillLoader`` (single source of truth for the
    catalog). create writes a validated markdown skill.
    """
    from core.skills import SkillLoader, SkillLoadError
    action = (action or "").strip().lower()
    loader = SkillLoader()

    if action == "list":
        skills = loader.load_all()
        if not skills:
            return reason("skill_list_empty", "[skill_manage] no skills")
        return "\n".join(f"- {s.name}: {s.description}" for s in skills)

    if action == "show":
        if not name.strip():
            return reason("skill_show_needs_name", "[skill_manage] show needs 'name'")
        try:
            skill = loader.load(name.strip())
        except SkillLoadError as exc:
            return f"[skill_manage] {exc}"
        return (
            f"# {skill.name}\n"
            f"Trigger: {skill.trigger}\n"
            f"Description: {skill.description}\n"
            f"Tools: {', '.join(skill.tools)}\n\n"
            f"{skill.system_prompt}"
        )

    if action == "create":
        if not name.strip() or not trigger.strip() or not description.strip():
            return reason("skill_create_needs_fields",
                          "[skill_manage] create needs name, trigger, description")
        if not system_prompt.strip():
            return reason("skill_create_needs_prompt",
                          "[skill_manage] create needs system_prompt")
        tool_list = [t.strip() for t in tools.split(",") if t.strip()]
        try:
            skill = loader.save(
                name=name.strip(),
                trigger=trigger.strip(),
                description=description.strip(),
                tools=tool_list,
                system_prompt=system_prompt,
                test_input=test_input,
                test_expect_tool=test_expect_tool,
                test_expect_contains=test_expect_contains,
            )
        except (SkillLoadError, Exception) as exc:  # noqa: BLE001
            return reason("skill_create_failed", f"[skill_manage] create failed: {exc}",
                          error=str(exc))
        return reason("skill_saved", f"[skill_manage] skill '{skill.name}' saved",
                      name=skill.name)

    if action == "delete":
        if not name.strip():
            return reason("skill_delete_needs_name", "[skill_manage] delete needs 'name'")
        try:
            loader.delete(name.strip())
        except Exception as exc:  # noqa: BLE001
            return reason("skill_delete_failed", f"[skill_manage] delete failed: {exc}",
                          error=str(exc))
        return reason("skill_deleted", f"[skill_manage] skill '{name.strip()}' deleted",
                      name=name.strip())

    # Unreachable: the four branches above are the whole action set.
    return "[skill_manage] action must be list|show|create|delete"
