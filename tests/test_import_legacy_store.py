"""M4 — the importer that carries an old store into Kepta after the package left.

The subject is a shape rather than a user's data: the fixture builds a synthetic directory
with the same three collections an installed Ephe wrote, including a workspace store that
sits inside the root store's folder. No test here needs a real store, and the ones that
need the reading package say so with `importorskip`; the pure half (space, gate, naming)
runs in a venv where that package is gone, which is the state this change moves toward.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "import_legacy_store.py"
LEGACY_NAME = "mimi_nox_memory"  # gate:legacy
WORKSPACE_HASH = "0123456789abcdef"
VISION_COORDINATES = {"last_known_x": 412, "last_known_y": 260, "raw_target": "Save button"}
CROP = "iVBORw0KGgoAAAANSUhEUg=="
SOURCE_VECTORS = 9


def load_module():
    """The script as a module, so its pure half runs without a subprocess."""
    spec = importlib.util.spec_from_file_location("import_legacy_store_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unit_vector(slot: int, dimension: int = 384) -> list[float]:
    """A vector of length 1, the property the L2-to-cosine conversion rests on."""
    vector = [0.0] * dimension
    vector[slot % dimension] = 1.0
    return vector


def long_vector(slot: int, dimension: int = 384) -> list[float]:
    """The same shape at length 2, so a conversion has to be refused."""
    vector = [0.0] * dimension
    vector[slot % dimension] = 2.0
    return vector


def seed(root: Path, *, vision_vectors=None) -> None:
    """Writes the directory an older install left: root collections plus one workspace."""
    chromadb = pytest.importorskip("chromadb")
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    root.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(root))
    memory = client.get_or_create_collection(LEGACY_NAME, metadata={"hnsw:space": "cosine"})
    memory.add(
        ids=["legacy-1", "mig:legacy-2", "legacy-empty"],
        documents=[
            "The user prefers the Black Forest for holidays",
            "The API gateway runs on port 8765",
            "   ",
        ],
        metadatas=[
            {"source": "auto_memory", "priority": "high", "timestamp": 1700000000.0, "hits": 4},
            {"source": "agent", "timestamp": 1700000100.0, "hits": 1},
            {"source": "agent"},
        ],
        embeddings=[unit_vector(1), unit_vector(2), unit_vector(3)],
    )
    vision = client.get_or_create_collection("vision_rules")
    vision.add(
        ids=["vision-1"],
        documents=["Appearance and position of Save button in the current context."],
        metadatas=[{"base64_crop": CROP, **VISION_COORDINATES}],
        embeddings=[(vision_vectors or unit_vector)(4)],
    )
    other = client.get_or_create_collection("another_tool_notes")
    other.add(ids=["other-1"], documents=["Something else entirely"],
              embeddings=[unit_vector(5)])
    workspace = chromadb.PersistentClient(path=str(root / WORKSPACE_HASH))
    scoped = workspace.get_or_create_collection(f"ephe_memory_{WORKSPACE_HASH}",
                                                metadata={"hnsw:space": "cosine"})
    scoped.add(
        ids=["ws-1", "ws-2"],
        documents=["The office is in Bad Liebenzell", "The sprint ends on Friday"],
        metadatas=[{"source": "auto_memory"}, {"source": "agent"}],
        embeddings=[unit_vector(6), unit_vector(7)],
    )
    # The install this was measured on keeps the old-prefix bucket beside the new one in
    # the same workspace store, one of its rows restating a fact the new bucket holds.
    legacy_scoped = workspace.get_or_create_collection(
        f"{LEGACY_NAME}_{WORKSPACE_HASH}", metadata={"hnsw:space": "cosine"})
    legacy_scoped.add(
        ids=["legacy-ws-1", "legacy-ws-2"],
        documents=["The office is in Bad Liebenzell", "The standup is at nine"],
        metadatas=[{"source": "auto_memory"}, {"source": "agent"}],
        embeddings=[unit_vector(8), unit_vector(9)],
    )


def run_importer(tmp_path: Path, source: Path, *extra: str, **env_extra: str):
    env = dict(os.environ)
    env.update({
        "EPHE_CONFIG_DIR": str(tmp_path / "config"),
        "EPHE_MEMORY_EMBEDDER": "none",
        "EPHE_OFFLINE": "1",
        "ANONYMIZED_TELEMETRY": "False",
    })
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--source", str(source),
         "--target-root", str(tmp_path / "kepta"), *extra],
        capture_output=True, text=True, cwd=REPO, env=env, timeout=300,
    )


def rows(db_path: Path) -> list[dict]:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(
            "SELECT id, content, metadata, created_at FROM memories ORDER BY id")]
    finally:
        connection.close()


def meta_value(db_path: Path, key: str):
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        connection.close()


def embedded_chunks(db_path: Path) -> int:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return connection.execute(
            "SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL").fetchone()[0]
    finally:
        connection.close()


def db(tmp_path: Path, scope: str) -> Path:
    return tmp_path / "kepta" / f"kepta_{scope}.db"


@pytest.fixture()
def source(tmp_path):
    root = tmp_path / "chroma_db"
    seed(root)
    return root


# The pure half — a venv without the reading package still runs all of this


def test_the_module_loads_without_the_reading_package():
    """The package is imported inside the reader, so importing this file stays possible."""
    probe = (
        "import importlib.util, sys;"
        f"spec = importlib.util.spec_from_file_location('m', r'{SCRIPT}');"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m);"
        "print('chromadb' in sys.modules)"
    )
    done = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                          cwd=REPO, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip() == "False", "the module must not pull the package in"


def test_classify_reads_the_legacy_vocabulary():
    module = load_module()
    assert module.classify(LEGACY_NAME)[0] == "memory"
    assert module.classify(f"{LEGACY_NAME}_archive")[0] == "memory"
    assert module.classify(f"ephe_memory_{WORKSPACE_HASH}")[0] == "memory"
    assert module.classify("vision_rules")[0] == "vision"
    assert module.classify("someones_notes")[0] == "unknown"


def test_classify_gives_a_workspace_its_hash_and_a_global_bucket_its_name():
    module = load_module()
    assert module.classify(f"ephe_memory_{WORKSPACE_HASH}")[1] == WORKSPACE_HASH
    assert module.classify(f"{LEGACY_NAME}_{WORKSPACE_HASH}")[1] == WORKSPACE_HASH
    assert module.classify(LEGACY_NAME)[1] == LEGACY_NAME
    assert module.classify("vision_rules")[1] == "vision_rules"
    assert module.classify(LEGACY_NAME, "chosen")[1] == "chosen"


def test_classify_keeps_the_old_prefix_bucket_out_of_its_own_scope():
    """The measured install holds both prefixes in one workspace store; they are one
    workspace, so the old-prefix bucket must not become a scope of its own."""
    module = load_module()
    kind, scope = module.classify(f"{LEGACY_NAME}_{WORKSPACE_HASH}")
    assert kind == "memory"
    assert scope != f"{LEGACY_NAME}_{WORKSPACE_HASH}"


def test_equivalent_gate_restates_an_l2_radius_for_unit_vectors():
    module = load_module()
    assert module.equivalent_gate(1.2, "l2", unit_norm=True) == ("cosine", 0.28)
    assert module.equivalent_gate(0.0, "l2", unit_norm=True) == ("cosine", 1.0)
    assert module.equivalent_gate(0.08, "cosine", unit_norm=False) == ("cosine", 0.08)


def test_equivalent_gate_refuses_a_number_it_cannot_carry():
    """A loose vector or an inner-product index has no cosine floor, so none is invented."""
    module = load_module()
    assert module.equivalent_gate(1.2, "l2", unit_norm=False) is None
    assert module.equivalent_gate(1.2, "ip", unit_norm=True) is None


def test_gate_for_keeps_the_metric_of_the_vision_boundary():
    module = load_module()
    carried = module.gate_for("vision_rules", "l2", unit_norm=True)
    assert carried["source"] == {"distance": 1.2, "space": "l2",
                                 "origin": "core/vision_memory.py LEGACY_L2_RADIUS"}
    assert carried["target"] == {"metric": "cosine", "threshold": 0.28}
    refused = module.gate_for("vision_rules", "l2", unit_norm=False)
    assert refused["target"] is None and "unit-norm" in refused["reason"]
    assert module.gate_for(LEGACY_NAME, "cosine", unit_norm=True) is None


# The importer against a synthetic directory


def test_every_row_arrives_under_its_own_id_with_its_metadata(source, tmp_path):
    done = run_importer(tmp_path, source)
    assert done.returncode == 0, done.stderr[-3000:]
    written = {row["id"]: row for row in rows(db(tmp_path, LEGACY_NAME))}
    assert set(written) == {"legacy-1", "mig:legacy-2"}, written
    assert "auto_memory" in written["legacy-1"]["metadata"]
    assert written["legacy-1"]["created_at"] == 1700000000.0, "the original timestamp travels"

    assert {row["id"] for row in rows(db(tmp_path, WORKSPACE_HASH))} == {
        "ws-1", "ws-2", "legacy-ws-2"}
    assert not db(tmp_path, f"{LEGACY_NAME}_{WORKSPACE_HASH}").exists(), (
        "the old-prefix bucket is the same workspace, not a scope of its own")

    vision = rows(db(tmp_path, "vision_rules"))
    assert [row["id"] for row in vision] == ["vision-1"]
    carried = json.loads(vision[0]["metadata"])
    assert carried["base64_crop"] == CROP
    assert carried["last_known_x"] == VISION_COORDINATES["last_known_x"]
    assert carried["raw_target"] == VISION_COORDINATES["raw_target"]


def test_the_receipt_names_every_store_and_what_it_did(source, tmp_path):
    done = run_importer(tmp_path, source)
    assert done.returncode == 0, done.stderr[-3000:]
    receipt = done.stdout
    for name in (LEGACY_NAME, "vision_rules", "another_tool_notes",
                 f"ephe_memory_{WORKSPACE_HASH}"):
        assert name in receipt, receipt
    assert "1 no text" in receipt, receipt
    assert "not an Ephe collection" in receipt, receipt
    assert "1 merged into one fact" in receipt, receipt
    assert "read-only" in receipt, receipt
    assert "9 row(s) read, 6 written" in receipt, receipt


def test_the_vision_radius_crosses_with_its_metric_and_is_recorded(source, tmp_path):
    done = run_importer(tmp_path, source)
    assert done.returncode == 0, done.stderr[-3000:]
    assert "l2 distance <= 1.2 (core/vision_memory.py LEGACY_L2_RADIUS)" in done.stdout
    assert "cosine >= 0.28" in done.stdout
    recorded = meta_value(db(tmp_path, "vision_rules"), "chroma_import")
    assert recorded["target"] == {"metric": "cosine", "threshold": 0.28}
    assert recorded["source"]["space"] == "l2" and recorded["rows"] == 1
    assert "1.2" not in json.dumps(recorded["target"]), "the radius must not cross as written"


def test_a_loose_vector_store_refuses_the_conversion(tmp_path):
    root = tmp_path / "chroma_db"
    seed(root, vision_vectors=long_vector)
    done = run_importer(tmp_path, root)
    assert done.returncode == 0, done.stderr[-3000:]
    assert "cosine >= 0.28" not in done.stdout, "no number may be invented"
    assert "no conversion" in done.stdout
    recorded = meta_value(db(tmp_path, "vision_rules"), "chroma_import")
    assert recorded["target"] is None
    assert "cosine equivalent" in recorded["reason"]


def test_the_source_keeps_its_rows_and_is_reported_as_untouched(source, tmp_path):
    done = run_importer(tmp_path, source)
    assert done.returncode == 0, done.stderr[-3000:]
    assert source.is_dir(), "the importer is additive; the owner deletes the directory"
    assert "stored vectors before/after: 9 -> 9 (nothing removed)" in done.stdout

    chromadb = pytest.importorskip("chromadb")
    client = chromadb.PersistentClient(path=str(source))
    assert client.get_collection(LEGACY_NAME).count() == 3, "the source still holds its data"
    assert (source / WORKSPACE_HASH).is_dir()


def test_an_unknown_collection_is_reported_and_only_taken_on_request(source, tmp_path):
    first = run_importer(tmp_path, source)
    assert "not an Ephe collection" in first.stdout
    assert not db(tmp_path, "another_tool_notes").exists()

    second = run_importer(tmp_path, source, "--all")
    assert second.returncode == 0, second.stderr[-3000:]
    assert [row["id"] for row in rows(db(tmp_path, "another_tool_notes"))] == ["other-1"]


def test_a_second_run_reports_nothing_written_again(source, tmp_path):
    first = run_importer(tmp_path, source)
    assert first.returncode == 0, first.stderr[-3000:]
    assert "2 row(s) with their ids" in first.stdout, first.stdout
    count_after_first = len(rows(db(tmp_path, LEGACY_NAME)))

    second = run_importer(tmp_path, source)
    assert second.returncode == 0, second.stderr[-3000:]
    assert "9 row(s) read, 0 written" in second.stdout, second.stdout
    assert "2 already there" in second.stdout, second.stdout
    assert len(rows(db(tmp_path, LEGACY_NAME))) == count_after_first == 2
    assert len(rows(db(tmp_path, WORKSPACE_HASH))) == 3


def test_dry_run_reports_the_same_shape_and_writes_nothing(source, tmp_path):
    done = run_importer(tmp_path, source, "--dry-run")
    assert done.returncode == 0, done.stderr[-3000:]
    assert "read only (--dry-run)" in done.stdout
    assert LEGACY_NAME in done.stdout
    assert not (tmp_path / "kepta").exists(), "a dry run creates no memory root"


def test_the_target_is_searchable_when_the_vectorizer_is_available(source, tmp_path):
    """A vector store importer that lands text without vectors is a loss; assert the leg."""
    from core.memory_embed import get_embedder

    available = get_embedder() is not None
    done = run_importer(tmp_path, source, EPHE_MEMORY_EMBEDDER="")
    assert done.returncode == 0, done.stderr[-3000:]
    expected = 2 if available else 0
    assert f"{expected} embedded chunk(s)" in done.stdout, done.stdout
    assert embedded_chunks(db(tmp_path, LEGACY_NAME)) == expected


def test_the_model_switch_is_the_product_own_env_var(source, tmp_path):
    """No second switch: EPHE_MEMORY_EMBEDDER=none leaves the vector leg out and says so."""
    done = run_importer(tmp_path, source)
    assert done.returncode == 0, done.stderr[-3000:]
    assert "0 embedded chunk(s)" in done.stdout, done.stdout
    assert embedded_chunks(db(tmp_path, LEGACY_NAME)) == 0
