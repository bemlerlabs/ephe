"""server/routes/git_info.py – GET /api/git/info (header chips: workspace + branch).

AI client parity: the topbar shows the workspace name and the active git branch
(+ dirty count). Purely read-only, fixed git arguments (no user input), cwd is the
validated workspace_dir from core.engine_config. No new exec freedom: git runs
with an argument list (no shell) and DEVNULL-stderr; a failing git call =
git:False, not an error.
"""
from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.engine_config import get_workspace_dir, workspace_is_explicit

router = APIRouter(tags=["Git"])

_TIMEOUT = 5.0


def _explicit_workspace() -> str | None:
    """The workspace a user chose; None for the neutral default.

    Git surfaces are about the user's project. A server started in the source
    checkout must not turn that checkout's branches and dirty count into the
    product's default header.
    """
    if not workspace_is_explicit():
        return None
    return get_workspace_dir()


class GitInfoResponse(BaseModel):
    workspace: str
    git: bool = False
    branch: str = ""
    dirty: int = 0


async def _git_raw(cwd: str, *args: str) -> tuple[int, str]:
    """Runs git; returns (returncode, stdout). No shell, DEVNULL-stderr."""
    proc = await asyncio.create_subprocess_exec(
        "git", *args, cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, ""
    text = out.decode("utf-8", errors="replace")
    if proc.returncode != 0 and err:
        text = err.decode("utf-8", errors="replace").strip()
    return proc.returncode, text.strip()


async def _git(cwd: str, *args: str) -> str:
    rc, out = await _git_raw(cwd, *args)
    return out if rc == 0 else ""


@router.get("/git/info", response_model=GitInfoResponse)
async def git_info() -> GitInfoResponse:
    wd = _explicit_workspace()
    if wd is None:
        return GitInfoResponse(workspace="")
    workspace = Path(wd).name or wd
    if not Path(wd).is_dir():
        return GitInfoResponse(workspace=workspace)
    try:
        branch = await _git(wd, "rev-parse", "--abbrev-ref", "HEAD")
    except OSError:
        return GitInfoResponse(workspace=workspace)
    if not branch:
        return GitInfoResponse(workspace=workspace)
    dirty_out = await _git(wd, "status", "--porcelain")
    dirty = sum(1 for line in dirty_out.splitlines() if line.strip())
    return GitInfoResponse(workspace=workspace, git=True, branch=branch, dirty=dirty)



class BranchListResponse(BaseModel):
    workspace: str
    git: bool = False
    current: str = ""
    branches: list[str] = []


class CheckoutRequest(BaseModel):
    branch: str


class CheckoutResponse(BaseModel):
    ok: bool
    branch: str


# Only local branch names: no rev/remote magic, no whitespace, no leading -
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,120}$")


@router.get("/git/branches", response_model=BranchListResponse)
async def git_branches() -> BranchListResponse:
    """Local branches for the header chip dropdown (read-only)."""
    wd = _explicit_workspace()
    if wd is None:
        return BranchListResponse(workspace="")
    workspace = Path(wd).name or wd
    if not Path(wd).is_dir():
        return BranchListResponse(workspace=workspace)
    out = await _git(wd, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    current = await _git(wd, "rev-parse", "--abbrev-ref", "HEAD")
    return BranchListResponse(
        workspace=workspace,
        git=bool(current),
        current=current,
        branches=[b for b in out.splitlines() if b.strip()],
    )


@router.post("/git/checkout", response_model=CheckoutResponse)
async def git_checkout(req: CheckoutRequest) -> CheckoutResponse:
    """Switches the branch in the workspace. Conservative: only validated local
    branch names, no --force, no branch creation, argument list (no shell)."""
    branch = (req.branch or "").strip()
    if not _BRANCH_RE.fullmatch(branch):
        raise HTTPException(status_code=400, detail="invalid branch name")
    wd = _explicit_workspace()
    if wd is None:
        raise HTTPException(status_code=409, detail="No workspace selected")
    if not Path(wd).is_dir():
        raise HTTPException(status_code=409, detail="Workspace directory does not exist")
    rc, out = await _git_raw(wd, "checkout", branch)
    if rc != 0:
        raise HTTPException(status_code=409, detail=out or "Checkout failed")
    return CheckoutResponse(ok=True, branch=branch)


# round G (review tab, 2026-09-07)
# GET /api/git/status  → working-tree/index changes with +N/−M stats
# GET /api/git/diff    → patch text of one file (read-only, path guard, size cap)


class GitFileChange(BaseModel):
    path: str
    status: str          # 'M' | 'A' | 'D' | '?' | 'R' | 'C' | 'T' | 'U'
    additions: int
    deletions: int


class GitStatusResponse(BaseModel):
    workspace: str
    git: bool = False
    branch: str = ""
    changes: list[GitFileChange] = []
    #: The directory the status was read in, absolute. A caller that joins these paths to
    #: its own tree needs it: the list is relative to this root, and a tree rooted
    #: elsewhere would read the same strings as different files. Empty when git could not
    #: answer, so a caller that requires it fails closed.
    root: str = ""


class GitDiffResponse(BaseModel):
    path: str
    diff: str
    binary: bool = False


_MAX_DIFF_CHARS = 200_000
_MAX_UNTRACKED_LINES = 5000


def _numstat_map(out: str) -> dict[str, tuple[str, str]]:
    """Parses 'git diff --numstat' into {path: (adds, dels)}; '-' fields = binary."""
    result: dict[str, tuple[str, str]] = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        adds, dels = parts[0].strip(), parts[1].strip()
        path = "\t".join(parts[2:]).split(" -> ")[-1].strip().strip('"')
        if path:
            result[path] = (adds, dels)
    return result


def _status_changes(porcelain: str, nums: dict[str, tuple[str, str]], staged: bool, wd: str) -> list[GitFileChange]:
    changes: list[GitFileChange] = []
    for line in porcelain.splitlines():
        if len(line) < 4:
            continue
        xy, path = line[:2], line[3:].split(" -> ")[-1].strip().strip('"')
        if not path:
            continue
        if xy == "??":
            if staged:
                continue
            try:
                handle = Path(wd, path).open("r", encoding="utf-8", errors="replace")
                with handle as stream:
                    adds = min(sum(1 for _ in stream), _MAX_UNTRACKED_LINES)
            except OSError:
                adds = 0
            changes.append(GitFileChange(path=path, status="?", additions=adds, deletions=0))
            continue
        code = (xy[0] if staged else xy[1]).strip() or (xy[0].strip() or "M")
        if code not in {"M", "A", "D", "R", "C", "T", "U"}:
            code = "M"
        if staged and xy[0] == " ":
            continue
        if not staged and xy[1] == " " and xy != "??":
            continue
        adds_raw, dels_raw = nums.get(path, ("0", "0"))
        changes.append(GitFileChange(
            path=path,
            status=code,
            additions=int(adds_raw) if adds_raw.isdigit() else 0,
            deletions=int(dels_raw) if dels_raw.isdigit() else 0,
        ))
    return changes


@router.get("/git/status", response_model=GitStatusResponse)
async def git_status(staged: bool = False) -> GitStatusResponse:
    """Change list for the review tab. Read-only, fixed git arguments."""
    wd = _explicit_workspace()
    if wd is None:
        return GitStatusResponse(workspace="")
    workspace = Path(wd).name or wd
    if not Path(wd).is_dir():
        return GitStatusResponse(workspace=workspace)
    branch = await _git(wd, "rev-parse", "--abbrev-ref", "HEAD")
    if not branch:
        return GitStatusResponse(workspace=workspace)
    # Porcelain must NOT run through _git/_git_raw: both strip() the result and
    # would remove the leading space of the XY column (' M pfad') — but that column
    # value ' ' vs 'M' is exactly the signal for unstaged/staged. Hence an own call
    # without trimming.
    proc = await asyncio.create_subprocess_exec(
        "git", "status", "--porcelain", cwd=wd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        out, _err = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        out = b""
    porcelain = out.decode("utf-8", errors="replace") if proc.returncode == 0 else ""
    if staged:
        num_out = await _git(wd, "diff", "--numstat", "--cached")
    else:
        num_out = await _git(wd, "diff", "--numstat")
    changes = _status_changes(porcelain, _numstat_map(num_out), staged, wd)
    return GitStatusResponse(
        workspace=workspace,
        git=True,
        branch=branch,
        changes=changes,
        root=str(Path(wd).resolve()),
    )


def _safe_relpath(wd: str, raw: str) -> str | None:
    """Allows only relative workspace paths: no absolute, no '..', no
    option injection (leading '-'), no NUL. No git access when rejected."""
    if not raw or raw.startswith("-") or raw.startswith("/") or "\\" in raw or "\x00" in raw:
        return None
    if any(part == ".." for part in raw.split("/")):
        return None
    # The real path of the file plus its separator, then the prefix check against the
    # real path of the workspace: that is the containment, and what makes the returned
    # name safe to hand to git (py/path-injection).
    try:
        # Path(wd).resolve() is the workspace root this route reports everywhere else;
        # the containment itself is checked on real paths, so `..` parts and symlinks
        # cannot step out (py/path-injection).
        base = Path(wd).resolve()
        probe = os.path.realpath(os.path.join(str(base), raw)) + os.sep
        if not probe.startswith(str(base) + os.sep):
            return None
    except (OSError, ValueError):
        return None
    return raw


@router.get("/git/diff", response_model=GitDiffResponse)
async def git_diff(path: str, staged: bool = False) -> GitDiffResponse:
    """Patch text of one file for the review tab. Read-only, path guard, cap."""
    wd = _explicit_workspace()
    if wd is None:
        raise HTTPException(status_code=409, detail="No workspace selected")
    if not Path(wd).is_dir():
        raise HTTPException(status_code=409, detail="workspace directory missing")
    rel = _safe_relpath(wd, path)
    if rel is None:
        raise HTTPException(status_code=400, detail="invalid path")
    head = ("--cached",) if staged else ()
    num_out = await _git(wd, "diff", "--numstat", *head, "--", rel)
    if not num_out.strip():
        raise HTTPException(status_code=404, detail="no pending change for path")
    for line in num_out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].strip() == "-" and parts[1].strip() == "-":
            return GitDiffResponse(path=rel, diff="", binary=True)
    patch = await _git(wd, "diff", *head, "--", rel)
    return GitDiffResponse(path=rel, diff=patch[:_MAX_DIFF_CHARS], binary=False)


# W3c (2026-09-09): git actions — stage + commit from the git tab


class GitAddRequest(BaseModel):
    paths: list[str] | None = None


class GitAddResponse(BaseModel):
    ok: bool
    staged: int = 0


class GitCommitRequest(BaseModel):
    message: str


class GitCommitResponse(BaseModel):
    ok: bool
    hash: str = ""
    branch: str = ""


@router.post("/git/add", response_model=GitAddResponse)
async def git_add(req: GitAddRequest) -> GitAddResponse:
    """Stages files (add with path guard) or everything (-A). Argument list, no shell."""
    wd = _explicit_workspace()
    if wd is None:
        raise HTTPException(status_code=409, detail="No workspace selected")
    if not Path(wd).is_dir():
        raise HTTPException(status_code=409, detail="workspace directory missing")
    if req.paths:
        rels: list[str] = []
        for raw in req.paths:
            rel = _safe_relpath(wd, (raw or "").strip())
            if rel is None:
                raise HTTPException(status_code=400, detail=f"invalid path: {raw!r}")
            rels.append(rel)
        rc, out = await _git_raw(wd, "add", "--", *rels)
    else:
        rc, out = await _git_raw(wd, "add", "-A")
    if rc != 0:
        raise HTTPException(status_code=409, detail=out or "git add failed")
    names = await _git(wd, "diff", "--cached", "--name-only")
    staged = sum(1 for line in names.splitlines() if line.strip())
    return GitAddResponse(ok=True, staged=staged)


@router.post("/git/commit", response_model=GitCommitResponse)
async def git_commit(req: GitCommitRequest) -> GitCommitResponse:
    """Commit with a message. 409 on empty index/small error; no shell."""
    wd = _explicit_workspace()
    if wd is None:
        raise HTTPException(status_code=409, detail="No workspace selected")
    message = (req.message or "").strip()
    if not Path(wd).is_dir():
        raise HTTPException(status_code=409, detail="workspace directory missing")
    if not message:
        raise HTTPException(status_code=400, detail="empty commit message")
    rc, out = await _git_raw(wd, "commit", "-m", message)
    if rc != 0:
        raise HTTPException(status_code=409, detail=out or "git commit failed")
    short = await _git(wd, "rev-parse", "--short", "HEAD")
    branch = await _git(wd, "rev-parse", "--abbrev-ref", "HEAD")
    return GitCommitResponse(ok=True, hash=short, branch=branch)


# W16 (2026-09-10): hunk-wise stage/apply from the interactive diff view


class GitApplyRequest(BaseModel):
    patch: str
    staged: bool = False
    reverse: bool = False


class GitApplyResponse(BaseModel):
    ok: bool
    #: P1-5: 3-way merge conflict (U1/U2 markers in stderr) as its own signal.
    conflict: bool = False


def _apply_path_guard(wd: str, patch: str) -> str | None:
    """Path guard over the file headers of the patch (--- a/x / +++ b/x).

    Allows only relative workspace paths (SSOT: _safe_relpath); the 'a/'/'b/'
    prefixes are stripped before the check. Returns: error text or None."""
    for line in patch.splitlines():
        if not (line.startswith("--- ") or line.startswith("+++ ")):
            continue
        raw = line[4:].strip()
        if raw in {"/dev/null", "dev/null"}:
            continue
        for prefix in ("a/", "b/"):
            if raw.startswith(prefix):
                raw = raw[len(prefix):]
                break
        if _safe_relpath(wd, raw) is None:
            return f"invalid path in patch header: {line[4:].strip()!r}"
    return None


@router.post("/git/apply", response_model=GitApplyResponse)
async def git_apply(req: GitApplyRequest) -> GitApplyResponse:
    """W16: apply a hunk patch (stage: --cached; discard: --reverse).

    git apply reads the patch from stdin; fixed argument list, no shell.
    400 on empty patch/path outside the workspace, 409 when applying fails."""
    wd = _explicit_workspace()
    if wd is None:
        raise HTTPException(status_code=409, detail="No workspace selected")
    if not Path(wd).is_dir():
        raise HTTPException(status_code=409, detail="workspace directory missing")
    patch = (req.patch or "").replace("\r\n", "\n")
    if not patch.strip():
        raise HTTPException(status_code=400, detail="empty patch")
    # git apply enforces the final newline — otherwise 'corrupt patch'.
    if not patch.endswith("\n"):
        patch += "\n"
    guard = _apply_path_guard(wd, patch)
    if guard is not None:
        raise HTTPException(status_code=400, detail=guard)

    # Flags: --cached stages into the index only; without --cached a plain
    # working-copy apply; --reverse turns the patch around (discard).
    # P1-5: --3way yields the conflict status (U1/U2) on the forward path. On
    # reverse apply 3-way is limited (base blob resolution against the index),
    # which is why reverse runs on the deterministic plain path.
    args: list[str] = ["apply"]
    if not req.reverse:
        args.append("--3way")
    if req.reverse:
        args.append("--reverse")
    if req.staged:
        args.append("--cached")
    proc = await asyncio.create_subprocess_exec(
        "git", *args, cwd=wd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(
            proc.communicate(input=patch.encode("utf-8")), timeout=_TIMEOUT,
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise HTTPException(status_code=409, detail="git apply timed out")
    if proc.returncode != 0:
        err_txt = err.decode("utf-8", errors="replace").strip()
        detail = (err_txt
                  or out.decode("utf-8", errors="replace").strip()
                  or "git apply failed")
        # P1-5: mark a 3-way conflict (U1/U2 index markers) explicitly.
        conflict = "U1" in err_txt or "U2" in err_txt or "U" in err_txt and "conflict" in err_txt.lower()
        raise HTTPException(status_code=409, detail=detail[:500], headers={"X-Git-Conflict": "1" if conflict else "0"})
    return GitApplyResponse(ok=True)
