"""The cut's argv builder and job table, read without ffmpeg.

The builder is the contract: called as a pure function, its list asserted for
every shape of a cut. The table is exercised against a fake Popen so states,
ids, the busy path and cancel answer without the binary. The real render lives
in ``tests/test_film_tools.py``.
"""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import pytest

from core import film_cut
from core.film_cut import CutShot, build_cut_argv

FFMPEG = "/usr/bin/ffmpeg"
TARGET = Path("/tmp/cut-target.mp4")


def _argv(shots=None, **kwargs):
    kwargs.setdefault("ffmpeg", FFMPEG)
    kwargs.setdefault("target", TARGET)
    kwargs.setdefault("fps", 24)
    kwargs.setdefault("width", 1280)
    kwargs.setdefault("height", 720)
    if shots is None:
        shots = [CutShot(image=Path("/shots/a.png"), duration=2.0)]
    return build_cut_argv(shots=shots, **kwargs)


def _filter_graph(argv: list[str]) -> str:
    return argv[argv.index("-filter_complex") + 1]


def _inputs(argv: list[str]) -> list[str]:
    return [argv[i + 1] for i, part in enumerate(argv) if part == "-i"]


def test_given_one_shot_when_the_argv_is_built_then_the_loop_and_the_encode_stand_there():
    """GIVEN one still WHEN the argv is built THEN loop, caps and the pinned encode read back.

    The encode is pinned by its bytes because the hardware alternative measured slower over this
    product's material and several times heavier; the numbers stand on the constant."""
    argv = _argv()
    assert argv[0] == FFMPEG
    assert argv[-1] == str(TARGET)
    assert ["-loop", "1"] == argv[argv.index("-loop") : argv.index("-loop") + 2]
    assert "-nostdin" in argv and "-y" in argv
    assert ["-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", "20"] in [
        argv[i : i + 8] for i in range(len(argv))
    ]
    assert ["-c:a", "aac", "-b:a", "192k"] in [argv[i : i + 4] for i in range(len(argv))]
    assert ["-movflags", "+faststart"] in [argv[i : i + 2] for i in range(len(argv))]
    assert argv.count("-filter_complex") == 1
    assert "drawtext" not in " ".join(argv)


def test_given_the_same_arguments_when_the_argv_is_built_twice_then_the_lists_are_equal():
    """GIVEN one call shape WHEN the builder runs twice THEN it answers the same bytes, having touched no disk."""
    shots = [CutShot(image=Path("/nope/a.png"), duration=1.0)]
    first = _argv(shots)
    second = _argv(shots)
    assert first == second
    assert all(isinstance(part, str) for part in first)


def test_given_no_audio_at_all_when_the_argv_is_built_then_a_silent_source_carries_the_stream():
    """GIVEN voice and music both absent WHEN the argv is built THEN anullsrc feeds the audio stream."""
    argv = _argv()
    assert "anullsrc=channel_layout=stereo:sample_rate=48000" in _inputs(argv)
    assert "-f" in argv and "lavfi" in argv
    assert "amix" not in _filter_graph(argv)


def test_given_a_voice_track_when_the_argv_is_built_then_only_the_voice_reaches_the_map():
    """GIVEN a voice WAV and no bed WHEN the argv is built THEN aformat carries it and anullsrc stays out."""
    argv = _argv(audio=Path("/media/voice.wav"))
    assert "/media/voice.wav" in _inputs(argv)
    assert "aformat=sample_rates=48000" in _filter_graph(argv)
    assert "anullsrc" not in " ".join(argv)
    assert "amix" not in _filter_graph(argv)
    assert "[aout]" in argv


def test_given_only_a_bed_when_the_argv_is_built_then_the_gain_rides_on_the_music():
    """GIVEN a music WAV and no voice WHEN the argv is built THEN the gain stands on that input."""
    argv = _argv(music=Path("/media/bed.wav"), music_gain=0.3)
    assert "/media/bed.wav" in _inputs(argv)
    assert "volume=0.3" in _filter_graph(argv)
    assert "amix" not in _filter_graph(argv)
    assert "anullsrc" not in " ".join(argv)


def test_given_voice_and_bed_when_the_argv_is_built_then_amix_mixes_the_bed_under_the_voice():
    """GIVEN both audio inputs WHEN the argv is built THEN amix joins them after the bed's volume."""
    argv = _argv(audio=Path("/media/voice.wav"), music=Path("/media/bed.wav"))
    graph = _filter_graph(argv)
    assert "amix=inputs=2" in graph
    assert "volume=0.25" in graph
    assert "/media/voice.wav" in _inputs(argv) and "/media/bed.wav" in _inputs(argv)


def test_given_three_captioned_shots_when_the_argv_is_built_then_each_caption_arrives_as_an_overlay():
    """GIVEN three shots with caption PNGs WHEN the argv is built THEN each PNG enters as an input and an overlay."""
    shots = [
        CutShot(image=Path(f"/shots/s{i}.png"), duration=1.0, caption_png=Path(f"/caps/cap{i}.png"))
        for i in range(3)
    ]
    argv = _argv(shots=shots)
    graph = _filter_graph(argv)
    assert graph.count("overlay=0:0") == 3
    assert graph.count("concat") == 1 and "concat=n=3:v=1:a=0" in graph
    for i in range(3):
        assert f"/shots/s{i}.png" in _inputs(argv)
        assert f"/caps/cap{i}.png" in _inputs(argv)


def test_given_a_caption_full_of_quotes_when_the_argv_is_built_then_only_the_png_path_travels():
    """GIVEN caption text holding a quote and a comma WHEN the argv is built THEN the words sit in no argv element."""
    words = 'He said "cut", roll'
    shots = [CutShot(image=Path("/shots/a.png"), duration=1.0, caption_png=Path("/caps/cap0.png"))]
    argv = _argv(shots=shots)
    assert "/caps/cap0.png" in _inputs(argv)
    assert not any(words in part for part in argv)
    assert '"' not in _filter_graph(argv)


def _install_popen(monkeypatch, returncode=0, stderr="", release=None, slow=False):
    """The Popen of the job table replaced by one that answers what the test asks."""

    class FakePopen:
        instances: list["FakePopen"] = []
        slow = False

        def __init__(self, argv, **_kwargs):
            self.argv = list(argv)
            self.pid = 424242
            self.returncode = None
            FakePopen.instances.append(self)

        def communicate(self, timeout=None):
            if FakePopen.slow:
                bound = timeout if timeout is not None else 0.1
                threading.Event().wait(bound + 0.05)
                self.returncode = -film_cut.signal.SIGKILL
                raise subprocess.TimeoutExpired(cmd=self.argv, timeout=bound)
            if release is not None:
                assert release.wait(15), "the fake ffmpeg was never released"
            self.returncode = returncode
            return "", stderr

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            self.returncode = -film_cut.signal.SIGKILL

    FakePopen.slow = slow
    monkeypatch.setattr(film_cut.subprocess, "Popen", FakePopen)
    return FakePopen


@pytest.fixture
def clean_table(monkeypatch):
    """The job table of this test alone: the module registry is replaced."""
    monkeypatch.setattr(film_cut, "_JOBS", {})
    return film_cut


def test_given_a_finished_render_when_the_table_is_read_then_the_job_reads_done(clean_table, monkeypatch):
    """GIVEN a fake ffmpeg that exits 0 WHEN the job settles THEN its line is done and names the path."""
    _install_popen(monkeypatch, returncode=0)
    job, busy = film_cut.start_job([FFMPEG], TARGET, 3)
    assert busy == "" and job is not None
    assert job.done.wait(2)
    line = film_cut.job_line(job)
    assert job.state == film_cut.STATE_DONE
    assert f"job {job.id}: done, 3 shots" in line and str(TARGET) in line
    assert film_cut.find_job(job.id) is job
    assert film_cut.job_ids() == [job.id]


def test_given_a_failing_render_when_the_table_is_read_then_the_trimmed_stderr_stands_on_the_line(
    clean_table, monkeypatch
):
    """GIVEN a fake ffmpeg that exits 1 with ten stderr lines WHEN the job settles THEN the tail is kept."""
    noise = "\n".join(f"line {n}" for n in range(10)) + "\n"
    _install_popen(monkeypatch, returncode=1, stderr=noise)
    job, _ = film_cut.start_job([FFMPEG], TARGET, 1)
    assert job is not None and job.done.wait(2)
    assert job.state == film_cut.STATE_FAILED and job.returncode == 1
    assert "line 9" in job.error and "line 6" in job.error
    assert "line 0" not in job.error
    assert "ffmpeg said:" in film_cut.job_line(job)


def test_given_a_running_job_on_a_path_when_the_same_path_is_started_again_then_the_live_job_is_named(
    clean_table, monkeypatch
):
    """GIVEN one render on a path WHEN a second asks for the same path THEN the refusal names the live id."""
    release = threading.Event()
    _install_popen(monkeypatch, release=release)
    first, _ = film_cut.start_job([FFMPEG], TARGET, 2)
    assert first is not None and first.state == film_cut.STATE_RUNNING
    second, busy = film_cut.start_job([FFMPEG], TARGET, 2)
    assert second is None
    assert f"job {first.id}" in busy
    release.set()


def test_given_a_running_job_when_it_is_cancelled_then_the_process_group_dies_and_the_state_says_cancelled(
    clean_table, monkeypatch
):
    """GIVEN a render in flight WHEN cancel runs THEN the group is killed once and the job is cancelled."""
    release = threading.Event()
    _install_popen(monkeypatch, release=release)
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(film_cut.os, "getpgid", lambda pid: pid + 1)
    monkeypatch.setattr(film_cut.os, "killpg", lambda pgid, sig: killed.append((pgid, sig)))
    job, _ = film_cut.start_job([FFMPEG], TARGET, 1)
    assert job is not None
    for _ in range(200):
        if job.proc is not None:
            break
        threading.Event().wait(0.01)
    answer = film_cut.cancel_job(job)
    assert "cancelled" in answer and job.state == film_cut.STATE_CANCELLED
    assert killed == [(job.proc.pid + 1, film_cut.signal.SIGKILL)]
    assert film_cut.cancel_job(job) == f"job {job.id} is already cancelled"
    release.set()


def test_given_two_jobs_when_the_table_is_listed_then_each_gets_one_line(clean_table, monkeypatch):
    """GIVEN two settled renders WHEN the table is listed THEN one line per job carries id, state and path."""
    _install_popen(monkeypatch, returncode=0)
    first, _ = film_cut.start_job([FFMPEG], TARGET, 1)
    second, _ = film_cut.start_job([FFMPEG], Path("/tmp/other.mp4"), 2)
    assert first is not None and second is not None
    first.done.wait(2)
    second.done.wait(2)
    lines = film_cut.job_lines()
    assert len(lines) == 2
    assert any(str(TARGET) in line for line in lines)
    assert any("/tmp/other.mp4" in line for line in lines)


def test_given_two_renders_running_when_a_third_is_started_then_the_studio_says_no(
    clean_table, monkeypatch
):
    """GIVEN two cuts in flight WHEN a third asks for a new path THEN it is refused, naming the live jobs and the bound."""
    release = threading.Event()
    _install_popen(monkeypatch, release=release)
    first, _ = film_cut.start_job([FFMPEG], TARGET, 1)
    second, _ = film_cut.start_job([FFMPEG], Path("/tmp/second.mp4"), 1)
    assert first is not None and second is not None
    third, busy = film_cut.start_job([FFMPEG], Path("/tmp/third.mp4"), 1)
    assert third is None
    assert first.id in busy and second.id in busy
    assert str(film_cut.MAX_CONCURRENT_RENDERS) in busy
    release.set()


def test_given_more_settled_jobs_than_the_table_keeps_when_a_new_one_starts_then_the_oldest_are_gone(
    clean_table, monkeypatch
):
    """GIVEN six settled renders and a table that keeps four WHEN the last starts THEN the two oldest left and every live job stayed."""
    monkeypatch.setattr(film_cut, "MAX_KEPT_JOBS", 4)
    _install_popen(monkeypatch, returncode=0)
    started = []
    for index in range(6):
        job, busy = film_cut.start_job([FFMPEG], Path(f"/tmp/keep{index}.mp4"), 1)
        assert job is not None and busy == ""
        job.done.wait(2)
        started.append(job.id)
    kept = film_cut.job_ids()
    assert len(kept) == 4
    assert started[:2] == [job_id for job_id in started[:2] if job_id not in kept]
    assert started[-4:] == kept


def test_given_a_finished_render_when_ffmpeg_prints_stats_then_the_job_line_carries_no_stderr(
    clean_table, monkeypatch
):
    """GIVEN an ffmpeg that exits 0 after printing kb/s stats WHEN the job settles THEN the line stays clean."""
    stats = (
        "frame=  100 fps= 24 q=28.0 size=    512kB time=00:00:04.00 "
        "bitrate=1024.0kbits/s speed=1.0x\n"
    )
    _install_popen(monkeypatch, returncode=0, stderr=stats)
    job, _ = film_cut.start_job([FFMPEG], TARGET, 1)
    assert job is not None and job.done.wait(2)
    assert job.state == film_cut.STATE_DONE
    assert job.error == ""
    line = film_cut.job_line(job)
    assert "ffmpeg said" not in line and "bitrate" not in line


def test_given_a_hung_ffmpeg_when_the_render_times_out_then_the_job_fails_and_the_slot_frees(
    clean_table, monkeypatch
):
    """GIVEN an ffmpeg that outruns the bound WHEN the timeout fires THEN the group dies and a new cut starts."""
    monkeypatch.setattr(film_cut, "RENDER_TIMEOUT_SECONDS", 0.1)
    fake = _install_popen(monkeypatch, slow=True)
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(film_cut.os, "getpgid", lambda pid: pid + 1)
    monkeypatch.setattr(film_cut.os, "killpg", lambda pgid, sig: killed.append((pgid, sig)))
    job, _ = film_cut.start_job([FFMPEG], TARGET, 1)
    assert job is not None
    assert job.done.wait(2)
    assert job.state == film_cut.STATE_FAILED
    assert "timed out" in job.error
    assert "timed out" in film_cut.job_line(job)
    assert job.proc is not None
    assert killed == [(job.proc.pid + 1, film_cut.signal.SIGKILL)]
    fake.slow = False
    again, busy = film_cut.start_job([FFMPEG], Path("/tmp/after-timeout.mp4"), 1)
    assert again is not None and busy == ""
    assert again.done.wait(2)
    assert again.state == film_cut.STATE_DONE
