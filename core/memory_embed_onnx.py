"""
◑ Ephe – The embedding model, owned in-repo
core/memory_embed_onnx.py

`all-MiniLM-L6-v2` as ONNX, 384 dimensions, L2-normalised, offline. This is the
forward pass the retired vector store ran on our behalf, written down here so the
vectors already sitting in every Kepta store stay readable now that the store is
gone from the product.

Byte identity is the contract, not closeness. A chunk the retired store embedded
and the same chunk embedded here have to produce the same 1536 bytes, otherwise
every stored vector needs re-embedding and the `embedding_model` label that the
ranking leg filters on (`core/memory_kepta_ranking.py:143`) starts describing data
it can no longer describe. So the arithmetic below is that store's arithmetic,
kept line for line — pad to 256 tokens, mean-pool under the attention mask, L2
normalise, float32 — and the artifact it reads is the one the retired store
already unpacked into `~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx/`.
Nothing here downloads anything and nothing here opens a database.

Two facts pin what "the same bytes" means, and both are hashes rather than
versions, because the file is what the session reads: `ARCHIVE_SHA256` is the
archive chroma's model URL serves, `MODEL_SHA256` is the `model.onnx` inside it.
They differ, and only the second one decides the output. A file this module
cannot vouch for is refused instead of loaded: vectors from some other model
would keep the label `all-MiniLM-L6-v2` and be silently incomparable to the
vectors already stored under that name. `EPHE_EMBED_VERIFY=0` accepts an
unvouched-for file anyway, `EPHE_EMBED_MODEL_DIR` reads another copy of the same
one. A refusal is not fatal — `core/memory_embed.py` turns it into a missing
vector leg, and retrieval keeps working on the lexical and entity legs.

What a frozen hash cannot catch: a future `onnxruntime` whose kernels round
differently would produce different bytes from an unchanged file. That is what
`tests/test_memory_embed_onnx.py` measures rather than argues — the golden
vectors in `tests/fixtures/memory_embed_golden.json` were captured from the
stored data, so a runtime that moves the last bits fails a test instead of
quietly mixing two generations of vector in one store.
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"
EMBED_DIM = 384
MAX_TOKENS = 256

#: The batch chroma's forward pass used. Each sequence pads to `MAX_TOKENS`
#: independently, so batch size cannot move a vector — it only bounds memory.
_BATCH = 32

#: chroma's model URL serves this archive; the session reads the file inside it.
ARCHIVE_SHA256 = "913d7300ceae3b2dbc2c50d1de4baacab4be7b9380491c27fab7418616a16ec3"
MODEL_SHA256 = "4f148ba8ae9c2c7fbee4af2b132db8d06c6a6545b47fc83bbb98c3d22b8393e6"

#: The six names chroma's own downloader checks before it will load a model dir.
ARTIFACTS = (
    "config.json",
    "model.onnx",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
)

ENV_MODEL_DIR = "EPHE_EMBED_MODEL_DIR"
ENV_VERIFY = "EPHE_EMBED_VERIFY"
_OFF = {"0", "off", "false", "no", "none"}


def verify_enabled() -> bool:
    """The hash check runs unless the environment turns it off."""
    return os.environ.get(ENV_VERIFY, "").strip().lower() not in _OFF


def model_dir() -> Path:
    """Where the artifact is read from, defaulting to the retired store's own cache."""
    override = os.environ.get(ENV_MODEL_DIR, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cache" / "chroma" / "onnx_models" / MODEL_NAME / "onnx"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def model_problem(directory: Path | None = None) -> str | None:
    """None when the artifact is usable, otherwise the sentence saying why not."""
    directory = directory or model_dir()
    missing = [name for name in ARTIFACTS if not (directory / name).is_file()]
    if missing:
        return f"{directory} is incomplete — missing {', '.join(missing)}"
    if not verify_enabled():
        return None
    found = sha256_of(directory / "model.onnx")
    if found != MODEL_SHA256:
        return (
            f"{directory}/model.onnx hashes to {found}, not {MODEL_SHA256}: vectors from "
            f"this file would carry the label {MODEL_NAME!r} without being comparable to "
            f"the ones already stored under that label (set {ENV_VERIFY}=0 to accept it)"
        )
    return None


def _normalise(vectors: Any) -> Any:
    """L2 on the row axis, zero-safe, float32 — chroma's guard value included."""
    import numpy as np

    norms = np.linalg.norm(vectors, axis=1)
    norms[norms == 0] = 1e-12
    return (vectors / norms[:, None]).astype(np.float32)


class MiniLmEmbedder:
    """One ONNX session and one tokenizer over the pinned artifact."""

    def __init__(self, directory: Path | None = None) -> None:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.directory = directory or model_dir()
        self._np = np
        tokenizer = Tokenizer.from_file(str(self.directory / "tokenizer.json"))
        tokenizer.enable_truncation(max_length=MAX_TOKENS)
        tokenizer.enable_padding(pad_id=0, pad_token="[PAD]", length=MAX_TOKENS)
        self._tokenizer = tokenizer
        options = ort.SessionOptions()
        options.log_severity_level = 3
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        # CoreML is dropped for the same reason chroma dropped it: a different
        # execution provider sums the same matmuls in a different order, and the
        # bytes are the contract. Everything else stays available.
        providers = [
            name for name in ort.get_available_providers() if name != "CoreMLExecutionProvider"
        ]
        self._session = ort.InferenceSession(
            str(self.directory / "model.onnx"),
            sess_options=options,
            providers=providers or None,
        )

    def __call__(self, texts: list[str]) -> list[list[float]]:
        return self.embed(texts)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """One 384-long unit vector per text, as plain Python floats."""
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
        run = self._session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": np.zeros_like(attention_mask),
            },
        )
        hidden: Any = run[0]
        # The mask stays int64 on purpose. int64 * float32 promotes the product to
        # float64, and that is the arithmetic the stored vectors were written with;
        # narrowing the mask to float32 moves the last bits of every vector and breaks
        # byte identity with a store that holds 180 of them.
        expanded = np.broadcast_to(np.expand_dims(attention_mask, -1), hidden.shape)
        pooled = np.sum(hidden * expanded, 1) / np.clip(expanded.sum(1), a_min=1e-9, a_max=None)
        return _normalise(pooled)
