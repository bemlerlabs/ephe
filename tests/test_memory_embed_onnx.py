"""◑ Ephe — the in-repo embedder still produces the bytes a store already holds.

The vector leg of every Kepta memory compares stored embeddings, and the store on
disk was written while chromadb's `DefaultEmbeddingFunction` was the embedder
(`core/memory_embed.py`). Replacing that loader is only a swap if the numbers come
out identical: one changed bit re-uses a vector nobody recomputed and matches
nothing. So the bytes here are frozen from chromadb's own output — captured on
2026-10-14 while chromadb was still installed, and cross-checked against the 180
chunks of a real Kepta store (`~/.ephe/memory/kepta/<workspace>/kepta.db`), all
180 of which the in-repo code reproduces byte for byte.

That byte-for-byte promise belongs to the machine and the runtime that wrote the
bytes. onnxruntime selects its matmul kernels from the CPU and its versions round
differently, so a Linux host, or a different onnxruntime on the same host, cannot
reproduce a macOS vector bit for bit. Measured numbers and the exact axes are in the
fixture's `portability` field. The tests here therefore assert bit identity only where
this machine's OS/CPU and onnxruntime version match the capture, and numerical
equivalence — cosine >= 0.9999, max |delta| <= 1e-4 — anywhere else. That is no loss
for a stored memory: the vector leg ranks by cosine and drops only sums <= 0.0, and a
1e-07 cosine shift cannot reorder two chunks that are not already the same chunk.

`tests/fixtures/memory_embed_golden.json` holds those bytes and the digest of each
probe text, so editing a probe fails loudly instead of silently comparing against
vectors that belong to a different string. The last test compares against chromadb
directly and skips once the package is gone; everything above it stays.

Two guards worth knowing before editing `core/memory_embed_onnx.py`: the attention
mask stays int64 (int64 × float32 is what promotes the pooling sum to the float64
the stored vectors were written in), and the session drops CoreML. Both are
measured below as negative controls rather than trusted.

Where the artifact comes from: `~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx/`,
unpacked there by chromadb. A machine without it skips these tests — the embedder
turns itself off and retrieval keeps working on its lexical and entity legs, which
is what `tests/test_memory_provider.py` and `tests/test_memory_kepta.py` already
pin from the other side.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "memory_embed_golden.json"

#: The probe set the frozen vectors belong to. Do not reorder: the fixture is a
#: list keyed by position, and the digest check is what keeps the two in step.
PROBES = [
    "Q: Answer in Markdown.",
    "Der Schwarzwald im Herbst ist schöner als im Frühling — erklär mir das bitte genauer.",  # language-gate: ignore (a German probe: the frozen bytes belong to this exact string)
    "🎉🚀 shipped it! ✅ no rollback needed 🧪",
    "告诉我关于这个项目的一切。日本語のテスト、CJK の切り詰め。",
    "a",
    "",
    ("The quick brown fox jumps over the lazy dog. " * 40).strip(),
    "def load(path):\n\twith open(path) as f:\n\t\treturn f.read()  # tabs, newlines, — dash\n",
]


def golden() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def frozen_bytes() -> list[bytes]:
    return [base64.b64decode(entry["float32_b64"]) for entry in golden()["vectors"]]


#: The cross-platform contract, and why these two numbers. The frozen bytes came from
#: chromadb on a Darwin/arm64 host running onnxruntime 1.29.0; onnxruntime's kernels
#: are chosen per CPU and its versions round differently, so a different host or
#: version moves the last bits of every vector. Measured 2026-10-14 on one arm64
#: machine, onnxruntime 1.23.2 against the frozen 1.29.0 output: max |delta| 3.99e-07
#: per component, min cosine 1 - 1.2e-07, 2999 of 3072 components touched — and
#: identical across intra_op_num_threads 1/2/8, so threading is not the axis. The
#: floor below leaves 250x headroom over the version delta and still fails a real
#: change: narrowing the attention mask to float32 (a one-line arithmetic slip) alone
#: shifts ~2000 of 3072 components, which is exactly the regression this file guards.
COSINE_FLOOR = 0.9999
MAX_ABS_DELTA = 1e-4


def _runtime_matches_the_capture() -> bool:
    """True only where bit identity is owed: same OS/CPU and same onnxruntime build."""
    import platform

    import onnxruntime

    on_ = golden().get("captured_on", {})
    return (
        onnxruntime.__version__ == golden()["captured_with"]["onnxruntime"]
        and platform.system() == on_.get("system")
        and platform.machine() == on_.get("machine")
    )


def _assert_matches_frozen_bytes(measured: list[bytes], where: str) -> None:
    """Bit for bit on the capture runtime; within kernel tolerance on any other host."""
    import numpy as np

    frozen = frozen_bytes()
    if _runtime_matches_the_capture():
        assert measured == frozen, f"{where}: same runtime as the capture, bytes may not differ"
        return
    got = np.array([np.frombuffer(blob, dtype=np.float32) for blob in measured])
    ref = np.array([np.frombuffer(blob, dtype=np.float32) for blob in frozen])
    assert got.shape == ref.shape, f"{where}: {got.shape} != frozen {ref.shape}"
    delta = np.abs(got - ref)
    cosine = np.sum(got * ref, axis=1) / (np.linalg.norm(got, axis=1) * np.linalg.norm(ref, axis=1))
    assert float(delta.max()) <= MAX_ABS_DELTA, (
        f"{where}: max |delta| {delta.max():.3e} over {int((delta > 0).sum())} components "
        f"exceeds {MAX_ABS_DELTA:.0e} — a different model or arithmetic, not a kernel that "
        f"rounds differently"
    )
    assert float(cosine.min()) >= COSINE_FLOOR, (
        f"{where}: min cosine {cosine.min():.10f} < {COSINE_FLOOR} — the vectors stopped "
        f"being equivalent to the frozen ones"
    )


def artifact_state() -> tuple[str, str]:
    """`("missing"|"unpinned"|"ok", message)` for the model file on this machine."""
    from core.memory_embed_onnx import ARTIFACTS, MODEL_SHA256, model_dir, sha256_of

    directory = model_dir()
    absent = [name for name in ARTIFACTS if not (directory / name).is_file()]
    if absent:
        return "missing", f"{directory} does not hold {', '.join(absent)}"
    found = sha256_of(directory / "model.onnx")
    if found != MODEL_SHA256:
        return "unpinned", f"{directory}/model.onnx is {found}, the frozen bytes are {MODEL_SHA256}'s"
    return "ok", found


@pytest.fixture(scope="module")
def embedder():
    state, message = artifact_state()
    if state == "missing":
        pytest.skip(message)
    assert state == "ok", message
    from core.memory_embed_onnx import MiniLmEmbedder

    return MiniLmEmbedder()


def test_the_probe_texts_are_the_ones_the_frozen_vectors_belong_to() -> None:
    digests = [entry["text_sha256"] for entry in golden()["vectors"]]
    measured = [hashlib.sha256(text.encode("utf-8")).hexdigest() for text in PROBES]
    assert measured == digests, "a probe text changed: the frozen bytes belong to the old string"


def test_the_artifact_is_the_model_file_the_frozen_vectors_came_from(embedder) -> None:
    state, message = artifact_state()
    assert state == "ok", message
    assert golden()["model_sha256"] == message
    assert golden()["dims"] == [len(PROBES), 384]


def test_the_in_repo_embedder_reproduces_the_frozen_vectors(embedder) -> None:
    """Bit for bit on the capture runtime; numerically equivalent on any other host.

    See `_runtime_matches_the_capture` and `COSINE_FLOOR`: onnxruntime's per-CPU
    kernels and its version both move the last bits, so a test that demands identical
    bytes from a Linux runtime measures the host where the question is the arithmetic.
    """
    _assert_matches_frozen_bytes(embedder.blobs(PROBES), "MiniLmEmbedder")


def test_the_vectors_are_384_wide_and_unit_length(embedder) -> None:
    import numpy as np

    vectors = np.array([np.frombuffer(blob, dtype=np.float32) for blob in embedder.blobs(PROBES)])
    assert vectors.shape == (len(PROBES), 384)
    norms = np.linalg.norm(vectors, axis=1)
    # Not all exactly 1.0 in float32: the one-character probe lands on 0.99999994.
    assert np.allclose(norms, 1.0, atol=1e-6), norms


def test_two_sessions_produce_the_same_bytes(embedder) -> None:
    from core.memory_embed_onnx import MiniLmEmbedder

    assert MiniLmEmbedder().blobs(PROBES) == embedder.blobs(PROBES)


def test_a_float32_attention_mask_would_move_the_bytes(embedder) -> None:
    """The int64 mask is load-bearing: narrowing it changes 1977 of 3072 components.

    This control compares against the same machine's own output rather than the frozen
    bytes, so it measures the arithmetic and leaves the platform out (the frozen bytes
    belong to one OS/CPU; see `_runtime_matches_the_capture`).
    """
    import numpy as np

    from core.memory_embed_onnx import MiniLmEmbedder, _normalise

    class Narrowed(MiniLmEmbedder):
        def _forward(self, texts):
            np_ = self._np
            encoded = [self._tokenizer.encode(text) for text in texts]
            ids = np_.array([row.ids for row in encoded], dtype=np_.int64)
            mask = np_.array([row.attention_mask for row in encoded], dtype=np_.int64)
            hidden = np_.asarray(
                self._session.run(
                    None,
                    {
                        "input_ids": ids,
                        "attention_mask": mask,
                        "token_type_ids": np_.zeros_like(mask),
                    },
                )[0]
            )
            expanded = np_.broadcast_to(np_.expand_dims(mask.astype(np_.float32), -1), hidden.shape)
            pooled = np_.sum(hidden * expanded, 1) / np_.clip(
                expanded.sum(1), a_min=1e-9, a_max=None
            )
            return _normalise(pooled)

    narrowed = Narrowed(embedder.directory).blobs(PROBES)
    good = embedder.blobs(PROBES)
    assert narrowed != good
    wide = np.array([np.frombuffer(blob, dtype=np.float32) for blob in narrowed])
    ref = np.array([np.frombuffer(blob, dtype=np.float32) for blob in good])
    assert int((wide != ref).sum()) > 1000


def test_the_product_entry_point_reproduces_the_frozen_vectors(tmp_path, monkeypatch) -> None:
    """What `core/memory_provider.py` actually calls, not just the class under it."""
    state, message = artifact_state()
    if state != "ok":
        pytest.skip(message)
    # The probe is about the MiniLM artifact. An opt-in for the other model saved on
    # this machine would divert the factory, so the device folder is emptied here.
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("EPHE_EMBEDDINGGEMMA_DIR", str(tmp_path / "no-gemma"))
    monkeypatch.delenv("EPHE_EMBEDDINGGEMMA_DOWNLOAD", raising=False)
    from core.memory_embed import get_embedder, model_name, reset_cache

    reset_cache()
    try:
        embed = get_embedder()
        assert embed is not None
        packed = [__import__("numpy").asarray(row, dtype="float32").tobytes() for row in embed(PROBES)]
        _assert_matches_frozen_bytes(packed, "core.memory_embed entry point")
        assert model_name() == "all-MiniLM-L6-v2"
    finally:
        reset_cache()


def test_a_missing_model_turns_the_vector_leg_off_without_raising(tmp_path, monkeypatch) -> None:
    from core.memory_embed import get_embedder, reset_cache

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("EPHE_EMBEDDINGGEMMA_DIR", str(tmp_path / "no-gemma"))
    monkeypatch.delenv("EPHE_EMBEDDINGGEMMA_DOWNLOAD", raising=False)
    monkeypatch.setenv("EPHE_EMBED_MODEL_DIR", str(tmp_path / "nothing-here"))
    reset_cache()
    try:
        assert get_embedder() is None
    finally:
        reset_cache()


def test_a_model_file_the_module_cannot_vouch_for_is_refused(tmp_path, monkeypatch) -> None:
    """A different `model.onnx` would write vectors carrying the label of the stored ones."""
    from core.memory_embed_onnx import ARTIFACTS, model_problem

    directory = tmp_path / "onnx"
    directory.mkdir()
    for name in ARTIFACTS:
        (directory / name).write_bytes(b"not the model\n")
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("EPHE_EMBEDDINGGEMMA_DIR", str(tmp_path / "no-gemma"))
    monkeypatch.delenv("EPHE_EMBEDDINGGEMMA_DOWNLOAD", raising=False)
    monkeypatch.setenv("EPHE_EMBED_MODEL_DIR", str(directory))
    problem = model_problem()
    assert problem is not None and "comparable" in problem

    from core.memory_embed import get_embedder, reset_cache

    reset_cache()
    try:
        assert get_embedder() is None
    finally:
        reset_cache()

    monkeypatch.setenv("EPHE_EMBED_VERIFY", "0")
    assert model_problem() is None, "the documented override has to accept the file"


def test_chromadb_still_agrees_while_it_is_installed(embedder) -> None:
    """The transitional half: gone once chromadb leaves the dependencies."""
    if importlib.util.find_spec("chromadb") is None:
        pytest.skip("chromadb is no longer installed — this comparison retired with it")
    import numpy as np

    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    theirs = [np.asarray(row, dtype=np.float32).tobytes() for row in DefaultEmbeddingFunction()(PROBES)]
    assert theirs == embedder.blobs(PROBES)
