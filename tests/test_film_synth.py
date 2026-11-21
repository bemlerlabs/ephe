"""The synthesis core: lengths, levels, and the determinism the studio's claim rests on.

A cue that changes between two renders cannot be cut against, so the seeded-noise
promise is asserted on bytes. Levels are asserted at both ends: nothing silent, and
nothing past full scale after the limiter or after the int16 conversion.
"""
from __future__ import annotations

import wave

import pytest

from core import film_synth as synth

FLOOR = 0.02


def _peak(layer: tuple[list[float], list[float]]) -> float:
    return max(
        max((abs(value) for value in layer[0]), default=0.0),
        max((abs(value) for value in layer[1]), default=0.0)
    )


def _write(tmp_path, name: str, layer) -> bytes:
    target = tmp_path / name
    synth.write_wav(target, layer)
    return target.read_bytes()


def test_given_a_two_second_tone_when_rendered_then_it_holds_ninety_six_thousand_samples():
    """GIVEN a tone of two seconds WHEN it renders THEN both channels carry 48 kHz x 2."""
    left, right = synth.tone(440.0, 2.0)
    assert len(left) == len(right) == 2 * synth.SAMPLE_RATE


def test_given_a_tone_when_rendered_then_it_is_audible_and_inside_full_scale():
    """GIVEN a rendered tone WHEN its samples are read THEN it is above the floor, at or under full scale."""
    layer = synth.tone(320.0, 0.5, shape="triangle", amp=0.9)
    assert _peak(layer) > FLOOR
    assert _peak(layer) <= 1.0


@pytest.mark.parametrize("shape", ["sine", "triangle", "square"])
def test_given_each_wave_shape_when_it_renders_then_no_sample_leaves_the_signed_range(shape):
    """GIVEN a wave shape on the table WHEN it renders THEN its samples stay inside the range."""
    layer = synth.tone(180.0, 0.2, shape=shape, amp=1.0)
    assert _peak(layer) > FLOOR
    assert _peak(layer) <= 1.0


def test_given_an_unknown_wave_shape_when_a_tone_is_asked_then_the_request_is_refused():
    """GIVEN a shape off the table WHEN a tone is asked for THEN the call names the shapes."""
    with pytest.raises(ValueError) as caught:
        synth.tone(440.0, 0.1, shape="sawtooth")
    assert "sine" in str(caught.value)


def test_given_the_same_arguments_when_noise_renders_twice_then_the_wav_bytes_are_identical(tmp_path):
    """GIVEN one set of noise arguments WHEN they render twice THEN the files match byte for byte."""
    first = _write(tmp_path, "a.wav", synth.noise(0.3, seed=7, cutoff=1800.0, amp=0.4))
    second = _write(tmp_path, "b.wav", synth.noise(0.3, seed=7, cutoff=1800.0, amp=0.4))
    assert first == second


def test_given_a_different_seed_when_noise_renders_then_the_wav_bytes_differ(tmp_path):
    """GIVEN two seeds WHEN the same noise renders THEN the two files are not the same bytes."""
    first = _write(tmp_path, "a.wav", synth.noise(0.3, seed=7, amp=0.4))
    second = _write(tmp_path, "b.wav", synth.noise(0.3, seed=8, amp=0.4))
    assert first != second


def test_given_a_filtered_noise_burst_when_it_renders_then_it_is_audible_without_a_click_at_the_edges():
    """GIVEN a low-passed burst WHEN it renders THEN it rises above the floor and ends at zero."""
    left, right = synth.noise(0.25, seed=2, cutoff=900.0, amp=0.5)
    assert _peak((left, right)) > FLOOR
    assert abs(left[0]) < 0.01 and abs(left[-1]) < 0.01


def test_given_a_note_when_it_renders_then_the_tail_decays_to_silence():
    """GIVEN a struck note WHEN its tail is read THEN the last samples are quieter than the peak."""
    left, _ = synth.note(660.0, 0.8, decay=0.15)
    peak = max(abs(value) for value in left)
    tail = max(abs(value) for value in left[-200:])
    assert peak > FLOOR
    assert tail < peak * 0.1


def test_given_silence_when_it_renders_then_the_buffer_is_flat():
    """GIVEN a length WHEN silence renders THEN every sample is zero."""
    layer = synth.silence(0.1)
    assert _peak(layer) == 0.0
    assert len(layer[0]) == int(0.1 * synth.SAMPLE_RATE)


def test_given_layers_louder_than_full_scale_when_they_mix_then_the_limit_holds():
    """GIVEN three layers of full-scale tones WHEN they mix THEN the sum stays inside full scale."""
    layers = [
        synth.tone(220.0, 0.2, amp=1.0),
        synth.tone(330.0, 0.2, amp=1.0),
        synth.tone(440.0, 0.2, amp=1.0),
    ]
    mixed = synth.mix(layers)
    assert _peak(mixed) <= 1.0
    assert _peak(mixed) > FLOOR


def test_given_layers_of_different_lengths_when_they_mix_then_the_shorter_one_pads_out():
    """GIVEN a short layer beside a long one WHEN they mix THEN the result is the longer length."""
    mixed = synth.mix([synth.tone(300.0, 0.1, amp=0.5), synth.tone(300.0, 0.4, amp=0.2)])
    assert len(mixed[0]) == int(0.4 * synth.SAMPLE_RATE)


def test_given_samples_past_full_scale_when_they_convert_then_int16_stays_in_range():
    """GIVEN samples beyond plus and minus one WHEN they convert THEN none passes full scale."""
    frames = synth.to_int16([1.5, -1.5, 0.0, 0.5, 1.0])
    assert all(abs(value) <= synth.FULL_SCALE for value in frames)
    assert frames[2] == 0
    assert frames[0] == frames[4] == -frames[1] > frames[3] > 0


def test_given_stereo_channels_when_they_convert_then_the_frames_interleave_as_pcm(tmp_path):
    """GIVEN two channels WHEN they pack THEN the block length says two channels of 16-bit."""
    block = synth.to_int16_stereo([0.5, -0.5], [0.25, -0.25])
    assert len(block) == 2 * 2 * 2


def test_given_a_pair_and_a_layer_list_when_both_are_written_then_both_produce_a_wav(tmp_path):
    """GIVEN the two accepted shapes WHEN either is written THEN both land as readable stereo PCM."""
    pair = synth.tone(300.0, 0.1, amp=0.4)
    layers = [synth.tone(300.0, 0.1, amp=0.4), synth.noise(0.1, seed=4, amp=0.1)]
    for index, argument in enumerate((pair, layers)):
        target = tmp_path / f"shape-{index}.wav"
        synth.write_wav(target, argument)
        with wave.open(str(target)) as handle:
            assert handle.getnchannels() == 2
            assert handle.getframerate() == synth.SAMPLE_RATE
            assert handle.getsampwidth() == 2
            assert handle.getnframes() > 0


@pytest.mark.parametrize("name", sorted(synth.SFX))
def test_given_every_effect_on_the_table_when_it_renders_then_it_is_audible_and_limited(name):
    """GIVEN a named effect WHEN it renders THEN it is above the floor and inside full scale."""
    layer = synth.render_sfx(name)
    assert _peak(layer) > FLOOR, f"{name} rendered silent"
    assert _peak(layer) <= 1.0, f"{name} passed full scale"


@pytest.mark.parametrize("name", sorted(synth.SFX))
def test_given_every_effect_on_the_table_when_it_is_written_then_the_wav_is_the_asked_duration(tmp_path, name):
    """GIVEN a named effect and a length WHEN it is written THEN the file reads back at that length."""
    target = tmp_path / f"{name}.wav"
    synth.write_wav(target, synth.render_sfx(name, seconds=1.0))
    with wave.open(str(target)) as handle:
        assert handle.getframerate() == synth.SAMPLE_RATE
        assert handle.getnframes() == int(1.0 * synth.SAMPLE_RATE)


@pytest.mark.parametrize("name", sorted(synth.MUSIC))
def test_given_every_bed_on_the_table_when_it_renders_then_the_wav_holds_the_bars(tmp_path, name):
    """GIVEN a named bed at a tempo WHEN two bars render THEN the file holds eight beats of that tempo."""
    bars, bpm = 2, 120
    target = tmp_path / f"{name}.wav"
    synth.write_wav(target, synth.music_bed(name, bars=bars, bpm=bpm, seed=5))
    asked = bars * 4 * 60.0 / bpm
    with wave.open(str(target)) as handle:
        assert handle.getnchannels() == 2
        assert abs(handle.getnframes() / handle.getframerate() - asked) < 0.02


@pytest.mark.parametrize("name", sorted(synth.MUSIC))
def test_given_every_bed_on_the_table_when_it_renders_then_it_is_audible_and_limited(tmp_path, name):
    """GIVEN a named bed WHEN it renders THEN it is above the floor and inside full scale."""
    layer = synth.music_bed(name, bars=1, bpm=100, seed=1)
    assert _peak(layer) > FLOOR, f"{name} rendered silent"
    assert _peak(layer) <= 1.0, f"{name} passed full scale"


def test_given_a_randomised_effect_when_it_renders_twice_then_the_wav_bytes_are_identical(tmp_path):
    """GIVEN the effect whose bursts fall at seeded places WHEN it renders twice THEN the bytes match."""
    first = _write(tmp_path, "a.wav", synth.render_sfx("glitch"))
    second = _write(tmp_path, "b.wav", synth.render_sfx("glitch"))
    assert first == second


def test_given_one_bed_at_one_seed_when_it_renders_twice_then_the_wav_bytes_are_identical(tmp_path):
    """GIVEN one (name, bpm, bars, seed) WHEN it renders twice THEN the bytes match."""
    first = _write(tmp_path, "a.wav", synth.music_bed("driving", bars=1, bpm=128, seed=9))
    second = _write(tmp_path, "b.wav", synth.music_bed("driving", bars=1, bpm=128, seed=9))
    assert first == second


def test_given_one_bed_at_another_bpm_when_it_renders_then_the_wav_bytes_differ(tmp_path):
    """GIVEN the same bed at two tempos WHEN both render THEN the files are not the same bytes."""
    slow = _write(tmp_path, "slow.wav", synth.music_bed("calm", bars=1, bpm=70, seed=0))
    fast = _write(tmp_path, "fast.wav", synth.music_bed("calm", bars=1, bpm=96, seed=0))
    assert slow != fast


def test_given_the_published_tables_when_they_are_read_then_they_carry_the_names_the_product_says():
    """GIVEN the effect and bed tables WHEN they are read THEN they hold exactly the named surface."""
    assert set(synth.SFX) == {
        "click", "tick", "pop", "thud", "whoosh", "riser", "chime", "success",
        "error", "ui_hover", "glitch", "countdown",
    }
    assert set(synth.MUSIC) == {"calm", "driving", "playful", "tense", "corporate"}


def test_given_an_effect_off_the_table_when_it_is_rendered_then_the_call_raises_key_error():
    """GIVEN a name no recipe carries WHEN it renders THEN the table says so."""
    with pytest.raises(KeyError):
        synth.render_sfx("airhorn")
