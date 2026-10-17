# Ephe — Offline Voice Loop (R18)

Speech output and speech input run **local first**. Microsoft Edge-TTS (cloud) is only ever an
explicit opt-in fallback.

## TTS engines (Settings → Voice)

| Engine | Behaviour |
|---|---|
| **Auto** (default) | Piper when the binary + a voice are installed — otherwise the Edge cloud fallback (existing behaviour preserved) |
| **Piper (local)** | strictly local; without setup an honest error instead of silent cloud use |
| **Edge (cloud)** | explicit opt-in, Microsoft cloud, no offline guarantee |

Configuration: `~/.ephe/voice.json` (Settings → Voice writes it; API: `GET/PUT /api/settings/voice`).

### Piper setup (local, free)

```bash
brew install piper                 # binary (alternative: pipx install piper-tts)
ephe voice install en_US-amy-medium      # voice from HuggingFace (opt-in, ~60 MB)
ephe voice install de_DE-thorsten-medium # German voice
ephe voice list                 # status: binary + installed voices
```

Afterwards pick engine "Piper (local)" in Settings → Voice (or "Auto" — it takes Piper automatically
once everything is installed). The voices live under `~/.ephe/voices/` (`.onnx` + `.onnx.json`).

Deliberately **no** piper pip dependency in the product (ONNX-Runtime is heavy — offline-first here
means: no forced ML framework). The `piper` binary is found via `shutil.which` or `EPHE_PIPER_BIN`.

## STT (faster-whisper)

- Model selectable: `tiny` (39 MB, fast) / `base` / `small` (Settings → Voice; hard-coded to "tiny" before).
- Language selectable: **auto** (detection), `de`, `en` — previously "de" was hard-coded and English input got bent out of shape.
- Installation: `pip install -e ".[voice]"` or via `ephe doctor --fix` (the repair installs the voice extra).

## Voice-Composer (PWA)

- **Hold-to-talk:** press the microphone button = record, release = stop; a short tap = hands-free mode (the old click convenience).
- **Level meter:** live RMS bar on the microphone button (AnalyserNode, no extra dependency).
- **Barge-in:** recording starts → the running read-aloud stops immediately (`ephe:stop-speech` event).
- **Auto read-aloud per session:** toggle in the StatusBar (`ephe.autospeak.session.<id>` overrides the global privacy default).

## Doctor

`ephe doctor` reports the active engine honestly: "piper local (…)" or "Edge cloud fallback (auto fallback) — switch to local: brew install piper, ephe voice install …". STT status (Whisper model/language, installed/missing) is included. The check is informational and does not feed into the exit code.

## Tests

- `tests/test_voice_config.py` — config store, engine resolution, routes, synthesis engines (Piper WAV via a mocked subprocess, Edge fallback via a mocked `edge_tts`), CLI install/list, doctor checks.
- `tests/test_audio.py` — existing coverage: transcription safety (MIME whitelist, size cap, path sandbox) unchanged.
