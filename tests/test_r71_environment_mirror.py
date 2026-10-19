"""
◑ Ephe – r71 (wave B): Environment Mirror — detection without secrets.
tests/test_r71_environment_mirror.py

Pins (always against fixtures in a tmp home, never against real machine data):
1. Installed tools are detected (opencode/claude/cursor/hermes/codex).
2. Models/providers come out of the config — secret values (apiKey/token/
   password/auth branches) never leave the module (value equality is pinned).
3. Auth detection is existence-based (auth.json present → auth_present=True).
4. Missing tools → installed=False, scan never raises.
5. JSONC comments are parsed tolerantly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import environment_mirror as em  # noqa: E402


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "home"


def _mk_opencode(home: Path, secret_value: str = "sk-SUPERSECRET-123") -> None:
    cfg = home / ".config" / "opencode"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "opencode.jsonc").write_text(
        "// user config\n"
        "{\n"
        '  "provider": { "anthropic": { "models": { "claude-x": {} } } },\n'
        '  "model": "anthropic/claude-x",\n'
        '  "apiKey": "' + secret_value + '"\n'
        "}\n",
        encoding="utf-8",
    )


class TestDetection:

    def test_installed_tools_reported(self, home: Path):
        _mk_opencode(home)
        tools = em.installed_tools(home)
        assert "opencode" in tools
        assert "codex" not in tools

    def test_models_extracted_and_jsonc_tolerant(self, home: Path):
        _mk_opencode(home)
        entry = next(e for e in em.scan(home) if e["tool"] == "opencode")
        assert entry["installed"] is True
        assert "anthropic/claude-x" in entry["models"]
        assert "anthropic" in entry["providers"]
        assert "claude-x" in entry["models"]  # catalog form: model slugs

    def test_secret_values_never_leak(self, home: Path):
        """The hard privacy pin: the secret value may not show up anywhere in the
        report — not even as a fragment of a longer string."""
        secret = "sk-SUPERSECRET-123"
        _mk_opencode(home, secret_value=secret)
        blob = json.dumps(em.scan(home))
        assert secret not in blob

    def test_auth_present_is_existence_based(self, home: Path):
        _mk_opencode(home)
        (home / ".hermes").mkdir(parents=True, exist_ok=True)
        (home / ".hermes" / "auth.json").write_text('{"token": "x"}', encoding="utf-8")
        entries = {e["tool"]: e for e in em.scan(home)}
        assert entries["hermes"]["auth_present"] is True
        assert entries["opencode"]["auth_present"] is False  # no auth.json
        # the token value must still never reach the report:
        assert '"token"' not in json.dumps(em.scan(home))

    def test_missing_tools_are_not_installed(self, home: Path):
        for e in em.scan(home):
            assert e["installed"] is False

    def test_broken_config_is_fail_soft(self, home: Path):
        cfg = home / ".config" / "opencode"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "opencode.jsonc").write_text("{ not valid json", encoding="utf-8")
        entry = next(e for e in em.scan(home) if e["tool"] == "opencode")
        assert entry["installed"] is True  # config present (folder fallback)
        assert entry["models"] == []

    def test_claude_detected_via_dir(self, home: Path):
        (home / ".claude").mkdir(parents=True, exist_ok=True)
        assert "claude" in em.installed_tools(home)

    def test_nested_env_model_and_base_url(self, home: Path):
        # claude form: model and endpoint sit nested inside env.*
        cfg = home / ".claude"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "settings.json").write_text(
            json.dumps(
                {
                    "env": {
                        "ANTHROPIC_BASE_URL": "http://spark.local:8000",
                        "ANTHROPIC_AUTH_TOKEN": "local-token-wert",
                        "ANTHROPIC_MODEL": "deepseek-v4-flash",
                    }
                }
            ),
            encoding="utf-8",
        )
        entry = next(e for e in em.scan(home) if e["tool"] == "claude")
        assert "deepseek-v4-flash" in entry["models"]
        assert [urlparse(p).netloc for p in entry["providers"]] == ["spark.local:8000"]
        blob = json.dumps(entry)
        assert "local-token-wert" not in blob  # secret never in the report

    def test_model_list_dicts_use_slug_not_description(self, home: Path):
        # codex form: models as a list of dicts — only slug/id/name counts.
        cfg = home / ".codex"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "models_cache.json").write_text(
            json.dumps(
                {
                    "fetched_at": "x",
                    "models": [
                        {"slug": "gpt-5.5", "display_name": "GPT-5.5", "description": "lang"}
                    ],
                }
            ),
            encoding="utf-8",
        )
        entry = next(e for e in em.scan(home) if e["tool"] == "codex")
        assert "gpt-5.5" in entry["models"]
        assert "lang" not in entry["models"]

    def test_model_descriptor_dict_skips_meta_keys(self, home: Path):
        # cursor form: model descriptor with modelId plus meta keys.
        cfg = home / ".cursor"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "cli-config.json").write_text(
            json.dumps(
                {
                    "model": {
                        "modelId": "gpt-5",
                        "displayName": "OpenAI GPT-5",
                        "aliases": ["g5"],
                    }
                }
            ),
            encoding="utf-8",
        )
        entry = next(e for e in em.scan(home) if e["tool"] == "cursor")
        assert entry["models"] == ["gpt-5"]
        for junk in ("displayName", "aliases", "OpenAI GPT-5"):
            assert junk not in entry["models"]

    def test_provider_catalog_form(self, home: Path):
        # hermes form: models.dev cache = provider objects holding a models dict.
        cfg = home / ".hermes"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "models_dev_cache.json").write_text(
            json.dumps(
                {
                    "deepinfra": {"models": {"tencent/Hy3": {"id": "tencent/Hy3"}}},
                    "cerebras": {"models": {"Qwen-2.5": {}}},
                }
            ),
            encoding="utf-8",
        )
        entry = next(e for e in em.scan(home) if e["tool"] == "hermes")
        assert "deepinfra" in entry["providers"]
        assert "tencent/Hy3" in entry["models"]

    def test_doc_and_schema_urls_are_not_endpoints(self, home: Path):
        cfg = home / ".config" / "opencode"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "opencode.jsonc").write_text(
            json.dumps(
                {
                    "$schema": "https://opencode.ai/config.json",
                    "provider": {"doc": "https://deepinfra.com/models"},
                }
            ),
            encoding="utf-8",
        )
        entry = next(e for e in em.scan(home) if e["tool"] == "opencode")
        urls = [p for p in entry["providers"] if "://" in p]
        assert "https://opencode.ai/config.json" not in urls
        assert "https://deepinfra.com/models" not in urls

    def test_hermes_yaml_and_custom_url_provider_keys(self, home: Path):
        # Hermes pattern: YAML main config plus a provider cache keyed by 'custom:<url>'.
        cfg = home / ".hermes"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "config.yaml").write_text(
            "model:\n"
            "  default: qwen-active\n"
            "  base_url: http://spark.local:8888/v1\n"
            "providers:\n"
            "  custom:dgx:\n"
            "    default_model: qwen-active\n"
            "    base_url: http://spark.local:8888/v1\n"
            "    api_key: SUPER-YAML-SECRET\n",
            encoding="utf-8",
        )
        (cfg / "provider_models_cache.json").write_text(
            json.dumps(
                {
                    "anthropic": {"fp": "x", "at": 1, "models": ["claude-y"]},
                    "custom:http://spark.local:8000/v1": {
                        "fp": "y",
                        "at": 2,
                        "models": ["qwen-cache", "nomic-embed"],
                    },
                }
            ),
            encoding="utf-8",
        )
        entry = next(e for e in em.scan(home) if e["tool"] == "hermes")
        assert entry["installed"] is True
        # the active model first (the config file merges before the caches).
        assert entry["models"][0] == "qwen-active"
        assert "claude-y" in entry["models"] and "qwen-cache" in entry["models"]
        # endpoints out of base_url values and 'custom:<url>' keys, not out of secrets.
        assert "http://spark.local:8888/v1" in entry["providers"]
        assert "http://spark.local:8000/v1" in entry["providers"]
        assert "SUPER-YAML-SECRET" not in json.dumps(entry)

    def test_ollama_detected_from_manifests(self, home: Path):
        # Ollama self-detection: manifest tree -> name:tag, marked as free.
        base = home / ".ollama" / "models" / "manifests" / "registry.ollama.ai" / "library"
        (base / "gemma4" / "e4b").parent.mkdir(parents=True, exist_ok=True)
        (base / "gemma4" / "e4b").write_text("{}", encoding="utf-8")
        entries = {e["tool"]: e for e in em.scan(home)}
        assert entries["ollama"]["installed"] is True
        assert "gemma4:e4b" in entries["ollama"]["models"]
        assert "gemma4:e4b" in entries["ollama"]["free_models"]
        assert entries["ollama"]["providers"] == ["http://127.0.0.1:11434"]

    def test_codex_toml_config_parsed(self, home: Path):
        # codex form: config.toml (TOML) with model + model_provider.
        cfg = home / ".codex"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "config.toml").write_text(
            'model = "gpt-5.1"\nmodel_provider = "custom"\n', encoding="utf-8"
        )
        entry = next(e for e in em.scan(home) if e["tool"] == "codex")
        assert entry["installed"] is True
        assert "gpt-5.1" in entry["models"]

    def test_free_models_suffix_marker(self, home: Path):
        cfg = home / ".config" / "opencode"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "opencode.jsonc").write_text(
            json.dumps({"model": "opencode/muse-spark-1.2-contributor-free"}),
            encoding="utf-8",
        )
        entry = next(e for e in em.scan(home) if e["tool"] == "opencode")
        assert any(m.endswith("-free") for m in entry["free_models"])

    def test_opencode_last_used_from_sqlite(self, home: Path):
        import sqlite3

        cfg = home / ".config" / "opencode"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "opencode.jsonc").write_text('{"model": "x/y"}', encoding="utf-8")
        db_dir = home / ".local" / "share" / "opencode"
        db_dir.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(db_dir / "opencode.db")
        con.execute("CREATE TABLE session (model TEXT, time_updated INTEGER)")
        con.execute(
            "INSERT INTO session VALUES ('muse-spark-1.2-contributor-free', 2)"
        )
        con.execute("INSERT INTO session VALUES (?, 1)",
                    ['{"id":"x-preview-f-free","providerID":"opencode"}'])
        con.commit()
        con.close()
        entry = next(e for e in em.scan(home) if e["tool"] == "opencode")
        # JSON blobs reduce to their model id, newest first.
        assert entry["last_used"] == [
            "muse-spark-1.2-contributor-free", "x-preview-f-free",
        ]
        assert entry["models"][:2] == entry["last_used"]
        assert set(entry["free_models"]) == {
            "muse-spark-1.2-contributor-free", "x-preview-f-free",
        }

    def test_model_endpoints_pairing_from_catalog(self, home: Path):
        """Every model carries its own real provider endpoint (the models.dev 'api'
        field), so a probe never inherits the endpoint of a foreign provider."""
        cfg = home / ".config" / "opencode"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "opencode.jsonc").write_text('{"model": "x/y"}', encoding="utf-8")
        cache = home / ".cache" / "opencode"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "models.json").write_text(
            '{"lmstudio":{"api":"http://127.0.0.1:1234/v1","models":{"gemma4:e4b":{}}},'
            '"opencode":{"api":"https://opencode.ai/zen/v1","models":{"muse-spark-1.2-contributor-free":{}}}}',
            encoding="utf-8",
        )
        entry = next(e for e in em.scan(home) if e["tool"] == "opencode")
        assert entry["model_endpoints"]["gemma4:e4b"] == "http://127.0.0.1:1234/v1"
        assert (
            entry["model_endpoints"]["muse-spark-1.2-contributor-free"]
            == "https://opencode.ai/zen/v1"
        )

    def test_mirror_api_key_resolves_from_auth_json(self, home: Path):
        from core.model_probe import mirror_api_key

        (home / ".cache" / "opencode").mkdir(parents=True, exist_ok=True)
        (home / ".cache" / "opencode" / "models.json").write_text(
            '{"opencode":{"api":"https://opencode.ai/zen/v1","models":{"m":{}}}}',
            encoding="utf-8",
        )
        share = home / ".local" / "share" / "opencode"
        share.mkdir(parents=True, exist_ok=True)
        (share / "auth.json").write_text(
            '{"opencode":{"type":"api","key":"oc_key_123"}}', encoding="utf-8"
        )
        assert mirror_api_key("https://opencode.ai/zen/v1", home=home) == "oc_key_123"
        assert mirror_api_key("https://unknown.example/v1", home=home) is None


class TestProbeKeySource:
    """S4, owner decision 2026-10-18: the mirror stays, its source gets named.

    Pins the one order ``resolve_probe_key`` implements (given > own > foreign > none),
    that both discovery routes report ``foreign``, that the borrowed token goes to the
    endpoint it belongs to and to no other sink, and that exactly one production call
    site may read that store at all.
    """

    KEY = "oc-borrowed-4f9c21"
    URL = "https://opencode.ai/zen/v1"

    def _mirror(self, home: Path, key: str = KEY) -> None:
        """The other tool's two files: a catalog that pairs a provider id with an
        endpoint, and an auth store that holds that provider's key."""
        (home / ".cache" / "opencode").mkdir(parents=True, exist_ok=True)
        (home / ".cache" / "opencode" / "models.json").write_text(
            json.dumps({"opencode": {"api": self.URL, "models": {"m": {}}}}), encoding="utf-8"
        )
        share = home / ".local" / "share" / "opencode"
        share.mkdir(parents=True, exist_ok=True)
        (share / "auth.json").write_text(
            json.dumps({"opencode": {"type": "api", "key": key}}), encoding="utf-8"
        )

    def _own_store_empty(self, monkeypatch) -> None:
        """Nothing of Ephe's own resolves, so any token that comes back is borrowed."""
        import core.engine_config as ec

        monkeypatch.delenv("EPHE_OPENAI_COMPAT_API_KEY", raising=False)
        monkeypatch.setattr(ec, "_load_engine_keyring", lambda: "")

    def test_the_four_sources_resolve_in_one_order(self, home: Path, monkeypatch):
        from core.model_probe import resolve_probe_key

        self._own_store_empty(monkeypatch)
        self._mirror(home)
        key_file = home / ".ephe" / "engine.key"
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text("own-file-key\n", encoding="utf-8")
        key_file.chmod(0o600)

        assert resolve_probe_key(self.URL, "typed-into-this-request", home=home) == (
            "typed-into-this-request",
            "given",
        )
        assert resolve_probe_key(self.URL, None, home=home) == ("own-file-key", "own")

        key_file.unlink()
        assert resolve_probe_key(self.URL, None, home=home) == (self.KEY, "foreign")

        (home / ".local" / "share" / "opencode" / "auth.json").unlink()
        assert resolve_probe_key(self.URL, None, home=home) == (None, "none")

    def test_ephes_own_env_key_beats_the_mirror(self, home: Path, monkeypatch):
        from core.model_probe import resolve_probe_key

        self._own_store_empty(monkeypatch)
        self._mirror(home)
        monkeypatch.setenv("EPHE_OPENAI_COMPAT_API_KEY", "env-key")
        assert resolve_probe_key(self.URL, None, home=home) == ("env-key", "own")

    def _probe_app(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from server.routes import model_provider, settings

        app = FastAPI()
        app.include_router(model_provider.router, prefix="/api")
        app.include_router(settings.router, prefix="/api")
        return TestClient(app)

    def _fake_answer(self, seen: dict):
        """Every endpoint answers with one model, and the Authorization header of the
        engine check is recorded so the test can say where the token actually went."""
        import httpx

        async def fake_get(self, url, *a, **kw):
            seen["authorization"] = (kw.get("headers") or {}).get("Authorization", "")
            seen["url"] = str(url)
            return httpx.Response(
                200, json={"data": [{"id": "m-1"}]}, request=httpx.Request("GET", url)
            )

        return fake_get

    def _isolate_home(self, monkeypatch, home: Path, tmp_path: Path) -> Path:
        monkeypatch.setenv("HOME", str(home))
        config = tmp_path / "ephe-config"
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
        return config

    def test_probe_route_reports_foreign_and_sends_the_key_only_to_its_endpoint(
        self, home: Path, monkeypatch, tmp_path: Path
    ):
        from unittest.mock import patch

        self._own_store_empty(monkeypatch)
        self._mirror(home)
        self._isolate_home(monkeypatch, home, tmp_path)
        seen: dict = {}
        client = self._probe_app()
        with patch("httpx.AsyncClient.get", new=self._fake_answer(seen)):
            body = client.post(
                "/api/model/providers/probe",
                json={"provider": "openai_compatible", "base_url": self.URL},
            ).json()
        assert body["reachable"] is True, body
        assert body["key_source"] == "foreign"
        assert seen["authorization"] == f"Bearer {self.KEY}"
        assert self.KEY not in json.dumps(body), "the token left the server in a response"

    def test_ollama_probe_carries_no_key_source(self, home: Path, monkeypatch, tmp_path: Path):
        """The field exists only where a token was in play; an Ollama probe must not
        answer with a source it never consulted."""
        from unittest.mock import patch

        self._own_store_empty(monkeypatch)
        self._isolate_home(monkeypatch, home, tmp_path)
        with patch("httpx.AsyncClient.get", new=self._fake_answer({})):
            body = self._probe_app().post(
                "/api/model/providers/probe",
                json={"provider": "local_ollama", "base_url": "http://127.0.0.1:11434"},
            ).json()
        assert "key_source" not in body

    def test_detect_route_reports_foreign_for_what_it_offers(
        self, home: Path, monkeypatch, tmp_path: Path
    ):
        """The scan is the surface that speaks first on a fresh install: the offer
        sentence has to be able to say that a borrowed key produced it."""
        from unittest.mock import patch

        self._own_store_empty(monkeypatch)
        self._mirror(home)
        config = self._isolate_home(monkeypatch, home, tmp_path)
        monkeypatch.setenv("EPHE_OPENAI_COMPAT_BASE_URL", self.URL)
        with patch("httpx.AsyncClient.get", new=self._fake_answer({})):
            body = self._probe_app().get("/api/setup/detect").json()
        hit = next(d for d in body["detected"] if d["url"] == self.URL)
        assert hit["reachable"] is True and hit["models"] == ["m-1"], hit
        assert hit["key_source"] == "foreign"
        # Control: the scan wrote state (the endpoint history), so the absence below
        # is measured against a run that had something to write.
        history = sorted(config.rglob("*.json"))
        assert history, "the scan wrote no state, so this check proved nothing"
        for f in history:
            assert self.KEY not in f.read_text(encoding="utf-8"), f
        assert not (home / ".ephe").exists(), "a probe must not create Ephe's own key file"

    def test_a_borrowed_key_never_reaches_a_log(self, home: Path, monkeypatch, tmp_path: Path):
        import logging
        from unittest.mock import patch

        self._own_store_empty(monkeypatch)
        self._mirror(home)
        self._isolate_home(monkeypatch, home, tmp_path)

        records: list[str] = []

        class _Capture(logging.Handler):
            def emit(self, record):
                records.append(self.format(record))

        handler = _Capture()
        handler.setFormatter(logging.Formatter("%(name)s %(message)s"))
        root = logging.getLogger()
        previous = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            with patch("httpx.AsyncClient.get", new=self._fake_answer({})):
                client = self._probe_app()
                client.post(
                    "/api/model/providers/probe",
                    json={"provider": "openai_compatible", "base_url": self.URL},
                )
                client.get("/api/setup/detect")
            logging.getLogger("test.r71.control").warning("marker-control")
        finally:
            root.removeHandler(handler)
            root.setLevel(previous)

        blob = "\n".join(records)
        assert "marker-control" in blob, "the sink captured nothing, so this proved nothing"
        assert self.KEY not in blob, "a borrowed token was logged"

    def test_the_mirror_has_exactly_one_production_caller(self):
        callers = []
        for root in ("server", "core", "scripts"):
            for path in (ROOT / root).rglob("*.py"):
                for n, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), start=1
                ):
                    if "mirror_api_key(" in line and "def mirror_api_key" not in line:
                        callers.append(path.relative_to(ROOT).as_posix())
        assert callers == ["core/model_probe.py"], callers
