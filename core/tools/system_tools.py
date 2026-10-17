"""Ephe – System/Core tools: datetime, projects, workspace, image, screenshot, SVG."""

from __future__ import annotations

import asyncio
import base64
import os
import subprocess
import sys
import time as time_module
from datetime import datetime
from pathlib import Path

from core.tools.base import (
    DirectoryNotFoundError,
    FileNotAllowedError,
    MAX_WORKSPACE_CHARS,
    MAX_WORKSPACE_DEPTH,
    SUPPORTED_IMAGE_EXTENSIONS,
    _get_shared_client,
    _is_path_allowed,
)


EN_WEEKDAYS = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]

EN_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


async def get_datetime() -> str:
    now = datetime.now()
    weekday = EN_WEEKDAYS[now.weekday()]
    month = EN_MONTHS[now.month - 1]
    return f"{weekday}, {now.day:02d}. {month} {now.year}, {now.hour:02d}:{now.minute:02d}"


async def discover_projects(query: str = "", root: str | None = None, max_results: int = 10) -> str:
    from core.project_discovery import discover_project_records, format_project_listing

    roots = None
    if root:
        candidate = Path(root).expanduser()
        if not _is_path_allowed(candidate):
            return f"Access to '{candidate}' not allowed (security whitelist)."
        roots = [candidate]
    records = await asyncio.to_thread(
        discover_project_records,
        query=query,
        roots=roots,
        max_results=max(1, min(int(max_results), 25)),
    )
    return format_project_listing(records)


async def analyze_project(path: str) -> str:
    from core.project_discovery import analyze_project_path

    return await asyncio.to_thread(analyze_project_path, path)


async def load_workspace(
    path: str,
    extensions: list[str] | None = None,
    max_depth: int = MAX_WORKSPACE_DEPTH,
) -> str:
    resolved = Path(path).expanduser()

    if not _is_path_allowed(resolved):
        raise FileNotAllowedError(str(resolved))
    if not resolved.is_dir():
        raise DirectoryNotFoundError(str(resolved))

    allowed_ext = set(extensions) if extensions else None
    parts: list[str] = []
    total_chars = 0

    def _collect(dir_path: Path, depth: int) -> None:
        nonlocal total_chars
        if depth > max_depth or total_chars >= MAX_WORKSPACE_CHARS:
            return
        try:
            entries = sorted(dir_path.iterdir())
        except PermissionError:
            return
        for entry in entries:
            if total_chars >= MAX_WORKSPACE_CHARS:
                break
            if entry.is_dir() and not entry.name.startswith("."):
                _collect(entry, depth + 1)
            elif entry.is_file():
                if allowed_ext and entry.suffix.lower() not in allowed_ext:
                    continue
                if entry.name.startswith("."):
                    continue
                try:
                    content = entry.read_text(encoding="utf-8", errors="replace")
                    remaining = MAX_WORKSPACE_CHARS - total_chars
                    if len(content) > remaining:
                        content = content[:remaining] + "\n[... abgeschnitten]"
                    rel = entry.relative_to(resolved)
                    parts.append(f"\n### 📄 {rel}\n```\n{content}\n```")
                    total_chars += len(content)
                except (UnicodeDecodeError, PermissionError, OSError):
                    continue

    _collect(resolved, 0)

    if not parts:
        return f"No matching files found in '{resolved}'."

    header = f"## 📁 Workspace: {resolved}\n{len(parts)} files loaded\n"
    result = header + "\n".join(parts)

    if total_chars >= MAX_WORKSPACE_CHARS:
        result += f"\n\n[⚠ workspace truncated: limit of {MAX_WORKSPACE_CHARS:,} characters reached]"

    return result


def _crop_image_bytes(image_bytes: bytes, region: list[int]) -> bytes | None:
    """Cropped [x1,y1,x2,y2] in original pixels. None on missing PIL/invalid region."""
    try:
        import io

        from PIL import Image
    except ImportError:
        return None
    try:
        x1, y1, x2, y2 = (int(v) for v in region)
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
        w, h = img.size
        x1, x2 = max(0, min(x1, w)), max(0, min(x2, w))
        y1, y2 = max(0, min(y1, h)), max(0, min(y2, h))
        if x2 <= x1 or y2 <= y1:
            return None
        buf = io.BytesIO()
        img.crop((x1, y1, x2, y2)).save(buf, format=(img.format or "PNG"))
        return buf.getvalue()
    except Exception:
        return None


async def analyze_image(
    path: str,
    question: str = "Describe this image in detail.",
    region: list[int] | None = None,
) -> str:
    resolved = Path(path).expanduser()

    if not _is_path_allowed(resolved):
        raise FileNotAllowedError(str(resolved))
    if not resolved.exists():
        raise FileNotFoundError(f"Image not found: '{resolved}'")
    if resolved.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        return (
            f"Unsupported image format: '{resolved.suffix}'. Supported: {', '.join(sorted(SUPPORTED_IMAGE_EXTENSIONS))}"
        )

    image_bytes = resolved.read_bytes()
    # region crop [x1,y1,x2,y2] in original pixels, before encoding — keeps the
    # effective resolution for small vision models (4b/12b) with small text.
    if region and len(region) == 4:
        image_bytes = _crop_image_bytes(image_bytes, region) or image_bytes
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    client = _get_shared_client()
    try:
        from core.model_provider import chosen_model

        response = await client.chat(
            model=chosen_model("the screen-vision tool"),
            messages=[
                {
                    "role": "user",
                    "content": question,
                    "images": [image_b64],
                },
            ],
            stream=False,
        )
        return str(response.message.content or "No description generated.")
    except Exception as exc:
        return f"[vision error: {exc}]"


async def take_screenshot() -> str:
    image_dir = Path(os.environ.get("EPHE_IMAGE_DIR", str(Path.home() / ".ephe" / "sessions" / "images")))
    image_dir.mkdir(parents=True, exist_ok=True)

    filename = f"screenshot_{int(time_module.time())}.png"
    filepath = image_dir / filename

    try:
        if sys.platform == "darwin":
            await asyncio.to_thread(
                subprocess.run, ["screencapture", "-x", str(filepath)], check=True
            )
        else:
            def _mss_capture():
                import mss
                with mss.mss() as sct:
                    sct.shot(output=str(filepath))
            await asyncio.to_thread(_mss_capture)

        return f"Here is the screen:\n\n![Screenshot](/images/{filename})"
    except subprocess.CalledProcessError as e:
        if sys.platform == "darwin":
            return (
                "[Screenshot failed: macOS blocked screen recording. Allow the terminal process access in System Settings > Privacy & Security > Screen Recording, then restart Ephe.]"
            )
        return f"[Screenshot failed: {e}]"
    except Exception as e:
        return f"[Screenshot failed: {e}]"


async def create_svg(
    svg_code: str,
    filename: str = "ephe_grafik.svg",
) -> str:
    import re

    try:
        from core.engine_config import artifact_output_dir

        downloads = artifact_output_dir()
        out = downloads / filename

        svg_code = re.sub(
            r"<script[^>]*>.*?</script[^>]*>", "", svg_code,
            flags=re.DOTALL | re.IGNORECASE
        )
        svg_code = re.sub(
            r"<foreignObject[^>]*>.*?</foreignObject[^>]*>", "", svg_code,
            flags=re.DOTALL | re.IGNORECASE
        )
        svg_code = re.sub(
            r'\s+on\w+\s*=\s*"[^"]*"', "", svg_code,
            flags=re.IGNORECASE
        )
        svg_code = re.sub(
            r"\s+on\w+\s*=\s*'[^']*'", "", svg_code,
            flags=re.IGNORECASE
        )
        svg_code = re.sub(
            r'href\s*=\s*"javascript:[^"]*"', 'href="#"', svg_code,
            flags=re.IGNORECASE
        )

        if "<svg" not in svg_code:
            svg_code = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300">\n{svg_code}\n</svg>'

        out.write_text(svg_code, encoding="utf-8")
        return f"SVG_FILE:{out}"

    except Exception as e:
        return f"[svg error: {e}]"
