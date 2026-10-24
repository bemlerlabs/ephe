"""Six pre-filled team shapes; a role without an agent becomes one.

A template names its roles and tools; creating a team from it materializes any
missing role as a local agent first. The instruction is engine-facing and stays
in English like every prompt in the kernel.
"""
from __future__ import annotations

from typing import Any

from core import agent_store
from core.agent_team_schema import ROUNDS_DEFAULT, TEAM_TIMEOUT_DEFAULT_S, TeamError

TEMPLATES: dict[str, dict[str, Any]] = {
    "research": {
        "name": "Research team",
        "description": "Parallel sources, one verifier, one lead summary.",
        "orchestration": "parallel",
        "instructions": (
            "Answer with sourced facts only. Name contradictions between sources "
            "and say what remains unknown."
        ),
        "roles": [
            {
                "name": "Research Lead",
                "description": "Plans the question and writes the final answer.",
                "tools": ["read_file", "list_directory", "file_search", "web_search", "fetch_url"],
                "instructions": "Lead the team. Keep the final answer short and sourced.",
            },
            {
                "name": "Source Analyst",
                "description": "Collects primary sources and numbers.",
                "tools": ["web_search", "fetch_url", "read_file"],
                "instructions": "Prefer primary sources and quote exact numbers.",
            },
            {
                "name": "Claim Verifier",
                "description": "Checks claims against the collected evidence.",
                "tools": ["web_search", "fetch_url", "read_file"],
                "instructions": "Mark each claim supported, contradicted or unproven.",
            },
        ],
    },
    "code-review": {
        "name": "Code review team",
        "description": "Correctness, security and test coverage in one pass.",
        "orchestration": "review",
        "instructions": (
            "Review the named change only. Every finding names file, line, impact "
            "and the smallest fix."
        ),
        "roles": [
            {
                "name": "Review Lead",
                "description": "Merges member findings and ranks them.",
                "tools": ["read_file", "list_directory", "file_search"],
                "instructions": "Merge findings without duplicates; rank by impact.",
            },
            {
                "name": "Security Reviewer",
                "description": "Looks for credential, path and injection defects.",
                "tools": ["read_file", "file_search", "web_search"],
                "instructions": "Report only defects you can point at in the code.",
            },
            {
                "name": "Test Reviewer",
                "description": "Checks what the tests do and do not prove.",
                "tools": ["read_file", "list_directory", "file_search"],
                "instructions": "Name the untested branch and the missing assertion.",
            },
        ],
    },
    "release": {
        "name": "Release team",
        "description": "Version, changelog and artifact checks before a tag.",
        "orchestration": "sequential",
        "instructions": "A release passes only when every check names the artifact it saw.",
        "roles": [
            {
                "name": "Release Lead",
                "description": "Runs the release checklist and writes the verdict.",
                "tools": ["read_file", "file_search"],
                "instructions": "List each check as pass, fail or not run.",
            },
            {
                "name": "Version Checker",
                "description": "Checks version pins across the tree.",
                "tools": ["read_file", "file_search"],
                "instructions": "Report every version string that disagrees.",
            },
            {
                "name": "Changelog Checker",
                "description": "Checks the changelog against the changes.",
                "tools": ["read_file", "file_search"],
                "instructions": "Name missing entries and unreleased sections.",
            },
        ],
    },
    "product-design": {
        "name": "Product design team",
        "description": "Flow, visual and copy review of a screen.",
        "orchestration": "parallel",
        "instructions": "Judge the shipped screen, not an imagined one.",
        "roles": [
            {
                "name": "Design Lead",
                "description": "Merges the review into a decision list.",
                "tools": ["read_file", "file_search", "analyze_image"],
                "instructions": "Rank the findings and name the smallest change.",
            },
            {
                "name": "UX Reviewer",
                "description": "Checks flow, states and accessibility.",
                "tools": ["read_file", "file_search", "analyze_image"],
                "instructions": "Name the state and the user who gets stuck.",
            },
            {
                "name": "Copy Reviewer",
                "description": "Checks labels, errors and tone.",
                "tools": ["read_file", "file_search"],
                "instructions": "Quote the current string and the replacement.",
            },
        ],
    },
    "data-analysis": {
        "name": "Data analysis team",
        "description": "Numbers, checks and a written result.",
        "orchestration": "sequential",
        "instructions": "Every number names its source file and row.",
        "roles": [
            {
                "name": "Analysis Lead",
                "description": "Defines the question and writes the result.",
                "tools": ["read_file", "list_directory", "file_search"],
                "instructions": "State the method and its limits.",
            },
            {
                "name": "Data Checker",
                "description": "Checks totals, gaps and duplicates.",
                "tools": ["read_file", "file_search"],
                "instructions": "Recompute the totals and report the difference.",
            },
            {
                "name": "Report Writer",
                "description": "Turns the checked numbers into prose.",
                "tools": ["read_file"],
                "instructions": "No claim without a number or a source.",
            },
        ],
    },
    "support": {
        "name": "Support team",
        "description": "Triage, answer and escalation note.",
        "orchestration": "sequential",
        "instructions": "Answer the user's question; escalate only with a reason.",
        "roles": [
            {
                "name": "Support Lead",
                "description": "Owns the answer and the escalation decision.",
                "tools": ["read_file", "web_search", "fetch_url"],
                "instructions": "Say what is known, what is not and the next step.",
            },
            {
                "name": "Triage Analyst",
                "description": "Finds the failing surface and its history.",
                "tools": ["read_file", "file_search"],
                "instructions": "Name the surface, the version and the trigger.",
            },
            {
                "name": "Response Writer",
                "description": "Writes the user-facing reply.",
                "tools": ["read_file"],
                "instructions": "Plain language, no internal identifiers.",
            },
        ],
    },
}


def template_names() -> list[dict[str, str]]:
    return [
        {"key": key, "name": spec["name"], "description": spec["description"]}
        for key, spec in TEMPLATES.items()
    ]


def _agent_for_role(spec: dict[str, Any]) -> str:
    wanted = str(spec["name"])
    for row in agent_store.list_agents()["agents"]:
        if row["name"].casefold() == wanted.casefold() and not row.get("archived"):
            return str(row["id"])
    record = agent_store.create_agent(
        {
            "name": wanted,
            "description": spec.get("description", ""),
            "instructions": spec.get("instructions", ""),
            "tools": spec["tools"],
            "limits": {"max_turns": 8, "timeout": 180},
        }
    )
    return str(record["id"])


def from_template(key: str, name: str = "") -> dict[str, Any]:
    spec = TEMPLATES.get(key)
    if spec is None:
        raise TeamError("unknown_template", f"unknown template: {key}", 404)
    ids = [_agent_for_role(role) for role in spec["roles"]]
    return {
        "name": name or spec["name"],
        "description": spec["description"],
        "instructions": spec["instructions"],
        "leader_id": ids[0],
        "member_ids": ids[1:],
        "orchestration": spec["orchestration"],
        "shared_context": {"session": True, "workspace": True, "artifacts": False, "memory": True},
        "model_policy": "per_member",
        "budget": {"max_rounds": ROUNDS_DEFAULT, "wall_timeout": TEAM_TIMEOUT_DEFAULT_S},
        "template": key,
    }

