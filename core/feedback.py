"""
◑ Ephe – Feedback System (👍 / 👎)
core/feedback.py

Stores positive and negative answer examples.
Positive examples are inserted as few-shot context ahead of answers
to steer the style toward user preferences.

Storage path:
  ~/.ephe/memory/good_examples/  (👍)
  ~/.ephe/memory/bad_examples/   (👎)

Format: JSON files, one per example.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_BASE_DIR = Path.home() / ".ephe" / "memory"


@dataclass
class FeedbackExample:
    """A feedback example (prompt + response pair)."""
    prompt: str
    response: str
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class FeedbackStore:
    """
    Stores 👍/👎 feedback and serves few-shot examples.

    Usage:
        store = FeedbackStore()
        store.thumbs_up(prompt="Was ist Python?", response="Eine Programmiersprache...")  # language-gate: ignore (verbatim German sample values of the usage example — literals, not prose)
        examples = store.get_good_examples(max_items=3)
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = Path(base_dir or DEFAULT_BASE_DIR)
        self._good_dir = self._base / "good_examples"
        self._bad_dir = self._base / "bad_examples"

    # Public API

    def thumbs_up(self, prompt: str, response: str) -> bool:
        """Stores a positive example (👍). True means: the file is on disk."""
        return self._save(FeedbackExample(prompt=prompt, response=response), self._good_dir)

    def thumbs_down(self, prompt: str, response: str) -> bool:
        """Stores a negative example (👎)."""
        return self._save(FeedbackExample(prompt=prompt, response=response), self._bad_dir)

    def get_good_examples(self, max_items: int = 5) -> list[FeedbackExample]:
        """
        Returns the most recent positive examples.

        Returns:
            List of FeedbackExample objects, newest first.
        """
        return self._load_from(self._good_dir, max_items)

    def get_bad_examples(self, max_items: int = 5) -> list[FeedbackExample]:
        """Returns the most recent negative examples."""
        return self._load_from(self._bad_dir, max_items)

    def count_good(self) -> int:
        """Number of stored positive examples."""
        return self._count(self._good_dir)

    def count_bad(self) -> int:
        """Number of stored negative examples."""
        return self._count(self._bad_dir)

    def to_few_shot_string(self, max_items: int = 3) -> str:
        """
        Returns the positive examples as few-shot context for the system prompt.

        Returns:
            Formatted string holding the examples, or "" when there are none.
        """
        examples = self.get_good_examples(max_items=max_items)
        if not examples:
            return ""

        lines = ["[Examples of the preferred answer style:]"]
        for i, ex in enumerate(examples, 1):
            lines.append(f"\nBeispiel {i}:")
            lines.append(f"Frage: {ex.prompt[:200]}")
            lines.append(f"Antwort: {ex.response[:300]}")

        return "\n".join(lines)

    # Private

    def _save(self, example: FeedbackExample, directory: Path) -> bool:
        """Stores one example as a JSON file under a unique name.

        False when the disk says no. Without that answer `saved` in the API
        would be a label instead of an observation — the surface would report a
        thumb that exists nowhere.
        """
        try:
            directory.mkdir(parents=True, exist_ok=True)
            # microseconds + hash give uniqueness even in fast-running tests
            unique = hashlib.sha256(
                f"{example.timestamp}:{example.prompt}:{example.response}".encode()
            ).hexdigest()[:8]
            filename = directory / f"{int(example.timestamp * 1_000_000)}_{unique}.json"
            # Temp file + swap: an interrupted write must not leave a partial
            # ``*.json`` that ``_load_from`` skips while ``_count`` still counts
            # it — a phantom example the surface reports and never returns.
            tmp = filename.with_suffix(filename.suffix + ".tmp")
            try:
                tmp.write_text(
                    json.dumps(asdict(example), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                os.replace(tmp, filename)
            except OSError:
                with contextlib.suppress(OSError):
                    tmp.unlink()
                raise
        except OSError:
            logging.getLogger("ephe").exception("feedback example could not be stored")
            return False
        return True

    def _load_from(self, directory: Path, max_items: int) -> list[FeedbackExample]:
        """Loads examples from a directory, newest first."""
        if not directory.exists():
            return []

        files = sorted(directory.glob("*.json"), reverse=True)[:max_items]
        examples: list[FeedbackExample] = []

        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                examples.append(FeedbackExample(
                    prompt=data.get("prompt", ""),
                    response=data.get("response", ""),
                    timestamp=data.get("timestamp", 0.0),
                ))
            except Exception:
                continue  # skip a corrupt file

        return examples

    def _count(self, directory: Path) -> int:
        """Counts the JSON files in a directory."""
        if not directory.exists():
            return 0
        return len(list(directory.glob("*.json")))
