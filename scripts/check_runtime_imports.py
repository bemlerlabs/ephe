"""Fast local runtime import diagnostics for Ephe."""
from __future__ import annotations

import json
import subprocess
import sys
import time


MODULES = ["core.tools", "core.quality", "core.chat", "core.model_provider", "server.main", "run_server", "uvicorn", "pytest"]


def check_module(module: str, timeout: int = 8) -> dict:
    start = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-c", f"import {module}; print('ok')"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "module": module,
        "status": "passed" if proc.returncode == 0 else "failed",
        "seconds": round(time.monotonic() - start, 3),
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip()[-500:],
    }


def main() -> int:
    results = []
    for module in MODULES:
        try:
            results.append(check_module(module))
        except subprocess.TimeoutExpired:
            results.append({"module": module, "status": "timeout", "seconds": 8})
    print(json.dumps({"results": results}, indent=2))
    return 1 if any(result["status"] != "passed" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
