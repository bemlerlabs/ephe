"""server/routes/profile.py – GET /api/profile + PUT /api/profile"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.profile import UserProfile, load_profile, save_profile

router = APIRouter(tags=["Profile"])


def _profile_path() -> Path | None:
    """Return the configured profile path (ENV value, or None → the default)."""
    p = os.environ.get("EPHE_PROFILE_PATH")
    return Path(p) if p else None


# Pydantic Models

class ProfileResponse(BaseModel):
    name: str | None
    expertise: str | None
    preferred_language: str | None
    response_style: str | None
    topics_of_interest: list[str]
    projects: list[str]
    dislikes: list[str]


class ProfileUpdateRequest(BaseModel):
    name: str | None = None
    expertise: str | None = None
    preferred_language: str | None = None
    response_style: str | None = None
    topics_of_interest: list[str] | None = None
    projects: list[str] | None = None
    dislikes: list[str] | None = None


# Routes

@router.get("/profile", response_model=ProfileResponse)
async def get_profile() -> ProfileResponse:
    """The stored profile, read through load_profile() on every request."""
    profile = load_profile(path=_profile_path())
    return ProfileResponse(
        name=profile.name,
        expertise=profile.expertise,
        preferred_language=profile.preferred_language,
        response_style=profile.response_style,
        topics_of_interest=profile.topics_of_interest,
        projects=profile.projects,
        dislikes=profile.dislikes,
    )


@router.put("/profile", response_model=ProfileResponse)
async def update_profile(request: ProfileUpdateRequest) -> ProfileResponse:
    """
    Update individual fields of the user profile.
    Only fields that carry a value overwrite the stored ones.
    """
    path = _profile_path()
    profile = load_profile(path=path)

    # update only the fields that were set explicitly
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    for key, value in updates.items():
        if hasattr(profile, key):
            setattr(profile, key, value)

    save_profile(profile, path=path)

    return ProfileResponse(
        name=profile.name,
        expertise=profile.expertise,
        preferred_language=profile.preferred_language,
        response_style=profile.response_style,
        topics_of_interest=profile.topics_of_interest,
        projects=profile.projects,
        dislikes=profile.dislikes,
    )


# R30: USER.md — portable profile document

_USERMD_HEADER = "# USER.md"
_FIELD_KEYS = {
    "name": "name",
    "expertise": "expertise",
    "preferred language": "preferred_language",
    "response style": "response_style",
    "topics of interest": "topics_of_interest",
    "projects": "projects",
    "dislikes": "dislikes",
}


def _profile_to_markdown(profile: UserProfile) -> str:
    lines = [_USERMD_HEADER, ""]
    def emit(label: str, value) -> None:
        if isinstance(value, list):
            if value:
                lines.append(f"- {label}: {', '.join(str(v) for v in value)}")
        elif value:
            lines.append(f"- {label}: {value}")

    emit("Name", profile.name)
    emit("Expertise", profile.expertise)
    emit("Preferred language", profile.preferred_language)
    emit("Response style", profile.response_style)
    emit("Topics of interest", profile.topics_of_interest)
    emit("Projects", profile.projects)
    emit("Dislikes", profile.dislikes)
    return "\n".join(lines).rstrip() + "\n"


@router.get("/profile/export")
async def export_profile() -> dict:
    """The user profile as a portable USER.md document (memory-pack style)."""
    profile = load_profile(path=_profile_path())
    return {"markdown": _profile_to_markdown(profile), "filename": "USER.md"}


class ProfileImportRequest(BaseModel):
    markdown: str


@router.put("/profile/import")
async def import_profile(request: ProfileImportRequest) -> ProfileResponse:
    """Parse a USER.md back into the profile (strict: header required)."""
    md = request.markdown or ""
    first = md.strip().splitlines()[0] if md.strip() else ""
    if first.strip() != _USERMD_HEADER:
        raise HTTPException(status_code=422, detail="not a USER.md document (must start with '# USER.md')")

    path = _profile_path()
    profile = load_profile(path=path)
    got_any = False
    for line in md.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        label, sep, value = stripped[2:].partition(":")
        if not sep:
            continue
        key = _FIELD_KEYS.get(label.strip().lower())
        if key is None:
            continue
        value = value.strip()
        if key in ("topics_of_interest", "projects", "dislikes"):
            items = [v.strip() for v in value.split(",") if v.strip()]
            setattr(profile, key, items)
        else:
            setattr(profile, key, value)
        got_any = True
    if not got_any:
        raise HTTPException(status_code=422, detail="no recognizable fields in USER.md")

    save_profile(profile, path=path)
    return ProfileResponse(
        name=profile.name,
        expertise=profile.expertise,
        preferred_language=profile.preferred_language,
        response_style=profile.response_style,
        topics_of_interest=profile.topics_of_interest,
        projects=profile.projects,
        dislikes=profile.dislikes,
    )
