#!/usr/bin/env python3
"""As-is audit: smoke every OpenAPI GET endpoint against a live server.

GET only (idempotent, no side effects). 404/405 on path-parameter endpoints are
expected and counted as skips; 5xx and timeouts are findings.
"""
import json
import urllib.request
import urllib.error
import time

spec = json.load(urllib.request.urlopen("http://127.0.0.1:8765/openapi.json"))
base = "http://127.0.0.1:8765"
results = {"ok": [], "skip": [], "fail": []}

for path, ops in sorted(spec["paths"].items()):
    if "get" not in ops:
        continue
    url = base + path
    if "{" in path:  # path parameter — substitute a plausible placeholder
        url = path.replace("{doc_id}", "probe").replace("{job_id}", "probe") \
                  .replace("{task_id}", "probe").replace("{name}", "help")
        url = base + url
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"Authorization": "***"})
        code = urllib.request.urlopen(req, timeout=25).status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:
        results["fail"].append((path, f"EXC {type(e).__name__}: {e}"))
        continue
    dt = int((time.time() - t0) * 1000)
    if 200 <= code < 300:
        results["ok"].append((path, code, dt))
    elif code in (401, 403):
        results["fail"].append((path, f"{code} AUTH"))
    elif code in (404, 405):
        results["skip"].append((path, code))
    else:
        results["fail"].append((path, code))

print(f"GET-Ends: ok={len(results['ok'])} skip={len(results['skip'])} FAIL={len(results['fail'])}")
slow = [x for x in results["ok"] if x[2] > 3000]
for s in slow:
    print(f"  LANG >3s: {s[0]} {s[2]}ms")
for f in results["fail"]:
    print("  FAIL:", f)
for s in results["skip"]:
    print("  skip:", s)
