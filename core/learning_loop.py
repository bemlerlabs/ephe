"""Ephe — learning loop (R31).

The Referenz-A-style loop: notice learnable patterns in real conversations and  # language-gate: ignore (Referenz-A is the repo's name for the anonymised reference client, used verbatim even in the English locale — app/src/locales/en.json:747)
offer to turn them into skills — but never install anything without a
quality gate and the user's explicit acceptance.

Pipeline:
    conversation → detect_patterns() → ProposalStore (pending)
                 → user accepts → build_skill() (structural gate inside)
                 → installed skill

Detection is deliberately regex/heuristic (zero model calls, runs per turn
for free). Matching covers DE and EN user phrasing because users write in
their own language; all code, keys and stored keys stay English.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_PROPOSALS = 20
MIN_REQUEST_LEN = 24  # "ja" repeated is not a workflow worth a skill
MIN_REPEAT_COUNT = 3

# Correction / standing-instruction phrasing (DE + EN) — these mark a moment
# where the user had to steer the agent: the highest-value learning signal.
_CORRECTION_RE = re.compile(
    r"^(nein[ ,!]|stattdessen|non? [ ,]|immer |immerhin|denk dran|merk dir|"
    r"ab jetzt|von nun an|always |remember( to)? ?[: ]|instead[: ,]|no[,! ])",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower()).strip(" .!?:,;")


def detect_patterns(messages: list[dict]) -> list[dict]:
    """Learning candidates from a message list, in the order the messages arrived."""
    users = [str(m.get("content") or "") for m in messages if m.get("role") == "user"]
    candidates: list[dict] = []

    # 1) repeated near-identical requests = a recurring workflow
    groups: dict[str, int] = {}
    sample: dict[str, str] = {}
    for text in users:
        if len(text) < MIN_REQUEST_LEN:
            continue
        key = _normalize(text)
        if not key:
            continue
        groups[key] = groups.get(key, 0) + 1
        sample.setdefault(key, text)
    for key, count in groups.items():
        if count >= MIN_REPEAT_COUNT:
            candidates.append({
                "kind": "repeated_request",
                "topic": sample[key][:120],
                "evidence": sample[key][:400],
                "count": count,
            })

    # 2) corrections / standing instructions the user had to give
    for text in users:
        stripped = (text or "").strip()
        if len(stripped) < MIN_REQUEST_LEN:
            continue
        if _CORRECTION_RE.match(stripped):
            candidates.append({
                "kind": "correction",
                "topic": stripped[:120],
                "evidence": stripped[:400],
                "count": 1,
            })

    return candidates


def _learning_dir() -> Path:
    """Storage resolved LAZILY from env so tests can redirect after import."""
    return Path(os.environ.get("EPHE_LEARNING_DIR", str(Path.home() / ".ephe" / "learning")))


class ProposalStore:
    """Pending learning proposals, JSON-persisted, deduped, capped."""

    def _file(self) -> Path:
        return _learning_dir() / "proposals.json"

    def _load(self) -> list[dict]:
        try:
            data = json.loads(self._file().read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []

    def _save(self, items: list[dict]) -> None:
        path = self._file()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def add(self, candidate: dict, session_id: str = "") -> str | None:
        """Queue a candidate; None when deduped (same normalized topic pending)."""
        items = self._load()
        topic_key = _normalize(str(candidate.get("topic") or ""))
        if not topic_key:
            return None
        if any(_normalize(str(i.get("topic") or "")) == topic_key for i in items if i.get("status") == "pending"):
            return None
        pid = hashlib.sha256(f"{topic_key}:{time.time()}".encode()).hexdigest()[:12]
        items.append({
            "id": pid,
            "status": "pending",
            "session_id": session_id,
            "created_at": time.time(),
            **candidate,
        })
        # cap: keep newest MAX_PROPOSALS pending; dismissed history pruned hard
        pending = [i for i in items if i.get("status") == "pending"]
        if len(pending) > MAX_PROPOSALS:
            keep = {i["id"] for i in pending[-MAX_PROPOSALS:]}
            items = [i for i in items if i.get("status") != "pending" or i["id"] in keep]
        self._save(items)
        return pid

    def pending(self) -> list[dict]:
        return [i for i in self._load() if i.get("status") == "pending"]

    def get(self, pid: str) -> dict | None:
        for item in self._load():
            if item.get("id") == pid:
                return item
        return None

    def _set_status(self, pid: str, status: str) -> bool:
        items = self._load()
        for item in items:
            if item.get("id") == pid:
                item["status"] = status
                self._save(items)
                return True
        return False

    def dismiss(self, pid: str) -> bool:
        return self._set_status(pid, "dismissed")

    def accept(self, pid: str) -> bool:
        return self._set_status(pid, "accepted")


def record_turn_and_detect(session_id: str, messages: list[dict]) -> int:
    """Run detection for one finished turn; queue new proposals.

    Throttled per session: while a session still has a pending proposal, no
    further ones are queued (no notification spam). Returns the number of
    proposals created.
    """
    try:
        store = ProposalStore()
        if any(i.get("session_id") == session_id for i in store.pending()):
            return 0
        created = 0
        for cand in detect_patterns(messages[-24:]):
            if store.add(cand, session_id=session_id):
                created += 1
        if created:
            logger.info("learning loop: %s proposal(s) queued for session %s", created, session_id)
        return created
    except Exception as exc:  # never break a chat turn over learning bookkeeping
        logger.warning("learning loop detection failed: %s", exc)
        return 0
