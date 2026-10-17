"""Ephe – Kepta bridge: a memory provider that lives in a running Kepta instance.

D4a. Whoever already operates a Kepta (shared brain, own UI, own folder)
connects Ephe to it instead of fattening a second memory. The bridge is a
provider like the others — same contract, same D5 extras — and its counterpart
is the local `KeptaProvider` class, not the Chroma track.

Two boundaries are hard:

  * **No default, no guessing.** The instance URL comes exclusively from
    `EPHE_MEMORY_KEPTA_URL`; without it the bridge does not exist. No `localhost`,
    no silent fallback to the local brain (AGENTS.md: no hardcoded
    endpoints, no silent fallback).
  * **What does not exist there is not invented.** `clear()` has no route —
    a "clear memory" on a shared instance would be an announcement to everyone.

The transport is injectable so the tests run against the API shape of `server.ts`
and not against the network.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from core.reason import coded

logger = logging.getLogger(__name__)

ENV_KEPTA_URL = "EPHE_MEMORY_KEPTA_URL"
DEFAULT_TIMEOUT_SECONDS = 5.0

#: Fields Kepta carries in the record and that Ephe needs as metadata.
_PASSTHROUGH = ("type", "tags", "confidence", "validFrom", "validTo", "supersededBy", "deletedAt")


def bridge_url_from_env() -> str | None:
    """The explicitly set instance URL — or None. There is no default."""
    url = (os.environ.get(ENV_KEPTA_URL) or "").strip()
    return url or None


def _urllib_transport(base_url: str, timeout: float):
    """The real transport: path relative to the instance URL, JSON in, JSON out, None on 404."""

    def request(method: str, path: str, body: dict | None = None,
                params: dict | None = None) -> Any:
        url = base_url + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method)  # nosec B310 — URL from env
        if data is not None:
            req.add_header("content-type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        return json.loads(raw) if raw else None

    return request


class KeptaBridgeProvider:
    """Memory provider over the HTTP API of a running Kepta instance."""

    name = "kepta-bridge"

    def __init__(
        self,
        base_url: str | None,
        *,
        scope: str,
        transport: Callable[..., Any] | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        url = (base_url or "").strip().rstrip("/")
        if not url:
            raise coded(
                "kepta_needs_an_instance",
                RuntimeError(
                    f"The Kepta bridge needs an instance: set {ENV_KEPTA_URL} "
                    "(for example http://127.0.0.1:3000). There is no silent default endpoint."
                ),
                env=ENV_KEPTA_URL,
            )
        self._url = url
        self._scope = scope
        self._timeout = timeout_seconds
        self._transport = transport or _urllib_transport(url, timeout_seconds)

    # Transport

    def _call(self, method: str, path: str, body: dict | None = None,
              params: dict | None = None) -> Any:
        try:
            return self._transport(method, path, body, params)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise coded(
                "kepta_instance_unreachable",
                RuntimeError(
                    f"The Kepta instance is not reachable: {self._url} ({exc}). "
                    f"Check whether it runs, or point {ENV_KEPTA_URL} at the local brain."
                ),
                url=self._url,
                error=str(exc),
                env=ENV_KEPTA_URL,
            ) from exc

    # Mapping

    def _entry(self, rec: dict) -> dict[str, Any]:
        meta: dict[str, Any] = {"source": "kepta_bridge", "scope": self._scope}
        for key in _PASSTHROUGH:
            if rec.get(key) not in (None, "", [], {}):
                meta[key] = rec[key]
        if rec.get("createdAt"):
            meta["timestamp"] = rec["createdAt"]
        if rec.get("deletedAt"):
            meta["deleted_at"] = rec["deletedAt"]
        return {"id": str(rec.get("id", "")), "text": str(rec.get("content", "")), "metadata": meta}

    # Write

    def store(
        self, text: str, metadata: dict[str, Any] | None = None, *,
        memory_type: str | None = None, title: str | None = None,
        tags: list[str] | None = None, entities: list[str] | None = None,
        confidence: float | None = None, doc_id: str | None = None,
    ) -> str:
        """Creates a fact in the instance and returns that instance's ID.

        The HTTP route has no `entities` — the bridge does not invent it.
        `doc_id` (migration only) is an error here, not silent ignoring.
        """
        text = (text or "").strip()
        if not text:
            return ""
        if doc_id:
            raise coded(
                "kepta_writes_its_own_ids",
                ValueError("The Kepta bridge assigns its own ids; it takes none from outside."),
            )
        if entities:
            logger.debug("memory bridge: %d entities without a route — dropped", len(entities))
        body: dict[str, Any] = {"content": text, "scope": self._scope}
        if title:
            body["title"] = title
        if memory_type:
            body["type"] = memory_type
        if tags:
            body["tags"] = list(tags)
        if confidence is not None:
            body["confidence"] = confidence
        res = self._call("POST", "/api/memories", body) or {}
        return str((res.get("memory") or {}).get("id", ""))

    def update(self, doc_id: str, text: str,
               metadata: dict[str, Any] | None = None) -> str:
        """Overwrites the text of the same entry (patch route with `id`)."""
        text = (text or "").strip()
        if not text:
            raise coded("kepta_empty_text_is_data_loss", ValueError("Empty text would be silent data loss."))
        res = self._call("POST", "/api/memories", {"id": doc_id, "content": text})
        if not res:
            raise KeyError(f"Memory entry '{doc_id}' not found.")
        return doc_id

    def supersede(self, doc_id: str, new_text: str,
                  metadata: dict[str, Any] | None = None, **write_options: Any) -> str:
        """Correction as its own write: new leading fact, old one marked.

        The instance knows `supersededBy` per record — so two writes in this
        order: first create the correction, then have the old entry
        point at it.
        """
        old = self._get_record(doc_id)
        if old is None:
            raise KeyError(f"Memory entry '{doc_id}' not found.")
        new_id = self.store(new_text, metadata, **write_options)
        if new_id and new_id != doc_id:
            self._call("POST", "/api/memories", {"id": doc_id, "supersededBy": new_id})
        return new_id

    def delete(self, doc_id: str) -> None:
        """Puts the entry into the instance's trash (Kepta's default)."""
        res = self._call("DELETE", f"/api/memories/{urllib.parse.quote(doc_id)}") or {}
        if not res.get("ok"):
            raise KeyError(f"Memory entry '{doc_id}' not found.")

    def restore(self, doc_id: str) -> None:
        """Restores an entry from the instance's trash."""
        res = self._call("POST", f"/api/memories/{urllib.parse.quote(doc_id)}/restore")
        if not res:
            raise KeyError(f"Deleted memory entry '{doc_id}' not found.")

    def clear(self) -> None:
        raise coded(
            "kepta_clear_needs_the_instance",
            RuntimeError(
                "The Kepta bridge has no clear(): emptying a shared instance is not a local "
                "action. Clean up inside the Kepta instance itself."
            ),
        )

    # Read

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search over the engine route. The ranking comes from Kepta; the score is
        only the order that survives the sorting in the facade."""
        res = self._call("GET", "/api/memories/search", params={
            "q": query, "limit": max(1, min(int(limit), 50)),
        }) or {}
        hits = [self._entry(r) for r in res.get("memories", [])][: max(1, int(limit))]
        total = len(hits) + 1
        for i, hit in enumerate(hits):
            hit["score"] = round(max(0.35, 1.0 - i / total), 4)
        return hits

    def list_all(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._list({}, limit)

    def list_deleted(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._list({"trash": "1"}, limit)

    def _list(self, params: dict, limit: int) -> list[dict[str, Any]]:
        rows = self._call("GET", "/api/memories", params=params or None) or []
        return [self._entry(r) for r in rows][: max(1, int(limit))]

    def _get_record(self, doc_id: str) -> dict | None:
        for row in self._call("GET", "/api/memories", params=None) or []:
            if str(row.get("id")) == str(doc_id):
                return row
        return None

    def count(self) -> int:
        info = self._call("GET", "/api/storage-info") or {}
        return int(info.get("count", 0))

    def stats(self) -> dict[str, Any]:
        info = self._call("GET", "/api/storage-info") or {}
        return {
            "total": int(info.get("count", 0)),
            "deleted": int(info.get("trashed", 0)),
            "scope": self._scope,
            "provider": self.name,
            "lexical_leg": True,
            "vector_leg": bool((info.get("embeddings") or {}).get("available", True)),
        }

    def close(self) -> None:
        """No long-lived object behind urllib — nothing to close."""
        return None
