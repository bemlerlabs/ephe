"""The four film verbs: what they write, what they answer, and what they refuse.

Every file lands in the artifact folder the tools ask ``core.engine_config`` for,
so the fixture below pins that folder to the test's own ``tmp_path``. The status
verb is asserted through a patched ``shutil.which`` and a fake probe, so it runs
on a machine with no ffmpeg at all.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
import wave
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import film_cut
from core.tools import film_tools
from core.tools.film_tools import (
    FILM_TOOL_SCHEMAS,
    film_card,
    film_clip,
    film_job,
    film_music,
    film_sound,
    film_status,
)
from core.tools.registry import TOOL_MAP


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    """The birth place under test: the artifact folder is this test's own."""
    import core.engine_config as engine_config

    folder = tmp_path / "artifacts"
    monkeypatch.setattr(engine_config, "artifact_output_dir", lambda: folder)
    return folder


@pytest.fixture
def no_render_jobs():
    """The render table is process-global, so these two cases read it alone."""
    with film_cut._LOCK:
        kept = dict(film_cut._JOBS)
        film_cut._JOBS.clear()
    try:
        yield
    finally:
        with film_cut._LOCK:
            film_cut._JOBS.clear()
            film_cut._JOBS.update(kept)


def _marker_path(result: str, marker: str) -> Path:
    for line in result.splitlines():
        if line.startswith(marker):
            return Path(line[len(marker):].strip())
    raise AssertionError(f"no {marker} line in: {result}")


def _frame_is_not_flat(path: Path) -> bool:
    from PIL import Image

    with Image.open(path) as image:
        colours = image.convert("RGB").getcolors(maxcolors=1_000_000)
    return colours is None or len(colours) > 1


async def test_given_a_headline_when_the_card_renders_then_a_png_of_that_size_lands(artifacts):
    """GIVEN a headline WHEN film_card renders THEN the marker names a PNG of the asked size."""
    from PIL import Image

    result = await film_card("The studio that speaks and cuts", width=900, height=500)
    target = _marker_path(result, "PNG_FILE:")
    assert target.is_file()
    assert target.parent == artifacts
    with Image.open(target) as image:
        assert image.size == (900, 500)
    assert "900x500" in result


async def test_given_a_card_when_it_renders_then_the_frame_carries_more_than_one_colour(artifacts):
    """GIVEN a rendered card WHEN its pixels are counted THEN the frame is not one flat colour."""
    result = await film_card("Ninety seconds, one take")
    assert _frame_is_not_flat(_marker_path(result, "PNG_FILE:"))


@pytest.mark.parametrize("style", ["title", "card", "quote", "stat"])
async def test_given_each_style_when_it_renders_then_a_frame_with_text_lands(artifacts, style):
    """GIVEN a style on the offer WHEN it renders THEN a non-flat PNG arrives in the folder."""
    result = await film_card("Forty-two\ntakes from first light", style=style)
    target = _marker_path(result, "PNG_FILE:")
    assert target.is_file()
    assert target.suffix == ".png"
    assert _frame_is_not_flat(target)


async def test_given_no_text_when_the_card_runs_then_it_refuses(artifacts):
    """GIVEN empty text WHEN film_card runs THEN the answer is a refusal and nothing is written."""
    result = await film_card("   \n  ")
    assert result.startswith("[tool-error 'film_card':")
    assert "empty" in result
    assert list(artifacts.glob("*")) == []


async def test_given_text_past_the_limit_when_the_card_runs_then_the_refusal_names_the_limit(artifacts):
    """GIVEN text over the bound WHEN film_card runs THEN the refusal carries the number."""
    result = await film_card("word " * 200)
    assert result.startswith("[tool-error 'film_card':")
    assert str(film_tools.MAX_CARD_CHARS) in result
    assert list(artifacts.glob("*")) == []


async def test_given_an_unknown_style_when_the_card_runs_then_the_refusal_lists_the_four(artifacts):
    """GIVEN a style off the offer WHEN film_card runs THEN the refusal names the styles it has."""
    result = await film_card("hello", style="poster")
    for style in ("title", "card", "quote", "stat"):
        assert style in result


async def test_given_a_colour_that_is_not_hex_when_the_card_runs_then_the_refusal_says_so(artifacts):
    """GIVEN a colour the palette cannot take WHEN film_card runs THEN the field is named."""
    result = await film_card("hello", bg="sepia")
    assert "bg" in result and "#rgb" in result


async def test_given_a_size_off_the_bound_when_the_card_runs_then_the_refusal_names_the_bound(artifacts):
    """GIVEN an impossible width WHEN film_card runs THEN the refusal states the range."""
    result = await film_card("hello", width=40)
    assert str(film_tools.MIN_CARD_SIZE) in result and str(film_tools.MAX_CARD_SIZE) in result


async def test_given_an_absolute_out_when_the_card_runs_then_the_user_path_wins(tmp_path):
    """GIVEN an absolute path WHEN film_card runs THEN the file is written there."""
    target = tmp_path / "somewhere" / "else.png"
    result = await film_card("named by the user", out=str(target))
    assert _marker_path(result, "PNG_FILE:") == target
    assert target.is_file()


async def test_given_a_named_effect_when_sound_runs_then_a_wav_of_that_length_lands(artifacts):
    """GIVEN an effect on the table WHEN film_sound runs THEN a readable WAV holds the asked seconds."""
    result = await film_sound("whoosh", seconds=0.8)
    target = _marker_path(result, "WAV_FILE:")
    assert target.parent == artifacts
    with wave.open(str(target)) as handle:
        assert handle.getnchannels() == 2
        assert handle.getframerate() == 48_000
        assert abs(handle.getnframes() / handle.getframerate() - 0.8) < 0.02
    assert "0.80 s" in result and "48000" in result


async def test_given_no_length_when_sound_runs_then_the_effect_keeps_its_own_duration(artifacts):
    """GIVEN an effect with no length asked WHEN film_sound runs THEN its natural duration is used."""
    result = await film_sound("countdown")
    with wave.open(str(_marker_path(result, "WAV_FILE:"))) as handle:
        assert abs(handle.getnframes() / handle.getframerate() - 4.0) < 0.05


async def test_given_an_unknown_effect_when_sound_runs_then_the_refusal_lists_the_table(artifacts):
    """GIVEN a name off the table WHEN film_sound runs THEN every real name is offered back."""
    result = await film_sound("airhorn")
    assert result.startswith("[tool-error 'film_sound':")
    for name in film_tools.SFX:
        assert name in result
    assert list(artifacts.glob("*")) == []


async def test_given_an_impossible_length_when_sound_runs_then_the_refusal_names_the_bound(artifacts):
    """GIVEN a length past the bound WHEN film_sound runs THEN the refusal states it."""
    result = await film_sound("thud", seconds=900)
    assert str(film_tools.MAX_SFX_SECONDS) in result


async def test_given_a_named_wav_in_the_library_when_sound_runs_then_that_file_is_delivered(
    monkeypatch, tmp_path, artifacts
):
    """GIVEN the user's own effect folder WHEN film_sound runs THEN a named WAV is usable."""
    folder = tmp_path / "cc0"
    folder.mkdir()
    source = folder / "boom.wav"
    source.write_bytes(b"RIFF-library-effect")
    monkeypatch.setenv(film_tools.SFX_DIR_ENV, str(folder))
    result = await film_sound("boom")
    target = _marker_path(result, "WAV_FILE:")
    assert target.read_bytes() == source.read_bytes()
    assert "sound_effect" in result


async def test_given_the_stored_setting_when_a_library_wav_is_named_then_it_resolves(
    monkeypatch, tmp_path, artifacts
):
    """GIVEN the deep setting instead of an env var WHEN film_sound runs THEN the folder is used."""
    from core import settings_schema

    folder = tmp_path / "stored"
    folder.mkdir()
    source = folder / "boom.wav"
    source.write_bytes(b"RIFF-stored-effect")
    monkeypatch.delenv(film_tools.SFX_DIR_ENV, raising=False)
    monkeypatch.setattr(
        settings_schema,
        "load_deep_settings",
        lambda: {"advanced": {"advanced.film_sfx_dir": str(folder)}},
    )
    result = await film_sound("boom")
    assert _marker_path(result, "WAV_FILE:").read_bytes() == source.read_bytes()


async def test_given_a_bed_when_music_runs_then_a_wav_of_the_bar_length_lands(artifacts):
    """GIVEN four bars at 120 bpm WHEN film_music runs THEN the WAV holds eight seconds of audio."""
    result = await film_music("driving", bars=4, bpm=120, seed=2)
    target = _marker_path(result, "WAV_FILE:")
    assert target.parent == artifacts
    with wave.open(str(target)) as handle:
        assert handle.getframerate() == 48_000
        assert abs(handle.getnframes() / handle.getframerate() - 8.0) < 0.05
    assert "4 bars at 120 bpm" in result


async def test_given_the_same_bed_call_twice_when_music_runs_then_the_bytes_match(artifacts):
    """GIVEN one (name, bars, bpm, seed) WHEN it renders twice THEN the two files are the same bytes."""
    first = _marker_path(await film_music("tense", bars=1, bpm=90, seed=4, out="one.wav"), "WAV_FILE:")
    second = _marker_path(await film_music("tense", bars=1, bpm=90, seed=4, out="two.wav"), "WAV_FILE:")
    assert first.read_bytes() == second.read_bytes()


async def test_given_an_unknown_bed_when_music_runs_then_the_refusal_lists_the_five(artifacts):
    """GIVEN a bed off the table WHEN film_music runs THEN every real bed is offered back."""
    result = await film_music("wedding")
    assert result.startswith("[tool-error 'film_music':")
    for name in film_tools.MUSIC:
        assert name in result
    assert list(artifacts.glob("*")) == []


async def test_given_zero_bars_when_music_runs_then_the_refusal_names_the_range(artifacts):
    """GIVEN an impossible bar count WHEN film_music runs THEN the refusal states the range."""
    result = await film_music("calm", bars=0)
    assert str(film_tools.MIN_BARS) in result and str(film_tools.MAX_BARS) in result


def _fake_ffmpeg(monkeypatch, filters: str):
    """A PATH that finds ffmpeg and a probe that answers with the given filter table."""
    calls: list[list[str]] = []

    monkeypatch.setattr(film_tools.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return SimpleNamespace(returncode=0, stdout=filters, stderr="")

    monkeypatch.setattr(film_tools.subprocess, "run", fake_run)
    return calls


async def test_given_a_machine_without_ffmpeg_when_status_runs_then_it_says_so_and_probes_nothing(
    monkeypatch,
):
    """GIVEN no ffmpeg on PATH WHEN film_status runs THEN the line calls it absent."""
    monkeypatch.setattr(film_tools.shutil, "which", lambda name: None)

    def never(*_args, **_kwargs):
        raise AssertionError("a status probe ran without a binary")

    monkeypatch.setattr(film_tools.subprocess, "run", never)
    report = await film_status()
    ffmpeg_line = next(line for line in report.splitlines() if line.startswith("ffmpeg:"))
    assert "not on PATH" in ffmpeg_line
    assert "version" not in ffmpeg_line


async def test_given_an_ffmpeg_with_the_filters_when_status_runs_then_it_names_what_it_probed(monkeypatch):
    """GIVEN a build carrying drawtext and subtitles WHEN film_status runs THEN both read as present."""
    table = (
        "Filters:\n"
        " .. abench            A->A       Benchmark part of a filtergraph.\n"
        " T.C drawtext         V->V       Draw text on top of video inputs.\n"
        " ... subtitles        V->V       Render text subtitles.\n"
    )
    calls = _fake_ffmpeg(monkeypatch, table)
    report = await film_status()
    ffmpeg_line = next(line for line in report.splitlines() if line.startswith("ffmpeg:"))
    assert "drawtext yes" in ffmpeg_line
    assert "subtitles yes" in ffmpeg_line
    assert "libass" not in report
    assert any(argv[-1] == "-version" for argv in calls)
    assert any(argv[-1] == "-filters" for argv in calls)


async def test_given_an_ffmpeg_without_them_when_status_runs_then_the_missing_build_is_named(monkeypatch):
    """GIVEN a build with neither filter WHEN film_status runs THEN each absence names its library."""
    calls = _fake_ffmpeg(monkeypatch, "Filters:\n .. abench            A->A       Benchmark.\n")
    report = await film_status()
    assert "drawtext no" in report and "subtitles no" in report
    assert "libfreetype" in report and "libass" in report
    assert calls


async def test_given_a_probe_that_never_answers_when_status_runs_then_the_line_still_reports(
    monkeypatch,
):
    """GIVEN a hanging binary WHEN film_status runs THEN the status says it did not answer."""
    import subprocess as sp

    monkeypatch.setattr(film_tools.shutil, "which", lambda name: f"/usr/bin/{name}")

    def hang(argv, **_kwargs):
        raise sp.TimeoutExpired(cmd=argv, timeout=1)

    monkeypatch.setattr(film_tools.subprocess, "run", hang)
    report = await film_status()
    assert "did not answer" in report


async def test_given_the_machine_as_it_is_when_status_runs_then_it_names_the_folders_and_tables(
    artifacts,
):
    """GIVEN this machine WHEN film_status runs THEN the artifact folder and both tables are reported."""
    report = await film_status()
    assert str(artifacts) in report
    assert "ui_hover" in report and "corporate" in report


async def test_given_a_machine_with_a_font_when_status_runs_then_the_face_it_found_is_named():
    """GIVEN this machine WHEN film_status runs THEN the Pillow line says which face a card uses."""
    report = await film_status()
    line = next(line for line in report.splitlines() if line.startswith("Pillow:"))
    assert "render with the face at" in line or "no outline font was found" in line


async def test_given_no_outline_font_when_status_runs_then_the_card_warning_shows(monkeypatch):
    """GIVEN a machine whose fonts are all missing WHEN film_status runs THEN it warns about the face."""
    monkeypatch.setattr(film_tools, "_FONT_CANDIDATES", ("/definitely/not/a/font.ttf",))
    report = await film_status()
    assert "no outline font was found" in report


async def test_given_a_cc0_folder_on_the_machine_when_status_runs_then_it_counts_what_is_there(
    monkeypatch, tmp_path
):
    """GIVEN a folder of the user's own effects WHEN film_status runs THEN it reports the count."""
    folder = tmp_path / "cc0"
    folder.mkdir()
    (folder / "boom.wav").write_bytes(b"RIFF")
    monkeypatch.setenv(film_tools.SFX_DIR_ENV, str(folder))
    report = await film_status()
    line = next(line for line in report.splitlines() if line.startswith("SFX library:"))
    assert "1 wav file" in line and str(folder) in line


async def test_given_a_setting_that_points_nowhere_when_status_runs_then_the_line_says_so(monkeypatch):
    """GIVEN a folder that is not there WHEN film_status runs THEN the line refuses to count it."""
    monkeypatch.setenv(film_tools.SFX_DIR_ENV, "/definitely/not/a/folder")
    report = await film_status()
    line = next(line for line in report.splitlines() if line.startswith("SFX library:"))
    assert "not a directory" in line


def test_given_the_film_schemas_when_the_registry_is_read_then_every_name_has_a_handler():
    """GIVEN the film schemas WHEN the registry is read THEN each one dispatches."""
    for schema in FILM_TOOL_SCHEMAS:
        name = schema["function"]["name"]
        assert name in TOOL_MAP, f"{name} is offered with no handler"
        assert callable(TOOL_MAP[name])


def test_given_the_registry_handlers_when_the_schemas_are_read_then_none_is_offered_twice_or_lost():
    """GIVEN the six verbs WHEN the schemas are read THEN the two lists hold the same names."""
    offered = {schema["function"]["name"] for schema in FILM_TOOL_SCHEMAS}
    assert offered == {
        "film_status", "film_card", "film_sound", "film_music", "film_clip", "film_job",
    }
    handlers = {
        "film_status": film_status,
        "film_card": film_card,
        "film_sound": film_sound,
        "film_music": film_music,
        "film_clip": film_clip,
        "film_job": film_job,
    }
    for name in offered:
        assert TOOL_MAP[name] is handlers[name]


def test_given_the_offer_list_when_the_registry_is_read_then_the_four_verbs_are_in_it():
    """GIVEN the advertised array WHEN the registry is asked THEN the four verbs are offered."""
    from core.tools.registry import get_tool_schemas

    offered = {entry["function"]["name"] for entry in get_tool_schemas()}
    assert {"film_status", "film_card", "film_sound", "film_music"} <= offered


async def test_given_a_call_through_the_map_when_the_verb_runs_then_the_marker_line_comes_back(
    artifacts,
):
    """GIVEN the handler as the registry holds it WHEN it is called THEN it answers with a marker."""
    result = await TOOL_MAP["film_sound"]("click")
    assert _marker_path(result, "WAV_FILE:").is_file()


def _install_cut_popen(monkeypatch, returncode=0, stderr="", release=None, slow=False):
    """The subprocess handle of ``core.film_cut`` replaced for the job-table tests."""

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

    FakePopen.slow = slow
    monkeypatch.setattr(film_cut.subprocess, "Popen", FakePopen)
    return FakePopen


def _still(tmp: Path, name: str, phase: int) -> Path:
    """One gradient PNG: real pixels, so the encoder has something to bite."""
    from PIL import Image

    image = Image.new("RGB", (320, 180))
    pixels = image.load()
    for y in range(180):
        for x in range(320):
            pixels[x, y] = ((x * phase) % 256, (y * 3 + phase) % 256, (x + y) % 256)
    path = tmp / name
    image.save(path, "PNG")
    return path


def _one_shot(artifacts: Path, tmp: Path) -> list[dict]:
    return [{"image": str(_still(tmp, "a.png", 1)), "duration": 0.4}]


@pytest.fixture
def clean_cut_table(monkeypatch):
    """The job table of this test alone: the module registry is replaced."""
    monkeypatch.setattr(film_cut, "_JOBS", {})
    return film_cut


@pytest.fixture
def with_ffmpeg(monkeypatch):
    """The binary exists on this fake machine, wherever it really comes from."""
    monkeypatch.setattr(film_cut.shutil, "which", lambda name: "/usr/bin/" + name)


async def test_given_seventeen_shots_when_the_cut_runs_then_the_refusal_names_the_cap(
    artifacts, tmp_path, with_ffmpeg
):
    """GIVEN more shots than the cap WHEN film_clip runs THEN the refusal states the cap and the fix."""
    still = str(_still(tmp_path, "a.png", 1))
    shots = [{"image": still, "duration": 0.4} for _ in range(17)]
    result = await film_clip(shots)
    assert result.startswith("[tool-error 'film_clip':")
    assert str(film_cut.MAX_SHOTS) in result
    assert "two shorter clips" in result


async def test_given_a_missing_still_when_the_cut_runs_then_the_refusal_names_the_path(
    artifacts, with_ffmpeg
):
    """GIVEN a shot whose image does not exist WHEN film_clip runs THEN the refusal carries the path."""
    result = await film_clip([{"image": str(artifacts / "gone.png"), "duration": 1.0}])
    assert result.startswith("[tool-error 'film_clip':")
    assert "gone.png" in result and "is not a file" in result


async def test_given_a_text_file_as_a_still_when_the_cut_runs_then_the_refusal_names_the_suffixes(
    artifacts, tmp_path, with_ffmpeg
):
    """GIVEN a .txt standing in for an image WHEN film_clip runs THEN the answer names the allowed kinds."""
    impostor = tmp_path / "still.txt"
    impostor.write_text("not a picture", encoding="utf-8")
    result = await film_clip([{"image": str(impostor), "duration": 1.0}])
    assert result.startswith("[tool-error 'film_clip':")
    assert ".jpg" in result and ".png" in result


async def test_given_a_bad_frame_rate_when_the_cut_runs_then_the_refusal_names_the_bounds(
    artifacts, tmp_path, with_ffmpeg
):
    """GIVEN fps 0 and fps 1000 WHEN film_clip runs THEN both refusals carry the bounds."""
    low = await film_clip(_one_shot(artifacts, tmp_path), fps=0)
    high = await film_clip(_one_shot(artifacts, tmp_path), fps=1000)
    assert low.startswith("[tool-error 'film_clip':") and str(film_cut.MIN_FPS) in low
    assert high.startswith("[tool-error 'film_clip':") and str(film_cut.MAX_FPS) in high


async def test_given_a_wait_past_the_horizon_when_the_cut_runs_then_the_refusal_names_the_bound(
    artifacts, tmp_path, with_ffmpeg
):
    """GIVEN wait_seconds 900 WHEN film_clip runs THEN the refusal states the 600 bound."""
    result = await film_clip(_one_shot(artifacts, tmp_path), wait_seconds=900)
    assert result.startswith("[tool-error 'film_clip':")
    assert str(film_cut.MAX_WAIT_SECONDS) in result


async def test_given_a_caption_past_the_card_limit_when_the_cut_runs_then_the_refusal_names_the_limit(
    artifacts, tmp_path, with_ffmpeg
):
    """GIVEN a caption over the card limit WHEN film_clip runs THEN the refusal carries the number."""
    shot = dict(_one_shot(artifacts, tmp_path)[0])
    shot["caption"] = "word " * 200
    result = await film_clip([shot])
    assert result.startswith("[tool-error 'film_clip':")
    assert str(film_tools.MAX_CARD_CHARS) in result


async def test_given_a_shot_without_seconds_when_the_cut_runs_then_the_refusal_names_the_duration(
    artifacts, tmp_path, with_ffmpeg
):
    """GIVEN a duration of zero WHEN film_clip runs THEN the refusal gives the accepted range."""
    shot = dict(_one_shot(artifacts, tmp_path)[0])
    shot["duration"] = 0
    result = await film_clip([shot])
    assert result.startswith("[tool-error 'film_clip':")
    assert str(film_cut.MIN_SHOT_SECONDS) in result and str(film_cut.MAX_SHOT_SECONDS) in result


async def test_given_no_ffmpeg_on_the_machine_when_the_cut_runs_then_the_refusal_says_how_to_install(
    artifacts, tmp_path, monkeypatch
):
    """GIVEN shutil.which answering nothing WHEN film_clip runs THEN the refusal names the install path."""
    monkeypatch.setattr(film_cut.shutil, "which", lambda name: None)
    result = await film_clip(_one_shot(artifacts, tmp_path))
    assert result.startswith("[tool-error 'film_clip':")
    assert "ffmpeg is not on PATH" in result
    assert "brew install ffmpeg" in result


async def test_given_ffmpeg_failing_when_the_cut_runs_then_the_refusal_carries_the_stderr_tail(
    artifacts, tmp_path, with_ffmpeg, monkeypatch, clean_cut_table
):
    """GIVEN an ffmpeg that exits 1 with ten log lines WHEN film_clip runs THEN the tail reaches the refusal."""
    noise = "\n".join(f"reason {n}" for n in range(10)) + "\n"
    _install_cut_popen(monkeypatch, returncode=1, stderr=noise)
    result = await film_clip(_one_shot(artifacts, tmp_path))
    assert result.startswith("[tool-error 'film_clip':")
    assert "ffmpeg exited 1" in result
    assert "reason 9" in result and "reason 6" in result
    assert "reason 0" not in result


async def test_given_a_finished_fake_render_when_the_cut_answers_then_the_marker_line_is_first(
    artifacts, tmp_path, with_ffmpeg, monkeypatch, clean_cut_table
):
    """GIVEN a fake ffmpeg that exits 0 WHEN film_clip waits for it THEN the answer opens with VIDEO_FILE."""
    _install_cut_popen(monkeypatch, returncode=0)
    result = await film_clip(_one_shot(artifacts, tmp_path), out=str(tmp_path / "cut.mp4"))
    assert result.startswith("VIDEO_FILE:")
    assert "1 shot" in result and "1280x720" in result and "24 fps" in result


async def test_given_a_slow_render_when_the_cut_answers_then_it_keeps_running_under_its_job_id(
    artifacts, tmp_path, with_ffmpeg, monkeypatch, clean_cut_table
):
    """GIVEN an ffmpeg that does not answer WHEN the wait runs out THEN the id keeps the job findable."""
    release = threading.Event()
    fake = _install_cut_popen(monkeypatch, returncode=0, release=release)
    result = await film_clip(
        _one_shot(artifacts, tmp_path), out=str(tmp_path / "cut.mp4"), wait_seconds=0
    )
    assert "still rendering (job " in result
    job_id = re.search(r"job ([0-9a-f]{6})", result).group(1)
    assert str(tmp_path / "cut.mp4") in result
    line = await film_job(job_id, wait_seconds=0)
    assert f"job {job_id}: running" in line
    release.set()
    landed = await film_job(job_id, wait_seconds=2)
    assert landed.startswith("VIDEO_FILE:")
    assert fake.instances[0].returncode == 0


async def test_given_a_running_render_when_it_is_cancelled_then_the_group_dies_and_the_job_reads_cancelled(
    artifacts, tmp_path, with_ffmpeg, monkeypatch, clean_cut_table
):
    """GIVEN a render in flight WHEN film_job cancels it THEN the kill reaches the group and the state moves."""
    release = threading.Event()
    _install_cut_popen(monkeypatch, returncode=0, release=release)
    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(film_cut.os, "getpgid", lambda pid: pid + 1)
    monkeypatch.setattr(film_cut.os, "killpg", lambda pgid, sig: killed.append((pgid, sig)))
    result = await film_clip(
        _one_shot(artifacts, tmp_path), out=str(tmp_path / "cut.mp4"), wait_seconds=0
    )
    job_id = re.search(r"job ([0-9a-f]{6})", result).group(1)
    job = film_cut.find_job(job_id)
    for _ in range(200):
        if job is not None and job.proc is not None:
            break
        threading.Event().wait(0.01)
    answer = await film_job(job_id, action="cancel")
    assert "cancelled" in answer
    assert killed == [(job.proc.pid + 1, film_cut.signal.SIGKILL)]
    line = await film_job(job_id)
    assert "cancelled" in line
    release.set()


async def test_given_a_busy_output_path_when_a_second_cut_asks_for_it_then_the_live_job_is_named(
    artifacts, tmp_path, with_ffmpeg, monkeypatch, clean_cut_table
):
    """GIVEN one render on a path WHEN a second cut asks for the same path THEN the refusal quotes the live id."""
    release = threading.Event()
    _install_cut_popen(monkeypatch, returncode=0, release=release)
    first = await film_clip(
        _one_shot(artifacts, tmp_path), out=str(tmp_path / "cut.mp4"), wait_seconds=0
    )
    job_id = re.search(r"job ([0-9a-f]{6})", first).group(1)
    second = await film_clip(
        _one_shot(artifacts, tmp_path), out=str(tmp_path / "cut.mp4"), wait_seconds=0
    )
    assert second.startswith("[tool-error 'film_clip':")
    assert f"job {job_id}" in second
    release.set()


async def test_given_a_caption_with_a_quote_and_a_comma_when_the_cut_runs_then_the_words_only_reach_a_png(
    artifacts, tmp_path, with_ffmpeg, monkeypatch, clean_cut_table
):
    """GIVEN a caption carrying a quote and a comma WHEN the cut builds THEN only a PNG path enters argv."""
    from PIL import Image

    release = threading.Event()
    fake = _install_cut_popen(monkeypatch, returncode=0, release=release)
    shot = dict(_one_shot(artifacts, tmp_path)[0])
    shot["caption"] = 'He said "roll, camera", cut'
    await film_clip([shot], out=str(tmp_path / "cut.mp4"), wait_seconds=0)
    argv = fake.instances[0].argv
    graph = argv[argv.index("-filter_complex") + 1]
    assert not any("roll, camera" in part for part in argv)
    assert '"' not in graph
    pngs = [
        argv[i + 1] for i, part in enumerate(argv[:-1])
        if part == "-i" and "clipcap" in argv[i + 1] and argv[i + 1].endswith(".png")
    ]
    assert pngs, "the caption never arrived as a PNG input"
    with Image.open(pngs[0]) as drawn:
        assert drawn.mode == "RGBA"
    release.set()


async def test_given_no_cuts_yet_when_the_job_table_is_asked_then_it_says_so(
    clean_cut_table,
):
    """GIVEN an empty table WHEN film_job is asked without an id THEN the answer is one honest line."""
    assert await film_job() == "no cut jobs in this session yet"


async def test_given_a_cut_job_when_the_registry_is_read_then_both_verbs_are_offered():
    """GIVEN the advertised arrays WHEN the registry is asked THEN the cut and its job verb stand in both."""
    from core.tools.registry import get_tool_schemas

    offered = {entry["function"]["name"] for entry in get_tool_schemas()}
    assert {"film_clip", "film_job"} <= offered
    assert {"film_clip", "film_job"} <= set(TOOL_MAP)


#: Seconds each still holds in the real render below, so the length the ffprobe
#: window is built from is the length the test asked for.
SHOT_SECONDS = 0.4


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="the real cut needs ffmpeg on PATH")
async def test_given_two_stills_when_the_cut_renders_for_real_then_ffprobe_reads_a_complete_mp4(
    artifacts, tmp_path
):
    """GIVEN two 0.4 s stills WHEN the real ffmpeg renders THEN a two-stream mp4 of that length lands."""
    probe_tool = shutil.which("ffprobe")
    first = _still(tmp_path, "a.png", 3)
    second = _still(tmp_path, "b.png", 7)
    result = await film_clip(
        [
            {"image": str(first), "duration": SHOT_SECONDS, "caption": "the first frame"},
            {"image": str(second), "duration": SHOT_SECONDS},
        ],
        out=str(tmp_path / "real-cut.mp4"),
        wait_seconds=120,
    )
    target = _marker_path(result, "VIDEO_FILE:")
    assert target.is_file()
    assert target.stat().st_size > 2000
    duration = subprocess.run(
        [probe_tool, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(target)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    # The window is the asked-for length plus the frame rounding of a 24 fps
    # still loop; it is a property of the media, not of this machine's speed.
    asked = 2 * SHOT_SECONDS
    assert asked - 0.25 <= float(duration) <= asked + 0.25
    kinds = subprocess.run(
        [probe_tool, "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "default=nw=1:nk=1", str(target)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "video" in kinds and "audio" in kinds


async def test_given_no_effect_named_when_sound_runs_then_the_menu_answers_not_a_guess():
    """GIVEN a call that named nothing WHEN film_sound runs THEN the menu comes back in place of a guessed effect."""
    report = await film_sound()
    assert "no effect named" in report
    assert "'None'" not in report
    assert all(name in report for name in ("ui_hover", "riser", "countdown"))


def test_given_the_sound_schema_when_it_is_read_then_name_is_optional():
    """GIVEN the kernel refuses an unset required parameter before the verb runs WHEN the schema is read THEN name is off that list.

    The refusal the kernel writes (`missing-param: required parameter(s) not set`)
    teaches a model nothing; the verb's own answer names every effect it can render.
    """
    schema = next(s for s in FILM_TOOL_SCHEMAS if s["function"]["name"] == "film_sound")
    assert schema["function"]["parameters"]["required"] == []
    assert "Omit it" in schema["function"]["parameters"]["properties"]["name"]["description"]


async def test_given_a_render_in_flight_when_status_runs_then_the_table_is_read(artifacts, no_render_jobs):
    """GIVEN one kept job WHEN film_status runs THEN its state and path answer without an id."""
    job = film_cut.CutJob(
        id="job-1", target=artifacts / "cut.mp4", shots=3, started=datetime(2026, 11, 18, 17, 48, 16)
    )
    with film_cut._LOCK:
        film_cut._JOBS[job.id] = job
    report = await film_status()
    assert "renders: 1 job(s) in this server process" in report
    assert "restart" in report
    assert "job job-1: running, 3 shots, started 17:48:16" in report
    assert str(artifacts / "cut.mp4") in report


async def test_given_a_machine_that_never_rendered_when_status_runs_then_the_table_says_so(
    artifacts, no_render_jobs
):
    """GIVEN no kept job WHEN film_status runs THEN the absence is stated rather than skipped."""
    assert "renders: none in this server process" in await film_status()
