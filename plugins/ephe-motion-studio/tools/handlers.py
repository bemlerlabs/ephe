"""Ephe Motion Studio tools.

One JSON document per project, its sources, assets and renders under the plugin
state root. Every mutating tool names the revision it read; a stale revision is
refused before a byte is written, so two writers cannot silently overwrite each
other. The render path loads the project sources in Chromium, captures frames
with Playwright and cuts them with ffmpeg; no frame leaves the machine.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "ephe-motion-project/1"
REVISION_RE = re.compile(r"^[0-9a-f]{64}$")
PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SOURCE_SUFFIXES = frozenset({".html", ".css", ".js", ".svg", ".txt"})
MAX_FRAMES = 600
MAX_DURATION = 60.0
MAX_DIMENSION = 1920
MAX_ASSET_BYTES = 8 * 1024 * 1024
MAX_PROJECT_BYTES = 64 * 1024 * 1024
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_FPS = 30
DEFAULT_DURATION = 5.0


class _Refusal(Exception):
    """A coded refusal: the model reads the code, the audit row keeps it."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _refusal(code: str, detail: str) -> str:
    return "[TOOL-DENIED] " + _json({"ok": False, "error": code, "detail": detail})


def _state(state_dir) -> Path:
    path = Path(state_dir or ".")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _project_dir(state_dir, project_id: str) -> Path:
    if not isinstance(project_id, str) or not PROJECT_ID_RE.match(project_id):
        raise _Refusal("invalid_argument", "project_id must be a lowercase slug of at most 64 characters")
    return _state(state_dir) / "projects" / project_id


def _load(state_dir, project_id: str) -> dict:
    path = _project_dir(state_dir, project_id) / "project.json"
    if not path.is_file():
        raise _Refusal("project_not_found", f"no project {project_id!r} under this plugin state")
    try:
        project = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _Refusal("project_not_found", f"project {project_id!r} is unreadable ({exc.__class__.__name__})")
    if not isinstance(project, dict) or project.get("schema") != SCHEMA:
        raise _Refusal("project_not_found", f"project {project_id!r} is not a {SCHEMA} document")
    return project


def _revision(project: dict) -> str:
    body = {key: value for key, value in project.items() if key != "revision"}
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _save(state_dir, project: dict) -> str:
    project["updated"] = datetime.now(timezone.utc).isoformat()
    project["revision"] = _revision(project)
    path = _project_dir(state_dir, str(project["id"])) / "project.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return project["revision"]


def _check_revision(project: dict, expected) -> None:
    if not isinstance(expected, str) or not expected:
        raise _Refusal("invalid_argument", "expected_revision is required and must be the 64-hex revision you read")
    if not REVISION_RE.match(expected):
        raise _Refusal("invalid_argument", "expected_revision must be 64 hexadecimal characters")
    current = str(project.get("revision") or _revision(project))
    if expected != current:
        raise _Refusal(
            "revision_conflict",
            f"expected revision {expected} but the project is at {current}; "
            "read it again and retry the write",
        )


def _number(arguments: dict, key: str, default, lowest: float, highest: float):
    value = arguments.get(key, default)
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise _Refusal("invalid_argument", f"{key} must be a number")
    if not lowest <= value <= highest:
        raise _Refusal("limit_exceeded", f"{key} must be between {lowest} and {highest}")
    return value


def _source_path(state_dir, project_id: str, relative: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise _Refusal("invalid_argument", "path must be a relative source path")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise _Refusal("path_escape", "path must stay inside the project sources")
    if candidate.suffix.lower() not in SOURCE_SUFFIXES:
        raise _Refusal("invalid_argument", f"source suffix must be one of {sorted(SOURCE_SUFFIXES)}")
    return _project_dir(state_dir, project_id) / "sources" / candidate


def _clip_color(clip_id: str) -> str:
    hue = int(hashlib.sha256(clip_id.encode("utf-8")).hexdigest()[:6], 16) % 360
    return f"hsl({hue}, 65%, 45%)"


def _preview_payload(project: dict) -> str:
    clips = []
    for clip in project.get("clips") or []:
        clips.append({
            "id": clip.get("id"),
            "text": clip.get("text") or clip.get("id"),
            "start": float(clip.get("start") or 0),
            "duration": float(clip.get("duration") or 0),
            "track": int(clip.get("track") or 0),
            "color": _clip_color(str(clip.get("id") or "")),
        })
    return json.dumps({
        "width": int(project.get("width") or DEFAULT_WIDTH),
        "height": int(project.get("height") or DEFAULT_HEIGHT),
        "brand": project.get("brand") or {},
        "clips": clips,
        "captions": [
            {
                "text": caption.get("text") or "",
                "start": float(caption.get("start") or 0),
                "duration": float(caption.get("duration") or 0),
            }
            for caption in project.get("captions") or []
        ],
    }, ensure_ascii=False)


def _preview_html(project: dict) -> str:
    payload = _preview_payload(project)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{project.get("name") or project.get("id") or "Motion"}</title>
<style>html,body{{margin:0;background:#000}}</style>
</head>
<body>
<canvas id="stage" width="{int(project.get("width") or DEFAULT_WIDTH)}" height="{int(project.get("height") or DEFAULT_HEIGHT)}"></canvas>
<script>
const P={payload};
const cv=document.getElementById("stage"),ctx=cv.getContext("2d");
function draw(t){{
  ctx.fillStyle=(P.brand&&P.brand.primary)||"#101418";
  ctx.fillRect(0,0,cv.width,cv.height);
  (P.clips||[]).forEach(function(c){{
    if(t>=c.start&&t<=c.start+c.duration){{
      ctx.fillStyle=c.color||"#3b82f6";
      ctx.fillRect(40,40+(c.track||0)*80,cv.width-80,60);
      ctx.fillStyle="#ffffff";
      ctx.font="20px sans-serif";
      ctx.fillText(c.text,60,80+(c.track||0)*80);
    }}
  }});
  (P.captions||[]).forEach(function(cap){{
    if(t>=cap.start&&t<=cap.start+cap.duration){{
      ctx.fillStyle="rgba(0,0,0,0.6)";
      ctx.fillRect(0,cv.height-64,cv.width,44);
      ctx.fillStyle="#ffffff";
      ctx.font="18px sans-serif";
      ctx.fillText(cap.text,20,cv.height-34);
    }}
  }});
}}
window.__seek=function(t){{draw(t);return true;}};
window.__seek(0);
</script>
</body>
</html>
"""


def _chromium_launch(playwright):
    try:
        return playwright.chromium.launch()
    except Exception:  # noqa: BLE001 - the default path is one candidate, not the only one
        pass
    roots = [Path.home() / "Library" / "Caches" / "ms-playwright", Path.home() / ".cache" / "ms-playwright"]
    patterns = (
        "chromium_headless_shell-*/*/chrome-headless-shell",
        "chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
    )
    for root in roots:
        if not root.is_dir():
            continue
        for pattern in patterns:
            for executable in sorted(root.glob(pattern)):
                if not executable.is_file():
                    continue
                try:
                    return playwright.chromium.launch(executable_path=str(executable))
                except Exception:  # noqa: BLE001 - a candidate that refuses is the next candidate
                    continue
    raise _Refusal("render_failed", "no Chromium executable was found for the frame capture")


def _render(state_dir, project: dict, output_name: str) -> dict:
    width = int(project.get("width") or DEFAULT_WIDTH)
    height = int(project.get("height") or DEFAULT_HEIGHT)
    fps = int(project.get("fps") or DEFAULT_FPS)
    duration = float(project.get("duration") or DEFAULT_DURATION)
    frames = int(round(duration * fps))
    if frames < 1:
        raise _Refusal("limit_exceeded", "a render needs at least one frame")
    if frames > MAX_FRAMES:
        raise _Refusal("limit_exceeded", f"{frames} frames exceed the {MAX_FRAMES} frame limit; shorten the film or lower the frame rate")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise _Refusal("render_failed", "ffmpeg is not on PATH; the cut needs it")

    project_id = str(project["id"])
    render_id = uuid.uuid4().hex[:12]
    render_dir = _project_dir(state_dir, project_id) / "renders" / render_id
    frames_dir = render_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    html_path = render_dir / "preview.html"
    html_path.write_text(_preview_html(project), encoding="utf-8")
    output_name = output_name or f"{project_id}.mp4"
    output_path = (render_dir / output_name).resolve()
    if render_dir.resolve() not in output_path.parents:
        raise _Refusal("path_escape", "output_name must stay inside the render folder")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _chromium_launch(playwright)
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(html_path.as_uri(), wait_until="load")
            for index in range(frames):
                page.evaluate("window.__seek(%r)" % (index / fps))
                page.locator("#stage").screenshot(path=str(frames_dir / f"frame_{index:04d}.png"))
        finally:
            browser.close()

    command = [
        ffmpeg, "-y", "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(output_path),
    ]
    try:
        finished = subprocess.run(command, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as exc:
        raise _Refusal("render_failed", f"ffmpeg did not run ({exc.__class__.__name__})")
    if finished.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
        tail = (finished.stderr or finished.stdout or "").strip()[-400:]
        raise _Refusal("render_failed", f"ffmpeg exited {finished.returncode}: {tail}")

    status = {
        "render_id": render_id,
        "project_id": project_id,
        "status": "done",
        "artifact": str(output_path),
        "frames": frames,
        "fps": fps,
        "duration": duration,
        "finished": datetime.now(timezone.utc).isoformat(),
    }
    (render_dir.parent / f"{render_id}.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return status


def _status_path(state_dir, project_id: str, render_id: str) -> Path:
    return _project_dir(state_dir, project_id) / "renders" / f"{render_id}.json"


def _status(state_dir, project_id: str, render_id: str) -> dict:
    path = _status_path(state_dir, project_id, render_id)
    if not path.is_file():
        raise _Refusal("render_not_found", f"no render {render_id!r} for project {project_id!r}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise _Refusal("render_not_found", f"render {render_id!r} has an unreadable status")


def _slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug[:48] or fallback


def _run(name: str, arguments, state_dir, bridge):
    """One handler body behind the contract: a coded refusal or a JSON answer."""
    arguments = arguments or {}
    try:
        return _dispatch(name, arguments, state_dir)
    except _Refusal as refusal:
        return _refusal(refusal.code, refusal.detail)
    except Exception as exc:  # noqa: BLE001 - the worker keeps the class, the model gets a code
        return _refusal("render_failed" if name == "ephe_motion_render" else "invalid_argument",
                        f"{name} failed: {exc.__class__.__name__}")


def _dispatch(name: str, arguments: dict, state_dir) -> str:
    if name == "ephe_motion_create_project":
        return _create_project(arguments, state_dir)
    if name == "ephe_motion_open_project":
        return _open_project(arguments, state_dir)
    if name == "ephe_motion_list_assets":
        return _list_assets(arguments, state_dir)
    if name == "ephe_motion_import_asset":
        return _import_asset(arguments, state_dir)
    if name == "ephe_motion_read_source":
        return _read_source(arguments, state_dir)
    if name == "ephe_motion_write_source":
        return _write_source(arguments, state_dir)
    if name == "ephe_motion_inspect_project":
        return _inspect_project(arguments, state_dir)
    if name == "ephe_motion_list_timeline":
        return _list_timeline(arguments, state_dir)
    if name == "ephe_motion_trim_clip":
        return _trim_clip(arguments, state_dir)
    if name == "ephe_motion_reorder_clips":
        return _reorder_clips(arguments, state_dir)
    if name == "ephe_motion_add_caption":
        return _add_caption(arguments, state_dir)
    if name == "ephe_motion_apply_brand":
        return _apply_brand(arguments, state_dir)
    if name == "ephe_motion_render":
        return _render_tool(arguments, state_dir)
    if name == "ephe_motion_render_status":
        return _render_status(arguments, state_dir)
    if name == "ephe_motion_cancel_render":
        return _cancel_render(arguments, state_dir)
    if name == "ephe_motion_export_project":
        return _export_project(arguments, state_dir)
    if name == "ephe_motion_wait_render":
        return _wait_render(arguments, state_dir)
    raise _Refusal("invalid_argument", f"unknown tool {name!r}")


def _create_project(arguments: dict, state_dir) -> str:
    name = str(arguments.get("name") or "").strip()
    if not name:
        raise _Refusal("invalid_argument", "name is required")
    width = int(_number(arguments, "width", DEFAULT_WIDTH, 16, MAX_DIMENSION))
    height = int(_number(arguments, "height", DEFAULT_HEIGHT, 16, MAX_DIMENSION))
    fps = int(_number(arguments, "fps", DEFAULT_FPS, 1, 60))
    duration = _number(arguments, "duration", DEFAULT_DURATION, 0.1, MAX_DURATION)
    project_id = f"{_slug(name, 'project')}-{uuid.uuid4().hex[:8]}"
    project = {
        "schema": SCHEMA,
        "id": project_id,
        "name": name,
        "width": width,
        "height": height,
        "fps": fps,
        "duration": duration,
        "scenes": [{"id": "scene-1", "name": "Scene 1", "start": 0, "duration": duration}],
        "clips": [],
        "captions": [],
        "brand": {"name": name, "primary": "#101418", "secondary": "#3b82f6", "font": "sans-serif"},
        "template": str(arguments.get("template") or ""),
    }
    if str(arguments.get("template") or "") == "reveal":
        step = duration / 3
        project["clips"] = [
            {"id": f"clip-{index + 1}", "text": f"Beat {index + 1}", "start": index * step,
             "duration": step, "track": index, "order": index}
            for index in range(3)
        ]
        project["captions"] = [{"id": "caption-1", "text": name, "start": 0, "duration": step}]
    revision = _save(state_dir, project)
    return _json({"ok": True, "project_id": project_id, "revision": revision,
                  "path": str(_project_dir(state_dir, project_id))})


def _open_project(arguments: dict, state_dir) -> str:
    project = _load(state_dir, str(arguments.get("project_id") or ""))
    return _json({"ok": True, "project": project, "revision": str(project.get("revision") or ""),
                  "path": str(_project_dir(state_dir, str(project["id"])))})


def _list_assets(arguments: dict, state_dir) -> str:
    project = _load(state_dir, str(arguments.get("project_id") or ""))
    folder = _project_dir(state_dir, str(project["id"])) / "assets"
    assets = []
    if folder.is_dir():
        for path in sorted(folder.iterdir()):
            if path.is_file():
                assets.append({"id": path.stem, "name": path.name, "path": str(path),
                               "size": path.stat().st_size, "suffix": path.suffix.lower()})
    return _json({"ok": True, "project_id": project["id"], "assets": assets})


def _import_asset(arguments: dict, state_dir) -> str:
    project = _load(state_dir, str(arguments.get("project_id") or ""))
    if arguments.get("expected_revision") is not None:
        _check_revision(project, arguments.get("expected_revision"))
    source = Path(str(arguments.get("source_path") or ""))
    if not source.is_file():
        raise _Refusal("asset_not_found", f"no file at {source}")
    if source.stat().st_size > MAX_ASSET_BYTES:
        raise _Refusal("limit_exceeded", f"{source.stat().st_size} bytes exceed the {MAX_ASSET_BYTES} byte asset limit")
    asset_id = f"{_slug(str(arguments.get('name') or source.stem), 'asset')}-{uuid.uuid4().hex[:6]}"
    folder = _project_dir(state_dir, str(project["id"])) / "assets"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{asset_id}{source.suffix.lower()}"
    shutil.copyfile(source, target)
    revision = _save(state_dir, project)
    return _json({"ok": True, "asset_id": asset_id, "path": str(target), "revision": revision})


def _read_source(arguments: dict, state_dir) -> str:
    project = _load(state_dir, str(arguments.get("project_id") or ""))
    if arguments.get("expected_revision") is not None:
        _check_revision(project, arguments.get("expected_revision"))
    path = _source_path(state_dir, str(project["id"]), str(arguments.get("path") or ""))
    if not path.is_file():
        raise _Refusal("asset_not_found", f"no source at {arguments.get('path')!r}")
    return _json({"ok": True, "path": str(path), "text": path.read_text(encoding="utf-8"),
                  "revision": str(project.get("revision") or "")})


def _write_source(arguments: dict, state_dir) -> str:
    project = _load(state_dir, str(arguments.get("project_id") or ""))
    _check_revision(project, arguments.get("expected_revision"))
    path = _source_path(state_dir, str(project["id"]), str(arguments.get("path") or ""))
    content = arguments.get("content")
    if not isinstance(content, str):
        raise _Refusal("invalid_argument", "content must be a string")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    revision = _save(state_dir, project)
    return _json({"ok": True, "path": str(path), "revision": revision})


def _inspect_project(arguments: dict, state_dir) -> str:
    project = _load(state_dir, str(arguments.get("project_id") or ""))
    folder = _project_dir(state_dir, str(project["id"]))
    sources = sorted(str(path.relative_to(folder)) for path in (folder / "sources").rglob("*") if path.is_file())
    assets = sorted(str(path.relative_to(folder)) for path in (folder / "assets").rglob("*") if path.is_file())
    return _json({
        "ok": True,
        "project_id": project["id"],
        "schema": project.get("schema"),
        "revision": str(project.get("revision") or ""),
        "width": project.get("width"), "height": project.get("height"),
        "fps": project.get("fps"), "duration": project.get("duration"),
        "clips": len(project.get("clips") or []),
        "captions": len(project.get("captions") or []),
        "scenes": len(project.get("scenes") or []),
        "sources": sources, "assets": assets,
        "brand": project.get("brand") or {},
    })


def _list_timeline(arguments: dict, state_dir) -> str:
    project = _load(state_dir, str(arguments.get("project_id") or ""))
    clips = sorted(project.get("clips") or [], key=lambda clip: (float(clip.get("start") or 0), int(clip.get("order") or 0)))
    captions = sorted(project.get("captions") or [], key=lambda caption: float(caption.get("start") or 0))
    return _json({"ok": True, "project_id": project["id"], "clips": clips, "captions": captions})


def _trim_clip(arguments: dict, state_dir) -> str:
    project = _load(state_dir, str(arguments.get("project_id") or ""))
    _check_revision(project, arguments.get("expected_revision"))
    clip_id = str(arguments.get("clip_id") or "")
    start = _number(arguments, "start", 0, 0, MAX_DURATION)
    duration = _number(arguments, "duration", 0, 0.05, MAX_DURATION)
    for clip in project.get("clips") or []:
        if str(clip.get("id")) == clip_id:
            clip["start"] = start
            clip["duration"] = duration
            revision = _save(state_dir, project)
            return _json({"ok": True, "clip_id": clip_id, "revision": revision})
    raise _Refusal("asset_not_found", f"no clip {clip_id!r} in this project")


def _reorder_clips(arguments: dict, state_dir) -> str:
    project = _load(state_dir, str(arguments.get("project_id") or ""))
    _check_revision(project, arguments.get("expected_revision"))
    order = arguments.get("clip_ids")
    if not isinstance(order, list) or not order:
        raise _Refusal("invalid_argument", "clip_ids must be a non-empty list")
    clips = project.get("clips") or []
    known = {str(clip.get("id")) for clip in clips}
    wanted = [str(item) for item in order]
    if len(set(wanted)) != len(wanted) or set(wanted) != known:
        raise _Refusal("invalid_argument", "clip_ids must name every clip exactly once")
    for index, clip_id in enumerate(wanted):
        next(clip for clip in clips if str(clip.get("id")) == clip_id)["order"] = index
    revision = _save(state_dir, project)
    return _json({"ok": True, "clip_ids": wanted, "revision": revision})


def _add_caption(arguments: dict, state_dir) -> str:
    project = _load(state_dir, str(arguments.get("project_id") or ""))
    _check_revision(project, arguments.get("expected_revision"))
    text = str(arguments.get("text") or "").strip()
    if not text:
        raise _Refusal("invalid_argument", "text is required")
    start = _number(arguments, "start", 0, 0, MAX_DURATION)
    duration = _number(arguments, "duration", 0, 0.05, MAX_DURATION)
    caption = {"id": f"caption-{uuid.uuid4().hex[:8]}", "text": text, "start": start, "duration": duration}
    project.setdefault("captions", []).append(caption)
    revision = _save(state_dir, project)
    return _json({"ok": True, "caption": caption, "revision": revision})


def _apply_brand(arguments: dict, state_dir) -> str:
    project = _load(state_dir, str(arguments.get("project_id") or ""))
    _check_revision(project, arguments.get("expected_revision"))
    brand = arguments.get("brand")
    if not isinstance(brand, dict) or not brand:
        raise _Refusal("invalid_argument", "brand must be a non-empty object")
    merged = dict(project.get("brand") or {})
    for key in ("name", "primary", "secondary", "font", "logo_asset_id"):
        if key in brand and isinstance(brand[key], str):
            merged[key] = brand[key]
    project["brand"] = merged
    revision = _save(state_dir, project)
    return _json({"ok": True, "brand": merged, "revision": revision})


def _render_tool(arguments: dict, state_dir) -> str:
    project = _load(state_dir, str(arguments.get("project_id") or ""))
    if arguments.get("expected_revision") is not None:
        _check_revision(project, arguments.get("expected_revision"))
    status = _render(state_dir, project, str(arguments.get("output_name") or ""))
    return _json({"ok": True, **status})


def _render_status(arguments: dict, state_dir) -> str:
    project_id = str(arguments.get("project_id") or "")
    _load(state_dir, project_id)
    return _json({"ok": True, **_status(state_dir, project_id, str(arguments.get("render_id") or ""))})


def _cancel_render(arguments: dict, state_dir) -> str:
    project_id = str(arguments.get("project_id") or "")
    _load(state_dir, project_id)
    status = _status(state_dir, project_id, str(arguments.get("render_id") or ""))
    if status.get("status") in {"pending", "running"}:
        status["status"] = "cancelled"
        status["cancelled"] = datetime.now(timezone.utc).isoformat()
        _status_path(state_dir, project_id, str(arguments.get("render_id") or "")).write_text(
            json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return _json({"ok": True, **status})


def _export_project(arguments: dict, state_dir) -> str:
    project = _load(state_dir, str(arguments.get("project_id") or ""))
    folder = _project_dir(state_dir, str(project["id"]))
    total = sum(path.stat().st_size for path in folder.rglob("*") if path.is_file())
    if total > MAX_PROJECT_BYTES:
        raise _Refusal("limit_exceeded", f"the project holds {total} bytes, past the {MAX_PROJECT_BYTES} byte export limit")
    target_dir = Path(str(arguments.get("target_dir") or _state(state_dir) / "exports"))
    target_dir.mkdir(parents=True, exist_ok=True)
    target = (target_dir / f"{project['id']}-{str(project.get('revision'))[:8]}.zip").resolve()
    if target_dir.resolve() not in target.parents:
        raise _Refusal("path_escape", "target_dir must stay a writable folder")
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(folder).as_posix())
    return _json({"ok": True, "path": str(target), "bytes": target.stat().st_size})


def _wait_render(arguments: dict, state_dir) -> str:
    project_id = str(arguments.get("project_id") or "")
    render_id = str(arguments.get("render_id") or "")
    _load(state_dir, project_id)
    timeout = _number(arguments, "timeout", 120, 0, 600)
    deadline = time.monotonic() + timeout
    status = _status(state_dir, project_id, render_id)
    while status.get("status") in {"pending", "running"} and time.monotonic() < deadline:
        time.sleep(0.25)
        status = _status(state_dir, project_id, render_id)
    return _json({"ok": True, **status})


def ephe_motion_create_project(arguments, state_dir, bridge):
    return _run("ephe_motion_create_project", arguments, state_dir, bridge)


def ephe_motion_open_project(arguments, state_dir, bridge):
    return _run("ephe_motion_open_project", arguments, state_dir, bridge)


def ephe_motion_list_assets(arguments, state_dir, bridge):
    return _run("ephe_motion_list_assets", arguments, state_dir, bridge)


def ephe_motion_import_asset(arguments, state_dir, bridge):
    return _run("ephe_motion_import_asset", arguments, state_dir, bridge)


def ephe_motion_read_source(arguments, state_dir, bridge):
    return _run("ephe_motion_read_source", arguments, state_dir, bridge)


def ephe_motion_write_source(arguments, state_dir, bridge):
    return _run("ephe_motion_write_source", arguments, state_dir, bridge)


def ephe_motion_inspect_project(arguments, state_dir, bridge):
    return _run("ephe_motion_inspect_project", arguments, state_dir, bridge)


def ephe_motion_list_timeline(arguments, state_dir, bridge):
    return _run("ephe_motion_list_timeline", arguments, state_dir, bridge)


def ephe_motion_trim_clip(arguments, state_dir, bridge):
    return _run("ephe_motion_trim_clip", arguments, state_dir, bridge)


def ephe_motion_reorder_clips(arguments, state_dir, bridge):
    return _run("ephe_motion_reorder_clips", arguments, state_dir, bridge)


def ephe_motion_add_caption(arguments, state_dir, bridge):
    return _run("ephe_motion_add_caption", arguments, state_dir, bridge)


def ephe_motion_apply_brand(arguments, state_dir, bridge):
    return _run("ephe_motion_apply_brand", arguments, state_dir, bridge)


def ephe_motion_render(arguments, state_dir, bridge):
    return _run("ephe_motion_render", arguments, state_dir, bridge)


def ephe_motion_render_status(arguments, state_dir, bridge):
    return _run("ephe_motion_render_status", arguments, state_dir, bridge)


def ephe_motion_cancel_render(arguments, state_dir, bridge):
    return _run("ephe_motion_cancel_render", arguments, state_dir, bridge)


def ephe_motion_export_project(arguments, state_dir, bridge):
    return _run("ephe_motion_export_project", arguments, state_dir, bridge)


def ephe_motion_wait_render(arguments, state_dir, bridge):
    return _run("ephe_motion_wait_render", arguments, state_dir, bridge)
