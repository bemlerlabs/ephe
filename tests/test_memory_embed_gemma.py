"""EmbeddingGemma 2: the loader arithmetic, the consent gate, the label boundary.

The 542 MB artifact never appears here. A real `tokenizers` vocabulary plus a
`model.onnx` placeholder file stand in for the download, and the ONNX session is
replaced by a Gather over a fixed table that emits the sentence embedding — so
the Matryoshka truncation and the L2 normalisation the loader owns stay under
test, while the graph itself is a stand-in.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import memory_embed_gemma  # noqa: E402
from core.memory_embed_gemma import (  # noqa: E402
    EMBED_DIM,
    MODEL_HOST,
    MODEL_LABEL,
    MODEL_REPO,
    MODEL_SIZE_MB,
    NATIVE_DIM,
    EmbeddingGemmaEmbedder,
    EmbeddingGemmaNotAvailable,
    download_consent,
    ensure_model,
    model_present,
)

PAD_TOKEN = "<pad>"
VOCAB = {PAD_TOKEN: 0, "[UNK]": 1, "hello": 2, "world": 3, "gemma": 4, "ephe": 5}


def _write_tokenizer(path: Path) -> None:
    """A word-level vocabulary; the loader's own truncation and padding stay real."""
    from tokenizers import Tokenizer, models, pre_tokenizers

    tokenizer = Tokenizer(models.WordLevel(vocab=dict(VOCAB), unk_token="[UNK]"))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    tokenizer.save(str(path))


class _FakeSession:
    """A Gather over a fixed table stands in for the embedding graph."""

    def __init__(self, table: np.ndarray) -> None:
        self.table = table
        self.feeds: list[dict] = []

    def run(self, _outputs, feeds):
        self.feeds.append(dict(feeds))
        tokens = np.take(self.table, feeds["input_ids"], axis=0)  # [batch, seq, 768]
        mask = np.expand_dims(feeds["attention_mask"], -1)
        pooled = np.sum(tokens * mask, 1) / np.clip(mask.sum(1), a_min=1e-9, a_max=None)
        return [pooled]  # sentence_embedding: [batch, 768]


@pytest.fixture
def gemma_dir(tmp_path, monkeypatch):
    """A model directory holding a real tokenizer and a placeholder graph."""
    directory = tmp_path / "embeddinggemma-2"
    directory.mkdir()
    _write_tokenizer(directory / "tokenizer.json")
    (directory / "model.onnx").write_bytes(b"placeholder for the mocked session\n")
    table = np.random.default_rng(7).standard_normal((len(VOCAB), NATIVE_DIM)).astype(np.float32)
    monkeypatch.setattr(memory_embed_gemma, "open_session", lambda _path: _FakeSession(table))
    return directory, table


def _isolate(tmp_path, monkeypatch, *, model_dir: Path | None = None):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    (tmp_path / "cfg").mkdir(exist_ok=True)
    monkeypatch.delenv("EPHE_EMBEDDINGGEMMA_DOWNLOAD", raising=False)
    monkeypatch.delenv("EPHE_OFFLINE", raising=False)
    monkeypatch.delenv("EPHE_MEMORY_EMBEDDER", raising=False)
    monkeypatch.setenv("EPHE_EMBEDDINGGEMMA_DIR", str(model_dir or (tmp_path / "no-model")))


def test_the_two_vector_spaces_carry_their_own_labels() -> None:
    from core.memory_embed_onnx import MODEL_NAME

    assert MODEL_LABEL == "embeddinggemma-2"
    assert MODEL_LABEL != MODEL_NAME
    assert (NATIVE_DIM, EMBED_DIM) == (768, 256)


def test_the_embedder_keeps_the_matryoshka_prefix_and_normalises(gemma_dir) -> None:
    directory, table = gemma_dir
    embedder = EmbeddingGemmaEmbedder(directory)
    (vector,) = embedder.embed(["hello world"])
    # The masked rows are hello (2) and world (3); pads carry id 0 and mask 0.
    reference = table[[2, 3]].astype(np.float64).mean(0)[:EMBED_DIM]
    reference = reference / np.linalg.norm(reference)
    assert len(vector) == EMBED_DIM
    assert abs(float(np.linalg.norm(vector)) - 1.0) < 1e-5
    assert np.allclose(vector, reference, atol=1e-5)


def test_a_padded_row_pools_only_its_real_tokens(gemma_dir) -> None:
    directory, table = gemma_dir
    embedder = EmbeddingGemmaEmbedder(directory)
    (vector,) = embedder.embed(["gemma"])
    reference = table[4].astype(np.float64)[:EMBED_DIM]
    reference = reference / np.linalg.norm(reference)
    assert np.allclose(vector, reference, atol=1e-5)


def test_the_stored_blob_is_one_kilobyte_of_float32(gemma_dir) -> None:
    directory, _table = gemma_dir
    (blob,) = EmbeddingGemmaEmbedder(directory).blobs(["hello"])
    assert len(blob) == EMBED_DIM * 4
    assert np.frombuffer(blob, dtype=np.float32).shape == (EMBED_DIM,)


def test_a_full_width_call_returns_the_native_dimension(gemma_dir) -> None:
    directory, table = gemma_dir
    embedder = EmbeddingGemmaEmbedder(directory, dim=NATIVE_DIM)
    (vector,) = embedder.embed(["hello"])
    reference = table[2].astype(np.float64)
    reference = reference / np.linalg.norm(reference)
    assert len(vector) == NATIVE_DIM
    assert np.allclose(vector, reference, atol=1e-5)


def test_a_missing_model_without_consent_names_the_offer(tmp_path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(
        memory_embed_gemma, "_fetch",
        lambda *_a, **_k: pytest.fail("a fetch ran without consent"),
    )
    with pytest.raises(EmbeddingGemmaNotAvailable) as caught:
        ensure_model()
    message = str(caught.value)
    for token in (MODEL_REPO, MODEL_HOST, str(MODEL_SIZE_MB),
                  "EPHE_EMBEDDINGGEMMA_DOWNLOAD", "memory.embedder_allow_download"):
        assert token in message, token


def test_offline_outranks_the_download_switch(tmp_path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    monkeypatch.setenv("EPHE_EMBEDDINGGEMMA_DOWNLOAD", "1")
    monkeypatch.setattr(
        memory_embed_gemma, "_fetch",
        lambda *_a, **_k: pytest.fail("an offline process reached out"),
    )
    with pytest.raises(EmbeddingGemmaNotAvailable) as caught:
        ensure_model()
    assert "EPHE_OFFLINE" in str(caught.value)


def test_the_env_switch_fetches_into_the_device_folder(tmp_path, monkeypatch) -> None:
    target = tmp_path / "models" / MODEL_LABEL
    _isolate(tmp_path, monkeypatch, model_dir=target)
    monkeypatch.setenv("EPHE_EMBEDDINGGEMMA_DOWNLOAD", "1")
    calls: list[tuple[str, Path, tuple[str, ...]]] = []

    def fake_fetch(repo_id, directory, allow_patterns):
        calls.append((repo_id, Path(directory), tuple(allow_patterns)))
        Path(directory).mkdir(parents=True, exist_ok=True)
        _write_tokenizer(Path(directory) / "tokenizer.json")
        (Path(directory) / "model.onnx").write_bytes(b"downloaded\n")

    monkeypatch.setattr(memory_embed_gemma, "_fetch", fake_fetch)
    assert Path(ensure_model()) == target
    assert model_present()
    assert calls[0][0] == MODEL_REPO
    assert "onnx/model_fp16.onnx" in calls[0][2], "the fp16 graph has to be requested by its repo path"


def test_the_deep_setting_is_the_second_consent_spelling(tmp_path, monkeypatch) -> None:
    from core.settings_schema import save_deep_settings, validate_sections

    _isolate(tmp_path, monkeypatch)
    assert download_consent() is False

    def fake_fetch(repo_id, directory, allow_patterns):
        Path(directory).mkdir(parents=True, exist_ok=True)
        _write_tokenizer(Path(directory) / "tokenizer.json")
        (Path(directory) / "model.onnx").write_bytes(b"downloaded\n")

    monkeypatch.setattr(memory_embed_gemma, "_fetch", fake_fetch)
    written = validate_sections({"memory": {"memory.embedder_allow_download": True}})
    assert save_deep_settings(written), "the setting has to persist into the device folder"
    assert download_consent() is True
    assert Path(ensure_model()).exists()
    assert model_present(), "the agreed fetch leaves the artifact behind"


def test_default_falls_back_to_minilm_until_the_fetch_is_allowed(tmp_path, monkeypatch) -> None:
    from core import memory_embed

    _isolate(tmp_path, monkeypatch)
    memory_embed.reset_cache()
    try:
        assert memory_embed.effective_label() == "all-MiniLM-L6-v2"
        assert memory_embed.model_name() == "all-MiniLM-L6-v2"
    finally:
        memory_embed.reset_cache()


def test_a_local_model_is_chosen_without_any_consent(gemma_dir, tmp_path, monkeypatch) -> None:
    from core import memory_embed

    directory, _table = gemma_dir
    _isolate(tmp_path, monkeypatch, model_dir=directory)
    memory_embed.reset_cache()
    try:
        assert memory_embed.effective_label() == MODEL_LABEL
        embedder = memory_embed.get_embedder()
        assert isinstance(embedder, EmbeddingGemmaEmbedder)
        assert memory_embed.model_name() == MODEL_LABEL
        assert len(embedder(["hello world"])[0]) == EMBED_DIM
    finally:
        memory_embed.reset_cache()


def test_ranking_never_scores_one_space_against_the_other(tmp_path) -> None:
    from core.memory_kepta_ranking import leg_vector
    from core.memory_kepta_schema import to_blob

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        "CREATE TABLE memories (id TEXT, scope TEXT, deleted_at REAL);"
        "CREATE TABLE chunks (memory_id TEXT, seq INTEGER, text TEXT, "
        "embedding BLOB, embedding_model TEXT);"
    )
    db.execute("INSERT INTO memories (id, scope, deleted_at) VALUES ('m1', 's', NULL)")
    db.execute(
        "INSERT INTO chunks (memory_id, seq, text, embedding, embedding_model) VALUES (?,?,?,?,?)",
        ("m1", 0, "hello", to_blob([1.0, 0.0]), "all-MiniLM-L6-v2"),
    )
    active = {"m1": db.execute("SELECT * FROM memories WHERE id = 'm1'").fetchone()}
    embed = lambda _texts: [[1.0, 0.0]]  # noqa: E731 — the query vector of both spaces

    other = leg_vector(db, "s", "hello", active, embed_model=MODEL_LABEL, embed=embed)
    ours = leg_vector(db, "s", "hello", active, embed_model="all-MiniLM-L6-v2", embed=embed)
    assert other == [], "a MiniLM chunk must stay invisible to the other label"
    assert ours == ["m1"]


def test_the_provider_writes_the_label_of_the_loaded_model(gemma_dir, tmp_path, monkeypatch) -> None:
    from core import memory_embed
    from core.memory_provider import KEPTA, open_provider

    directory, _table = gemma_dir
    _isolate(tmp_path, monkeypatch, model_dir=directory)
    memory_embed.reset_cache()
    try:
        provider = open_provider(KEPTA, persist_dir=str(tmp_path / "store"), scope="s")
        assert provider._embed_model == MODEL_LABEL
        provider.store("hello world and a longer fact for the chunker", entities=["ephe"])
        row = provider._db.execute(
            "SELECT DISTINCT embedding_model AS model FROM chunks WHERE embedding IS NOT NULL"
        ).fetchone()
        assert row["model"] == MODEL_LABEL
    finally:
        memory_embed.reset_cache()
