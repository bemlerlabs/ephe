"""
◑ Ephe – User Profile
core/profile.py

Persistent user profile. Learns preferences over time.

Storage path: ~/.ephe/memory/user_profile.json (default)
              Or any path (for tests)
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_PATH = Path.home() / ".ephe" / "memory" / "user_profile.json"


@dataclass
class UserProfile:
    """Persistent user profile for Ephe."""

    name: str | None = None
    expertise: str | None = None
    preferred_language: str | None = None
    response_style: str | None = None       # e.g. "short and direct", "detailed"
    topics_of_interest: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    dislikes: list[str] = field(default_factory=list)

    def to_context_string(self) -> str:
        """
        Returns the profile as a system-prompt context string.
        Inserted as extra context before every answer.
        """
        parts: list[str] = ["[User Profile]"]

        if self.name:
            parts.append(f"Name: {self.name}")
        if self.expertise:
            parts.append(f"Expertise: {self.expertise}")
        if self.preferred_language:
            # Language mirrors the INPUT, not a hard profile lock. The profile's
            # preferred_language is only a FALLBACK for ambiguous/short input —
            # never an override that forces German onto an English question.
            parts.append(
                f"Language: ALWAYS reply in the SAME language the user writes in "
                f"(English question -> English answer, German question -> German answer). "
                f"Use {self.preferred_language} ONLY as a fallback when the input language "
                f"is ambiguous or too short to detect."
            )
        if self.response_style:
            parts.append(f"Response style: {self.response_style}")
        if self.topics_of_interest:
            parts.append(f"Topics of interest: {', '.join(self.topics_of_interest)}")
        if self.projects:
            parts.append(f"Current projects: {', '.join(self.projects)}")
        if self.dislikes:
            parts.append(f"Please avoid: {', '.join(self.dislikes)}")

        if len(parts) == 1:
            return ""  # only the header, no content -> return empty

        return "\n".join(parts)

    def is_empty(self) -> bool:
        """True when no field is set."""
        return (
            self.name is None
            and self.expertise is None
            and self.preferred_language is None
            and self.response_style is None
            and not self.topics_of_interest
            and not self.projects
            and not self.dislikes
        )


# IO Functions

def load_profile(path: Path | None = None) -> UserProfile:
    """
    Loads the user profile from a JSON file.

    Returns a default UserProfile when:
      - the file is missing
      - the JSON is corrupt
      - the format is wrong
    """
    profile_path = Path(path or DEFAULT_PROFILE_PATH)

    if not profile_path.exists():
        return UserProfile()

    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            logger.warning("Profile file has an invalid format, using the default.")
            return UserProfile()

        return UserProfile(
            name=data.get("name"),
            expertise=data.get("expertise"),
            preferred_language=data.get("preferred_language"),
            response_style=data.get("response_style"),
            topics_of_interest=data.get("topics_of_interest", []),
            projects=data.get("projects", []),
            dislikes=data.get("dislikes", []),
        )
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Profile could not be read: %s. Using the default.", exc)
        return UserProfile()


def save_profile(profile: UserProfile, path: Path | None = None) -> None:
    """
    Stores the user profile as a JSON file.
    Creates missing directories automatically.
    """
    profile_path = Path(path or DEFAULT_PROFILE_PATH)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        json.dumps(asdict(profile), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def update_profile(updates: dict[str, Any], path: Path | None = None) -> UserProfile:
    """
    Updates individual fields of the user profile.
    Loads, updates, stores.

    Returns:
        The updated UserProfile
    """
    profile = load_profile(path=path)

    for key, value in updates.items():
        if hasattr(profile, key):
            setattr(profile, key, value)

    save_profile(profile, path=path)
    return profile
