"""Ephe — the film verbs a chat turn calls: a still, an effect, a bed, a status line.

Each verb builds its file under the workbench birth place and answers with the
marker line the chat route turns into an artifact card (``PNG_FILE:``/``WAV_FILE:``,
``core/artifact_markers.py``), followed by the one line a reader needs: what the
file is and where it landed. A verb whose WAV is not a spoken line says so on the
``AUDIO_ROLE:`` line above its marker, because the card has to name what it shows.
A verb that could not deliver answers with a refusal in the
``[tool-error '<name>': …]`` shape ``core/voice_synth.py`` uses, so the audit and
the goal loop read it as a failed call.

The audio comes from ``core/film_synth.py`` — no ffmpeg for a sound, no model for
a bed. ``film_status`` is where that stops: it probes this machine and says what
is there, what is missing and what the missing thing would unlock.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import uuid
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from core import film_cut
from core.artifact_markers import (
    AUDIO_ROLE_LINE_PREFIX,
    AUDIO_ROLE_MUSIC_BED,
    AUDIO_ROLE_SOUND_EFFECT,
)
from core.film_synth import MUSIC, SFX, SAMPLE_RATE, music_bed, render_sfx, write_wav

#: A still is a title card, not a document: past this the words stop fitting.
MAX_CARD_CHARS = 400
MIN_CARD_SIZE = 160
MAX_CARD_SIZE = 4096
MAX_SFX_SECONDS = 30.0
MIN_BARS = 1
MAX_BARS = 64
MIN_BPM = 40
MAX_BPM = 220

#: A probe that hangs must not hang the status line with it.
_PROBE_TIMEOUT_SECONDS = 10

#: A user's own CC0 effects, when they have them: one folder, read at the call.
SFX_DIR_ENV = "EPHE_SFX_DIR"

#: One resolver for the library folder. The env wins over the stored setting,
#: so an operator can point a single run elsewhere without changing the app.
def _sfx_folder() -> tuple[str, Path | None]:
    from core.settings_schema import deep_value

    raw = str(os.environ.get(SFX_DIR_ENV) or deep_value("advanced.film_sfx_dir") or "").strip()
    if not raw:
        return "", None
    folder = Path(raw).expanduser()
    return raw, folder if folder.is_dir() else None


_HEX_COLOR = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")

_STYLES: dict[str, tuple[str, str, str, int]] = {
    # (background, foreground, accent, base point size)
    "title": ("#101820", "#F5F7FA", "#4CC2A0", 96),
    "card": ("#F5F7FA", "#12212B", "#2A6F97", 64),
    "quote": ("#1B1B14", "#EFE9DA", "#C9A227", 56),
    "stat": ("#0B3D2E", "#E7F6EF", "#7FD8AE", 150),
}


def _refusal(verb: str, detail: str) -> str:
    return f"[tool-error '{verb}': {detail}]"


def _artifact_dir() -> Path:
    from core.engine_config import artifact_output_dir

    return artifact_output_dir()


def _target(out: str | None, kind: str, name: str, extension: str) -> Path:
    """An absolute ``out`` is the user naming the path; anything else is a name."""
    raw = (out or "").strip()
    if raw:
        candidate = Path(raw).expanduser()
        if candidate.is_absolute():
            candidate.parent.mkdir(parents=True, exist_ok=True)
            return candidate
        raw = candidate.name
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", raw or f"{kind}_{name}")
    if not slug.lower().endswith(extension):
        slug += extension
    stamp = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    folder = _artifact_dir()
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{stamp}_{slug}"


def _available(table: Mapping[str, object]) -> str:
    return ", ".join(sorted(table))


#: Outlines worth setting a card in, tried in order; the built-in face is the last resort.
_FONT_CANDIDATES: tuple[str, ...] = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
)


def _font(size: int):
    """The first outline font this machine has, the built-in face as the last resort."""
    from PIL import ImageFont

    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:  # Pillow before 10.1 has no scalable built-in font
        return ImageFont.load_default()


def _wrap(text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        current = ""
        for word in paragraph.split():
            trial = f"{current} {word}".strip()
            if current and font.getlength(trial) > max_width:
                lines.append(current)
                current = word
            else:
                current = trial
        lines.append(current)
    return [line for line in lines if line]


def _color(value: str | None, fallback: str) -> str:
    if value is None or not str(value).strip():
        return fallback
    return str(value).strip()


def _draw_card(
    text: str,
    target: Path,
    width: int,
    height: int,
    style: str,
    bg: str,
    fg: str,
) -> None:
    from PIL import Image, ImageDraw

    _, _, accent, base = _STYLES[style]
    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)
    margin = max(24, width // 12)
    body_width = width - 2 * margin

    if style == "stat":
        head, _, tail = text.partition("\n")
        head = head.strip() or text.strip()
        tail = tail.strip()
        head_font = _font(base)
        draw.text(
            (width / 2, height / 2 - base * 0.35),
            head,
            font=head_font,
            fill=fg,
            anchor="mm",
        )
        if tail:
            caption_font = _font(max(16, base // 5))
            draw.text(
                (width / 2, height / 2 + base * 0.45),
                tail,
                font=caption_font,
                fill=accent,
                anchor="mm",
            )
        image.save(target, "PNG")
        return

    size = base if style == "title" else base - 8
    font = _font(size)
    lines = _wrap(text, font, body_width)
    line_height = int(font.getlength("H") * 1.35) or int(size * 1.35)
    block = line_height * len(lines)
    top = (height - block) / 2.0
    if style == "quote":
        draw.rectangle((margin, top - 14, margin + 6, top + block), fill=accent)
    for index, line in enumerate(lines):
        draw.text(
            (width / 2.0, top + index * line_height),
            line,
            font=font,
            fill=fg,
            anchor="ma",
        )
    image.save(target, "PNG")


async def film_card(
    text: str,
    out: str | None = None,
    width: int = 1280,
    height: int = 720,
    style: str = "title",
    bg: str | None = None,
    fg: str | None = None,
) -> str:
    """A typographic still: wrapped, centred text on a palette, written as a PNG.

    Returns the ``PNG_FILE:`` marker line for the chat route plus the dimensions
    and the path; a card it cannot make answers with a refusal naming the limit.
    """
    body = (text or "").strip()
    if not body:
        return _refusal("film_card", "text is empty — pass the words to set on the card")
    if len(body) > MAX_CARD_CHARS:
        return _refusal(
            "film_card",
            f"text is {len(body)} characters, over the {MAX_CARD_CHARS} a still holds "
            "— shorten it or use create_pdf",
        )
    if style not in _STYLES:
        return _refusal(
            "film_card",
            f"unknown style '{style}' — available: {_available(_STYLES)}",
        )
    for label, value in (("width", width), ("height", height)):
        if not isinstance(value, int) or not MIN_CARD_SIZE <= value <= MAX_CARD_SIZE:
            return _refusal(
                "film_card",
                f"{label} must be an integer between {MIN_CARD_SIZE} and "
                f"{MAX_CARD_SIZE}, got {value!r}",
            )
    palette_bg = _color(bg, _STYLES[style][0])
    palette_fg = _color(fg, _STYLES[style][1])
    for label, colour in (("bg", palette_bg), ("fg", palette_fg)):
        if not _HEX_COLOR.match(colour):
            return _refusal(
                "film_card", f"{label} must be a #rgb or #rrggbb colour, got '{colour}'"
            )
    try:
        import PIL  # noqa: F401  (the probe is the import succeeding)
    except ImportError:
        return _refusal(
            "film_card",
            "Pillow is not installed — 'pip install pillow' unlocks the typographic stills",
        )

    target = _target(out, "card", style, ".png")
    try:
        await asyncio.to_thread(
            _draw_card, body, target, int(width), int(height), style, palette_bg, palette_fg
        )
    except Exception as exc:
        return _refusal("film_card", f"could not render the still — {type(exc).__name__}: {exc}")
    return (
        f"PNG_FILE:{target}\n"
        f"{style.title()} card {width}x{height} px at {target}"
    )


async def film_sound(name: str | None = None, seconds: float | None = None, out: str | None = None) -> str:
    """One named effect as a 48 kHz stereo WAV, announced as a ``sound_effect``.

    An omitted name is answered with the effect list rather than a guessed effect: a
    sound nobody asked for is worse than one round spent naming it.
    """
    key = (name or "").strip()
    if not key:
        return _refusal("film_sound", f"no effect named — available: {_available(SFX)}")
    sourced = None
    if key not in SFX:
        _, folder = _sfx_folder()
        if folder is not None:
            sourced = next(
                (wav for wav in folder.glob("*.wav")
                 if wav.is_file() and wav.stem.lower() == key.lower()),
                None,
            )
    if key not in SFX and sourced is None:
        return _refusal(
            "film_sound", f"unknown sound '{name}' — available: {_available(SFX)}"
        )
    if seconds is not None:
        try:
            asked = float(seconds)
        except (TypeError, ValueError):
            return _refusal("film_sound", f"seconds must be a number, got {seconds!r}")
        if not 0.0 < asked <= MAX_SFX_SECONDS:
            return _refusal(
                "film_sound",
                f"seconds must be between 0 and {MAX_SFX_SECONDS}, got {asked}",
            )
    else:
        asked = SFX[key].seconds if key in SFX else 0.0

    target = _target(out, "sfx", key, ".wav")
    try:
        if sourced is None:
            await asyncio.to_thread(_write_effect, key, asked, target)
        else:
            await asyncio.to_thread(shutil.copyfile, sourced, target)
    except Exception as exc:
        return _refusal("film_sound", f"could not deliver the sound — {exc}")
    if sourced is not None:
        return (
            f"{AUDIO_ROLE_LINE_PREFIX}{AUDIO_ROLE_SOUND_EFFECT}\n"
            f"WAV_FILE:{target}\n"
            f"{key} from your SFX library ({sourced}), {target}"
        )
    return (
        f"{AUDIO_ROLE_LINE_PREFIX}{AUDIO_ROLE_SOUND_EFFECT}\n"
        f"WAV_FILE:{target}\n"
        f"{key} {asked:.2f} s at {SAMPLE_RATE} Hz stereo, {target}"
    )


def _write_effect(key: str, seconds: float, target: Path) -> None:
    write_wav(target, render_sfx(key, seconds))


def _write_bed(name: str, bars: int, bpm: int, seed: int, target: Path) -> None:
    write_wav(target, music_bed(name, bars=bars, bpm=bpm, seed=seed))


async def film_music(
    name: str = "calm",
    bars: int = 8,
    bpm: int = 96,
    seed: int = 0,
    out: str | None = None,
) -> str:
    """One named music bed, deterministic per (name, bpm, bars, seed).

    Announced as a ``music_bed``; the answer carries the ``WAV_FILE:`` marker line
    plus the length it rendered.
    """
    key = (name or "").strip()
    if key not in MUSIC:
        return _refusal(
            "film_music", f"unknown bed '{name}' — available: {_available(MUSIC)}"
        )
    if not isinstance(bars, int) or not MIN_BARS <= bars <= MAX_BARS:
        return _refusal(
            "film_music",
            f"bars must be an integer between {MIN_BARS} and {MAX_BARS}, got {bars!r}",
        )
    if not isinstance(bpm, int) or not MIN_BPM <= bpm <= MAX_BPM:
        return _refusal(
            "film_music",
            f"bpm must be an integer between {MIN_BPM} and {MAX_BPM}, got {bpm!r}",
        )
    if not isinstance(seed, int):
        return _refusal("film_music", f"seed must be an integer, got {seed!r}")

    target = _target(out, "music", key, ".wav")
    try:
        await asyncio.to_thread(_write_bed, key, int(bars), int(bpm), int(seed), target)
    except Exception as exc:
        return _refusal("film_music", f"could not synthesise the bed — {exc}")
    seconds = bars * 4 * 60.0 / bpm
    return (
        f"{AUDIO_ROLE_LINE_PREFIX}{AUDIO_ROLE_MUSIC_BED}\n"
        f"WAV_FILE:{target}\n"
        f"{key} bed, {bars} bars at {bpm} bpm ({seconds:.1f} s) at "
        f"{SAMPLE_RATE} Hz stereo, {target}"
    )


def _clip_number(
    verb: str, label: str, value: object, low: float, high: float
) -> tuple[float | None, str]:
    """One validated numeric argument with its refusal sentence."""
    try:
        asked = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None, _refusal(
            verb, f"{label} must be a number between {low} and {high}, got {value!r}"
        )
    if not low <= asked <= high:
        return None, _refusal(
            verb, f"{label} must be between {low} and {high}, got {asked}"
        )
    return asked, ""


def _clip_input(verb: str, label: str, value: object, suffixes: frozenset[str]) -> tuple[Path | None, str]:
    """One validated input path: readable here, on disk, carrying one suffix."""
    raw = str(value or "").strip()
    if not raw:
        return None, _refusal(verb, f"{label} is empty — pass the path of the {label} file")
    path = Path(raw).expanduser()
    if not path.is_file():
        return None, _refusal(verb, f"{label} {path} is not a file")
    if path.suffix.lower() not in suffixes:
        wanted = ", ".join(sorted(suffixes))
        return None, _refusal(
            verb,
            f"{label} {path} carries {path.suffix or 'no extension'} — pass one of {wanted}",
        )
    if not _cut_input_allowed(path):
        return None, _refusal(
            verb,
            f"{label} {path} sits outside the artifact folder, the voice folder and "
            "the workspace roots this tool may read",
        )
    return path, ""


def _cut_input_allowed(path: Path) -> bool:
    """Read access for a cut input: the workbench and the voice folder, granted roots next.

    ``_is_path_allowed`` denies ``~/.ephe``, where the artifact workbench and the
    piper audio folder live, so both are opened here — the folders this verb's own
    sibling verbs write into. The whole workbench is open, because a cut is routinely
    made of a card from an earlier turn and a render thread carries no session context
    to scope by. Every other path passes the kernel's read rule.
    """
    from core.path_guard import within
    from core.tools.base import _is_path_allowed

    try:
        from core.artifact_workbench import in_workbench

        if in_workbench(path):
            return True
    except Exception:
        pass
    try:
        from core.voice_synth import audio_dir

        if within(path, audio_dir()):
            return True
    except Exception:
        pass
    return _is_path_allowed(path)


async def film_clip(
    shots: list,
    out: str | None = None,
    fps: int = 24,
    width: int = 1280,
    height: int = 720,
    audio: str | None = None,
    music: str | None = None,
    music_gain: float = 0.25,
    fade: float = 0.4,
    wait_seconds: float = 120,
) -> str:
    """Cut shots into one mp4; the ffmpeg argv comes from ``core/film_cut.py``.

    Answers with the ``VIDEO_FILE:`` marker line plus duration, resolution and
    shot count; a render still running answers with its job id for ``film_job``.
    Every bound refused names the bound and the fix.
    """
    verb = "film_clip"
    ffmpeg = film_cut.ffmpeg_binary()
    if ffmpeg is None:
        return _refusal(
            verb,
            "ffmpeg is not on PATH — the cut encodes with it; install it "
            f"({film_cut.FFMPEG_INSTALL_HINT}) and call again",
        )
    if not isinstance(shots, (list, tuple)) or not shots:
        return _refusal(
            verb,
            "shots must be a list of at least one {image, duration, caption} object",
        )
    if len(shots) > film_cut.MAX_SHOTS:
        return _refusal(
            verb,
            f"{len(shots)} shots is over the cap of {film_cut.MAX_SHOTS} — cut two "
            f"shorter clips of at most {film_cut.MAX_SHOTS} shots or drop the least "
            "important ones",
        )
    if isinstance(fps, bool) or not isinstance(fps, int) or not film_cut.MIN_FPS <= fps <= film_cut.MAX_FPS:
        return _refusal(
            verb,
            f"fps must be an integer between {film_cut.MIN_FPS} and "
            f"{film_cut.MAX_FPS}, got {fps!r}",
        )
    for label, value in (("width", width), ("height", height)):
        if isinstance(value, bool) or not isinstance(value, int) or not MIN_CARD_SIZE <= value <= MAX_CARD_SIZE:
            return _refusal(
                verb,
                f"{label} must be an integer between {MIN_CARD_SIZE} and "
                f"{MAX_CARD_SIZE}, got {value!r}",
            )
    gain, refusal = _clip_number(verb, "music_gain", music_gain, film_cut.MIN_MUSIC_GAIN, film_cut.MAX_MUSIC_GAIN)
    if refusal:
        return refusal
    fade_seconds, refusal = _clip_number(verb, "fade", fade, film_cut.MIN_FADE_SECONDS, film_cut.MAX_FADE_SECONDS)
    if refusal:
        return refusal
    wait, refusal = _clip_number(verb, "wait_seconds", wait_seconds, film_cut.MIN_WAIT_SECONDS, film_cut.MAX_WAIT_SECONDS)
    if refusal:
        return refusal
    assert gain is not None and fade_seconds is not None and wait is not None

    target = _target(out, "clip", "cut", ".mp4")
    live = film_cut.running_job_for(target)
    if live is not None:
        return _refusal(
            verb,
            f"{target} already has a render running (job {live.id}) — ask "
            "film_job for it before starting another cut at this path",
        )

    prepared: list[film_cut.CutShot] = []
    captions: list[tuple[str, Path]] = []
    for index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            return _refusal(
                verb, f"shot {index} is {type(shot).__name__}, expected an object with image and duration"
            )
        image, refusal = _clip_input(verb, f"shot {index} image", shot.get("image"), film_cut.IMAGE_SUFFIXES)
        if refusal:
            return refusal
        assert image is not None
        try:
            duration = float(str(shot.get("duration")))
        except (TypeError, ValueError):
            return _refusal(
                verb, f"shot {index} duration {shot.get('duration')!r} is not a number of seconds"
            )
        if not film_cut.MIN_SHOT_SECONDS <= duration <= film_cut.MAX_SHOT_SECONDS:
            return _refusal(
                verb,
                f"shot {index} duration must be between {film_cut.MIN_SHOT_SECONDS} "
                f"and {film_cut.MAX_SHOT_SECONDS} seconds, got {duration}",
            )
        caption_png: Path | None = None
        body = str(shot.get("caption") or "").strip()
        if body:
            if len(body) > MAX_CARD_CHARS:
                return _refusal(
                    verb,
                    f"shot {index} caption is {len(body)} characters, over the "
                    f"{MAX_CARD_CHARS} a card carries — shorten the caption",
                )
            caption_png = _target(None, "clipcap", f"shot{index}", ".png")
            captions.append((body, caption_png))
        prepared.append(film_cut.CutShot(image=image, duration=duration, caption_png=caption_png))

    voice: Path | None = None
    if audio is not None and str(audio).strip():
        voice, refusal = _clip_input(verb, "audio", audio, frozenset({".wav"}))
        if refusal:
            return refusal
    bed: Path | None = None
    if music is not None and str(music).strip():
        bed, refusal = _clip_input(verb, "music", music, frozenset({".wav"}))
        if refusal:
            return refusal

    for body, png in captions:
        try:
            await asyncio.to_thread(film_cut.draw_caption_png, body, png, int(width), int(height))
        except Exception as exc:
            return _refusal(
                verb, f"the caption of one shot could not be drawn — {type(exc).__name__}: {exc}"
            )
    argv = film_cut.build_cut_argv(
        ffmpeg=ffmpeg,
        shots=prepared,
        target=target,
        fps=int(fps),
        width=int(width),
        height=int(height),
        audio=voice,
        music=bed,
        music_gain=gain,
        fade=fade_seconds,
    )
    job, busy = film_cut.start_job(argv, target, len(prepared))
    if job is None:
        return _refusal(verb, busy)
    if wait > 0:
        await asyncio.to_thread(job.done.wait, wait)
    total = sum(shot.duration for shot in prepared)
    if job.state == film_cut.STATE_RUNNING:
        return (
            f"still rendering (job {job.id}) — ask film_job for it\n"
            f"the cut will land at {target}"
        )
    if job.state == film_cut.STATE_DONE:
        return (
            f"VIDEO_FILE:{target}\n"
            f"{width}x{height}, {len(prepared)} shots, {total:.2f} s at {fps} fps"
        )
    if job.state == film_cut.STATE_CANCELLED:
        return _refusal(verb, f"job {job.id} was cancelled before the cut finished")
    return _refusal(verb, f"ffmpeg exited {job.returncode} — {job.error}")


async def film_job(
    job_id: str | None = None,
    action: str = "status",
    wait_seconds: float = 30,
) -> str:
    """The job table: one line per render, the marker line again when one lands.

    Never raises: a table that cannot answer says so in the refusal shape.
    """
    verb = "film_job"
    try:
        if action not in ("status", "cancel"):
            return _refusal(verb, f"unknown action '{action}' — available: status, cancel")
        wait, refusal = _clip_number(
            verb, "wait_seconds", wait_seconds, film_cut.MIN_WAIT_SECONDS, film_cut.MAX_WAIT_SECONDS
        )
        if refusal:
            return refusal
        assert wait is not None
        if not job_id or not str(job_id).strip():
            if action == "cancel":
                return _refusal(verb, "cancel names one job — pass the job_id film_clip answered with")
            lines = film_cut.job_lines()
            return "\n".join(lines) if lines else "no cut jobs in this session yet"
        job = film_cut.find_job(str(job_id).strip())
        if job is None:
            return _refusal(
                verb, f"no job '{job_id}' — known ids: {', '.join(film_cut.job_ids()) or 'none'}"
            )
        if action == "cancel":
            return await asyncio.to_thread(film_cut.cancel_job, job)
        if job.state == film_cut.STATE_RUNNING and wait > 0:
            await asyncio.to_thread(job.done.wait, wait)
        line = film_cut.job_line(job)
        if job.state == film_cut.STATE_DONE:
            return f"VIDEO_FILE:{job.target}\n{line}"
        return line
    except Exception as exc:
        return _refusal(verb, f"the job table did not answer — {type(exc).__name__}: {exc}")


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, capture_output=True, text=True, timeout=_PROBE_TIMEOUT_SECONDS, check=False
    )


def _has_filter(output: str, name: str) -> bool:
    """Whether ``ffmpeg -filters`` lists ``name`` in its name column.

    The row is ``<flags> <name> <io> <description>``; only the leading columns are
    read, so a filter whose description mentions the name cannot be a false yes.
    """
    for line in (output or "").splitlines():
        if name in line.split()[:3]:
            return True
    return False


def _ffmpeg_lines() -> list[str]:
    binary = shutil.which("ffmpeg")
    if not binary:
        return [
            "ffmpeg: not on PATH — burned-in titles, subtitle burns and the cut "
            "itself need it; install it (brew install ffmpeg / apt install ffmpeg)"
        ]
    lines: list[str] = []
    version = "version unknown"
    filters = ""
    try:
        probe = _run([binary, "-hide_banner", "-version"])
        version = _first_line(probe.stdout) or f"exit {probe.returncode}"
    except Exception as exc:
        lines.append(f"ffmpeg: found at {binary} but the version did not answer ({exc.__class__.__name__})")
        return lines
    try:
        filters = _run([binary, "-hide_banner", "-filters"]).stdout
    except Exception as exc:
        filters = ""
        lines.append(f"ffmpeg: the filter list did not answer ({exc.__class__.__name__})")
    drawtext = _has_filter(filters, "drawtext")
    subtitles = _has_filter(filters, "subtitles")
    lines.append(
        f"ffmpeg: {version} at {binary} — "
        f"drawtext {'yes' if drawtext else 'no'}, "
        f"subtitles {'yes' if subtitles else 'no'}"
    )
    if not drawtext:
        lines.append(
            "ffmpeg drawtext: missing — titles drawn over a clip need a build with "
            "libfreetype (the usual brew/apt build carries it)"
        )
    if not subtitles:
        lines.append(
            "ffmpeg subtitles: missing — burning a subtitle track needs a build with "
            "libass"
        )
    return lines


def _voice_lines() -> list[str]:
    """What core/voice_synth.py would use on this machine, read from its own config."""
    from core.voice_config import (
        load_voice_config,
        piper_binary,
        piper_voice_installed,
    )

    binary = piper_binary()
    if not binary:
        return [
            "voice: no piper binary — speech over a cut needs one "
            "(brew install piper, then ephe voice install <voice>); "
            "without it the audio route's cloud path answers instead"
        ]
    voice = load_voice_config().piper_voice
    if not piper_voice_installed(voice):
        return [
            f"voice: piper at {binary} but no voice '{voice}' installed — "
            "ephe voice install <voice> unlocks local speech"
        ]
    return [f"voice: piper at {binary}, local voice '{voice}' installed"]


def _pillow_lines() -> list[str]:
    try:
        from PIL import Image  # noqa: F401  (the probe is the import succeeding)
        from PIL import __version__ as pillow_version
    except ImportError:
        return [
            "Pillow: not installed — film_card needs it; pip install pillow unlocks "
            "the typographic stills"
        ]
    face = next((path for path in _FONT_CANDIDATES if Path(path).is_file()), None)
    if face is None:
        return [
            f"Pillow: {pillow_version}, but no outline font was found — a card renders "
            f"in the built-in face only; install a TrueType font for a readable still"
        ]
    return [f"Pillow: {pillow_version}, cards render with the face at {face}"]


def _sfx_library_lines() -> list[str]:
    raw, folder = _sfx_folder()
    if not raw:
        return [
            "SFX library: no folder set — set advanced.film_sfx_dir or "
            f"{SFX_DIR_ENV} to a folder of your own .wav files and they become "
            "available by name beside the synthesised effects"
        ]
    if folder is None:
        return [
            f"SFX library: {raw} is not a directory "
            "— nothing beyond the synthesised effects is available"
        ]
    count = len([path for path in folder.glob("*.wav") if path.is_file()])
    return [
        f"SFX library: {count} wav file(s) in {folder} — usable by name in a cut, "
        "the synthesised effects stay the default"
    ]


async def film_status() -> str:
    """What this machine can make right now, one probed verdict per line.

    Every line states what was found. A capability that was not probed is not
    claimed; a missing one names what it would unlock.
    """
    lines = await asyncio.to_thread(_collect_status)
    return "\n".join(lines)


def _render_lines() -> list[str]:
    """The kept render jobs, so one status call answers what is cutting right now.

    ``film_job`` answers one id; a person or a model asking "what is rendering" has no
    id yet. The table is process-local: it answers for the server that holds it and
    is rebuilt on restart, so a finished job is forgotten when the process ends.
    """
    try:
        from core.film_cut import job_lines

        jobs = job_lines()
    except Exception as exc:
        return [f"renders: the job table did not answer ({exc.__class__.__name__})"]
    if not jobs:
        return ["renders: none in this server process"]
    lines = [f"renders: {len(jobs)} job(s) in this server process"]
    lines.extend(jobs)
    lines.append("job table is rebuilt on restart — a finished job is forgotten when the process ends")
    return lines


def _collect_status() -> list[str]:
    lines: list[str] = []
    lines.extend(_ffmpeg_lines())
    try:
        lines.extend(_voice_lines())
    except Exception as exc:
        lines.append(f"voice: the local voice config did not answer ({exc.__class__.__name__})")
    lines.extend(_pillow_lines())
    lines.extend(_sfx_library_lines())
    lines.extend(_render_lines())
    try:
        lines.append(f"Files land in {_artifact_dir()}")
    except Exception as exc:
        lines.append(f"Files: the artifact folder did not answer ({exc.__class__.__name__})")
    lines.append(
        f"Synthesis: {len(SFX)} effects ({_available(SFX)}) and "
        f"{len(MUSIC)} beds ({_available(MUSIC)}), all {SAMPLE_RATE} Hz stereo"
    )
    return lines


#: The offer-list schemas for the six verbs.
FILM_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "film_status",
            "description": (
                "Reports what this machine can make for a film right now: the ffmpeg "
                "binary with its version and whether the drawtext and subtitles filters "
                "are compiled in, the local voice engine, Pillow and the outline font a "
                "card would set in, any CC0 SFX folder the user installed, and the folder "
                "artifacts land in. Returns one verdict per line; a capability that was "
                "not probed is not claimed."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "film_card",
            "description": (
                "Renders a typographic still with Pillow: the text wrapped and centred on "
                "a palette, as a PNG in the artifact folder. Returns the PNG_FILE marker "
                "line plus the dimensions and path. Refuses empty or oversized text with "
                "the character limit named."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The words to set on the card, up to 400 characters.",
                    },
                    "out": {
                        "type": "string",
                        "description": (
                            "Optional output file name, or an absolute path to write "
                            "instead of the artifact folder."
                        ),
                    },
                    "width": {
                        "type": "integer",
                        "description": "Width in pixels, 160 to 4096. Default 1280.",
                    },
                    "height": {
                        "type": "integer",
                        "description": "Height in pixels, 160 to 4096. Default 720.",
                    },
                    "style": {
                        "type": "string",
                        "enum": ["title", "card", "quote", "stat"],
                        "description": (
                            "The layout and palette: title for a large centred headline, "
                            "card for a lighter block, quote for an attributed line with "
                            "an accent rule, stat for one large figure with a caption "
                            "under it (the caption is the text after the first newline)."
                        ),
                    },
                    "bg": {
                        "type": "string",
                        "description": "Optional background colour as #rgb or #rrggbb.",
                    },
                    "fg": {
                        "type": "string",
                        "description": "Optional text colour as #rgb or #rrggbb.",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "film_sound",
            "description": (
                "Synthesises one named sound effect on the standard library alone and "
                "writes it as a 48 kHz stereo WAV in the artifact folder. Returns the "
                "WAV_FILE marker line plus the duration and sample rate. An unknown name "
                "is refused with the available names listed: click, tick, pop, thud, "
                "whoosh, riser, chime, success, error, ui_hover, glitch, countdown."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "The effect to render: click, tick, pop, thud, whoosh, riser, "
                            "chime, success, error, ui_hover, glitch or countdown. Omit it "
                            "to get the list back as the refusal."
                        ),
                    },
                    "seconds": {
                        "type": "number",
                        "description": (
                            "Optional length in seconds up to 30; omit for the effect's "
                            "own natural duration."
                        ),
                    },
                    "out": {
                        "type": "string",
                        "description": (
                            "Optional output file name, or an absolute path to write "
                            "instead of the artifact folder."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "film_music",
            "description": (
                "Synthesises a music bed: a chord progression over the asked bars at a "
                "bpm, with a kick and a cymbal from filtered noise, written as a 48 kHz "
                "stereo WAV in the artifact folder. Deterministic for one (name, bpm, "
                "bars, seed). Returns the WAV_FILE marker line plus the rendered length. "
                "Available beds: calm, driving, playful, tense, corporate."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "The bed to render: calm, driving, playful, tense or "
                            "corporate. Default calm."
                        ),
                    },
                    "bars": {
                        "type": "integer",
                        "description": "How many 4/4 bars to render, 1 to 64. Default 8.",
                    },
                    "bpm": {
                        "type": "integer",
                        "description": (
                            "Tempo in beats per minute, 40 to 220. Default 96."
                        ),
                    },
                    "seed": {
                        "type": "integer",
                        "description": (
                            "Variation seed: the same seed gives byte-identical audio."
                        ),
                    },
                    "out": {
                        "type": "string",
                        "description": (
                            "Optional output file name, or an absolute path to write "
                            "instead of the artifact folder."
                        ),
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "film_clip",
            "description": (
                "Cuts a list of shots into one mp4 with ffmpeg: each shot is a still "
                "looped for its duration, scaled and padded to the frame; an optional "
                "caption is drawn by Pillow and overlaid; a voice WAV rides over an "
                "optional music bed at music_gain. At most 16 shots. The file lands in "
                "the artifact folder and the answer carries the VIDEO_FILE marker line "
                "plus duration, resolution and shot count. A render that needs longer "
                "than wait_seconds keeps running and answers with its job id for "
                "film_job. Every refusal names the bound it hit: the shot cap, a "
                "missing or unreadable still, a caption over 400 characters, an "
                "impossible fps, wait_seconds outside 0 to 600, or a missing ffmpeg."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "shots": {
                        "type": "array",
                        "description": "The shots in cut order, 1 to 16 entries.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "image": {
                                    "type": "string",
                                    "description": (
                                        "Path to a .png or .jpg still, as film_card "
                                        "writes or as any readable file carries."
                                    ),
                                },
                                "duration": {
                                    "type": "number",
                                    "description": "Seconds the still holds, 0.04 to 300.",
                                },
                                "caption": {
                                    "type": "string",
                                    "description": (
                                        "Optional caption drawn over the shot, up to "
                                        "400 characters."
                                    ),
                                },
                            },
                            "required": ["image", "duration"],
                        },
                    },
                    "out": {
                        "type": "string",
                        "description": (
                            "Optional output file name, or an absolute path to write "
                            "instead of the artifact folder."
                        ),
                    },
                    "fps": {
                        "type": "integer",
                        "description": "Frames per second, 1 to 240. Default 24.",
                    },
                    "width": {
                        "type": "integer",
                        "description": "Frame width in pixels, 160 to 4096. Default 1280.",
                    },
                    "height": {
                        "type": "integer",
                        "description": "Frame height in pixels, 160 to 4096. Default 720.",
                    },
                    "audio": {
                        "type": "string",
                        "description": "Optional voice track: a WAV from synthesize.",
                    },
                    "music": {
                        "type": "string",
                        "description": (
                            "Optional bed: a WAV from film_music, mixed under the "
                            "voice at music_gain."
                        ),
                    },
                    "music_gain": {
                        "type": "number",
                        "description": "Level of the music bed, 0 to 1. Default 0.25.",
                    },
                    "fade": {
                        "type": "number",
                        "description": (
                            "Fade-in and fade-out in seconds at head and tail, 0 to "
                            "10. Default 0.4."
                        ),
                    },
                    "wait_seconds": {
                        "type": "number",
                        "description": (
                            "How long to wait for the render, 0 to 600. Default 120; "
                            "past the wait the job keeps running and film_job answers "
                            "for it."
                        ),
                    },
                },
                "required": ["shots"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "film_job",
            "description": (
                "Reports and steers film_clip renders. With no id it answers one line "
                "per known job (id, state, shots, started, path); with an id it "
                "answers that job and repeats the VIDEO_FILE marker line once the "
                "render landed. wait_seconds blocks on a single id for that long. "
                "action cancel kills the ffmpeg process group of a running job and "
                "marks it cancelled."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The job id film_clip answered with.",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["status", "cancel"],
                        "description": "status reports the job, cancel kills a running one. Default status.",
                    },
                    "wait_seconds": {
                        "type": "number",
                        "description": "With one id, how long to wait for it, 0 to 600. Default 30.",
                    },
                },
            },
        },
    },
]
