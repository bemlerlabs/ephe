"""Synthesised audio for the film verbs, on the standard library alone.

``core/voice_synth.py`` asks piper for speech. A cut needs more around the speech —
a hit, a bed, a riser — and none of that wants a binary, a model or ``numpy`` on
the machine: oscillators, one-pole filters and the ``wave`` module cover it.

This lives in ``core/`` and not beside ``scripts/generate_onboarding_audio.py``,
which already builds waveforms for the first-run film. That script arranges one
fixed score whose cue times are that film's edit, it mixes at import time, and
``core/`` may not import ``scripts/`` (docs/ARCHITECTURE.md). Its shapes are the
ones measured here — phase-accumulator oscillators, one-pole filtered noise, the
harmonic stacks, all at 48 kHz — and the arrangement is per call.

Same arguments, same bytes: the only random source is seeded from the call, so a
re-render of a cue is byte-identical and a cached cut stays valid.
"""
from __future__ import annotations

import math
import random
import struct
import wave
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import cast
from pathlib import Path

SAMPLE_RATE = 48_000
FULL_SCALE = 32767
#: A rounding step under full scale, so the float→int16 round cannot reach a clipped sample.
CEILING = 0.9995
TAU = 2.0 * math.pi

#: A rendered sound: two float channels in -1.0..1.0.
Layer = tuple[list[float], list[float]]


def count(seconds: float) -> int:
    return max(1, int(round(float(seconds) * SAMPLE_RATE)))


def _pan_gains(pan: float) -> tuple[float, float]:
    """Equal-power pan, so a centred source keeps mono loudness."""
    clamped = max(-1.0, min(1.0, float(pan)))
    theta = (clamped + 1.0) * math.pi / 4.0
    return math.cos(theta), math.sin(theta)


def _fades(total: int, attack: int, release: int) -> tuple[int, int]:
    """Attack and release lengths in samples, each kept under half the buffer."""
    attack_n = max(1, min(attack, total // 2))
    release_n = max(1, min(release, total - attack_n))
    return attack_n, release_n


def _fade(index: int, total: int, attack: int, release: int) -> float:
    if index < attack:
        return index / attack
    from_end = total - index
    if from_end <= release:
        return from_end / release
    return 1.0


#: A bare square aliases above a few hundred hertz; the table keeps it for short
#: hits, where the edge is what the sound is made of.
_SHAPES: dict[str, Callable[[float], float]] = {
    "sine": lambda phase: math.sin(TAU * phase),
    "triangle": lambda phase: 4.0 * phase - 1.0 if phase < 0.5 else 3.0 - 4.0 * phase,
    "square": lambda phase: 1.0 if phase < 0.5 else -1.0,
}


def _one_pole_coefficient(cutoff: float) -> float:
    return 1.0 - math.exp(-TAU * min(cutoff, SAMPLE_RATE / 6.0) / SAMPLE_RATE)


def tone(
    freq: float,
    seconds: float,
    *,
    shape: str = "sine",
    amp: float = 0.3,
    pan: float = 0.0,
    attack: float = 0.005,
    release: float = 0.02,
    glide_to: float | None = None,
) -> Layer:
    """One oscillator over `seconds`, faded at both ends so nothing clicks."""
    wave_shape = _SHAPES.get(shape)
    if wave_shape is None:
        raise ValueError(f"unknown wave shape {shape!r} — one of {', '.join(_SHAPES)}")
    total = count(seconds)
    attack_n, release_n = _fades(total, count(attack), count(release))
    gain_left, gain_right = _pan_gains(pan)
    start_hz, end_hz = float(freq), float(freq if glide_to is None else glide_to)
    phase = 0.0
    left = [0.0] * total
    right = [0.0] * total
    for index in range(total):
        phase += (start_hz + (end_hz - start_hz) * (index / total)) / SAMPLE_RATE
        if phase >= 1.0:
            phase -= math.floor(phase)
        value = wave_shape(phase) * amp * _fade(index, total, attack_n, release_n)
        left[index] = value * gain_left
        right[index] = value * gain_right
    return left, right


def noise(
    seconds: float,
    *,
    seed: int = 0,
    cutoff: float | None = None,
    sweep: tuple[float, float] | None = None,
    amp: float = 0.3,
    pan: float = 0.0,
    attack: float = 0.01,
    release: float = 0.05,
) -> Layer:
    """Seeded white noise, optionally through a one-pole low-pass that may move.

    The buffer is peak-scaled before `amp`, so a filtered burst stays as loud as an
    unfiltered one and `amp` alone decides the level.
    """
    total = count(seconds)
    attack_n, release_n = _fades(total, count(attack), count(release))
    draw = random.Random(seed).uniform
    gain_left, gain_right = _pan_gains(pan)
    state = 0.0
    peak = 0.0
    values = [0.0] * total
    for index in range(total):
        source = draw(-1.0, 1.0)
        coefficient: float | None = None
        if sweep is not None:
            progress = index / total
            coefficient = _one_pole_coefficient(sweep[0] + (sweep[1] - sweep[0]) * progress)
        elif cutoff is not None:
            coefficient = _one_pole_coefficient(cutoff)
        if coefficient is None:
            value = source
        else:
            state += coefficient * (source - state)
            value = state
        values[index] = value
        if abs(value) > peak:
            peak = abs(value)
    scale = amp / peak if peak > 0.0 else 0.0
    left = [0.0] * total
    right = [0.0] * total
    for index, value in enumerate(values):
        value *= scale * _fade(index, total, attack_n, release_n)
        left[index] = value * gain_left
        right[index] = value * gain_right
    return left, right


#: A struck string reads as a fundamental plus inharmonic-free partials falling away.
_BELL_HARMONICS: tuple[tuple[float, float], ...] = (
    (1.0, 1.0),
    (2.0, 0.3),
    (3.0, 0.12),
    (4.0, 0.05),
)


def note(
    freq: float,
    seconds: float,
    *,
    harmonics: tuple[tuple[float, float], ...] = _BELL_HARMONICS,
    decay: float = 0.35,
    amp: float = 0.3,
    pan: float = 0.0,
    attack: float = 0.004,
) -> Layer:
    """A struck voice: harmonics off one phase accumulator, exponential decay."""
    total = count(seconds)
    attack_n, release_n = _fades(total, count(attack), count(0.01))
    gain_left, gain_right = _pan_gains(pan)
    phase = 0.0
    step = float(freq) / SAMPLE_RATE
    left = [0.0] * total
    right = [0.0] * total
    for index in range(total):
        phase += step
        if phase >= 1.0:
            phase -= 1.0
        value = 0.0
        for ratio, level in harmonics:
            value += math.sin(TAU * ratio * phase) * level
        envelope = (
            (1.0 - math.exp(-(index / SAMPLE_RATE) / (attack_n / SAMPLE_RATE)))
            * math.exp(-(index / SAMPLE_RATE) / max(decay, 1e-4))
            * _fade(index, total, attack_n, release_n)
        )
        value *= amp * envelope
        left[index] = value * gain_left
        right[index] = value * gain_right
    return left, right


def silence(seconds: float) -> Layer:
    total = count(seconds)
    return [0.0] * total, [0.0] * total


def canvas(seconds: float) -> Layer:
    """A buffer of the asked length for `place` to fill."""
    return silence(seconds)


def place(target: Layer, source: Layer, at: float = 0.0, amp: float = 1.0) -> Layer:
    """Add `source` into `target` at `at` seconds. Returns `target` for chaining."""
    begin = int(round(at * SAMPLE_RATE))
    for channel in (0, 1):
        destination = target[channel]
        for offset, value in enumerate(source[channel]):
            slot = begin + offset
            if slot >= len(destination):
                break
            if slot >= 0:
                destination[slot] += value * amp
    return target


def _clamp(value: float) -> float:
    if value > CEILING:
        return CEILING
    if value < -CEILING:
        return -CEILING
    return value


def mix(layers: Sequence[Layer]) -> Layer:
    """Sum stereo layers, shorter ones padded with silence, then limit.

    A loud passage loses level rather than gaining distortion: the whole sum is
    pulled down when its peak passes the ceiling, and the clamp afterwards only
    catches what a rounding step could still push over.
    """
    total = max((len(channel) for layer in layers for channel in layer), default=0)
    if not total:
        return [], []
    left = [0.0] * total
    right = [0.0] * total
    for layer in layers:
        for index, value in enumerate(layer[0]):
            left[index] += value
        for index, value in enumerate(layer[1]):
            right[index] += value
    peak = max(
        max(abs(value) for value in left),
        max(abs(value) for value in right),
        CEILING,
    )
    scale = 1.0 if peak <= CEILING else CEILING / peak
    return (
        [_clamp(value * scale) for value in left],
        [_clamp(value * scale) for value in right],
    )


def to_int16(values: Iterable[float]) -> list[int]:
    """Mono float samples as 16-bit integers, clamped inside full scale."""
    return [int(round(_clamp(float(value)) * FULL_SCALE)) for value in values]


def to_int16_stereo(left: Sequence[float], right: Sequence[float]) -> bytes:
    """Interleaved 16-bit little-endian PCM frames, packed in blocks."""
    frames = zip(to_int16(left), to_int16(right))
    block = 4096
    buffer = bytearray()
    batch: list[int] = []
    for pair in frames:
        batch.extend(pair)
        if len(batch) >= block * 2:
            buffer += struct.pack(f"<{len(batch)}h", *batch)
            batch = []
    if batch:
        buffer += struct.pack(f"<{len(batch)}h", *batch)
    return bytes(buffer)


def _as_pair(layers_or_lr: Sequence[Layer] | Layer) -> Layer:
    """Either one ``(left, right)`` pair or a list of layers to mix, in one shape.

    A stereo pair starts with a channel of numbers; a list of layers starts with a
    layer, which is itself a pair.
    """
    if not len(layers_or_lr):
        return [], []
    first = layers_or_lr[0]
    # The probe is the authority on the shape; the casts only state what it proved.
    if isinstance(first, Sequence) and len(first) and isinstance(first[0], (int, float)):
        return mix([cast(Layer, layers_or_lr)])
    return mix(cast("Sequence[Layer]", layers_or_lr))


def write_wav(path: str | Path, layers_or_lr: Sequence[Layer] | Layer) -> Path:
    """Write stereo 16-bit PCM at 48 kHz. The only function here that touches disk."""
    left, right = _as_pair(layers_or_lr)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(to_int16_stereo(left, right))
    return target


def _semitone(root: float, semitones: float) -> float:
    return root * (2.0 ** (semitones / 12.0))


@dataclass(frozen=True)
class Recipe:
    """One named effect: its natural length and a builder that stretches it."""

    seconds: float
    build: Callable[[float], list[Layer]]


def _click(seconds: float) -> list[Layer]:
    hit = min(seconds, 0.035)
    return [
        tone(1150.0, hit, shape="square", amp=0.42, attack=0.0006, release=0.012),
        noise(hit, seed=11, cutoff=5200.0, amp=0.16, attack=0.0006, release=0.008),
    ]


def _tick(seconds: float) -> list[Layer]:
    hit = min(seconds, 0.02)
    return [
        tone(2400.0, hit * 0.7, amp=0.26, attack=0.0004, release=0.004),
        noise(hit, seed=3, cutoff=7200.0, amp=0.13, attack=0.0004, release=0.006),
    ]


def _pop(seconds: float) -> list[Layer]:
    body = min(seconds, 0.1)
    return [
        tone(340.0, body, amp=0.55, attack=0.001, release=0.02, glide_to=95.0),
        noise(0.02, seed=17, cutoff=2600.0, amp=0.2, attack=0.0005, release=0.008),
    ]


def _thud(seconds: float) -> list[Layer]:
    body = min(seconds, 0.32)
    return [
        tone(58.0, body, amp=0.8, attack=0.003, release=0.05, glide_to=41.0),
        note(116.0, body * 0.5, decay=0.05, amp=0.16),
        noise(0.06, seed=5, cutoff=240.0, amp=0.26, attack=0.001, release=0.02),
    ]


def _whoosh(seconds: float) -> list[Layer]:
    return [
        noise(
            seconds,
            seed=21,
            sweep=(320.0, 1900.0),
            amp=0.24,
            attack=seconds * 0.35,
            release=seconds * 0.25,
        ),
        noise(
            seconds * 0.7,
            seed=22,
            cutoff=2600.0,
            amp=0.11,
            attack=seconds * 0.4,
            release=seconds * 0.3,
        ),
        tone(
            190.0,
            seconds * 0.6,
            amp=0.07,
            attack=seconds * 0.3,
            release=0.08,
            glide_to=92.0,
        ),
    ]


def _riser(seconds: float) -> list[Layer]:
    return [
        tone(
            220.0,
            seconds,
            shape="triangle",
            amp=0.18,
            attack=seconds * 0.8,
            release=0.03,
            glide_to=1760.0,
        ),
        noise(
            seconds,
            seed=31,
            sweep=(400.0, 6200.0),
            amp=0.2,
            attack=seconds * 0.75,
            release=0.03,
        ),
    ]


def _chime(seconds: float) -> list[Layer]:
    bed = canvas(seconds)
    step = min(0.16, seconds / 4.0)
    for offset, freq in enumerate((659.25, 987.77, 1318.51)):
        place(
            bed,
            note(freq, min(1.4, seconds - offset * step), decay=0.9, amp=0.22,
                 pan=(offset - 1) * 0.3),
            at=offset * step,
        )
    return [bed]


def _success(seconds: float) -> list[Layer]:
    bed = canvas(seconds)
    step = min(0.1, seconds / 6.0)
    for offset, freq in enumerate((523.25, 659.25, 783.99, 1046.5)):
        place(
            bed,
            note(freq, min(0.9, seconds - offset * step), decay=0.45, amp=0.24,
                 pan=-0.3 + offset * 0.2),
            at=offset * step,
        )
    return [bed]


def _error(seconds: float) -> list[Layer]:
    bed = canvas(seconds)
    place(bed, tone(392.0, 0.16, shape="square", amp=0.2, attack=0.002, release=0.03))
    place(
        bed,
        tone(261.63, 0.34, shape="square", amp=0.2, attack=0.002, release=0.05),
        at=0.18,
    )
    place(bed, noise(0.09, seed=41, cutoff=900.0, amp=0.07), at=0.18)
    return [bed]


def _ui_hover(seconds: float) -> list[Layer]:
    hit = min(seconds, 0.022)
    return [tone(2050.0, hit, amp=0.11, attack=0.001, release=0.008)]


def _glitch(seconds: float) -> list[Layer]:
    """Seeded bursts at seeded pitches; the same arguments give the same broken clock."""
    bed = canvas(seconds)
    draw = random.Random(13)
    for _ in range(7):
        at = draw.uniform(0.0, max(0.0, seconds - 0.05))
        freq = draw.uniform(180.0, 3400.0)
        length = draw.uniform(0.006, 0.045)
        place(
            bed,
            tone(freq, length, shape="square", amp=draw.uniform(0.06, 0.24),
                 attack=0.0005, release=0.004, pan=draw.uniform(-0.8, 0.8)),
            at=at,
        )
        place(
            bed,
            noise(length, seed=int(at * 1000), cutoff=draw.uniform(600.0, 9000.0),
                  amp=0.12, attack=0.0005, release=0.004),
            at=at,
        )
    return [bed]


def _countdown(seconds: float) -> list[Layer]:
    bed = canvas(seconds)
    step = seconds / 4.0
    for beat in range(3):
        place(bed, tone(880.0, step * 0.35, amp=0.24, attack=0.002, release=0.02),
              at=beat * step)
    place(bed, tone(1320.0, step * 0.8, amp=0.28, attack=0.002, release=0.05),
          at=3 * step)
    return [bed]


#: The effects a turn can ask for by name. The names are the product surface.
SFX: dict[str, Recipe] = {
    "click": Recipe(0.06, _click),
    "tick": Recipe(0.05, _tick),
    "pop": Recipe(0.18, _pop),
    "thud": Recipe(0.4, _thud),
    "whoosh": Recipe(0.6, _whoosh),
    "riser": Recipe(1.6, _riser),
    "chime": Recipe(1.8, _chime),
    "success": Recipe(1.1, _success),
    "error": Recipe(0.7, _error),
    "ui_hover": Recipe(0.05, _ui_hover),
    "glitch": Recipe(0.5, _glitch),
    "countdown": Recipe(4.0, _countdown),
}


def render_sfx(name: str, seconds: float | None = None) -> Layer:
    """The mixed layer for one named effect. A name off the table raises KeyError."""
    recipe = SFX[name]
    length = recipe.seconds if seconds is None else max(0.002, float(seconds))
    return mix([silence(length), *recipe.build(length)])


@dataclass(frozen=True)
class Bed:
    """One music bed: a tempo, a chord cycle and the levels the drums sit at."""

    bpm: int
    root: float
    progression: tuple[tuple[int, ...], ...]
    shape: str = "triangle"
    pad_gain: float = 0.13
    bass_gain: float = 0.2
    kick_gain: float = 0.5
    hihat_gain: float = 0.07
    lead: tuple[int, ...] | None = None
    lead_gain: float = 0.16
    kick_every: float = 2.0
    hihat_every: float = 0.5


MUSIC: dict[str, Bed] = {
    "calm": Bed(
        bpm=76,
        root=130.81,
        progression=((0, 4, 7, 11), (9, 12, 16, 19), (5, 9, 12, 16), (7, 11, 14, 17)),
        shape="sine",
        kick_gain=0.3,
        hihat_gain=0.03,
        lead=(12, 16, 19, 16),
        lead_gain=0.1,
        kick_every=4.0,
        hihat_every=1.0,
    ),
    "driving": Bed(
        bpm=124,
        root=110.0,
        progression=((0, 3, 7), (8, 12, 15), (3, 7, 10), (10, 14, 17)),
        shape="square",
        pad_gain=0.09,
        bass_gain=0.26,
        kick_every=1.0,
        hihat_every=0.5,
        lead=(0, 7, 12, 15),
        lead_gain=0.1,
    ),
    "playful": Bed(
        bpm=112,
        root=146.83,
        progression=((0, 4, 7), (2, 5, 9), (7, 11, 14), (0, 4, 7)),
        shape="triangle",
        pad_gain=0.1,
        kick_gain=0.38,
        hihat_gain=0.05,
        kick_every=2.0,
        hihat_every=0.5,
        lead=(0, 4, 7, 9, 12, 9, 7, 4),
        lead_gain=0.15,
    ),
    "tense": Bed(
        bpm=92,
        root=98.0,
        progression=((0, 3, 7, 13), (0, 3, 8, 13), (0, 2, 7, 11), (0, 3, 7, 14)),
        shape="triangle",
        pad_gain=0.11,
        bass_gain=0.22,
        kick_gain=0.42,
        hihat_gain=0.045,
        kick_every=4.0,
        hihat_every=0.5,
    ),
    "corporate": Bed(
        bpm=100,
        root=130.81,
        progression=((0, 4, 7), (9, 12, 16), (5, 9, 12), (7, 11, 14)),
        shape="sine",
        pad_gain=0.12,
        bass_gain=0.18,
        kick_gain=0.32,
        hihat_gain=0.04,
        kick_every=2.0,
        hihat_every=1.0,
        lead=(12, 14, 16, 19),
        lead_gain=0.08,
    ),
}

#: The drums are noise through a one-pole low-pass; a sine kick reads as a test tone.
_KICK_HZ = 52.0
_HAT_CUTOFF = 9000.0


def music_bed(
    name: str, bars: int = 8, bpm: int | None = None, seed: int = 0
) -> Layer:
    """The mixed layer for one named bed. A name off the table raises KeyError."""
    bed = MUSIC[name]
    tempo = bed.bpm if bpm is None else min(220, max(40, int(bpm)))
    beats_per_bar = 4
    beat = 60.0 / tempo
    bar = beats_per_bar * beat
    total = max(1, int(bars)) * bar
    track = canvas(total)
    choose = random.Random(seed)
    for bar_index in range(max(1, int(bars))):
        at = bar_index * bar
        chord = bed.progression[bar_index % len(bed.progression)]
        for voice, semitones in enumerate(chord):
            freq = _semitone(bed.root, semitones) + choose.uniform(-0.6, 0.6)
            place(
                track,
                tone(
                    freq,
                    bar * 0.97,
                    shape=bed.shape,
                    amp=bed.pad_gain,
                    attack=0.03,
                    release=0.12,
                    pan=-0.5 + voice * (1.0 / max(1, len(chord) - 1)),
                ),
                at=at,
            )
        place(
            track,
            tone(
                bed.root / 2.0,
                bar * 0.4,
                amp=bed.bass_gain,
                attack=0.006,
                release=0.06,
            ),
            at=at,
        )
        for step in range(beats_per_bar):
            if (step % int(bed.kick_every)) == 0:
                hit_at = at + step * beat
                place(
                    track,
                    noise(
                        0.12,
                        seed=seed * 7919 + bar_index * 16 + step,
                        cutoff=140.0,
                        amp=bed.kick_gain,
                        attack=0.001,
                        release=0.05,
                    ),
                    at=hit_at,
                )
                place(
                    track,
                    tone(
                        _KICK_HZ,
                        0.1,
                        amp=bed.kick_gain * 0.5,
                        attack=0.001,
                        release=0.04,
                        glide_to=_KICK_HZ * 0.7,
                    ),
                    at=hit_at,
                )
        step = 0
        while step < beats_per_bar / bed.hihat_every:
            place(
                track,
                noise(
                    0.035,
                    seed=seed * 104729 + bar_index * 32 + step,
                    cutoff=_HAT_CUTOFF,
                    amp=bed.hihat_gain,
                    attack=0.001,
                    release=0.02,
                    pan=(step % 2) * 0.35 - 0.18,
                ),
                at=at + step * bed.hihat_every * beat,
            )
            step += 1
        if bed.lead:
            for step, semitones in enumerate(bed.lead):
                if step % 2:
                    continue
                place(
                    track,
                    note(
                        _semitone(bed.root * 4.0, semitones),
                        beat * 0.9,
                        decay=beat * 0.6,
                        amp=bed.lead_gain,
                        pan=choose.uniform(-0.4, 0.4),
                    ),
                    at=at + step * beat,
                )
    return mix([track])
