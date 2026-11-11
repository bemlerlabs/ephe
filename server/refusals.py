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

from core.dynamic_refusals import (
    PLUGIN_STATE_FULL,
    PLUGIN_ENTRY_REFUSED,
    PLUGIN_WORKER_RESTART_EXHAUSTED,
    SANDBOX_UNAVAILABLE,
    TOOL_NOT_AVAILABLE,
)

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
    # The engine boundary (QA 2026-11-10, F5): a turn that never got an answer used to
    # leave the stream with the raw client line ("All connection attempts failed") and
    # the synchronous twin with a 500 `internal_error`. The code lives in the registry
    # the routes already answer with, so the reason and the move are written once:
    # `core.provider_errors` decides which of the two it was, the sentence says what to
    # do. `{endpoint}` is the address the turn dialled — never a guess, and never a
    # provider's own wording (that rides in `reason_params.detail` beside it).
    "engine_unreachable": (
        502,
        "no engine answered at {endpoint} — start it or check the address under "
        "Settings - Engine, then run `ephe doctor`",
    ),
    "engine_server_error": (
        502,
        "the engine answered with an error (HTTP {status}) — send the turn again, and if "
        "it stays, check the engine under Settings - Engine",
    ),
    # The same boundary, before any turn can run: the choice exists but cannot be used
    # (a provider named, its model missing). Setup mode already answers this door with
    # a coded 409; the half-written env used to answer 500 instead. `{reason}` is the
    # resolver's own sentence — it names the variable — and rides in `reason_params`.
    "engine_unconfigured": (
        409,
        "the engine choice is incomplete — pick an engine under Settings - Engine, or "
        "run `ephe configure`, then send the message again",
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
    # J2: the four-eyes rule. The author of a change set may not be its signer, and the
    # route says so with a code instead of a sentence only a German reader can parse.
    "self_sign_forbidden": (
        422,
        "An author cannot sign its own change set. Route it to an independent reviewer.",
    ),
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
    # The plugin surface route (2026-11-04, #42): a plugin document and the files
    # beside it arrive from an iframe, which can carry no header, so each of the
    # three ways that mount fails has to answer with a reason the reader's bundle can
    # put in their language. The `{reason}` slot is the route's own refusal text,
    # framed by the move the surface still has.
    "plugin_ui_unavailable": (
        404,
        "plugin '{plugin}' has no surface to serve here — {reason} — check the "
        "plugin on the Extensions page, then reopen the surface",
    ),
    "plugin_ui_unauthorized": (
        401,
        "the plugin surface for '{plugin}' lost its mount credential — request a "
        "fresh surface token and reload the surface",
    ),
    "plugin_ui_asset_refused": (
        400,
        "the plugin surface for '{plugin}' asked for a file this route does not "
        "serve — {reason} — reload the surface so its assets arrive by relative path",
    ),
    # The dynamic-tool rail (#10, 2026-11-05): the confined worker's four refusals. The
    # identifiers are `core.dynamic_refusals`' and ride in as keys, so the audit's
    # `decision`, a tool card's `reason_code` and this envelope are one string and not
    # three spellings of it — which is the whole point of a code. `{reason}` carries the
    # emitter's own sentence (the restart count, the entry that would not resolve) and
    # this layer adds the move still left, as the workspaces family above does. Nothing
    # here quotes a host path: a confinement refusal names the missing boundary, never a
    # directory, and a route that had one would be handing a machine layout to a browser.
    TOOL_NOT_AVAILABLE: (
        409,
        "the tool plugin '{plugin}' contributes over the {transport} transport is not "
        "available right now — check that plugin on the Extensions page, then call the "
        "tool again",
    ),
    SANDBOX_UNAVAILABLE: (
        503,
        "plugin '{plugin}' was not started: this machine offers no OS boundary to "
        "confine a plugin worker in, and a plugin tool runs nowhere else — check the "
        "confinement of the backend host, then run the tool again",
    ),
    PLUGIN_WORKER_RESTART_EXHAUSTED: (
        429,
        "{reason} — check that worker's exit status in the audit view, then start a new turn",
    ),
    PLUGIN_ENTRY_REFUSED: (
        422,
        "plugin '{plugin}' names a tool entry this build will not open: {reason} — "
        "correct the entry in the plugin manifest, then mount the plugin again",
    ),
    # #24 / #106: the ceiling on what a bundle may keep. The two numbers are what it
    # holds and what it may hold. The move is the Extensions row, which lists the
    # stored files and removes the one the reader picks. No directory is named.
    PLUGIN_STATE_FULL: (
        507,
        "plugin '{plugin}' is refused: its stored data holds {used_mb} MB of the {cap_mb} "
        "MB this bundle may keep — open this bundle on Extensions and remove a stored "
        "file there, then run the tool again",
    ),
    # A name the state folder does not hold. The sentence names no path.
    # The move is the file list on Extensions.
    "plugin_state_name": (
        400,
        "that stored file is not in this bundle — open this bundle on Extensions "
        "and pick a file the list shows",
    ),
    # A bundle name this install does not address. The move is the Extensions list.
    "plugin_unknown": (
        404,
        "no bundle by that name is installed — open Extensions and pick a bundle "
        "the list shows",
    ),
    # A field whose shape this route refuses. The move is to check it and send again.
    "tool_failed": (
        500,
        "the tool stopped with an error this page cannot show — the reason is in the run's "
        "log; try it again, and if it stays, check the tool under Extensions",
    ),
    "invalid_request": (
        400,
        "this request is not a shape the route takes — check the field the answer "
        "names and send it again",
    ),
    # The watch channel (#88): a name from the URL is not a reason to start a browser,
    # and an engine that will not cast still runs the task.
    "browser_session_unknown": (
        404,
        "no browser session '{session}' is open to watch — run the step that opens one, "
        "then open the view again; watching never starts a browser by itself",
    ),
    "browser_watch_unavailable": (
        409,
        "this browser session cannot send its frames right now: {reason} — the task keeps "
        "running and every step lands in the audit view, so check the engine under "
        "Settings - Browser and reopen the view",
    ),
    # The device clear (`POST /api/device/forget`): the declaration decides what may go,
    # so a request naming an entry it does not carry, or one it marks kept, is turned
    # down whole before anything is unlinked.
    "device_forget_undeclared": (
        400,
        "{names} is named by no row of the device declaration — check the listing "
        "under Settings - Privacy and run the clear on entries it does name",
    ),
    "device_forget_kept": (
        409,
        "{names} stands under the device declaration's keep — check the listing "
        "under Settings - Privacy and clear only what it marks forgettable",
    ),
    # The file route (#80): one guard decides whether a path may be read, and every
    # refusal it hands back rides the coded envelope so the surface can translate it.
    # #120 narrowed what that guard reads to the workspace and its output folder, so
    # the sentence names those two and nothing wider.
    "file_path_not_allowed": (
        403,
        "path is outside the workspace and its output folder — pick a file from "
        "one of those two",
    ),
    "file_path_protected": (
        403,
        "path is protected (credential or system file) — this route cannot read it; "
        "choose another file",
    ),
    "file_not_found": (
        404,
        "file not found — check the path or whether the file still exists",
    ),
    "file_too_large": (
        413,
        "file is larger than the preview limit ({max_mb} MB) — open it directly instead",
    ),
    "sandbox_start_refused": (
        502,
        "plugin '{plugin}' was not started: the OS boundary refused its worker "
        "({reason}) — check the backend host, then run the tool again.",
    ),
}


#: The move a coded refusal leaves, keyed by the same code. A surface shows the sentence
#: above; this line says what to do next, and the envelope carries it beside the code. The
#: plugin family is filled here because those are the refusals a bundle author meets while
#: building and installing; other families add their entry when their route learns a move.
NEXT_STEPS: dict[str, str] = {
    "invalid_request": "Check the field the answer names and send it again.",
    "tool_failed": "Open the run's log for the reason, then try the tool again.",
    "plugin_unknown": "Run `ephe plugin list` and open the bundle the list shows.",
    "plugin_state_name": "Open this bundle on Extensions and pick a file the list shows.",
    "plugin_state_full": "Open this bundle on Extensions and remove a stored file there.",
    "plugin_ui_unavailable": (
        "Check the plugin on Extensions, switch it on, then reopen the surface."
    ),
    "plugin_ui_unauthorized": "Reload the surface so it requests a fresh mount token.",
    "plugin_ui_asset_refused": (
        "Reload the surface so its assets arrive by relative path."
    ),
    "plugin_entry_refused": (
        "Correct the entry in the plugin manifest, then mount the plugin again."
    ),
    "tool_not_available": "Check that plugin on Extensions, then call the tool again.",
    "sandbox_unavailable": (
        "Check the confinement of the backend host, then run the tool again."
    ),
    "sandbox_start_refused": (
        502,
        "Check that the backend host lets the plugin worker start, then run the tool again."
    ),
    "plugin_lifecycle_read_only": (
        "Turn plugins.plugin_lifecycle_read_only off, then retry the switch."
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

    @property
    def next(self) -> str:
        """The move this refusal leaves, or "" when its family has no sentence yet."""
        return NEXT_STEPS.get(self.code, "")
