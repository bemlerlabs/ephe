"""
◑ Ephe – EmbeddingGemma 2 as the second vectorizer
core/memory_embed_gemma.py

The counterpart to `core/memory_embed_onnx.py`: Google's EmbeddingGemma 2 as ONNX,
768 dimensions narrowed to 256 through Matryoshka truncation and L2-normalised,
offline once the weights sit on disk.

Two loaders because the two models write different vector spaces,
and the ranking leg selects chunks by the `embedding_model` column
(`core/memory_kepta_ranking.py`, `leg_vector`). A 384-wide MiniLM vector and a
256-wide EmbeddingGemma vector share no axis, so one label over both would rank
noise. This module keeps its own label (`MODEL_LABEL`) and never reads or writes
MiniLM's artifacts.

The weights stay out of the install. `ensure_model()` answers the three ways
`core/transcribe.py` answers for the speech model:
  * on disk             → the directory, nothing fetched;
  * missing, no consent → `EmbeddingGemmaNotAvailable`, naming the repo, the host
                          and the size, plus how to allow it;
  * missing, consent    → fetch into `~/.ephe/models/embeddinggemma-2`, then load.
`EPHE_OFFLINE=1` outranks consent: an offline process reaches out to nobody.

Consent has two spellings, the same pair the speech model uses:
`EPHE_EMBEDDINGGEMMA_DOWNLOAD=1` for a shell, and the
`memory.embedder_allow_download` deep setting for the desktop app, which inherits
no shell environment.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: The stored label. It names the vector space, so `leg_vector` and
#: `cosine_matches` can filter on it and never compare it against MiniLM's.
MODEL_LABEL = "embeddinggemma-2"
MODEL_REPO = "onnx-community/embeddinggemma-2-ONNX"
MODEL_HOST = "huggingface.co"
#: The fp16 text encoder: the graph plus its external weights. The fp32 export
#: (1084 MB) and the q4 export (174 MB) exist too; fp16 is the default because
#: it keeps full precision at half the fp32 download. Named before a byte is fetched.
MODEL_SIZE_MB = 542
#: The ONNX export splits the graph (`*.onnx`) from its weights (`*.onnx_data`),
#: so both files of the chosen variant must be fetched together.
ONNX_VARIANT = "model_fp16.onnx"

#: What the graph emits; what we keep. EmbeddingGemma is trained with
#: Matryoshka loss, so a prefix of the vector keeps its ranking quality while the
#: stored blob drops from 3 KB to 1 KB per chunk.
NATIVE_DIM = 768
EMBED_DIM = 256
MAX_TOKENS = 512
_BATCH = 16

#: The names the downloaded directory must hold. The ONNX export lands in an
#: `onnx/` subdirectory, so `onnx_path()` also looks one level down.
ARTIFACTS = ("tokenizer.json", "model.onnx")
_ALLOW_PATTERNS = (
    "config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    f"onnx/{ONNX_VARIANT}",
    f"onnx/{ONNX_VARIANT}_data",
)

ENV_MODEL_DIR = "EPHE_EMBEDDINGGEMMA_DIR"
ENV_DOWNLOAD = "EPHE_EMBEDDINGGEMMA_DOWNLOAD"
ENV_OFFLINE = "EPHE_OFFLINE"

SETTING_ALLOW_DOWNLOAD = "memory.embedder_allow_download"


def _env_flag(name: str) -> bool:
    """One spelling of an on-switch, matching core/transcribe.py `_env_flag`."""
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def config_dir() -> Path:
    """The device folder — `EPHE_CONFIG_DIR`, otherwise `~/.ephe`."""
    return Path(os.environ.get("EPHE_CONFIG_DIR") or str(Path.home() / ".ephe"))


def model_dir() -> Path:
    """Where the artifact is read from, with a test override for another copy."""
    override = os.environ.get(ENV_MODEL_DIR, "").strip()
    if override:
        return Path(override).expanduser()
    return config_dir() / "models" / MODEL_LABEL


def tokenizer_path(directory: Path | None = None) -> Path | None:
    """`tokenizer.json`, at the directory root or one level below it."""
    root = directory or model_dir()
    top = root / "tokenizer.json"
    if top.is_file():
        return top
    found = sorted(root.glob("**/tokenizer.json"))
    return found[0] if found else None


def onnx_path(directory: Path | None = None) -> Path | None:
    """The chosen variant's graph, preferred over any other `.onnx` in the tree."""
    root = directory or model_dir()
    preferred = root / "onnx" / ONNX_VARIANT
    if preferred.is_file():
        return preferred
    found = sorted(root.glob("**/*.onnx"))
    return found[0] if found else None


def model_present() -> bool:
    """True when both the tokenizer and the graph sit on disk already."""
    return tokenizer_path() is not None and onnx_path() is not None


def offline() -> bool:
    """`EPHE_OFFLINE=1`: this process may not fetch anything, ever."""
    return _env_flag(ENV_OFFLINE)


def download_consent() -> bool:
    """Has the user allowed the 540 MB fetch?

    Two explicit sources, no default: the env switch for a shell, and the deep
    setting for the desktop app, which inherits no shell environment.
    """
    if _env_flag(ENV_DOWNLOAD):
        return True
    try:
        from core.settings_schema import deep_bool

        return bool(deep_bool("memory.embedder_allow_download"))
    except Exception:
        return False


class EmbeddingGemmaNotAvailable(RuntimeError):
    """No weights on disk and no consent to fetch them (or an offline process)."""


def refusal(reason: str) -> str:
    """The turn-away text: what it is, where it comes from, and how to allow it."""
    return (
        f"EmbeddingGemma 2 is not on disk ({reason}). It comes from "
        f"{MODEL_HOST}/{MODEL_REPO} (~{MODEL_SIZE_MB} MB). Allow the fetch with "
        f"{ENV_DOWNLOAD}=1 or the '{SETTING_ALLOW_DOWNLOAD}' setting; all-MiniLM-L6-v2 "
        f"stays selectable through 'memory.embedder'."
    )


def _fetch(repo_id: str, target: Path, allow_patterns: tuple[str, ...]) -> None:
    """Thin seam over `snapshot_download`, so a test can stand in for the hub."""
    from huggingface_hub import snapshot_download

    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=repo_id, local_dir=str(target), allow_patterns=list(allow_patterns))


def ensure_model() -> Path:
    """The model directory, fetched only under consent, else the caller is turned away."""
    if model_present():
        return model_dir()
    if offline():
        raise EmbeddingGemmaNotAvailable(refusal(f"{ENV_OFFLINE}=1 forbids any fetch"))
    if not download_consent():
        raise EmbeddingGemmaNotAvailable(refusal("no consent given"))
    target = model_dir()
    logger.info(
        "memory: fetching %s from %s (%d MB) into %s",
        MODEL_REPO, MODEL_HOST, MODEL_SIZE_MB, target,
    )
    _fetch(MODEL_REPO, target, _ALLOW_PATTERNS)
    if not model_present():
        raise EmbeddingGemmaNotAvailable(refusal("the fetch left the directory incomplete"))
    return target


def open_tokenizer(path: Path, max_length: int) -> Any:
    """A tokenizer fixed to `max_length`, so every row of a batch shares a shape."""
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(path))
    tokenizer.enable_truncation(max_length=max_length)
    tokenizer.enable_padding(pad_id=0, pad_token="<pad>", length=max_length)
    return tokenizer


def open_session(path: Path) -> Any:
    """One CPU-biased ONNX session. CoreML is dropped: it sums matmuls in another
    order and this label's vectors have no frozen-byte contract to protect, but a
    second provider only buys a second set of floating-point surprises."""
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.log_severity_level = 3
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    providers = [name for name in ort.get_available_providers() if name != "CoreMLExecutionProvider"]
    return ort.InferenceSession(str(path), sess_options=options, providers=providers or None)


def _normalise(vectors: Any) -> Any:
    """L2 on the row axis, zero-safe, float32 — the same guard MiniLM uses."""
    import numpy as np

    norms = np.linalg.norm(vectors, axis=1)
    norms[norms == 0] = 1e-12
    return (vectors / norms[:, None]).astype(np.float32)


class EmbeddingGemmaEmbedder:
    """One ONNX session and one tokenizer over the pinless EmbeddingGemma artifact.

    `directory` names another copy (a test fixture, or `EPHE_EMBEDDINGGEMMA_DIR`);
    without it the model directory is fetched on consent through `ensure_model()`.
    """

    def __init__(self, directory: Path | str | None = None, *, dim: int = EMBED_DIM) -> None:
        import numpy as np

        self._np = np
        self.directory = Path(directory) if directory is not None else ensure_model()
        self.dim = int(dim)
        tokenizer = tokenizer_path(self.directory)
        model = onnx_path(self.directory)
        if tokenizer is None:
            raise EmbeddingGemmaNotAvailable(f"{self.directory} holds no tokenizer.json")
        if model is None:
            raise EmbeddingGemmaNotAvailable(f"{self.directory} holds no model.onnx")
        self._tokenizer = open_tokenizer(tokenizer, MAX_TOKENS)
        self._session = open_session(model)

    def __call__(self, texts: list[str]) -> list[list[float]]:
        return self.embed(texts)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """One `dim`-long unit vector per text, as plain Python floats."""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH):
            for row in self._forward(list(texts[start : start + _BATCH])):
                vectors.append([float(value) for value in row])
        return vectors

    def blobs(self, texts: list[str]) -> list[bytes]:
        """The stored form: what `to_blob` in `core/memory_kepta_schema.py` writes."""
        import numpy as np

        return [np.asarray(row, dtype=np.float32).tobytes() for row in self.embed(texts)]

    def _forward(self, texts: list[str]) -> Any:
        np = self._np
        encoded = [self._tokenizer.encode(text) for text in texts]
        input_ids = np.array([row.ids for row in encoded], dtype=np.int64)
        attention_mask = np.array([row.attention_mask for row in encoded], dtype=np.int64)
        # Text-only: the export is the full multimodal graph, so the three
        # non-text modality slots are fed empty (zero-token) tensors.
        empty = np.zeros((0, 512), dtype=np.float32)
        run = self._session.run(
            ["sentence_embedding"],
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "image_features": empty,
                "video_features": empty,
                "audio_features": empty,
            },
        )
        sentence: Any = run[0]
        # Prefix first, then normalise: Matryoshka quality lives in the leading
        # dimensions, and a unit vector has to be unit after the cut.
        return _normalise(sentence[:, : self.dim])
