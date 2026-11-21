# The demo film

`docs/media/ephe-film-studio.mp4` is a 40 second film about the Film Studio. It was cut
with [HyperFrames](https://hyperframes.heygen.com) from HTML, and every picture and sound inside it is
a file this product produced on one machine on 2026-11-19. The composition project lives outside this
repository; this page is its home in the tree, so a reader can check where each frame came from.

## The two files in the tree

| file | surface | decision it is evidence for | bytes | sha256 |
| --- | --- | --- | --- | --- |
| `docs/media/ephe-film-studio.mp4` | the README's film block and the release asset of this version | the Studio turns one sentence into a playable file on the local machine, with the approval gate shown | 7 765 255 | `491a0260d8984acd3a61904ef6042a5f047c36f508267332b0ec2619bd39ac94` |
| `docs/media/ephe-film-studio-poster.png` | the poster behind that link, at 1920×1080 | the film is the product's own surface at 2.5 s, not a mock-up | 1 566 151 | `960820a1876b48d94166cf87c7c43a92e4a63f57d28825d8ad138bbca55cbe42` |

The mp4 is h264 1920×1080 at 30 fps with a stereo aac track, 39.5 s. It was rendered by HyperFrames
0.9.70 on 2026-11-19 with the composition described below. The render itself is
`renders/ephe-film-studio_2026-11-19_23-12-50.mp4`, 7 765 566 bytes,
`55ae0efcacdfa186ce48dc0934704133fb7f043a14c0e08a766f3e245f7fa86c`. The file in the tree is that same
picture and sound rewrapped losslessly with `ffmpeg -c copy` — no re-encode, 311 bytes lighter, a
different sha256 because the container was written again. Both numbers are recorded here so the copy in
the repository can be told apart from the render it came from.

## What the film shows

| second | on screen | where it came from |
| --- | --- | --- |
| 0–5 | the product's first-run film, "Ephe ist wach" | Playwright screenshot of the built PWA at `127.0.0.1:8771`, chromium at 1920×1080, locale `de-DE` |
| 5–11 | the composer with the film brief typed in | same capture run, before the turn was sent |
| 11–18 | the approval gate for `film_card` with its three buttons | same capture run |
| 18–25 | the turn at work: analysis lines, the model's own plan, the PARAMETER blocks | same capture run |
| 25–31 | the mp4 the product wrote, playing with its own sound | `film_clip` in turn `a4004cb47d4e` |
| 31–36 | the benchmark board as it stood when the film was cut | Playwright screenshot at `127.0.0.1:8770`, console clean; that board page is not part of this release, see below |
| 36–39.5 | the wordmark and the repository | set in the app's own fonts on the app's canvas colour |

## The files the product made

| file | made by | measured |
| --- | --- | --- |
| `20261119_203622_475739_card_title.png` | `film_card` | a title card, written by the product |
| `20261119_203622_fe9b30_music_calm.wav` | `film_music` | calm, 8 bars at 92 bpm, 20.9 s at 44.1 kHz |
| `20261119_203626_7478f5_clip_cut.mp4` | `film_clip` | h264 1280×720 @ 24 fps with aac, 6.000 s, 153 kB, read with ffprobe |
| `tts_20261119_203621_7ab1e488_supertonic.wav` | `synthesize` | pcm_s16le 44100 Hz mono; the product route answered in 1173.8 ms |
| `vo-01 … vo-07.wav` | `POST /api/audio/synthesize` | the film's German narration, spoken by the local in-process rung (voice M1, `lang de`, steps 8) |

## The turn the film is about

One brief in the composer produced five tool calls in one turn: `film_status`, `film_card`,
`film_card`, `film_music`, `film_clip`. The durations 157 / 8 / 7 / 1274 / 692 ms and the turn total of
13.1 s were read from the product's own audit log (`core.audit_log`) on the server that ran the turn.
The engine that streamed the answer was the operator's own configured choice — an
OpenAI-compatible endpoint named in that machine's `~/.ephe/engine.json`, never a default.
The local voice rung was measured the same day at 1.2 s per sentence at 44.1 kHz.

## What the film does and does not say

A person answered every approval in the chat, and the film shows the gate doing it. The Studio cuts
cards, music and a voice into a file with ffmpeg. There is no text-to-video model in the product, and
the film never suggests one. The frames at 31–36 show the former benchmark board page as it stood when
the film was cut; that page ships with neither this release nor any figure table. What ships is the
offline evaluation harness (`evals/`, `ephe bench`): measurements for whoever runs
them, not a headline to read off.

## Rebuilding it

The composition is ordinary HTML with the HyperFrames render contract: one paused GSAP timeline per
composition, `class="clip"` with `data-start` and `data-duration` on every timed element, and media
addressed under `assets/`. The frames are seven sub-compositions; the bed and the narration are
`<audio>` elements in the root. Rendering is `npm run render` in that project. The screenshots were
taken with Playwright against a server started with `scripts/run_server.py` and the built PWA in
`app/dist`; a browser profile with a first-run state would not show the intro, so each capture starts a
fresh profile and dismisses `first-run-intro` before it drives the composer.
