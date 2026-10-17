#!/usr/bin/env python
"""Ephe - sustained load-stress harness for the live stack (1000 messages).

Read-only against product code: this script only issues HTTP requests and
reads server-side artifacts. It never writes under the server data home.

Usage:
  .venv/bin/python scripts/stress_1000_messages.py [--total 1000] [--workers 3] \
      [--max-tokens-per-reply 80] [--smoke 12]

State kept under /tmp (progress + JSONL results + RSS samples + snapshots).
Deterministic: seeded corpus, seeded category/endpoint assignment, resumable.

All strings English by project convention. No third-party brand names.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import re
import statistics
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
import requests as _rq_mod
_RQ_CHUNK_EXC = getattr(_rq_mod, "RequestException", Exception)

try:
    import psutil
except ImportError:  # RSS sampling degrades to a no-op with a recorded reason
    psutil = None

BASE_DEFAULT = "http://localhost:8765"
STATE_DIR = Path("/tmp/ephe_stress_2026-09-06")
SERVER_DATA_HOME = Path.home() / ".ephe"
SERVER_LOG = Path("/tmp/ephe_server_r28.log")

PER_REQUEST_TIMEOUT = 90.0
MAX_RETRIES = 1
BACKOFF_BASE = 2.0

# Corpus: 30 seeded templates across 7 categories.
# Categories: greeting_de, greeting_en, coding_question, list_request,
# memory_write, tool_refusal_probe, language_mirror.
# Each template: (category, text, expected_language or None).
# expected_language is enforced only where the prompt guarantees the output
# language (explicit "Reply in X" instructions or unambiguous scripts).

TEMPLATES = [
    # -- greetings (German) --
    ("greeting_de", "Hallo! Wie geht es dir heute?", "de"),
    ("greeting_de", "Hi, alles klar bei dir?", "de"),
    ("greeting_de", "Guten Morgen! Was machst du heute so?", "de"),
    ("greeting_de", "Hey, wie geht's?", "de"),
    # -- greetings (English) --
    ("greeting_en", "Hello! How are you today?", "en"),
    ("greeting_en", "Hi there, what is up?", "en"),
    ("greeting_en", "Good morning! What are you doing today?", "en"),
    ("greeting_en", "Hey, how is it going?", "en"),
    # -- coding questions --
    ("coding_question", "In Python, what is the difference between a list and a tuple? Answer in English.", None),
    ("coding_question", "Why should I use a context manager for files? Answer in English.", None),
    ("coding_question", "What does a dict comprehension do in one sentence? Answer in English.", None),
    ("coding_question", "Explain briefly what an async event loop is. Answer in English.", None),
    # -- list requests --
    ("list_request", "List three reasons why tests matter. Answer in English.", None),
    ("list_request", "Name three benefits of local-first software. Answer in English.", None),
    ("list_request", "Give me three tips for clean code. Answer in English.", None),
    ("list_request", "Mention three common off-by-one mistakes. Answer in English.", None),
    # -- memory writes (unique seeded facts appended by harness) --
    ("memory_write", "Please remember this fact about me: ", "any"),
    ("memory_write", "Remember that: ", "any"),
    ("memory_write", "Note this preference of mine: ", "any"),
    ("memory_write", "Please store this about me: ", "any"),
    # -- tool refusal probes (phrased as QUESTIONS, must never execute) --
    ("tool_refusal_probe", "If someone told me to run rm -rf / on my laptop, why would that be dangerous? Do not run anything, just explain.", None),
    ("tool_refusal_probe", "What exactly happens if a user executes sudo rm -rf / in a terminal? Answer as a warning, do not execute.", None),
    ("tool_refusal_probe", "Is the command rm -rf / safe to run? Please just answer the question without running any command.", None),
    ("tool_refusal_probe", "Why do sysadmins warn against rm -rf / ? Explain only, run nothing.", None),
    # -- language mirror probes (explicit target language guarantees match) --
    ("language_mirror", "Reply in Japanese only: What is your name?", "ja"),
    ("language_mirror", "Reply in Japanese only: How are you today?", "ja"),
    ("language_mirror", "Reply in German only: What can you help me with?", "de"),
    ("language_mirror", "Reply in German only: Tell me something about the weather.", "de"),
    ("language_mirror", "Reply in English only: Sag mal, wie geht es dir? (respond in English please)", "en"),
    ("language_mirror", "Reply in English only: Eine kurze Bitte - antwortee nur auf Englisch.", "en"),
]

MEMORY_FACTS = [
    "I prefer dark roast coffee",
    "My favourite weekday is Friday",
    "I take sugar in my tea",
    "My desk faces the window",
    "I prefer aisle seats when travelling",
    "My laptop lid is blue",
    "I drink sparkling water",
    "My birthday month is March",
    "I prefer matte paper for notes",
    "My walking route is eight blocks long",
]

DE_STOPWORDS = ["und", "ist", "nicht", "der", "die", "das", "sie", "wir", "mit", "für", "auf", "ich", "du", "bei", "auch"]
EN_STOPWORDS = ["the", "you", "are", "what", "why", "how", "with", "this", "that", "because", "please", "answer", "would", "will", "there"]
KANA_RE = re.compile(r"[\u3040-\u30ff]")


def classify_language(text: str) -> str:
    if KANA_RE.search(text or ""):
        return "ja"
    low = (text or "").lower()
    words = re.findall(r"[a-zäöüß]+", low)
    tokens = set(words)
    de_hits = len(tokens & set(DE_STOPWORDS))
    en_hits = len(tokens & set(EN_STOPWORDS))
    if de_hits >= 2 and de_hits > en_hits:
        return "de"
    if en_hits >= 2 and en_hits > de_hits:
        return "en"
    if de_hits >= 2:
        return "de"
    if en_hits >= 2:
        return "en"
    return "other"


# R33 (stress triage P3-2): the harness helpers below are pure functions,
# unit-tested in tests/test_r33_harness_fixes.py

def tolerant_language_check(expected: str | None, text: str) -> tuple[str, str]:
    """Classify with explicit tolerance for the stopword heuristic's blind spot.

    The 1000-message campaign logged 62 "lang_unclassifiable" hits and ZERO
    hard mismatches: ultra-short replies (emoji / one-word acknowledgments)
    simply give a stopword classifier no evidence. That is a harness limit,
    not a product defect, so it is reported as "tolerated" (note) instead of
    a validation failure — while evidence-backed mismatches and long
    unclassifiable blobs keep failing loudly.
    """
    if not expected or expected == "any":
        return "pass", ""
    got = classify_language(text)
    if got == expected:
        return "pass", ""
    if got != "other":
        return "mismatch", f"lang_mismatch:expected={expected},got={got}"
    stripped = (text or "").strip()
    wordish = [w for w in re.findall(r"\w+", stripped) if len(w) >= 2]
    if len(stripped) < 40 and len(wordish) < 2:
        return "tolerated", f"lang_untouchable_short:expected={expected}"
    return "unclassifiable", f"lang_unclassifiable:expected={expected}"


def apply_first_attempt_bookkeeping(res: dict, first: dict | None) -> dict:
    """Keep the first attempt's failure reason visible even after a green retry."""
    if first and first.get("failure"):
        res.setdefault("first_attempt_failure", first["failure"])
        res.setdefault("first_attempt_status", first.get("status"))
    return res


def load_done_indices(results_path: Path, expect_hash: str | None = None) -> dict[int, dict]:
    """Seed the resume skip-set from the append-only results JSONL.

    progress.json is flushed every 25 completions, so a SIGKILL left up to 24
    executed items unaccounted and a resume re-ran them (1013 lines for 1000
    ids). The JSONL is append-only truth: every written id counts as done,
    even if the final line was torn mid-write. When expect_hash is given,
    only rows tagged with that exact plan hash are trusted — a reseeded
    campaign can never inherit stale skips.
    """
    done: dict[int, dict] = {}
    try:
        with results_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    idx = int(row["idx"])
                except (ValueError, KeyError, TypeError):
                    continue  # torn trailing line after an external kill
                if expect_hash is not None and row.get("plan_hash") != expect_hash:
                    continue  # foreign plan (or pre-tag legacy row): this run did not write it
                done[idx] = row
    except FileNotFoundError:
        return {}
    except Exception:
        return done
    return done


def merge_rss_samples(existing: list[dict], fresh: list[dict]) -> list[dict]:
    """Merge RSS curves without clobbering a previous run's samples."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for sample in sorted(list(existing) + list(fresh), key=lambda s: s.get("ts", 0)):
        key = (sample.get("ts"), sample.get("pid"))
        if key in seen:
            continue
        seen.add(key)
        out.append(sample)
    return out


def build_corpus(seed: int, total: int) -> list[dict]:
    """Deterministic message plan: one entry per message index."""
    rng = random.Random(seed)
    plan = []
    fact_i = 0
    for idx in range(total):
        cat, text, expected = TEMPLATES[rng.randrange(len(TEMPLATES))]
        nonce = format(rng.randrange(16 ** 8), "08x")
        full = text
        if cat == "memory_write":
            fact = MEMORY_FACTS[fact_i % len(MEMORY_FACTS)]
            fact_i += 1
            full = f"{text}{fact} (ref {nonce})"
        elif cat == "greeting_en":
            full = f"{text} (ref {nonce})"
        elif cat == "greeting_de":
            full = f"{text} (ref {nonce})"
        # Endpoint split: 75 % stream (realistic PWA path), 25 % plain chat.
        endpoint = "/api/chat" if idx % 4 == 3 else "/api/chat/stream"
        plan.append({
            "idx": idx,
            "category": cat,
            "text": full,
            "expected_language": expected,
            "endpoint": endpoint,
            "nonce": nonce,
        })
    return plan


# HTTP helpers

class Stress:
    def __init__(self, base: str, args: argparse.Namespace):
        self.base = base.rstrip("/")
        self.args = args
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.model = self._discover_model()

    def _discover_model(self) -> str:
        try:
            r = self.session.get(f"{self.base}/api/health", timeout=10)
            d = r.json()
            return d.get("active_model") or ""
        except Exception:
            return ""

    # -- response envelope helpers --
    @staticmethod
    def _err_message(body) -> str:
        """Extract error message from either error-envelope or detail shape."""
        if not isinstance(body, dict):
            return str(body)[:300]
        err = body.get("error")
        if isinstance(err, dict):
            return str(err.get("message") or err)[:300]
        return str(body.get("detail") or body)[:300]

    def brevity_suffix(self) -> str:
        words = max(10, int(self.args.max_tokens_per_reply * 0.75))
        return f" Keep your answer under {words} words."

    # -- non-stream chat --
    def call_chat(self, item: dict) -> dict:
        payload = {
            "message": item["text"] + self.brevity_suffix(),
            "history": [],
            "session_id": f"stress-{item['nonce']}",
        }
        if self.model:
            payload["model"] = self.model
        t0 = time.monotonic()
        try:
            r = self.session.post(f"{self.base}/api/chat", json=payload,
                                  timeout=PER_REQUEST_TIMEOUT)
        except requests.Timeout:
            return {"ok": False, "failure": "client_timeout_90s", "status": 0,
                    "latency": time.monotonic() - t0}
        except requests.ConnectionError as exc:
            return {"ok": False, "failure": f"connection_error:{exc.__class__.__name__}",
                    "status": 0, "latency": time.monotonic() - t0}
        latency = time.monotonic() - t0
        if r.status_code != 200:
            try:
                msg = self._err_message(r.json())
            except Exception:
                msg = r.text[:300]
            return {"ok": False, "failure": f"http_{r.status_code}", "status": r.status_code,
                    "error_sample": msg, "latency": latency}
        try:
            body = r.json()
        except Exception:
            return {"ok": False, "failure": "malformed_json_envelope", "status": 200,
                    "error_sample": r.text[:300], "latency": latency}
        if not isinstance(body, dict) or "response" not in body or "model" not in body:
            return {"ok": False, "failure": "missing_response_field", "status": 200,
                    "error_sample": str(body)[:300], "latency": latency}
        text = body.get("response") or ""
        if not text.strip():
            return {"ok": False, "failure": "empty_response", "status": 200,
                    "error_sample": "", "latency": latency}
        return {"ok": True, "status": 200, "latency": latency, "text": text,
                "chars": len(text), "chunks": 1, "ttfb": latency,
                "sandbox_denials": 0, "tool_activity": [], "revisions": 0}

    # -- streaming SSE chat --
    def call_stream(self, item: dict) -> dict:
        payload = {
            "message": item["text"] + self.brevity_suffix(),
            "history": [],
            "autonomous": False,
            "session_id": f"stress-{item['nonce']}",
        }
        if self.model:
            payload["model"] = self.model
        t0 = time.monotonic()
        ttfb = None
        buf: list[str] = []
        n_chunks = 0
        revisions = 0
        sandbox_denials = 0
        tool_activity: list[str] = []
        error_msg = None
        try:
            r = self.session.post(f"{self.base}/api/chat/stream", json=payload,
                                  stream=True, timeout=PER_REQUEST_TIMEOUT)
        except requests.Timeout:
            return {"ok": False, "failure": "client_timeout_90s", "status": 0,
                    "latency": time.monotonic() - t0}
        except requests.ConnectionError as exc:
            return {"ok": False, "failure": f"connection_error:{exc.__class__.__name__}",
                    "status": 0, "latency": time.monotonic() - t0}
        if r.status_code != 200:
            body = ""
            try:
                body = r.text[:300]
            except Exception:
                pass
            return {"ok": False, "failure": f"http_{r.status_code}", "status": r.status_code,
                    "error_sample": body, "latency": time.monotonic() - t0}
        got_done = False
        try:
            for raw in r.iter_lines(decode_unicode=True):
                if time.monotonic() - t0 > PER_REQUEST_TIMEOUT:
                    r.close()
                    return {"ok": False, "failure": "stream_timeout_90s", "status": 200,
                            "latency": time.monotonic() - t0}
                line = raw.strip()
                if not line.startswith("data:"):
                    continue
                try:
                    ev = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    return {"ok": False, "failure": "malformed_sse_frame", "status": 200,
                            "error_sample": line[:300], "latency": time.monotonic() - t0}
                et = ev.get("type")
                if et == "chunk":
                    if ttfb is None:
                        ttfb = time.monotonic() - t0
                    data = str(ev.get("data") or "")
                    if data:
                        n_chunks += 1
                        buf.append(data)
                elif et == "revision":
                    revisions += 1
                    buf = []  # PWA semantics: reset the bubble before re-stream
                elif et == "sandbox_confirm":
                    sandbox_denials += 1
                    self._deny_sandbox(ev.get("token", ""))
                elif et == "activity":
                    tool_activity.append(str(ev.get("cmd") or ev.get("status") or ""))
                elif et == "error":
                    error_msg = str(ev.get("msg") or "")[:300]
                elif et == "done":
                    got_done = True
                    break
        except _RQ_CHUNK_EXC as exc:
            return {"ok": False, "failure": f"chunked_encoding_error:{exc.__class__.__name__}",
                    "status": 200, "latency": time.monotonic() - t0}
        latency = time.monotonic() - t0
        if error_msg is not None:
            return {"ok": False, "failure": "stream_error_event", "status": 200,
                    "error_sample": error_msg, "latency": latency}
        if not got_done:
            return {"ok": False, "failure": "no_done_event", "status": 200,
                    "error_sample": "".join(buf)[:200], "latency": latency}
        text = "".join(buf)
        if not text.strip():
            return {"ok": False, "failure": "empty_response", "status": 200,
                    "error_sample": "", "latency": latency}
        return {"ok": True, "status": 200, "latency": latency, "text": text,
                "chars": len(text), "chunks": n_chunks,
                "ttfb": ttfb if ttfb is not None else latency,
                "sandbox_denials": sandbox_denials, "tool_activity": tool_activity,
                "revisions": revisions}

    def _deny_sandbox(self, token: str) -> None:
        """Refuse the tool like the PWA would when the user clicks 'no'."""
        if not token:
            return
        try:
            self.session.post(f"{self.base}/api/sandbox/approve",
                              json={"token": token, "approved": False, "remember": False},
                              timeout=10)
        except Exception:
            pass

    # -- one attempt with capped retries + exponential backoff --
    def run_item(self, item: dict) -> dict:
        call = self.call_chat if item["endpoint"] == "/api/chat" else self.call_stream
        attempts = 0
        result = {}
        first_attempt: dict | None = None
        while attempts <= MAX_RETRIES:
            result = call(item)
            if attempts == 0:
                first_attempt = {k: result.get(k) for k in ("failure", "status")}
            if result.get("ok"):
                break
            if result.get("failure", "").startswith(("empty_response", "malformed", "missing_", "stream_error", "no_done")):
                break  # malformed answers are findings, not retry candidates
            attempts += 1
            if attempts <= MAX_RETRIES:
                time.sleep(BACKOFF_BASE ** attempts)
        apply_first_attempt_bookkeeping(result, first_attempt)  # P3-2: keep the green-retry reason
        result["attempts"] = attempts + 1
        result["endpoint"] = item["endpoint"]
        result["category"] = item["category"]
        result["idx"] = item["idx"]
        # validation layer
        if result.get("ok"):
            violations = []
            text = result.get("text", "")
            expected = item["expected_language"]
            lang_status, lang_note = tolerant_language_check(expected, text)
            if lang_status in ("mismatch", "unclassifiable"):
                violations.append(lang_note)
            elif lang_status == "tolerated":
                # P3-2: the stopword heuristic has no evidence on ultra-short
                # emoji/one-word replies — record it honestly, do not fail it.
                result["lang_note"] = lang_note
            # tool-refusal probes must not have triggered an approved tool run
            if item["category"] == "tool_refusal_probe":
                for cmd in result.get("tool_activity", []):
                    if "rm" in cmd.lower() and "done" in cmd.lower():
                        violations.append(f"tool_executed:{cmd[:80]}")
            result["violations"] = violations
            result["valid"] = not violations
        else:
            result["violations"] = []
            result["valid"] = False
        return result


# RSS watchdog

def find_server_pid(port: int) -> int | None:
    """Locate the server pid without scanning every system process: match
    candidate cmdlines, then verify the LISTEN socket on that candidate.  # language-gate: ignore (LISTEN is the socket-status literal compared at line 501 of this file — an English technical term the wide net reads as German "Listen")
    (A full psutil.net_connections() sweep raises AccessDenied per-pid on macOS.)"""
    if psutil is None:
        return None
    for proc in psutil.process_iter():
        try:
            cmd = " ".join(proc.cmdline() or [])
        except Exception:
            continue
        if "run_server" not in cmd and "uvicorn" not in cmd:
            continue
        try:
            for conn in proc.net_connections(kind="tcp"):
                la = conn.laddr
                # laddr shapes across platforms: addr(ip=, port=), tuple, or "host:port"
                lp = getattr(la, "port", None)
                if lp is None and isinstance(la, (tuple, list)) and len(la) >= 2:
                    lp = la[1]
                if lp is None and isinstance(la, dict):
                    lp = la.get("port")
                if lp is None and isinstance(la, str) and ":" in la:
                    lp = la.split(":")[-1]
                if conn.status == "LISTEN" and str(lp) == str(port):
                    return proc.pid
        except Exception:
            continue
    return None


class RssWatcher(threading.Thread):
    def __init__(self, port: int, interval: float, out_path: Path, stop: threading.Event):
        super().__init__(daemon=True)
        self.port = port
        self.interval = interval
        self.out_path = out_path
        self.stop_ev = stop
        self.samples: list[dict] = []
        # P3-2: a resumed campaign must not clobber the earlier run's curve —
        # load what is on disk and merge (dedup by (ts, pid)) on every flush.
        self._prior: list[dict] = []
        try:
            loaded = json.loads(self.out_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                self._prior = [s for s in loaded if isinstance(s, dict)]
        except Exception:
            pass

    def _flush(self) -> None:
        self.out_path.write_text(
            json.dumps(merge_rss_samples(self._prior, self.samples), indent=1),
            encoding="utf-8",
        )

    def run(self) -> None:
        try:
            self._sample_loop()
        except Exception as exc:  # watcher must never take down the campaign
            self.samples.append({"ts": round(time.time(), 2), "note": f"watcher_error: {exc}"})
        finally:
            try:
                self._flush()
            except Exception:
                pass

    def _sample_loop(self) -> None:
        pid = find_server_pid(self.port)
        if pid is None or psutil is None:
            self.samples.append({"ts": time.time(), "pid": None, "note": "server pid not found or psutil missing"})
            return
        try:
            proc = psutil.Process(pid)
        except Exception as exc:
            self.samples.append({"ts": time.time(), "pid": pid, "note": f"pid gone: {exc}"})
            return
        while not self.stop_ev.is_set():
            try:
                self.samples.append({
                    "ts": round(time.time(), 2), "pid": pid,
                    "rss_mb": round(proc.memory_info().rss / 1048576, 1),
                    "vms_mb": round(proc.memory_info().vms / 1048576, 1),
                    "threads": proc.num_threads(),
                    "cpu": round(proc.cpu_percent(interval=None), 1),
                    "mem_pct": round(proc.memory_percent(), 2),
                })
                self._flush()
            except Exception as exc:
                self.samples.append({"ts": time.time(), "pid": pid, "note": f"sample_failed: {exc}"})
                break
            self.stop_ev.wait(self.interval)


# Persistence / accounting probes (read-only)

def snapshot_server_state(base: str) -> dict:
    snap: dict = {"ts": time.time()}
    s = requests.Session()
    # memory count via API
    try:
        snap["memory_stats"] = s.get(f"{base}/api/memory/stats", timeout=15).json()
    except Exception as exc:
        snap["memory_stats_error"] = str(exc)[:120]
    # scheduler jobs via API + file fingerprints
    try:
        snap["schedule_jobs"] = s.get(f"{base}/api/schedule", timeout=15).json()
    except Exception as exc:
        snap["schedule_jobs_error"] = str(exc)[:120]
    try:
        snap["schedule_results_count"] = len(s.get(f"{base}/api/schedule/results", timeout=15).json().get("results", []))
    except Exception as exc:
        snap["schedule_results_error"] = str(exc)[:120]
    for name in ("scheduled_jobs.json", "schedule_results.json", "compaction_checkpoints.json"):
        p = SERVER_DATA_HOME / name
        if p.exists():
            data = p.read_bytes()
            snap[f"file:{name}"] = {"sha1": hashlib.sha1(data).hexdigest()[:12],
                                   "size": len(data), "mtime": round(p.stat().st_mtime, 1)}
        else:
            snap[f"file:{name}"] = None
    # sessions dir inventory (server-side; PWA sessions live in browser storage)
    sess_dir = SERVER_DATA_HOME / "sessions"
    if sess_dir.is_dir():
        files = sorted(p.name for p in sess_dir.iterdir() if p.is_file() and p.suffix == ".json")
        sizes = {p.name: (p.stat().st_size, round(p.stat().st_mtime, 1)) for p in sess_dir.iterdir()
                 if p.is_file() and p.suffix == ".json"}
        snap["sessions_files"] = {"count": len(files), "detail": sizes}
    else:
        snap["sessions_files"] = None
    # audit log size (approval evidence)
    audit = SERVER_DATA_HOME / "audit.log"
    snap["audit_bytes"] = audit.stat().st_size if audit.exists() else 0
    # server log size
    snap["server_log_bytes"] = SERVER_LOG.stat().st_size if SERVER_LOG.exists() else 0
    # system metrics via API
    try:
        snap["system_metrics"] = s.get(f"{base}/api/system/metrics", timeout=15).json()
    except Exception as exc:
        snap["system_metrics_error"] = str(exc)[:120]
    return snap


def token_accounting_probe(base: str, n: int = 8) -> dict:
    """Hit the compat completions endpoint and compare reported usage
    against a len/4 heuristic. Flags systematic under-reporting > 25 %."""
    prompts = [
        "Say hello in three different languages.",
        "List four planets in one line.",
        "Write a fourteen-word sentence about coffee.",
        "What is the capital of France? One word.",
        "Name three primary colors.",
        "Give one joke about programmers.",
        "Explain 'idempotent' in one short sentence.",
        "Count from one to five, comma separated.",
    ]
    rows = []
    for i in range(n):
        p = prompts[i % len(prompts)]
        t0 = time.monotonic()
        try:
            r = requests.post(f"{base}/v1/chat/completions",
                              json={"messages": [{"role": "user", "content": p}], "stream": False},
                              timeout=PER_REQUEST_TIMEOUT)
            latency = time.monotonic() - t0
            body = r.json()
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            usage = body.get("usage", {}) or {}
            rows.append({
                "prompt": p, "status": r.status_code, "latency": round(latency, 2),
                "reported_prompt_tokens": usage.get("prompt_tokens"),
                "reported_completion_tokens": usage.get("completion_tokens"),
                "reported_total_tokens": usage.get("total_tokens"),
                "heuristic_prompt_tokens": round(len(p) / 4),
                "heuristic_completion_tokens": round(len(content or "") / 4),
                "content_chars": len(content or ""),
            })
        except Exception as exc:
            rows.append({"prompt": p, "error": str(exc)[:150]})
    reported = sum(r.get("reported_total_tokens") or 0 for r in rows)
    heuristic = sum((r.get("heuristic_prompt_tokens") or 0) + (r.get("heuristic_completion_tokens") or 0) for r in rows)
    divergence = None if heuristic == 0 else round((heuristic - reported) / heuristic * 100, 1)
    return {"rows": rows, "reported_total": reported, "heuristic_total": heuristic,
            "divergence_percent": divergence,
            "systematic_lie": bool(divergence is not None and divergence > 25.0)}


def compaction_probe(base: str) -> dict:
    """Attempt a server-side compaction verification.

    1. Look for a dedicated compaction route in the service's JSON API schema.
    2. Send /api/chat with a 40-message synthetic history (above the 28-message
       threshold) plus a session id, then read /api/context/budget for it.
    """
    out: dict = {"endpoint_found": False, "steps": []}
    try:
        schema = None
        for candidate in ("/openapi.json", "/api/openapi.json"):
            probe = requests.get(f"{base}{candidate}", timeout=15)
            if probe.status_code == 200:
                schema = probe.json()
                out["schema_path"] = candidate
                break
        if schema is not None:
            paths = schema.get("paths", {})
            comp_paths = [p for p in paths if "compact" in p.lower()]
            out["compaction_paths_in_schema"] = comp_paths
            out["endpoint_found"] = bool(comp_paths)
        else:
            out["schema_error"] = "openapi.json not reachable (404 on all candidates)"
    except Exception as exc:
        out["schema_error"] = str(exc)[:150]
    history = []
    for i in range(40):
        history.append({"role": "user", "content": f"synthetic question {i} about topic number {i}"})
        history.append({"role": "assistant", "content": f"synthetic answer {i} that is somewhat long to mimic a real reply " * 3})
    sid = "stress-compaction-probe-01"
    try:
        r = requests.post(f"{base}/api/chat",
                          json={"message": "Summarise the last topic in one word.", "history": history, "session_id": sid},
                          timeout=PER_REQUEST_TIMEOUT)
        out["steps"].append({"post_chat_with_history": r.status_code,
                             "body_sample": r.text[:120]})
    except Exception as exc:
        out["steps"].append({"post_chat_with_history_error": str(exc)[:150]})
    try:
        b = requests.get(f"{base}/api/context/budget", params={"session_id": sid}, timeout=15)
        out["context_budget"] = b.json()
    except Exception as exc:
        out["context_budget_error"] = str(exc)[:150]
    return out


def same_session_race_probe(base: str, model: str) -> dict:
    """Fire 4 concurrent stream requests sharing ONE session id. Detects
    cross-talk (identical bodies), losses, or hangs on shared state."""
    sid = "stress-same-session-01"
    suffix = " Keep your answer under 20 words."

    def one(i: int) -> dict:
        payload = {"message": f"Concurrent probe {i}: say a different single word. (ref {i})",
                   "history": [], "autonomous": False, "session_id": sid, "model": model}
        if not payload["model"]:
            payload.pop("model", None)
        t0 = time.monotonic()
        try:
            r = requests.post(f"{base}/api/chat/stream", json=payload, stream=True, timeout=PER_REQUEST_TIMEOUT)
            buf = []
            ok = r.status_code == 200
            for raw in r.iter_lines(decode_unicode=True):
                line = raw.strip()
                if line.startswith("data:"):
                    try:
                        ev = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    if ev.get("type") == "chunk":
                        buf.append(str(ev.get("data") or ""))
                    elif ev.get("type") == "done":
                        break
                    elif ev.get("type") == "error":
                        ok = False
            return {"i": i, "status": r.status_code, "ok": ok,
                    "latency": round(time.monotonic() - t0, 2), "text": "".join(buf)[:200]}
        except Exception as exc:
            return {"i": i, "ok": False, "error": str(exc)[:150],
                    "latency": round(time.monotonic() - t0, 2)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        rows = list(ex.map(one, range(1, 5)))
    texts = [r.get("text", "") for r in rows]
    return {"rows": rows, "all_ok": all(r.get("ok") for r in rows),
            "identical_bodies": len(set(texts)) == 1 and len(texts) > 1}


def slow_engine_probe(base: str) -> dict:
    """(a) Timeout behaviour while the engine is briefly slow. Nothing is
    killed: we simply ask for a very long generation and cut the client off
    early, then check the server log and that a normal request still works."""
    out: dict = {}
    t0 = time.monotonic()
    try:
        requests.post(f"{base}/api/chat",
                      json={"message": "Write a 3000-word essay about every season of the year, in detail, in English."},
                      timeout=20.0)
        out["unexpected"] = "request completed within 20s despite 3000-word ask"
    except requests.Timeout:
        out["client_cut_at"] = round(time.monotonic() - t0, 2)
        out["behaviour"] = "client_timeout_after_20s_as_expected"
    except Exception as exc:
        out["error"] = str(exc)[:200]
    # queue-head check: is a normal request still served right after?
    t1 = time.monotonic()
    try:
        r = requests.post(f"{base}/api/chat",
                          json={"message": "Reply with exactly: still alive"}, timeout=PER_REQUEST_TIMEOUT)
        out["follow_up_status"] = r.status_code
        out["follow_up_latency_s"] = round(time.monotonic() - t1, 2)
        out["follow_up_body"] = r.text[:150]
    except Exception as exc:
        out["follow_up_error"] = str(exc)[:150]
    return out


def memory_retrieval_check(base: str, nonce: str) -> dict:
    try:
        r = requests.get(f"{base}/api/memory/search", params={"q": "dark roast coffee", "top_k": 5}, timeout=20)
        hits = r.json().get("results", [])
        return {"checked": True, "hits": len(hits), "top_text": (hits[0]["text"][:140] if hits else "")}
    except Exception as exc:
        return {"checked": False, "error": str(exc)[:150]}


# Percentile helper (stdlib, no numpy)

def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    vs = sorted(values)
    k = max(0, min(len(vs) - 1, int(round(q / 100.0 * (len(vs) - 1)))))
    return vs[k]


def summarize(results: list[dict]) -> dict:
    by_cat: dict[str, dict] = {}
    for r in results:
        c = r["category"]
        d = by_cat.setdefault(c, {"n": 0, "ok": 0, "lat": [], "ttfb": [], "chars": 0})
        d["n"] += 1
        if r.get("ok"):
            d["ok"] += 1
            d["lat"].append(r.get("latency", 0.0))
            if r.get("ttfb") is not None:
                d["ttfb"].append(r.get("ttfb", r.get("latency", 0.0)))
            d["chars"] += r.get("chars", 0)
    out = {}
    for c, d in by_cat.items():
        lat = d["lat"]
        out[c] = {
            "n": d["n"], "ok": d["ok"], "err": d["n"] - d["ok"],
            "p50": round(pct(lat, 50), 2), "p95": round(pct(lat, 95), 2), "p99": round(pct(lat, 99), 2),
            "ttfb_p50": round(pct(d["ttfb"], 50), 2), "ttfb_p95": round(pct(d["ttfb"], 95), 2),
            "tok_s_est": round((d["chars"] / 4.0 / sum(lat)), 2) if lat and sum(lat) > 0 else None,
        }
    return out


# Main campaign

def main() -> int:
    ap = argparse.ArgumentParser(description="Ephe 1000-message stress campaign")
    ap.add_argument("--base-url", default=BASE_DEFAULT)
    ap.add_argument("--total", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--seed", type=int, default=4217)
    ap.add_argument("--max-tokens-per-reply", type=int, default=80)
    ap.add_argument("--rss-interval", type=float, default=30.0)
    ap.add_argument("--smoke", type=int, default=0, help="run N messages only (validation)")
    ap.add_argument("--skip-probes", action="store_true")
    args = ap.parse_args()

    total = args.smoke if args.smoke else args.total
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    progress_path = STATE_DIR / "progress.json"
    results_path = STATE_DIR / f"results_{'smoke' if args.smoke else 'full'}.jsonl"
    rss_path = STATE_DIR / "rss_samples.json"

    # resume: completed indexes from a previous run with identical plan hash
    done: dict[int, dict] = {}
    plan = build_corpus(args.seed, total)
    plan_hash = hashlib.sha1(json.dumps(
        [[p["idx"], p["category"], p["text"], p["endpoint"]] for p in plan]).encode()).hexdigest()[:12]
    if progress_path.exists():
        try:
            prev = json.loads(progress_path.read_text(encoding="utf-8"))
            if prev.get("plan_hash") == plan_hash and prev.get("total") == total:
                done = {int(k): v for k, v in prev.get("done", {}).items()}
        except Exception:
            pass
    # P3-2 idempotence: progress.json lags up to 25 items behind the
    # append-only results JSONL — after an external kill the JSONL is the
    # truth, so seed the skip-set from it too (no more re-executed ids).
    # Rows are trusted only when they carry this exact plan hash, so a new
    # seed/total can never inherit skips from an old campaign.
    done.update(load_done_indices(results_path, expect_hash=plan_hash))

    stress = Stress(args.base_url, args)
    print(f"[stress] base={args.base_url} model={stress.model!r} total={total} "
          f"workers={args.workers} seed={args.seed} already_done={len(done)} plan={plan_hash}")

    if not stress.model:
        print("[stress] WARNING: could not discover active model from /api/health")

    pre = snapshot_server_state(args.base_url)
    (STATE_DIR / "snapshot_pre.json").write_text(json.dumps(pre, indent=1), encoding="utf-8")
    print(f"[stress] pre-run memory_stats={pre.get('memory_stats')}")

    stop_ev = threading.Event()
    watcher = RssWatcher(urlparse(args.base_url).port or 8765, args.rss_interval, rss_path, stop_ev)
    watcher.start()

    todo = [p for p in plan if p["idx"] not in done]
    t_start = time.monotonic()
    aborted_reason = None
    lock = threading.Lock()

    def guarded(item: dict) -> dict:
        return stress.run_item(item)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(guarded, item): item for item in todo}
        completed_since_start = 0
        for fut in concurrent.futures.as_completed(futs):
            if fut.cancelled():
                continue  # budget guard aborted the queue: do not pollute the taxonomy
            item = futs[fut]
            try:
                res = fut.result()
            except Exception as exc:
                res = {"idx": item["idx"], "category": item["category"], "endpoint": item["endpoint"],
                       "ok": False, "valid": False, "failure": f"harness_exception:{exc.__class__.__name__}",
                       "error_sample": str(exc)[:200], "attempts": 1, "latency": 0.0,
                       "violations": [], "chars": 0}
            with lock:
                done[item["idx"]] = {k: v for k, v in res.items() if k != "text"}
                completed_since_start += 1
                res["plan_hash"] = plan_hash  # makes resume seeding trustworthy
                with results_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(res, ensure_ascii=False) + "\n")
                if completed_since_start % 25 == 0:
                    progress_path.write_text(json.dumps(
                        {"plan_hash": plan_hash, "total": total, "seed": args.seed,
                         "done": {str(k): v for k, v in done.items()}}, ensure_ascii=False), encoding="utf-8")
                # budget guard after 200 messages
                n = len(done)
                if not args.smoke and n >= 200 and aborted_reason is None and completed_since_start >= 200:
                    oks = [v for v in done.values() if v.get("ok")]
                    errs = n - len(oks)
                    p95 = pct([v.get("latency", 0.0) for v in oks], 95)
                    err_rate = errs / n
                    if p95 > 60.0:
                        aborted_reason = f"budget_guard:p95={p95:.1f}s > 60s at n={n}"
                    elif err_rate > 0.10:
                        aborted_reason = f"budget_guard:error_rate={err_rate:.1%} > 10% at n={n}"
                    if aborted_reason:
                        print(f"[stress] ABORTING: {aborted_reason}")
                        for f in futs:
                            f.cancel()
    wall = time.monotonic() - t_start

    stop_ev.set()
    watcher.join(timeout=args.rss_interval + 5)

    post = snapshot_server_state(args.base_url)
    (STATE_DIR / "snapshot_post.json").write_text(json.dumps(post, indent=1), encoding="utf-8")
    print(f"[stress] post-run memory_stats={post.get('memory_stats')}")

    probes = {}
    if not args.skip_probes and not args.smoke:
        print("[stress] token accounting probe ...")
        probes["token_accounting"] = token_accounting_probe(args.base_url)
        print("[stress] compaction probe ...")
        probes["compaction"] = compaction_probe(args.base_url)
        print("[stress] same-session race probe ...")
        probes["same_session"] = same_session_race_probe(args.base_url, stress.model)
        print("[stress] slow-engine / client-timeout probe ...")
        probes["slow_engine"] = slow_engine_probe(args.base_url)
        probes["memory_retrieval"] = memory_retrieval_check(args.base_url, "probe")

    results = list(done.values())
    summary = summarize(results)
    ok_n = sum(1 for r in results if r.get("ok"))
    valid_n = sum(1 for r in results if r.get("valid"))
    failures: dict[str, list] = {}
    for r in results:
        if not r.get("ok"):
            f = r.get("failure", "unknown")
            failures.setdefault(f, []).append({"idx": r["idx"], "cat": r["category"], "sample": r.get("error_sample", "")})
        elif not r.get("valid"):
            for v in r.get("violations", []):
                failures.setdefault(v.split(":")[0], []).append({"idx": r["idx"], "cat": r["category"], "sample": v})

    final = {
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "base_url": args.base_url, "model": stress.model,
        "total": total, "completed": len(done), "ok": ok_n, "valid": valid_n,
        "error_count": len(done) - ok_n, "wall_s": round(wall, 1),
        "throughput_msgs_per_min": round(len(results) / wall * 60, 2) if wall else 0,
        "summary_by_category": summary,
        "failure_taxonomy": {k: {"count": len(v), "examples": v[:3]} for k, v in failures.items()},
        "budget_guard_abort": aborted_reason,
        "probes": probes,
        "smoke": bool(args.smoke),
    }
    (STATE_DIR / f"summary_{'smoke' if args.smoke else 'full'}.json").write_text(
        json.dumps(final, indent=1, ensure_ascii=False), encoding="utf-8")
    progress_path.write_text(json.dumps(
        {"plan_hash": plan_hash, "total": total, "seed": args.seed,
         "done": {str(k): v for k, v in done.items()}, "finished": aborted_reason is None},
        ensure_ascii=False), encoding="utf-8")

    print(json.dumps({k: final[k] for k in ("completed", "ok", "valid", "error_count",
                                            "wall_s", "throughput_msgs_per_min", "budget_guard_abort")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
