"""What a model list actually says about one of its models.

Every field here is read out of the entry the endpoint sent. An absent field stays
``None`` — the surface prints an em-dash — because a number the product invented is a
promise the engine never made. Two measured cases carry that: the ``-free``/``:free``
name suffix, which the setup dropdown read as a price, and the window, which engines
name four different ways (``docs/receipts/context-window-probe-W7-6.json`` measured
DeepSeek writing ``context_window`` where the vLLM field is ``max_model_len``).
"""
from __future__ import annotations

from core.engine_config import window_from_model_entry

#: The keys one model record carries, in the order the surface reads them.
METADATA_KEYS = (
    "name",
    "context_window",
    "price_in_per_m",
    "price_out_per_m",
    "is_free",
    "supports_tools",
    "supports_vision",
)


def _text(value: object) -> str | None:
    """A non-empty string, or None. Whitespace-only is not a name."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _usd_per_million(value: object) -> float | None:
    """OpenRouter's USD-per-token string as USD per 1M, or None.

    ``"0.000000155"`` is 0.155 USD per 1M. A negative or unparseable figure is no
    figure: 0 stays a real price and a malformed string never becomes one.
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        per_token = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if per_token < 0:
        return None
    return round(per_token * 1_000_000, 6)


def _prices(entry: dict) -> tuple[float | None, float | None]:
    """The (in, out) pair of a present pricing table, one None per absent half."""
    pricing = entry.get("pricing")
    if not isinstance(pricing, dict):
        return None, None
    return _usd_per_million(pricing.get("prompt")), _usd_per_million(pricing.get("completion"))


def _is_free(entry: dict, price_in: float | None, price_out: float | None) -> bool | None:
    """Free is a pricing fact, never a name.

    True only when the endpoint priced both sides and both parse to zero. A partial
    table (in priced, out missing) says nothing about the total, so it stays unknown.
    """
    if not isinstance(entry.get("pricing"), dict) or price_in is None or price_out is None:
        return None
    return price_in == 0 and price_out == 0


def _supports_tools(value: object) -> bool | None:
    """``supported_parameters`` names the parameters this model takes."""
    if not isinstance(value, list):
        return None
    named = {str(item).strip().lower() for item in value}
    return "tools" in named or "tool_calls" in named


def _supports_vision(entry: dict) -> bool | None:
    """Image input, from ``architecture`` or from the flat fields of a live engine.

    OpenRouter nests modalities under ``architecture.input_modalities`` and older
    payloads put a ``modality`` string there; the receipt measured DeepSeek writing
    ``input_modalities`` at the top level of the entry. All three spellings name the
    same fact, so all three are read, and an entry with none of them is unknown.
    """
    architecture = entry.get("architecture")
    candidates: list[object] = []
    if isinstance(architecture, dict):
        candidates.append(architecture.get("input_modalities"))
        modality = architecture.get("modality")
        if isinstance(modality, str):
            return "image" in modality.lower()
    candidates.append(entry.get("input_modalities"))
    for value in candidates:
        if isinstance(value, list) and value:
            return "image" in {str(item).strip().lower() for item in value}
    return None


def bare_metadata() -> dict:
    """A record with nothing known — what an Ollama name alone supports.

    ``/api/tags`` supplies names, and ``/api/show`` per model is a request per model on
    the setup path; the list stays honest as unknown instead of paying it.
    """
    return {key: None for key in METADATA_KEYS}


def model_metadata(entry: object) -> dict:
    """The per-model record for one ``/v1/models`` entry, keyed by ``id``."""
    if not isinstance(entry, dict):
        return {"id": "", **bare_metadata()}
    price_in, price_out = _prices(entry)
    return {
        "id": _text(entry.get("id")) or "",
        "name": _text(entry.get("name")),
        "context_window": window_from_model_entry(entry),
        "price_in_per_m": price_in,
        "price_out_per_m": price_out,
        "is_free": _is_free(entry, price_in, price_out),
        "supports_tools": _supports_tools(entry.get("supported_parameters")),
        "supports_vision": _supports_vision(entry),
    }


def model_details(entries: list[object]) -> list[dict]:
    """Aligned per-model records for the entries a probe got back."""
    return [model_metadata(entry) for entry in entries]


def names_of(entries: list[object]) -> list[str]:
    """The id list the probes have always returned — an entry without an id is dropped."""
    names: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        identifier = _text(entry.get("id"))
        if identifier:
            names.append(identifier)
    return names


def metadata_by_id(entries: list[object]) -> dict[str, dict]:
    """id → record, for attaching metadata to a list the engine already named."""
    out: dict[str, dict] = {}
    for entry in entries:
        record = model_metadata(entry)
        if record["id"]:
            out[record["id"]] = record
    return out
