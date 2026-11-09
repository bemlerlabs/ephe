"""GET/PUT /api/creator/consent — what one session granted Creator mode, read from the gate.

Task #26: the mode asks for three permissions, and the answer has to live in one place
that both the dialog and the enforcement read. That place is `core.tools.creator_guard`;
this route shows its state and stores its new state, so a surface cannot keep a copy of
the consent that drifts from the gate keeping it.

The vocabulary comes back with the answer because the dialog is built from it: a client
that carried its own list of tickable permissions would be a second authority, and the
one defect this route exists to prevent is a dialog that says one thing while the guard
refuses another.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import audit_log, session_lifecycle
from core.tools import creator_guard

router = APIRouter(tags=["Creator"])

#: Where a stored answer came from a key this guard cannot honour.
BAD_SESSION = "this session id cannot name a session in the store"


class ConsentEdit(BaseModel):
    session_id: str
    privileges: list[str]


def _answer(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "privileges": sorted(creator_guard.PRIVILEGES),
        "held": sorted(creator_guard.privileges_for(session_id)),
        "mode": creator_guard.CREATOR_MODE,
    }


@router.get("/creator/consent")
def read_consent(session_id: str) -> dict:
    """What the session holds, beside every permission the dialog may state.

    A key that cannot name a session is the refusal the write already answers with, so a
    dialog cannot be built on a state the guard will not record. An empty key stays the
    app's own spelling of "no session was named", which is what the tool loop reads when
    it decides to hold nothing.
    """
    if session_id and not session_lifecycle.known_id(session_id):
        raise HTTPException(status_code=422, detail=BAD_SESSION)
    return _answer(session_id)


@router.put("/creator/consent")
def write_consent(body: ConsentEdit) -> dict:
    """Replace the permissions one session grants Creator mode, and say what moved.

    The whole set is stated on every save, which is what makes un-ticking a permission
    expressible; an additive route could only ever widen the grant.
    """
    before = creator_guard.privileges_for(body.session_id)
    try:
        after = creator_guard.set_privileges(body.session_id, body.privileges)
    except creator_guard.UnknownPrivilege as exc:
        wanted = {str(value) for value in body.privileges}
        raise HTTPException(
            status_code=422,
            detail={
                "unknown": sorted(wanted - creator_guard.PRIVILEGES),
                "privileges": sorted(creator_guard.PRIVILEGES),
                "reason": str(exc),
            },
        ) from exc
    except creator_guard.UnknownSession as exc:
        raise HTTPException(status_code=422, detail=BAD_SESSION) from exc
    # Read through the module, so a test that seams `core.audit_log.audit_event` sees the
    # row this write produces; a name bound at import time would keep the old function.
    audit_log.audit_event(
        "security",
        tool="creator_consent",
        decision="user",
        status="creator-consent",
        detail=(
            f"session={body.session_id} "
            f"granted={','.join(sorted(after - before))} "
            f"revoked={','.join(sorted(before - after))} "
            f"held={','.join(sorted(after))}"
        ),
    )
    return _answer(body.session_id)
