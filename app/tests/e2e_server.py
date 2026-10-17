#!/usr/bin/env python3
"""E2E test server: the real Ephe FastAPI server on an isolated, deterministic config.

Starts the REAL FastAPI server (uvicorn) on 127.0.0.1:8765 with:
- a fresh, empty config dir under <repo>/.e2e-runtime/config
  (no engine.json → configured=false → the setup-page flow is testable)
- the PWA build from app/dist (`npm run build` has to exist beforehand)
- isolated audio/image dirs (the user's own data is never overwritten)

A deterministic path (not tempfile.gettempdir()): the config dir sits
under <repo>/.e2e-runtime/ — that way the server (via __file__) and the
Playwright spec (via __dirname) compute the same path, and the test can
read the persisted engine.json directly.

No mock, no stub — a production-equivalent server, only the config is isolated.

Start:  .venv/bin/python app/tests/e2e_server.py   (from the repo root)
Stop:   kill $PID (or the Playwright webServer teardown)
"""
import os
import shutil
import sys
from pathlib import Path

# ── Paths (deterministic, under the repo root) ───────────────────────────────
# This file lives at: <repo>/app/tests/e2e_server.py
project_root = Path(__file__).resolve().parent.parent.parent
runtime_dir = project_root / ".e2e-runtime"
config_dir = runtime_dir / "config"
data_dir = runtime_dir / "data"

# A fresh, empty config dir → load_engine_config() → None → configured=false.
# (Cleanup again on every start: an old engine.json from a previous run would
# make the first-run flow get skipped.)
for d in (runtime_dir, config_dir, data_dir):
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
(data_dir / "audio").mkdir(parents=True, exist_ok=True)
(data_dir / "images").mkdir(parents=True, exist_ok=True)

# ── Env vars for starting the server ─────────────────────────────────────────
os.environ["EPHE_CONFIG_DIR"] = os.environ["EPHE_CONFIG_DIR"] = str(config_dir)
os.environ["EPHE_FRONTEND_DIR"] = os.environ["EPHE_FRONTEND_DIR"] = str(project_root / "app" / "dist")
os.environ["EPHE_AUDIO_DIR"] = os.environ["EPHE_AUDIO_DIR"] = str(data_dir / "audio")
os.environ["EPHE_IMAGE_DIR"] = os.environ["EPHE_IMAGE_DIR"] = str(data_dir / "images")

# ── Server start ─────────────────────────────────────────────────────────────
sys.path.insert(0, str(project_root))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    print(f"[e2e] config_dir={config_dir}", flush=True)
    print(f"[e2e] frontend={os.environ['EPHE_FRONTEND_DIR']}", flush=True)
    print("[e2e] server starting on 127.0.0.1:8765 ...", flush=True)
    uvicorn.run(
        "server.main:app",
        host="127.0.0.1",
        port=8765,
        log_level="warning",
    )
