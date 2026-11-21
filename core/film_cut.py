"""The cut itself: the ffmpeg argv, the caption cards it overlays, the job table.

``core/tools/film_tools.py`` keeps the verbs thin; everything here is the render.
The argv builder is one pure function returning ``list[str]`` for ``subprocess``:
the filter graph is assembled from a list of parts and carries numbers and label
names only, so no word a caller passes can reach ffmpeg as filter text. Captions
travel as Pillow-rendered transparent PNGs — this machine's ffmpeg 8.1.2 build
carries neither drawtext nor subtitles (measured against its ``-version``
configuration line), so burned-in words can only arrive as pixels.

The job table is process-wide on purpose: a cut that outlived its verb call has
to stay answerable from ``film_job``, and one output path may hold one render.

The table is process-local: it answers for the server that holds it and is
rebuilt on restart, so a finished job is forgotten when the process ends. The
render slot is bounded by ``RENDER_TIMEOUT_SECONDS``: an encoder that stops
answering is killed and its job recorded failed, freeing the slot.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

#: Bounds the verbs enforce before they ask anything of this module.
MAX_SHOTS = 16
MIN_SHOT_SECONDS = 0.04
MAX_SHOT_SECONDS = 300.0
MIN_FPS = 1
MAX_FPS = 240
MIN_WAIT_SECONDS = 0
MAX_WAIT_SECONDS = 600
MIN_MUSIC_GAIN = 0.0
MAX_MUSIC_GAIN = 1.0
MIN_FADE_SECONDS = 0.0
MAX_FADE_SECONDS = 10.0
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg"})

#: The silent stand-in so every cut carries an audio stream and aac encodes.
SILENT_SOURCE = "anullsrc=channel_layout=stereo:sample_rate=48000"

#: The encode both films in this repo already use (render_onboarding_film.py).
#:
#: A hardware encoder was measured against this line and lost. ffmpeg 8.1.2 on an Apple M4,
#: 2026-11-19, one argv from `build_cut_argv` with this line as its only difference: six shots
#: of 5 s at 1280x720 and 24 fps took 1.11 s at 0.28 MB here, and 1.66 s at 0.92 MB with
#: `-c:v h264_videotoolbox -q:v 50`. Over worst-case noise plates at 1920x1080 videotoolbox won
#: the clock, 1.26 s against 1.77 s, and paid 20.98 MB against 4.42 MB. The time of a cut of
#: stills sits in ffmpeg's start and the filter chain, so the encoder decides the file size here
#: and little else — and these files are delivered into a chat. A swap needs its own measurement
#: over the material the studio actually cuts.
VIDEO_ENCODE_ARGS = ["-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", "20"]
AUDIO_ENCODE_ARGS = ["-c:a", "aac", "-b:a", "192k"]

FFMPEG_INSTALL_HINT = "brew install ffmpeg (macOS) or apt install ffmpeg (Linux)"

STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"

#: How much of ffmpeg's stderr a failed job keeps for the refusal.
STDERR_TAIL_LINES = 4
STDERR_TAIL_CHARS = 400

#: A render is the heaviest thing this product does: one encoder process per cut,
#: each holding a full x264 encode. Two at once keeps the machine usable.
MAX_CONCURRENT_RENDERS = 2

#: A hung encoder holds one of these two slots until the user cancels or this
#: wall-clock bound fires. Long cuts are an advertised capability, so the bound
#: is an hour: only an encoder that stopped answering for an hour is killed and
#: its job recorded failed, leaving the slot free for the next cut.
RENDER_TIMEOUT_SECONDS = 3600

#: The table answers for the session, and a server lives for days. Finished jobs
#: older than the newest of these many are forgotten; a running job never is.
MAX_KEPT_JOBS = 32


def ffmpeg_binary() -> Optional[str]:
    """The ffmpeg on PATH, when this machine has one."""
    return shutil.which("ffmpeg")


def _seconds(value: float) -> str:
    """A validated number in the one shape a filter argument may carry."""
    return f"{float(value):.3f}"


@dataclass(frozen=True)
class CutShot:
    """One validated shot: the still, its seconds, the caption PNG when it has one."""

    image: Path
    duration: float
    caption_png: Optional[Path] = None


def build_cut_argv(
    *,
    ffmpeg: str,
    shots: list[CutShot],
    target: Path,
    fps: int,
    width: int,
    height: int,
    audio: Optional[Path] = None,
    music: Optional[Path] = None,
    music_gain: float = 0.25,
    fade: float = 0.4,
) -> list[str]:
    """One ffmpeg argv for the whole cut; the caller validates every argument.

    The function touches no disk and no environment, which is what lets the
    unit tests read the contract without the binary. Every input path enters as
    its own ``-i`` element, and the filter graph is joined from a list of parts
    that hold numbers and pad labels only.
    """
    total = sum(shot.duration for shot in shots)
    argv: list[str] = [ffmpeg, "-hide_banner", "-nostdin", "-y"]
    filters: list[str] = []
    video_labels: list[str] = []
    next_input = 0

    for index, shot in enumerate(shots):
        argv += [
            "-loop", "1",
            "-framerate", str(fps),
            "-t", _seconds(shot.duration),
            "-i", str(shot.image),
        ]
        chain = (
            f"[{next_input}:v]scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=yuv420p"
        )
        next_input += 1
        label = f"v{index}"
        if shot.caption_png is not None:
            argv += ["-i", str(shot.caption_png)]
            filters.append(f"{chain}[b{index}]")
            filters.append(f"[b{index}][{next_input}:v]overlay=0:0[{label}]")
            next_input += 1
        else:
            filters.append(f"{chain}[{label}]")
        video_labels.append(f"[{label}]")

    audio_index: Optional[int] = None
    music_index: Optional[int] = None
    silent_index: Optional[int] = None
    if audio is not None:
        argv += ["-t", _seconds(total), "-i", str(audio)]
        audio_index = next_input
        next_input += 1
    if music is not None:
        argv += ["-t", _seconds(total), "-i", str(music)]
        music_index = next_input
        next_input += 1
    if audio_index is None and music_index is None:
        argv += ["-f", "lavfi", "-t", _seconds(total), "-i", SILENT_SOURCE]
        silent_index = next_input
        next_input += 1

    filters.append("".join(video_labels) + f"concat=n={len(shots)}:v=1:a=0[vcat]")
    video_out = "vcat"
    if fade > 0:
        shown = min(fade, total / 2)
        filters.append(
            f"[vcat]fade=t=in:st=0:d={_seconds(shown)},"
            f"fade=t=out:st={_seconds(max(0.0, total - shown))}:d={_seconds(shown)}[vout]"
        )
        video_out = "vout"

    audio_out: Optional[str] = None
    if audio_index is not None and music_index is not None:
        filters.append(
            f"[{audio_index}:a]aformat=sample_rates=48000:channel_layouts=stereo[voice]"
        )
        filters.append(
            f"[{music_index}:a]volume={float(music_gain)},"
            "aformat=sample_rates=48000:channel_layouts=stereo[bed]"
        )
        filters.append("[voice][bed]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]")
        audio_out = "aout"
    elif audio_index is not None:
        filters.append(
            f"[{audio_index}:a]aformat=sample_rates=48000:channel_layouts=stereo[aout]"
        )
        audio_out = "aout"
    elif music_index is not None:
        filters.append(
            f"[{music_index}:a]volume={float(music_gain)},"
            "aformat=sample_rates=48000:channel_layouts=stereo[aout]"
        )
        audio_out = "aout"

    argv += ["-filter_complex", ";".join(filters), "-map", f"[{video_out}]"]
    if audio_out is not None:
        argv += ["-map", f"[{audio_out}]"]
    else:
        argv += ["-map", f"{silent_index}:a:0"]
    argv += [
        "-r", str(fps),
        *VIDEO_ENCODE_ARGS,
        *AUDIO_ENCODE_ARGS,
        "-movflags", "+faststart",
        str(target),
    ]
    return argv


def draw_caption_png(text: str, target: Path, width: int, height: int) -> None:
    """A shot's caption as a transparent full-frame PNG with a lower band.

    The face, the wrapping and the palette come from ``film_card``'s machinery
    in ``core/tools/film_tools.py``; the import sits inside the call so the two
    modules stay acyclic.
    """
    from PIL import Image, ImageColor, ImageDraw

    from core.tools.film_tools import _STYLES, _font, _wrap

    background, foreground, accent, base = _STYLES["title"]
    size = max(16, min(72, base // 3))
    font = _font(size)
    margin = max(16, width // 24)
    lines = _wrap(text, font, width - 2 * margin)
    line_height = int(font.getlength("H") * 1.3) or int(size * 1.3)
    pad = max(8, size // 3)
    block = line_height * len(lines)
    panel_top = height - margin - block - 2 * pad

    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (margin, panel_top, width - margin, height - margin),
        fill=_with_alpha(ImageColor, background, 185),
    )
    draw.rectangle(
        (margin, panel_top, margin + max(3, size // 12), height - margin),
        fill=_with_alpha(ImageColor, accent, 255),
    )
    for index, line in enumerate(lines):
        draw.text(
            (width / 2.0, panel_top + pad + index * line_height),
            line,
            font=font,
            fill=_with_alpha(ImageColor, foreground, 255),
            anchor="ma",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, "PNG")


def _with_alpha(image_color_module, colour: str, alpha: int) -> tuple[int, int, int, int]:
    red, green, blue = image_color_module.getrgb(colour)
    return (red, green, blue, alpha)


@dataclass
class CutJob:
    """One render: the process, its state, and the event waiters block on."""

    id: str
    target: Path
    shots: int
    started: datetime
    state: str = STATE_RUNNING
    returncode: Optional[int] = None
    error: str = ""
    done: threading.Event = field(default_factory=threading.Event, repr=False)
    proc: Optional[subprocess.Popen[str]] = field(default=None, repr=False)

    def finish(self, state: str, returncode: Optional[int], error: str) -> None:
        """Record the outcome of a render still in flight; a cancel wins."""
        with _LOCK:
            if self.state == STATE_RUNNING:
                self.state = state
                self.returncode = returncode
                self.error = error
            self.done.set()


_JOBS: dict[str, CutJob] = {}
_LOCK = threading.Lock()


def _prune_locked() -> None:
    """Drop the oldest settled renders so the table stays the size of a session."""
    if len(_JOBS) <= MAX_KEPT_JOBS:
        return
    settled = [job for job in _JOBS.values() if job.state != STATE_RUNNING]
    surplus = len(_JOBS) - MAX_KEPT_JOBS
    for job in sorted(settled, key=lambda item: item.started)[:surplus]:
        _JOBS.pop(job.id, None)


def start_job(argv: list[str], target: Path, shots: int) -> tuple[Optional[CutJob], str]:
    """Register the render and run ffmpeg on a worker thread.

    Answers with the job, or with the sentence naming the live job when the
    path already carries a render.
    """
    with _LOCK:
        for job in _JOBS.values():
            if job.state == STATE_RUNNING and job.target == target:
                return None, (
                    f"{target} already has a render running (job {job.id}) — "
                    "ask film_job for it before starting another cut at this path"
                )
        live = [job for job in _JOBS.values() if job.state == STATE_RUNNING]
        if len(live) >= MAX_CONCURRENT_RENDERS:
            ids = ", ".join(job.id for job in live)
            return None, (
                f"{len(live)} renders are already running (jobs {ids}) — the studio "
                f"encodes at most {MAX_CONCURRENT_RENDERS} at a time; ask film_job for "
                "one of them and start this cut when a place frees up"
            )
        job = CutJob(
            id=uuid.uuid4().hex[:6],
            target=target,
            shots=shots,
            started=datetime.now(),
        )
        _JOBS[job.id] = job
        _prune_locked()
    worker = threading.Thread(
        target=_run_process, args=(job, list(argv)), name=f"film-cut-{job.id}", daemon=True
    )
    worker.start()
    return job, ""


def _run_process(job: CutJob, argv: list[str]) -> None:
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        job.finish(STATE_FAILED, None, f"{type(exc).__name__}: {exc}")
        return
    with _LOCK:
        job.proc = proc
        cancelled = job.state == STATE_CANCELLED
    if cancelled:
        _kill_group(proc)
        return
    # A hung encoder holds one of only two slots to death. Wait on it with a
    # wall-clock bound; when it fires, the whole process group is killed, the
    # job is recorded failed with its reason, and the entry is dropped from the
    # table so the slot is reusable by the next cut.
    try:
        _, error = proc.communicate(timeout=RENDER_TIMEOUT_SECONDS)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        # Reap the child so the slot is returned in finite time.
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        job.finish(STATE_FAILED, None, f"ffmpeg timed out after {RENDER_TIMEOUT_SECONDS} s — the cut did not finish")
        _JOBS.pop(job.id, None)
        return
    except OSError as exc:
        job.finish(STATE_FAILED, None, f"{type(exc).__name__}: {exc}")
        return
    if code == 0:
        job.finish(STATE_DONE, code, "")
    else:
        job.finish(STATE_FAILED, code, _trim_stderr(error or ""))


def _kill_group(proc: subprocess.Popen[str]) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _trim_stderr(error: str) -> str:
    lines = [line for line in error.splitlines() if line.strip()]
    tail = " | ".join(lines[-STDERR_TAIL_LINES:])
    return tail[-STDERR_TAIL_CHARS:]


def find_job(job_id: str) -> Optional[CutJob]:
    with _LOCK:
        return _JOBS.get(job_id)


def running_job_for(target: Path) -> Optional[CutJob]:
    """The live render on this output path, when one is running."""
    with _LOCK:
        for job in _JOBS.values():
            if job.state == STATE_RUNNING and job.target == target:
                return job
    return None


def job_ids() -> list[str]:
    with _LOCK:
        return list(_JOBS)


def job_line(job: CutJob) -> str:
    """One line: id, state, shots, start time, output path."""
    line = (
        f"job {job.id}: {job.state}, {job.shots} shots, "
        f"started {job.started.strftime('%H:%M:%S')}, path {job.target}"
    )
    if job.error:
        line += f", ffmpeg said: {job.error}"
    return line


def job_lines() -> list[str]:
    with _LOCK:
        jobs = list(_JOBS.values())
    return [job_line(job) for job in jobs]


def cancel_job(job: CutJob) -> str:
    """Kill the process group of a running job; a settled job answers its state."""
    with _LOCK:
        if job.state != STATE_RUNNING:
            return f"job {job.id} is already {job.state}"
        proc = job.proc
        job.state = STATE_CANCELLED
        job.done.set()
    if proc is not None:
        _kill_group(proc)
    return f"job {job.id} cancelled, ffmpeg and its children were killed"
