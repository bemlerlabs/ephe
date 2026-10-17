"""Refusals that carry a reason code, so a surface can answer in the reader's language.

The class this file exists for (measured by driving the running product, 2026-10-11): a route
raises `HTTPException` with a German sentence, FastAPI wraps it as `{"detail": "…"}`, and
`app/src/lib/api/http.ts` puts that string in front of a reader who asked for an English
interface. Rewriting the sentences would take the German reader's text along — the mistake
already paid for once with 23 receipt lines that went English with no key. So the sentence
stays and a code travels beside it, in the envelope `http.ts` already prefers over `detail`
(`server/main.py:243` ships that shape for an unknown `/v1` route, and the codes follow the
`reason_code` convention `tool_done` adopted in f5d88653).

`REASONS` is the registry: one entry per code, holding the sentence exactly as the route
wrote it before this file existed. A test pins that every entry renders to that sentence and
that both locale bundles carry a key for it, which is what keeps a code from becoming the
next key with no reader.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

#: code -> (status, template with `{param}` slots). English here on purpose: the sentence a
#: reader sees is the one their bundle holds under `serverError.<code>`, and a fallback that
#: arrived in another language is the leak this registry closes.
REASONS: dict[str, tuple[int, str]] = {
    "audio_empty": (
        422,
        "Empty audio file — record the message again or attach a file that carries audio.",
    ),
    "audio_model_download_required": (
        409,
        "Transcription needs the local speech model '{model}' (~{size_mb} MB from {host}) "
        "and it is not on this machine yet — set EPHE_STT_DOWNLOAD=1 (with EPHE_OFFLINE "
        "unset), or set stt_allow_download in voice.json, then send the recording again.",
    ),
    "audio_model_fetch_failed": (
        503,
        "The speech model '{model}' (~{size_mb} MB from {host}) could not be fetched "
        "— check the connection, then send the recording again.",
    ),
    "tts_failed": (
        500,
        "Speech synthesis failed: {error}. Try again; if it stays, check the audio engine "
        "under Settings - Audio.",
    ),
    "proxy_port_out_of_range": (
        400,
        "port {port} is outside the preview range {min_port}..{max_port} — pick a port in "
        "that range (privileged services sit below it).",
    ),
    "proxy_port_is_service": (
        400,
        "port {port} is {service}, not a dev server — allow it for the preview explicitly "
        "with {env}={port}",
    ),
    "vision_failed": (
        500,
        "Image analysis failed: {error}. Try again; if it stays, check the active engine "
        "under Settings - Engine.",
    ),
    "settings_register_unwritable": (
        500,
        "settings.json could not be written — check that the file is writable, then save "
        "again.",
    ),
    "audit_log_unreadable": (
        500,
        "The audit log exists but cannot be read — check the file's permissions, then reload "
        "the view.",
    ),
    # The workspaces routes (2026-10-14): an unknown id, an argument a `core` module turned
    # down, a state that cannot carry the operation, a bound already reached. Where the route
    # worded the sentence it is the template; where the words came from the module that refused
    # (`str(exc)`, the reached bound) the module's text rides in the `reason` slot and the
    # template frames it — the module reports what happened, this layer adds the move the reader
    # still has. A sentence that stopped at the reason is the half-answer
    # `tests/test_refusal_messages_actionable.py` refuses, in every family.
    "workspace_id_required": (
        422,
        "a workspace_id is required — pass your project folder from Settings - Engine",
    ),
    "workspace_unknown": (
        404,
        "workspace '{workspace}' is neither a register id nor a directory "
        "— pick your folder in Settings - Engine",
    ),
    "workspace_not_live": (
        404,
        "workspace '{workspace}' is not live — pick a live tree on the Workspaces page",
    ),
    "change_set_unknown": (
        404,
        "change set '{change_set}' is not in the store — check it on the Workspaces page",
    ),
    "change_set_no_author": (
        422,
        "change set '{change_set}' names no author in its provenance "
        "— record it again with an author named",
    ),
    "change_set_tree_gone": (409, "{reason} — record the set again from a live tree"),
    "workspace_create_refused": (409, "{reason} — check the base branch and retry"),
    "workspace_remove_refused": (409, "{reason} — retry with force=True"),
    "change_set_build_refused": (422, "{reason} — check what it names and record it again"),
    "review_refused": (422, "{reason} — check the reviewer and the reasons, then retry"),
    "agent_limit_reached": (429, "{reason} — reduce the wave, then retry"),
    "publish_without_approval": (
        409,
        "change set '{change_set}' carries no approval from a reviewer other than its author "
        "— ask another reviewer on the Workspaces page",
    ),
    "change_set_approval_superseded": (
        409,
        "change set '{change_set}' carries an approval filed against bytes an amend replaced "
        "— record a fresh verdict on it as it now stands, then publish on that",
    ),
    "publish_tree_moved": (
        409,
        "the tree moved after this set was recorded: {paths} — record the set again and publish",
    ),
    # The loop a change set runs (2026-10-14): a set sent back is amended under its own id
    # instead of being rebuilt, a state a surface may move by hand is bounded, and the two
    # states a decision earns — approved by a verdict, published by a publish — are refused
    # here when a caller tries to write them directly. Each names the move the reader still
    # has, in the same shape the sentences above use.
    "change_set_amend_refused": (
        409,
        "{reason} — record the set again from the live tree",
    ),
    "change_set_state_refused": (
        422,
        "{reason} — check the set's stage on the Workspaces page and move it with a verdict "
        "or a publish",
    ),
    "change_set_state_reserved": (
        409,
        "change set '{change_set}' is not set to '{state}' by hand — record a verdict or "
        "publish it",
    ),
    "change_set_unpublish_refused": (
        409,
        "{reason} — check the set's stage on the Workspaces page",
    ),
    # The collision between two runs, named before it lands instead of after: the set the reader
    # holds is not the only one in those files, and whoever publishes second meets a file the
    # other one moved. `force=True` is the move for a reader who has read the other run's set and
    # still wants theirs landed.
    "publish_path_claimed": (
        409,
        "{paths} is held by {holders} — check that run on the Workspaces page, "
        "then publish with force=True to write over it",
    ),
}


class Refused(HTTPException):
    """A refusal the route already knows the reason for.

    It *is* the `HTTPException` every caller and every guard already catches, with one thing
    added: the reason code the surface translates. `detail` stays the sentence, so a test or a
    client that reads it keeps working; the handler in `server/main.py` renders the same
    envelope and puts `reason_code` and `reason_params` beside the transport code — the pair
    `tool_done` carries since f5d88653.
    """

    def __init__(self, code: str, **params: Any) -> None:
        if code not in REASONS:
            raise KeyError(f"uncoded refusal: {code}")
        self.code = code
        self.params = params
        status, template = REASONS[code]
        self.message = template.format(**params) if params else template
        super().__init__(status_code=status, detail=self.message)
