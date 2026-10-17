"""Ephe — Environment Mirror (B-wave, docs/EXTENSIONS_V2_PLAN.md).
core/environment_mirror.py

Detects the agent tools the user already has installed — purely in READ-ONLY
mode — and delivers structural info for onboarding/settings: which tools are
present, which providers/models their configs name, whether a login file
exists. The registry below is a table of (the tool's own config directory →
what that directory holds); a tool's NAME is the name of that directory, so
every spelling here is data read from the user's home, never a name we write
down ourselves.

Hard data-protection contract:
- Only reading config files; never writing, never deleting, never executing.
- Values of keys containing key/token/secret/password/auth never leave the
  module — auth_present is a boolean fact, not a value.
- Fail-soft: a missing/malformed tool is an empty entry, never
  an error. The report stays local (no network call).

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

try:
    import tomllib  # stdlib from 3.11
except ModuleNotFoundError:  # Python 3.10: tomli is a marker-scoped main dependency
    import tomli as tomllib  # type: ignore[no-redef]

_SECRET_KEY_RE = re.compile(r"key|token|secret|password|auth", re.IGNORECASE)
_SLUGISH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ./_:-]{1,80}$")


def _strip_jsonc(text: str) -> str:
    """Removes // and /* */ comments (JSONC → JSON). String-safe enough
    for configs: comments inside strings are not relevant in practice —
    and a parse failure is fail-soft an empty entry."""
    out: list[str] = []
    in_string = False
    escape = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "*":
            i += 2
            while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _read_config(path: Path) -> dict | None:
    """Read a config (JSON, JSONC, TOML or YAML). Missing/broken → None."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml  # only when needed (present in .venv)

            data = yaml.safe_load(text)
        except (ValueError, ImportError):
            return None
        return data if isinstance(data, dict) else None
    if path.suffix == ".toml":
        try:
            data = tomllib.loads(text)
        except ValueError:  # TOMLDecodeError is a ValueError; a malformed file is an empty entry
            return None
        return data if isinstance(data, dict) else None
    try:
        data = json.loads(_strip_jsonc(text))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _safe_strings(value: object, depth: int = 0) -> list[str]:
    """Collects non-secret names from a config structure: dict KEYS are
    themselves names (provider/model IDs), so are string leaves. Values of
    secret-like keys are discarded — the key name alone
    satisfies the check."""
    found: list[str] = []
    if depth > 4:
        return found
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str):
                if _SECRET_KEY_RE.search(k):
                    continue  # secret-like branch: skip (children too)
                if _SLUGISH_RE.match(k):
                    found.append(k)
            found.extend(_safe_strings(v, depth + 1))
    elif isinstance(value, list):
        for item in value[:32]:
            found.extend(_safe_strings(item, depth + 1))
    elif isinstance(value, str) and len(value) <= 120:
        found.append(value)
    return found


@dataclass
class MirrorEntry:
    tool: str
    installed: bool
    config_path: str = ""
    providers: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    auth_present: bool = False
    """Names from models[] recognisable as free models by their suffix
    ('-free'/':free') — so the UI can tell subscription and free models apart."""
    free_models: list[str] = field(default_factory=list)
    """Model → real API endpoint from the provider catalog (models.dev shape:
    an 'api' field per provider). This pairs models honestly with their endpoint
    instead of guessing list position 1 out of a mixed provider list."""
    model_endpoints: dict[str, str] = field(default_factory=dict)
    """The registry row whose models this product is built around (its own
    reference harness). Read from here so the composer's ranking never has to
    compare a tool name: the flag travels with the data."""
    preferred: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


_URL_RE = re.compile(r"^https?://\S+$")
_NAME_KEYS = ("slug", "id", "modelId", "model", "name")


def _model_name_of(d: dict) -> str | None:
    """Honest model name of a descriptor dict: the first slug-capable
    ID-value, otherwise None (meta fields such as display_name are not names)."""
    for src in _NAME_KEYS:
        val = d.get(src)
        if isinstance(val, str) and _SLUGISH_RE.match(val) and "://" not in val:
            return val
    return None


_MODEL_KEYS = {"MODEL", "DEFAULT_MODEL", "ACTIVE_MODEL", "CURRENT_MODEL"}
_URL_KEYS = {"BASE_URL", "BASE__URL", "ENDPOINT"}


def _add_model_item(item: object, mods: list[str]) -> None:
    if isinstance(item, str):
        if _SLUGISH_RE.match(item) and "://" not in item:
            mods.append(item)
    elif isinstance(item, dict):
        name = _model_name_of(item)
        if name:
            mods.append(name)


def _collect_family(node: dict, parent: str, prov: list[str], mods: list[str], depth: int) -> None:
    """One set of key conventions applied to every tool's tree: model keys
    (model/default_model/…, including a nested ``default``) and
    base-URL/ENDPOINT values — through the whole tree dict."""
    if depth > 5 or not isinstance(node, dict):
        return
    for k, v in node.items():
        if not isinstance(k, str):
            continue
        ku = k.upper()
        if _SECRET_KEY_RE.search(ku):
            continue
        if ku in _URL_KEYS and isinstance(v, str) and _URL_RE.match(v):
            prov.append(v.split("?")[0])
        elif ku in _MODEL_KEYS:
            if isinstance(v, str):
                if _SLUGISH_RE.match(v) and "://" not in v:
                    mods.append(v)
            elif isinstance(v, list):
                for it in v[:24]:
                    _add_model_item(it, mods)
            elif isinstance(v, dict):
                nm = _model_name_of(v)
                if nm is None:
                    dflt = v.get("default")
                    if (
                        isinstance(dflt, str)
                        and _SLUGISH_RE.match(dflt)
                        and "://" not in dflt
                    ):
                        nm = dflt
                if nm:
                    mods.append(nm)
                _collect_family(v, ku, prov, mods, depth + 1)
        elif isinstance(v, dict):
            _collect_family(v, ku, prov, mods, depth + 1)
        elif isinstance(v, list):
            for it in v[:24]:
                if isinstance(it, dict):
                    _collect_family(it, ku, prov, mods, depth + 1)


def _collect_catalog(data: dict, prov: list[str], mods: list[str], depth: int = 0) -> None:
    """Provider catalog shape: provider objects with 'models' (also nested,
    e.g. provider:{anthropic:{models:…}}) — provider key 'provider' OR
    'schema:<url>' (the endpoint sits in the key itself)."""
    if depth > 2 or not isinstance(data, dict):
        return
    for pk, pv in list(data.items())[:12]:
        if not isinstance(pv, dict):
            continue
        if "models" not in pv:
            _collect_catalog(pv, prov, mods, depth + 1)
            continue
        ks = str(pk)
        if ks.startswith("custom:") and _URL_RE.match(ks[7:]):
            prov.append(ks[7:].split("?")[0])
        elif _URL_RE.match(ks):
            prov.append(ks.split("?")[0])
        elif _SLUGISH_RE.match(ks):
            prov.append(ks)
        ml = pv["models"]
        if isinstance(ml, dict):
            mods.extend(str(k) for k in ml.keys() if _SLUGISH_RE.match(str(k)))
        elif isinstance(ml, list):
            for it in ml[:24]:
                _add_model_item(it, mods)


def _is_api_endpoint(url: str) -> bool:
    """The URL is an API endpoint (not a doc/schema link): no /models
    last segment, no file suffix — ports/paths like ':8000' or '/v1' are ok."""
    if not _URL_RE.match(url):
        return False
    clean = url.split("?")[0]
    rest = clean.split("://", 1)[-1]
    seg_path = rest.split("/", 1)[1] if "/" in rest else ""
    last = seg_path.rstrip("/").rsplit("/", 1)[-1]
    return seg_path.rstrip("/") != "models" and not ("." in last)


def _extract_providers_models(data: dict) -> tuple[list[str], list[str]]:
    """(providers, models) honestly extracted from a config structure.

    Four shapes are supported — otherwise the UI is left with an
    installation line without models (user finding in Settings/Environment):
    1. classic: provider/model fields primitive,
    2. model list of strings or dicts with slug/id/name
       (a ``models_cache.json``),
    3. nested ``env`` object with ``*_MODEL`` values and
       ``*_BASE_URL`` endpoints (the env-nested style),
    4. provider catalog shape: top-level provider objects each with a
       ``models`` dict (a models.dev-shaped cache).
    The secret rule stays: values of secret-like keys never leave the module.
    """
    # Provider line strictly by shape — no _safe_strings shotgun
    # (otherwise meta keys such as 'api_timeout' flow into the provider list).
    pv = data.get("provider") or data.get("providers") or {}
    prov: list[str] = []
    if isinstance(pv, str):
        prov = [pv] if _SLUGISH_RE.match(pv) else []
    elif isinstance(pv, list):
        prov = [x for x in pv[:12] if isinstance(x, str) and _SLUGISH_RE.match(x)]
    elif isinstance(pv, dict):
        prov = [
            str(k)
            for k, v in list(pv.items())[:12]
            if isinstance(v, dict) and _SLUGISH_RE.match(str(k))
        ]
    prov2: list[str] = []
    mods2: list[str] = []
    _collect_family(data, "", prov2, mods2, 0)
    _collect_catalog(data, prov2, mods2)
    prov += prov2
    raw_models = data.get("model") or data.get("models")
    if isinstance(raw_models, dict) and _model_name_of(raw_models):
        # Model descriptor dict (meta keys beside one ID value): the list takes
        # only the ID-value entries; meta keys (aliases/displayName) would blur
        # it.
        name = _model_name_of(raw_models)
        mods = [name] if name else []
    elif isinstance(raw_models, list):
        # Model list: strings directly, dicts only through their name
        # (otherwise display_name descriptions end up there as "model names").
        mods = []
        for item in raw_models[:24]:
            if isinstance(item, str) and _SLUGISH_RE.match(item):
                mods.append(item)
            elif isinstance(item, dict):
                name = _model_name_of(item)
                if name:
                    mods.append(name)
    elif isinstance(raw_models, dict):
        # A descriptor with a hidden name ('default') or an unnamed
        # dict (models.dev cache): then the keys are the model slugs.
        nm = _model_name_of(raw_models)
        if nm is None:
            dflt = raw_models.get("default")
            nm = dflt if isinstance(dflt, str) and _SLUGISH_RE.match(dflt) else None
        if nm:
            mods = [nm]
        else:
            mods = [str(k) for k in raw_models.keys() if _SLUGISH_RE.match(str(k))][:24]
    else:
        mods = []

    env = data.get("env")
    if isinstance(env, dict):
        for k, v in env.items():
            if not isinstance(k, str) or not isinstance(v, str):
                continue
            ku = k.upper()
            if _SECRET_KEY_RE.search(ku):
                continue
            if ku.endswith("_MODEL") and _SLUGISH_RE.match(v):
                mods.append(v)
            elif ku.endswith(("_BASE_URL", "_BASE__URL")) and _URL_RE.match(v):
                prov.append(v.split("?")[0])
    if not mods and not prov:
        # Provider-catalog shape (the models.dev cache): provider keys + model keys.
        for pk, pv in list(data.items())[:12]:
            if isinstance(pv, dict):
                if _SLUGISH_RE.match(str(pk)):
                    prov.append(str(pk))
                pmodels = pv.get("models")
                if isinstance(pmodels, dict):
                    mods.extend(k for k in pmodels.keys() if _SLUGISH_RE.match(str(k)))

    # Collect endpoints (for selectable picks): all non-secret URL values.
    for s in _safe_strings(data):
        if _URL_RE.match(s):
            prov.append(s.split("?")[0])
    clean_prov = [p for p in prov if not _URL_RE.match(p) or _is_api_endpoint(p)]
    seen_m: set[str] = set()
    final_mods = [m for m in [*mods, *mods2] if m and not (m in seen_m or seen_m.add(m))]
    return sorted({p for p in clean_prov})[:12], final_mods[:24]


def _catalog_model_endpoints(data: dict) -> dict[str, str]:
    """Model → API endpoint from the provider catalog shape (models.dev cache):
    top-level provider objects each with 'api' + 'models'. Only http(s) values.
    The first providers win (setdefault) — the active config is listed first."""
    out: dict[str, str] = {}
    for pv in data.values():
        if not isinstance(pv, dict):
            continue
        api = pv.get("api")
        ml = pv.get("models")
        if isinstance(api, str) and _URL_RE.match(api) and isinstance(ml, dict):
            for k in ml.keys():
                if _SLUGISH_RE.match(str(k)) and str(k) not in out:
                    out[str(k)] = api.split("?")[0]
    return out


@dataclass(frozen=True)
class ToolProbe:
    """One agent tool we mirror: where its config lives, what sits in there.

    ``config_dir`` is the tool's own directory on disk — its NAME is the tool's
    name (a fact about the user's home, never a name we invent). ``artifacts``
    are the files we read, or a directory whose mere existence is the signal;
    ``auth`` the files whose existence alone proves a login (contents are never
    read); ``catalog`` a provider/model cache that may fill endpoint gaps;
    ``session_db`` a read-only SQLite of the models the tool REALLY used;
    ``preferred`` marks the row whose models this product is built around — the
    composer lists them first. Set HERE on the row, so no consumer ranks on a name.
    """

    config_dir: Path
    artifacts: tuple[Path, ...]
    auth: tuple[Path, ...] = ()
    catalog: Path | None = None
    session_db: Path | None = None
    preferred: bool = False

    @property
    def name(self) -> str:
        """The tool's name as its own directory spells it (leading dot off)."""
        return self.config_dir.name.lstrip(".")


def _entry(probe: ToolProbe) -> MirrorEntry:
    """Builds a mirror entry for one probe row. artifacts: config files (read)
    or folders (existence suffices). auth: files whose mere existence proves a
    login — their contents are never read.

    A tool has SEVERAL sources (active config + model caches). All existing
    candidates are merged — earlier files (active config) before later ones
    (caches), duplicates drop out."""
    prov_acc: list[str] = []
    mods_acc: list[str] = []
    ep_acc: dict[str, str] = {}
    first_file = ""
    for cand in probe.artifacts:
        if not cand.is_file():
            continue
        if not first_file:
            first_file = str(cand)
        data = _read_config(cand)
        if not data:
            continue
        p, m = _extract_providers_models(data)
        prov_acc.extend(p)
        mods_acc.extend(m)
        for k, v in _catalog_model_endpoints(data).items():
            ep_acc.setdefault(k, v)
    if first_file:
        # Order: earlier files (active config) win over cache duplicates.
        prov_u = list(dict.fromkeys(prov_acc))
        mods_u = list(dict.fromkeys(mods_acc))
        return MirrorEntry(
            tool=probe.name,
            installed=True,
            config_path=first_file,
            providers=prov_u[:12],
            models=mods_u[:24],
            auth_present=any(a.is_file() for a in probe.auth),
            free_models=[m for m in mods_u if m.endswith(("-free", ":free"))][:24],
            model_endpoints=dict(ep_acc),
            preferred=probe.preferred,
        )
    for cand in probe.artifacts:
        if cand.exists():
            return MirrorEntry(
                tool=probe.name,
                installed=True,
                config_path=str(cand),
                auth_present=any(a.is_file() for a in probe.auth),
                preferred=probe.preferred,
            )
    return MirrorEntry(tool=probe.name, installed=False)


def _ollama_models(h: Path) -> list[str]:
    """Read Ollama models honestly from the manifest tree (no subprocess):
    ``~/.ollama/models/manifests/<registry>/library/<name>/<tag>`` →
    ``<name>:<tag>``. The OLLAMA_MODELS override is respected. Fail-soft."""
    import os

    roots = []
    override = os.environ.get("OLLAMA_MODELS")
    if override:
        roots.append(Path(override))
    roots.append(h / ".ollama" / "models")
    models: list[str] = []
    for root in roots:
        base = root / "manifests"
        if not base.is_dir():
            continue
        try:
            for registry in sorted(base.iterdir())[:4]:
                for name_dir in sorted(registry.rglob("*")):
                    if not name_dir.is_dir():
                        continue
                    tags = [f for f in sorted(name_dir.iterdir()) if f.is_file()]
                    for tag in tags[:4]:
                        if name_dir.name == "library" and name_dir.parent.name:
                            models.append(f"{name_dir.parent.name}:{tag.name}")
                        else:
                            models.append(f"{name_dir.name}:{tag.name}")
        except OSError:
            continue
        if models:
            break
    return models[:24]


def _recent_models_from_db(db: Path) -> list[str]:
    """The models a tool REALLY used last, from its own SQLite session DB
    (read-only, fail-soft) — more honest than any catalog."""
    if not db.is_file():
        return []
    try:
        import sqlite3

        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT model FROM session WHERE model IS NOT NULL AND model != ''"
                " ORDER BY time_updated DESC LIMIT 8"
            ).fetchall()
        finally:
            con.close()
    except Exception:
        return []
    out: list[str] = []
    for (m,) in rows:
        if not m:
            continue
        s = str(m)
        # Partly the column stores JSON blobs {"id":...,"providerID":...} —
        # take only the model ID out of those.
        if s.startswith("{"):
            try:
                parsed = json.loads(s)
                s = str(parsed.get("id") or s)
            except ValueError:
                pass
        if s and s not in out:
            out.append(s)
    return out[:8]


def probes(h: Path) -> list[ToolProbe]:
    """The registry: one row per tool we mirror, keyed by what the row holds.

    Every row names its own config directory — the names inside these paths are
    DATA from the user's home, and the detection cannot work without them. A
    fallback directory sits last in ``artifacts``: its mere existence is then
    the signal. One row carries ``preferred``: the reference harness this product
    is built around, whose models the composer chip lists first.
    """
    return [
        ToolProbe(
            h / ".config" / "opencode",
            (h / ".config" / "opencode" / "opencode.jsonc",
             h / ".config" / "opencode" / "config.json",
             h / ".cache" / "opencode" / "models.json",
             h / ".opencode"),
            (h / ".local" / "share" / "opencode" / "auth.json",),
            catalog=h / ".cache" / "opencode" / "models.json",
            session_db=h / ".local" / "share" / "opencode" / "opencode.db",
        ),
        ToolProbe(
            h / ".claude",
            (h / ".claude" / "settings.json", h / ".claude"),
            (h / ".claude" / ".credentials.json",),
        ),
        ToolProbe(
            h / ".cursor",
            (h / ".cursor" / "cli-config.json", h / ".cursor"),
        ),
        ToolProbe(
            h / ".hermes",
            (h / ".hermes" / "config.yaml",
             h / ".hermes" / "provider_models_cache.json",
             h / ".hermes" / "models_dev_cache.json",
             h / ".hermes" / "ollama_cloud_models_cache.json",
             h / ".hermes"),
            (h / ".hermes" / "auth.json",),
            preferred=True,  # the reference harness: its rows rank first (data on the row, never a name compared downstream)
        ),
        ToolProbe(
            h / ".codex",
            (h / ".codex" / "config.toml",
             h / ".codex" / "config.json",
             h / ".codex" / "models_cache.json",
             h / ".codex"),
            (h / ".codex" / "auth.json",),
        ),
    ]


def scan(home: Path | None = None) -> list[dict]:
    """Detects existing agent tools (fail-soft, read-only, secret-free)."""
    h = Path(home) if home is not None else Path.home()
    out: list[dict] = []
    for probe in probes(h):
        entry = _entry(probe)
        e = entry.to_dict()
        # The row that ships a session DB: the models REALLY used last go first
        # (a DB of real sessions is more honest than any catalog), and the model
        # cache afterwards fills endpoint gaps for them (fail-soft).
        if entry.installed and probe.session_db is not None:
            last = _recent_models_from_db(probe.session_db)
            merged = [m for m in last if m not in e["models"]] + list(e["models"])
            e["models"] = merged[:24]
            e["last_used"] = last
            # Re-derive free_models after the merge (suffix '-free'/':free').
            e["free_models"] = [m for m in e["models"]
                                if m.endswith(("-free", ":free"))][:24]
            # Merged models (from the DB) may have been absent from the catalog
            # map — resolve them afterwards from the model cache (fail-soft).
            if probe.catalog is not None and any(
                m not in e["model_endpoints"] for m in e["models"]
            ):
                cache = _read_config(probe.catalog) or {}
                for k, v in _catalog_model_endpoints(cache).items():
                    e["model_endpoints"].setdefault(k, v)
        out.append(e)
    # Ollama as its own tool: manifest tree = locally available models,
    # fixed local endpoint (11434) — derivePick derives honest
    # local_ollama/custom_ollama from that.
    ollama_mods = _ollama_models(h)
    if ollama_mods:
        # Local Ollama models are free by definition (no subscription needed).
        out.insert(0, MirrorEntry(
            tool="ollama",
            installed=True,
            config_path=str(h / ".ollama" / "models"),
            providers=["http://127.0.0.1:11434"],
            models=ollama_mods,
            auth_present=True,
            free_models=list(ollama_mods),
            model_endpoints={m: "http://127.0.0.1:11434" for m in ollama_mods},
        ).to_dict())
    return out


def installed_tools(home: Path | None = None) -> list[str]:
    """Compact list of the detected tools (doctor/UI)."""
    return [e["tool"] for e in scan(home) if e["installed"]]
