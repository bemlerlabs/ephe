#!/usr/bin/env python3
"""Synthesize the first-open score, deterministically, at 48 kHz stereo.

The cues are cut on the film's own clock: the spark falls and lands at 0.7 s, the
chase runs 2.2-5.2 s with the pan following the spark's x, two heartbeats sit in
the close-up at 5.6 s and 6.12 s, the wing burst lands at 8.0 s in a Dmaj9 chord,
and the awakening pad carries to 12.8 s. `scripts/render_onboarding_film.py` muxes
the result into the MP4 (AAC) and WebM (Opus).

    python3 scripts/generate_onboarding_audio.py --out build/first-run-score.wav
"""
from __future__ import annotations

import argparse
import math
import struct
import wave
from pathlib import Path

SR = 48_000
DUR = 12.8
N = int(SR * DUR)
TAU = math.pi * 2

D3 = 146.83
A3 = 220.0
C4 = 261.63
D4 = 293.66
E4 = 329.63
FS4 = 369.99
A4 = 440.0
CS5 = 554.37
D5 = 587.33
E5 = 659.25
FS5 = 739.99
A5 = 880.0
B5 = 987.77
D6 = 1174.66
FS6 = 1479.98
A6 = 1760.0

CHASE_X = [
    (2.2, 0.5), (2.6, 0.34), (3.0, 0.22), (3.3, 0.4), (3.6, 0.66),
    (3.9, 0.78), (4.2, 0.62), (4.55, 0.38), (4.8, 0.3), (4.95, 0.46), (5.2, 0.5),
]


def chase_x(t: float) -> float:
    if t <= CHASE_X[0][0]:
        return CHASE_X[0][1]
    for (t0, x0), (t1, x1) in zip(CHASE_X, CHASE_X[1:]):
        if t <= t1:
            return x0 + (x1 - x0) * (t - t0) / (t1 - t0)
    return CHASE_X[-1][1]


def mulberry32(seed: int):
    state = seed & 0xFFFFFFFF

    def nxt() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        value = state
        value = ((value ^ (value >> 15)) * (value | 1)) & 0xFFFFFFFF
        value ^= (value + ((value ^ (value >> 7)) * (value | 61))) & 0xFFFFFFFF
        return ((value ^ (value >> 14)) & 0xFFFFFFFF) / 4294967296

    return nxt


rand = mulberry32(0x5EED_2026)
NOISE = [rand() * 2 - 1 for _ in range(N)]

left = [0.0] * N
right = [0.0] * N


def pan_gains(pan: float) -> tuple[float, float]:
    theta = (max(-1.0, min(1.0, pan)) + 1.0) * math.pi / 4
    return math.cos(theta), math.sin(theta)


def add_samples(start: float, samples: list[float], amp: float, pan: float) -> None:
    begin = max(0, int(start * SR))
    gain_l, gain_r = pan_gains(pan)
    for index, sample in enumerate(samples):
        at = begin + index
        if at >= N:
            break
        left[at] += sample * amp * gain_l
        right[at] += sample * amp * gain_r


def tone(
    start: float,
    duration: float,
    freq: float,
    *,
    amp: float,
    pan: float = 0.0,
    attack: float = 0.01,
    decay: float = 0.0,
    harmonics: tuple[tuple[float, float], ...] = ((1.0, 1.0),),
    glide: float = 0.0,
) -> None:
    count = int(duration * SR)
    samples: list[float] = []
    for i in range(count):
        t = i / SR
        attack_env = min(1.0, t / attack) if attack > 0 else 1.0
        decay_env = math.exp(-t / decay) if decay > 0 else 1.0
        fade_out = 1.0
        if t > duration - 0.08:
            fade_out = max(0.0, (duration - t) / 0.08)
        f = max(20.0, freq + glide * t)
        value = 0.0
        for ratio, level in harmonics:
            value += math.sin(TAU * f * ratio * t) * level
        samples.append(value * attack_env * decay_env * fade_out)
    add_samples(start, samples, amp, pan)


def bell(start: float, note: float, *, amp: float, pan: float, decay: float = 1.1) -> None:
    tone(
        start,
        1.25,
        note,
        amp=amp,
        pan=pan,
        attack=0.006,
        decay=decay,
        harmonics=((1.0, 1.0), (2.01, 0.26), (3.02, 0.09)),
    )


def band_noise(
    start: float,
    duration: float,
    *,
    amp: float,
    pan: float,
    sweep: tuple[float, ...],
    q: float = 0.9,
    attack: float = 0.04,
) -> None:
    count = int(duration * SR)
    begin = int(start * SR)
    low = 0.0
    band = 0.0
    samples: list[float] = []
    for i in range(count):
        progress = i / max(1, count - 1)
        segment = progress * (len(sweep) - 1)
        slot = min(len(sweep) - 2, int(segment))
        local = segment - slot
        centre = sweep[slot] + (sweep[slot + 1] - sweep[slot]) * local
        f = 2 * math.sin(math.pi * min(centre, SR / 6) / SR)
        source = NOISE[(begin + i) % N]
        low += f * band
        high = source - low - q * band
        band += f * high
        t = i / SR
        env = min(1.0, t / attack) * min(1.0, (duration - t) / 0.1)
        samples.append(band * max(0.0, env))
    add_samples(start, samples, amp, pan)


def pad(start: float, duration: float, notes: tuple[float, ...], amp: float) -> None:
    for index, note in enumerate(notes):
        pan = -0.55 + index * 0.28
        tone(
            start,
            duration,
            note,
            amp=amp,
            pan=pan,
            attack=1.4,
            harmonics=((1.0, 1.0), (2.0, 0.16), (1.005, 0.5)),
        )


# 1. Night bed and the D-dorian pad, both ends faded.
for i in range(N):
    t = i / SR
    env = min(1.0, t / 1.6) * min(1.0, (DUR - t) / 1.4)
    left[i] += NOISE[i] * 0.012 * env
    right[i] += NOISE[(i * 7 + 11) % N] * 0.012 * env
for cricket_at in (1.1, 3.3, 5.0, 7.1, 9.9, 11.6):
    for offset in (0.0, 0.09, 0.17):
        tone(
            cricket_at + offset,
            0.035,
            4100 + offset * 600,
            amp=0.012,
            pan=0.5 - offset * 3,
            attack=0.004,
            decay=0.03,
        )
pad(0.0, DUR, (D3, A3, C4, E4, FS4), 0.03)

# 2. The fall (0.2-0.7) and the impact at 0.7.
tone(
    0.18,
    0.55,
    2100,
    amp=0.045,
    pan=-0.25,
    attack=0.02,
    decay=0.42,
    glide=-2600,
    harmonics=((1.0, 1.0), (2.0, 0.4), (3.0, 0.15)),
)
tone(0.7, 1.4, 65, amp=0.32, pan=0.0, attack=0.004, decay=0.55, harmonics=((1.0, 1.0), (2.0, 0.18)))
tone(0.7, 0.9, 784, amp=0.06, pan=0.15, attack=0.003, decay=0.32, harmonics=((1.0, 1.0), (2.0, 0.35)))
band_noise(0.7, 0.5, amp=0.08, pan=0.0, sweep=(900, 2400, 300), q=1.2, attack=0.004)

# 3. The chase: whooshes panned to the spark, celesta over the stream.
whoosh_at = 2.28
while whoosh_at < 5.1:
    pan = (chase_x(whoosh_at) - 0.5) * 1.6
    band_noise(whoosh_at, 0.3, amp=0.075, pan=pan, sweep=(420, 1700, 700), q=1.1, attack=0.02)
    whoosh_at += 0.26
for index, (at, note) in enumerate(
    zip((2.45, 2.9, 3.35, 3.8, 4.25, 4.7, 5.05), (D5, FS5, A5, B5, D6, A5, FS5))
):
    bell(at, note, amp=0.05, pan=-0.35 + index * 0.12, decay=0.85)

# 4. Close-up: two heartbeats and the fireflies' rising sizzle.
for beat_at in (5.6, 6.12):
    tone(beat_at, 0.3, 55, amp=0.24, attack=0.005, decay=0.12)
    tone(beat_at + 0.16, 0.24, 48, amp=0.15, attack=0.005, decay=0.1)
band_noise(5.25, 1.3, amp=0.05, pan=0.2, sweep=(1800, 5200, 7200), q=0.8, attack=0.5)
pings = 5.35
step = 0
while pings < 6.5:
    bell(pings, (D6, FS6, A6)[step % 3], amp=0.018 + step * 0.003, pan=math.sin(step) * 0.7, decay=0.4)
    pings += 0.12
    step += 1

# 5. Vortex suction, orchestral swell, the 8.0 s wing burst.
band_noise(6.6, 1.4, amp=0.09, pan=0.0, sweep=(160, 900, 2600), q=1.3, attack=0.9)
for index, note in enumerate((D3, A3, D4, E4, FS4)):
    tone(
        6.6,
        1.4,
        note,
        amp=0.018 + index * 0.006,
        pan=-0.4 + index * 0.2,
        attack=1.35,
        harmonics=((1.0, 1.0), (2.0, 0.2), (3.0, 0.08)),
    )
# Dmaj9 at the burst: D F# A C# E.
for index, note in enumerate((D4, FS4, A4, CS5, E5)):
    bell(8.0 + index * 0.055, note, amp=0.075 - index * 0.006, pan=-0.5 + index * 0.25, decay=1.5)
pad(8.0, 4.8, (D4, FS4, A4, CS5, E5), 0.014)
for flap_at in (8.0, 8.22):
    band_noise(flap_at, 0.26, amp=0.06, pan=-0.15, sweep=(380, 900, 260), q=1.4, attack=0.03)

# 6. Awakening shimmer into the fade.
for at, note in ((9.4, D5), (9.45, FS5), (9.5, A5), (9.55, D6)):
    bell(at, note, amp=0.028, pan=0.3 - (at - 9.4) * 1.4, decay=1.8)

# Normalise with a soft ceiling; 16-bit PCM stereo.
peak = max(max(abs(v) for v in left), max(abs(v) for v in right), 1e-9)
scale = 0.89 / peak
frames = bytearray()
for l, r in zip(left, right):
    sl = int(math.tanh(l * scale * 1.05) * 32767)
    sr = int(math.tanh(r * scale * 1.05) * 32767)
    frames += struct.pack('<hh', sl, sr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=Path('build/first-run-score.wav'))
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(args.out), 'wb') as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes(bytes(frames))
    print(f'{args.out} ({args.out.stat().st_size / 1e6:.1f} MB, {DUR:.1f} s)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
