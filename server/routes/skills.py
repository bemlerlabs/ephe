"""server/routes/skills.py – CRUD plus R16 pack management (install/disable)"""
from __future__ import annotations

import io
import os
import re
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import skill_provenance, skill_signing
from core.skills import SkillLoader, SkillLoadError, BUILTIN_SKILLS_DIR, _parse_skill

router = APIRouter(tags=["Skills"])

# R16 install guards (release bar: conservative)
# An installation archive is not trusted: paths get hard validation, extensions
# are allowlisted, sizes are capped. Built-ins are never overwritable (they are
# updated in the repo only).
MAX_ARCHIVE_BYTES = 10 * 1024 * 1024        # upload/download cap
MAX_EXTRACT_TOTAL = 20 * 1024 * 1024        # total extracted size
MAX_ENTRY_BYTES = 2 * 1024 * 1024           # a single file
MAX_ENTRY_COUNT = 500                       # number of files
ALLOWED_SKILL_FILE_EXTS = {".md", ".txt", ".json", ".yaml", ".yml", ".csv"}
_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class _ArchiveRejected(Exception):
    """The archive violates one of the install guards."""


def _get_loader() -> SkillLoader:
    """Loads a SkillLoader whose user directory is configurable through ENV."""
    user_skills = os.environ.get("EPHE_SKILLS_DIR")
    return SkillLoader(
        skills_dir=Path(user_skills) if user_skills else None,
        builtin_dir=BUILTIN_SKILLS_DIR,
    )


# Pydantic Models

class SkillSummary(BaseModel):
    name: str
    trigger: str
    description: str
    tools: list[str]
    is_builtin: bool = False
    quality_profile: str = "standard"
    artifact_types: list[str] = []
    has_references: bool = False
    when_to_use: list[str] = []
    when_not_to_use: list[str] = []
    version: str = "1.0.0"
    disabled: bool = False
    # R4: where an installed package came from — only for user skills, never for
    # built-ins, and never an invented source when the note is missing.
    install: dict | None = None
    unchanged: bool | None = None
    # W3-14: signature state of a signed pack (signed/verified/reason/kid).
    # None for flat skills (a single .md cannot carry a record).
    signature: dict | None = None


class SkillDetail(BaseModel):
    name: str
    trigger: str
    description: str
    tools: list[str]
    system_prompt: str
    is_builtin: bool = False
    quality_profile: str = "standard"
    artifact_types: list[str] = []
    has_references: bool = False
    when_to_use: list[str] = []
    when_not_to_use: list[str] = []
    reference_text: str = ""
    example_text: str = ""
    version: str = "1.0.0"
    install: dict | None = None
    unchanged: bool | None = None
    signature: dict | None = None


class SkillsListResponse(BaseModel):
    skills: list[SkillSummary]
    total: int


class SkillCreateRequest(BaseModel):
    name: str
    trigger: str
    description: str
    tools: list[str] = []
    system_prompt: str


class SkillInstallResponse(BaseModel):
    installed: list[dict] = []
    updated: list[dict] = []
    skipped: list[dict] = []


class SkillUrlInstallRequest(BaseModel):
    url: str
    force: bool = False


# Routes

def _provenance(loader: SkillLoader, name: str, builtin: bool) -> tuple[dict | None, bool | None]:
    """The note and the recompute, for cards without a note: (None, None), not ({})."""
    if builtin:
        return None, None
    skill_dir = loader._user_dir / name
    return skill_provenance.read(skill_dir), skill_provenance.unchanged(skill_dir)


def _signature(loader: SkillLoader, name: str) -> dict | None:
    """W3-14: the signature state of a pack, or None for a flat skill.

    Verification is advisory on the load path — the surface reports a drifted
    or foreign-signed pack rather than silently trusting it. Installs enforce
    it separately (see `_install_archive_bytes`)."""
    status = loader.signature_status(name)
    return status if status.get("signed") else None


@router.get("/skills", response_model=SkillsListResponse)
async def list_skills() -> SkillsListResponse:
    """Returns every available skill (built-in plus user)."""
    loader = _get_loader()
    skills = loader.load_all()
    summaries = []
    for s in skills:
        builtin = loader.is_builtin(s.name)
        install, unchanged = _provenance(loader, s.name, builtin)
        summaries.append(
            SkillSummary(
                name=s.name,
                trigger=s.trigger,
                description=s.description,
                tools=s.tools,
                is_builtin=builtin,
                quality_profile=s.quality_profile,
                artifact_types=s.artifact_types,
                has_references=s.has_references,
                when_to_use=s.when_to_use,
                when_not_to_use=s.when_not_to_use,
                version=s.version,
                disabled=loader.is_disabled(s.name),
                install=install,
                unchanged=unchanged,
                signature=_signature(loader, s.name),
            )
        )
    return SkillsListResponse(skills=summaries, total=len(summaries))


@router.post("/skills", response_model=SkillDetail, status_code=201)
async def create_skill(request: SkillCreateRequest) -> SkillDetail:
    """Creates a new user skill."""
    loader = _get_loader()
    try:
        skill = loader.save(
            name=request.name,
            trigger=request.trigger,
            description=request.description,
            tools=request.tools,
            system_prompt=request.system_prompt,
        )
    except SkillLoadError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return SkillDetail(
        name=skill.name,
        trigger=skill.trigger,
        description=skill.description,
        tools=skill.tools,
        system_prompt=skill.system_prompt,
        is_builtin=False,
        quality_profile=skill.quality_profile,
        artifact_types=skill.artifact_types,
        has_references=skill.has_references,
        when_to_use=skill.when_to_use,
        when_not_to_use=skill.when_not_to_use,
        reference_text=skill.reference_text,
        example_text=skill.example_text,
        version=skill.version,
    )



# R16: curated offline pack index + topic-pack export

def _load_pack_index() -> dict:
    import json

    path = BUILTIN_SKILLS_DIR / "pack-index.json"
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/skills/pack-index")
async def get_pack_index() -> dict:
    """A curated, OFFLINE pack index (no registry network): topic packs
    reference built-in skills; every pack exports as a zip and installs on other
    machines through POST /api/skills/install."""
    loader = _get_loader()
    index = _load_pack_index()
    installed = {s.name: s for s in loader.load_all()}
    packs = []
    for pack in index.get("packs", []):
        skills = []
        for name in pack.get("skills", []):
            skill = installed.get(name)
            skills.append({
                "name": name,
                "installed": skill is not None,
                "trigger": skill.trigger if skill else "",
            })
        packs.append({
            "id": pack["id"],
            "title": pack["title"],
            "description": pack["description"],
            "skills": skills,
            "complete": all(s["installed"] for s in skills),
        })
    return {"version": index.get("version", 1), "packs": packs}


@router.get("/skills/export-pack/{pack_id}")
async def export_skill_pack(pack_id: str):
    """Exports a topic pack as a zip (the SKILL.md packs of the referenced
    built-ins) — shareable offline, installable through POST /api/skills/install."""
    index = _load_pack_index()
    pack = next((p for p in index.get("packs", []) if p["id"] == pack_id), None)
    if not pack:
        raise HTTPException(status_code=404, detail=f"Pack '{pack_id}' is not in the index.")

    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in pack.get("skills", []):
            skill_file = BUILTIN_SKILLS_DIR / name / "SKILL.md"
            if not skill_file.exists():
                continue
            zf.writestr(f"{name}/SKILL.md", skill_file.read_text(encoding="utf-8"))
            count += 1
            ref_dir = BUILTIN_SKILLS_DIR / name / "references"
            if ref_dir.exists():
                for ref in sorted(ref_dir.glob("*")):
                    if ref.is_file() and ref.suffix in {".md", ".txt"}:
                        zf.writestr(f"{name}/references/{ref.name}", ref.read_text(encoding="utf-8"))
    if count == 0:
        raise HTTPException(status_code=404, detail=f"pack '{pack_id}' contains no installable skills.")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{pack_id}.zip"'},
    )


@router.get("/skills/{name}", response_model=SkillDetail)
async def get_skill(name: str) -> SkillDetail:
    """Returns the details of a single skill."""
    loader = _get_loader()
    try:
        skill = loader.load(name)
    except SkillLoadError:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found.")
    builtin = loader.is_builtin(name)
    install, unchanged = _provenance(loader, name, builtin)
    return SkillDetail(
        name=skill.name,
        trigger=skill.trigger,
        description=skill.description,
        tools=skill.tools,
        system_prompt=skill.system_prompt,
        is_builtin=builtin,
        quality_profile=skill.quality_profile,
        artifact_types=skill.artifact_types,
        has_references=skill.has_references,
        when_to_use=skill.when_to_use,
        when_not_to_use=skill.when_not_to_use,
        reference_text=skill.reference_text,
        example_text=skill.example_text,
        version=skill.version,
        install=install,
        unchanged=unchanged,
        signature=_signature(loader, name),
    )


@router.get("/skills/{name}/verify")
async def verify_skill_signature(name: str) -> dict:
    """W3-14 — the verify path for a signed skill pack.

    Advisory and fail-soft: a signed pack is checked against its CURRENT
    content and the shared trust anchors. `verified=false` with a reason
    (drift, foreign key, no_trusted_key); a pack without a record answers
    `signed=false`, as does a flat skill. 404 only when the skill does not
    exist at all."""
    loader = _get_loader()
    if not (loader.is_builtin(name) or loader.is_user_skill(name)):
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found.")
    return loader.signature_status(name)


@router.put("/skills/{name}", response_model=SkillDetail)
async def update_skill(name: str, request: SkillCreateRequest) -> SkillDetail:
    """Updates an existing user skill."""
    loader = _get_loader()
    if loader.is_builtin(name) and not loader.is_user_skill(name):
        raise HTTPException(
            status_code=403,
            detail=f"Built-in skill '{name}' cannot be edited directly. Create a copy first.",
        )
    try:
        skill = loader.save(
            name=name,
            trigger=request.trigger,
            description=request.description,
            tools=request.tools,
            system_prompt=request.system_prompt,
        )
    except SkillLoadError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return SkillDetail(
        name=skill.name,
        trigger=skill.trigger,
        description=skill.description,
        tools=skill.tools,
        system_prompt=skill.system_prompt,
        is_builtin=False,
        quality_profile=skill.quality_profile,
        artifact_types=skill.artifact_types,
        has_references=skill.has_references,
        when_to_use=skill.when_to_use,
        when_not_to_use=skill.when_not_to_use,
        reference_text=skill.reference_text,
        example_text=skill.example_text,
        version=skill.version,
    )


@router.delete("/skills/{name}")
async def delete_skill(name: str) -> dict:
    """Deletes a user skill. Built-in skills cannot be deleted."""
    loader = _get_loader()
    try:
        loader.delete(name)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except SkillLoadError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"deleted": name}


# R16: skill pack management

def _validate_member_rel(rel: str) -> None:
    """Hard path validation for archive entries (traversal/absolute/dotfiles)."""
    if rel.startswith("/") or "\\" in rel:
        raise _ArchiveRejected(f"invalid archive path: {rel!r}")
    parts = PurePosixPath(rel).parts
    if not parts or ".." in parts:
        raise _ArchiveRejected(f"Path traversal in archive: {rel!r}")
    if any(part.startswith(".") for part in parts):
        raise _ArchiveRejected(f"Hidden file in archive: {rel!r}")


def _extract_archive(data: bytes, dest: Path) -> None:
    """Extracts zip/tar into dest — validating entries instead of blind extraction.

    Every entry is written on its own (not through the archive API's extract), so
    no stdlib sanitizing can take the place of the guards.
    """
    total = 0
    count = 0
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        zf = None

    if zf is not None:
        with zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                rel = info.filename.replace("\\", "/")
                if PurePosixPath(rel).name == ".DS_Store" or rel.startswith("__MACOSX/"):
                    continue
                _validate_member_rel(rel)
                if PurePosixPath(rel).suffix.lower() not in ALLOWED_SKILL_FILE_EXTS:
                    raise _ArchiveRejected(f"File extension not allowed: {rel!r}")
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise _ArchiveRejected(f"Symlink in archive: {rel!r}")
                total += info.file_size
                count += 1
                if total > MAX_EXTRACT_TOTAL or count > MAX_ENTRY_COUNT:
                    raise _ArchiveRejected("archive too large (entries/size)")
                if info.file_size > MAX_ENTRY_BYTES:
                    raise _ArchiveRejected(f"single file too large: {rel!r}")
                target = (dest / rel).resolve()
                if not str(target).startswith(str(dest.resolve())):
                    raise _ArchiveRejected(f"Path traversal in archive: {rel!r}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
        return

    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    if member.issym() or member.islnk():
                        raise _ArchiveRejected(f"Link in archive: {member.name!r}")
                    continue
                rel = member.name.replace("\\", "/")
                if PurePosixPath(rel).name == ".DS_Store" or rel.startswith("__MACOSX/"):
                    continue
                _validate_member_rel(rel)
                if PurePosixPath(rel).suffix.lower() not in ALLOWED_SKILL_FILE_EXTS:
                    raise _ArchiveRejected(f"File extension not allowed: {rel!r}")
                total += member.size
                count += 1
                if total > MAX_EXTRACT_TOTAL or count > MAX_ENTRY_COUNT:
                    raise _ArchiveRejected("archive too large (entries/size)")
                if member.size > MAX_ENTRY_BYTES:
                    raise _ArchiveRejected(f"single file too large: {rel!r}")
                target = (dest / rel).resolve()
                if not str(target).startswith(str(dest.resolve())):
                    raise _ArchiveRejected(f"Path traversal in archive: {rel!r}")
                target.parent.mkdir(parents=True, exist_ok=True)
                src = tf.extractfile(member)
                if src is None:
                    raise _ArchiveRejected(f"Entry not readable: {rel!r}")
                with src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
    except tarfile.TarError as exc:
        raise _ArchiveRejected(f"not a valid archive (zip/tar): {exc}") from exc


def _semver_tuple(version: str) -> tuple[int, int, int]:
    try:
        return tuple(int(part) for part in str(version).split(".")[:3])  # type: ignore[return-value]
    except ValueError:
        return (0, 0, 0)


def _find_skill_dirs(root: Path) -> list[Path]:
    """SKILL.md in the archive root (a one-skill pack) or in exactly one subfolder."""
    candidates: list[Path] = []
    if (root / "SKILL.md").exists():
        candidates.append(root)
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        if (sub / "SKILL.md").exists():
            candidates.append(sub)
    return candidates


def _install_archive_bytes(
    data: bytes,
    *,
    force: bool,
    kind: str = "upload",
    origin: str = "",
    pack_id: str = "",
) -> SkillInstallResponse:
    if len(data) > MAX_ARCHIVE_BYTES:
        raise HTTPException(status_code=413, detail="archive too large (limit 10 MB)")

    loader = _get_loader()
    loader.invalidate_cache()
    user_dir = loader._user_dir
    result = SkillInstallResponse()

    with tempfile.TemporaryDirectory(prefix="ephe-skill-pack-") as tmp:
        root = Path(tmp) / "extract"
        root.mkdir()
        try:
            _extract_archive(data, root)
        except _ArchiveRejected as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        candidates = _find_skill_dirs(root)
        if not candidates:
            raise HTTPException(status_code=422, detail="No SKILL.md found in archive")

        # Validate ALL candidates first — only then is anything written.
        parsed: list[tuple[Path, object]] = []
        for cand in candidates:
            content = (cand / "SKILL.md").read_text(encoding="utf-8")
            try:
                skill = _parse_skill(cand.name if cand != root else "pack", content, skill_dir=cand)
            except SkillLoadError as exc:
                raise HTTPException(status_code=422, detail=f"invalid skill in pack: {exc}")
            if not _SKILL_NAME_RE.match(skill.name):
                raise HTTPException(
                    status_code=422,
                    detail=f"invalid skill name '{skill.name}' (allowed: a-z 0-9 - _)",
                )
            if cand != root and skill.name != cand.name:
                raise HTTPException(
                    status_code=422,
                    detail=f"Frontmatter name '{skill.name}' does not match the directory '{cand.name}'",
                )
            # W3-14: a pack that DECLARES a signature must verify before anything
            # is written. A self-declared signature that does not verify is a
            # forgery or a drift — fail closed (the same stance the plugin
            # marketplace takes). Unsigned packs are unaffected.
            if (cand / skill_signing.SIG_FILENAME).is_file():
                from core.plugin_signing import load_trusted_public_keys

                record = skill_signing.read(cand)
                ok, reason = skill_signing.verify_skill_pack(cand, record or {}, load_trusted_public_keys())
                if not ok:
                    raise HTTPException(
                        status_code=422,
                        detail=f"signed pack '{skill.name}' failed signature check: {reason}",
                    )
            parsed.append((cand, skill))

        for cand, skill in parsed:  # type: ignore[arg-type]
            if loader.is_builtin(skill.name):
                raise HTTPException(
                    status_code=403,
                    detail=f"built-in skill '{skill.name}' cannot be overwritten via pack.",
                )

        user_dir.mkdir(parents=True, exist_ok=True)
        for cand, skill in parsed:  # type: ignore[arg-type]
            installed_dir = user_dir / skill.name
            entry = {"name": skill.name, "version": skill.version, "trigger": skill.trigger}
            if installed_dir.exists():
                installed_version = "0.0.0"
                try:
                    installed_version = _parse_skill(
                        skill.name, (installed_dir / "SKILL.md").read_text(encoding="utf-8"),
                        skill_dir=installed_dir,
                    ).version
                except SkillLoadError:
                    pass
                if installed_version == skill.version:
                    result.skipped.append({"name": skill.name, "reason": "already-installed"})
                    continue
                if _semver_tuple(skill.version) < _semver_tuple(installed_version) and not force:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Skill '{skill.name}' is already at v{installed_version} (install would downgrade to v{skill.version} downgrade) — enforce with force=true."
                        ),
                    )
                shutil.rmtree(installed_dir)
                result.updated.append(entry)
            else:
                result.installed.append(entry)
            shutil.move(str(cand), str(installed_dir))
            record = skill_provenance.record_install(
                installed_dir, kind=kind, origin=origin, version=skill.version, pack_id=pack_id
            )
            entry["origin"] = record["origin"] or record["kind"]
            entry["content_hash"] = record["content_hash"]

    loader.invalidate_cache()
    return result


@router.post("/skills/install", response_model=SkillInstallResponse)
async def install_skill(
    file: UploadFile = File(...),
    force: bool = Form(False),
) -> SkillInstallResponse:
    """Installs a skill pack (zip/tar.gz) into the user skills.

    Guards: path traversal/absolute/symlinks/extensions/sizes (see the module
    constants), built-ins stay protected. Same-named pack, same version = skip,
    lower version = 409 (force overwrites).
    """
    data = bytearray()
    while chunk := await file.read(1 << 20):
        data.extend(chunk)
        if len(data) > MAX_ARCHIVE_BYTES:
            raise HTTPException(status_code=413, detail="archive too large (limit 10 MB)")
    return _install_archive_bytes(
        bytes(data), force=force, kind="upload", origin=file.filename or ""
    )


#: The hosts a pack install may fetch from. A pack is code the user installs, so the
#: fetch is clamped to the sources Ephe ships packs from; an operator widens the set on
#: purpose through `EPHE_SKILLS_INSTALL_HOSTS` (comma-separated). A loopback, link-local
#: or metadata address is never a pack source, whoever names it.
DEFAULT_PACK_HOSTS = (
    "github.com",
    "raw.githubusercontent.com",
    "codeload.github.com",
    "objects.githubusercontent.com",
)


def _allowed_pack_hosts() -> set[str]:
    extra = os.environ.get("EPHE_SKILLS_INSTALL_HOSTS", "")
    return set(DEFAULT_PACK_HOSTS) | {host.strip().lower() for host in extra.split(",") if host.strip()}


def _clamp_pack_url(raw: str) -> str:
    """The one URL an install may fetch: http(s), a host on the allowlist, no userinfo."""
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https"):
        raise HTTPException(status_code=422, detail="Only http(s) URLs allowed")
    host = (parts.hostname or "").lower()
    if host not in _allowed_pack_hosts():
        raise HTTPException(status_code=422, detail=f"host '{host}' is not an allowed skill-pack source")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


@router.post("/skills/install/url", response_model=SkillInstallResponse)
async def install_skill_from_url(request: SkillUrlInstallRequest) -> SkillInstallResponse:
    """Installs a skill pack pulled in through a URL (an explicit user action)."""
    url = _clamp_pack_url(request.url.strip())
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            # url passed _clamp_pack_url: http(s) scheme and a host on EPHE_SKILLS_INSTALL_HOSTS.
            # codeql[py/full-ssrf]
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.content
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Download failed: {exc}")
    return _install_archive_bytes(data, force=request.force, kind="url", origin=url)


def _set_disabled_response(loader: SkillLoader, name: str, disabled: bool) -> dict:
    try:
        state = loader.set_disabled(name, disabled)
    except SkillLoadError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"name": name, "disabled": state}


@router.post("/skills/{name}/disable")
async def disable_skill(name: str) -> dict:
    """Disables a skill (it stays listed and is never resolved automatically)."""
    return _set_disabled_response(_get_loader(), name, True)


@router.post("/skills/{name}/enable")
async def enable_skill(name: str) -> dict:
    """Re-enables a skill that was disabled."""
    return _set_disabled_response(_get_loader(), name, False)


