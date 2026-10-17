"""R34 Project Factory — tests for the verify_artifact evidence gate.

Hermetic: the allowed roots are patched onto tmp_path where
``core.tools.base`` resolves them, so no test reads or writes into
the real Downloads/Documents folders. Runs on the CI matrix (3.10–3.13):
only os/os.path primitives shared with the runtime build are used here.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import zipfile

import pytest

from core.tools import base as tools_base
from core.tools import verify_tools
from core.tools.verify_tools import _pdf_page_count, _verify, verify_artifact


def run(path, checks=None):
    return asyncio.run(verify_artifact(str(path), json.dumps(checks) if checks is not None else "{}"))


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    root = tmp_path / "artifacts"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tools_base, "_resolve_allowed_roots", lambda: [root])
    return root


def make_pdf(path, pages=2):
    """Handcrafted minimal PDF with N visible /Type /Page objects."""
    objs = []
    page_ids = [2 + i * 2 for i in range(pages)]
    body = []
    body.append(b"1 0 obj\n<< /Type /Catalog /Pages 100 0 R >>\nendobj\n")
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    body.append(f"100 0 obj\n<< /Type /Pages /Count {pages} /Kids [{kids}] >>\nendobj\n".encode())
    for pid in page_ids:
        body.append(f"{pid} 0 obj\n<< /Type /Page /Parent 100 0 R /MediaBox [0 0 595 842] >>\nendobj\n".encode())
        body.append(f"{pid + 1} 0 obj\n<< /Length 0 >>\nstream\n\nendstream\nendobj\n".encode())
    payload = b"%PDF-1.4\n" + b"".join(body) + b"%%EOF\n"
    path.write_bytes(payload)
    return path


def make_pptx(path, slides=3, empty_last=False):
    with zipfile.ZipFile(str(path), "w") as zf:
        for i in range(1, slides + 1):
            if empty_last and i == slides:
                zf.writestr(f"ppt/slides/slide{i}.xml", "<a:sld></a:sld>")
            else:
                zf.writestr(f"ppt/slides/slide{i}.xml",
                            f"<a:sld><a:t>Slide {i} with real substance</a:t></a:sld>")


def make_docx(path, paragraphs=20):
    runs = "".join(f"<w:p><w:r><w:t>section {i} filler words here</w:t></w:r></w:p>"
                   for i in range(paragraphs))
    with zipfile.ZipFile(str(path), "w") as zf:
        zf.writestr("word/document.xml", f"<w:doc>{runs}</w:doc>")


def make_xlsx(path, sheets=2, rows=12):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "data"
    for r in range(rows):
        ws.cell(row=r + 1, column=1, value=f"v{r}")
    for s in range(1, sheets):
        wb.create_sheet(f"extra{s}")["A1"] = "x"
    wb.save(str(path))


def make_project(root, with_readme=True, empty_file=False):
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    if with_readme:
        (root / "README.md").write_text("# Demo\n\nReal content.\n")
    (root / "src" / "main.py").write_text("def main():\n    return 1\n")
    (root / "tests" / "test_main.py").write_text("def test_ok():\n    assert True\n")
    (root / "pyproject.toml").write_text("[project]\nname = \"demo\"\n")
    if empty_file:
        (root / "notes.txt").write_text("")
    return root


class TestRegistration:
    def test_given_registry_when_resolved_then_verify_artifact_is_registered(self):
        from core.tools.registry import TOOL_MAP, get_tool_schemas

        assert "verify_artifact" in TOOL_MAP
        names = {s["function"]["name"] for s in get_tool_schemas()}
        assert "verify_artifact" in names

    def test_given_classification_when_checked_then_read_only(self):
        from core.tools.approval import classify_tool

        assert classify_tool("verify_artifact").is_mutating is False

    def test_given_package_when_imported_then_exported(self):
        import core.tools as tools_pkg

        assert hasattr(tools_pkg, "verify_artifact")


class TestPdfGate:
    def test_given_real_pdf_when_min_pages_met_then_verified(self, sandbox):
        out = run(make_pdf(sandbox / "doc.pdf", pages=2), {"min_pages": 2})
        assert out.startswith("ARTIFACT_VERIFIED")
        assert json.loads(out.split("ARTIFACT_VERIFIED: ", 1)[1])["metrics"]["pages"] >= 2

    def test_given_real_pdf_when_min_pages_unmet_then_failed(self, sandbox):
        out = run(make_pdf(sandbox / "doc.pdf", pages=2), {"min_pages": 5})
        assert out.startswith("ARTIFACT_FAILED")
        assert "min_pages" in out

    def test_given_fake_pdf_bytes_when_kind_pdf_then_failed(self, sandbox):
        p = sandbox / "fake.pdf"
        p.write_bytes(b"this is not a pdf" * 20)
        out = run(p, {"kind": "pdf"})
        assert out.startswith("ARTIFACT_FAILED")

    def test_given_byte_scan_fallback_when_parser_unavailable_then_counts_pages(self, tmp_path, monkeypatch):
        # Force the fallback path even where pypdfium2 exists (local runtime).
        import builtins

        real_import = builtins.__import__

        def blocked(name, *a, **kw):
            if name == "pypdfium2":
                raise ImportError("simulated: not installed (CI case)")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", blocked)
        pages = _pdf_page_count(str(make_pdf(tmp_path / "x.pdf", pages=3)))
        assert pages == 3


class TestOfficeGates:
    def test_given_pptx_when_slides_ok_then_verified(self, sandbox):
        make_pptx(sandbox / "deck.pptx", slides=4)
        out = run(sandbox / "deck.pptx", {"min_slides": 4})
        assert out.startswith("ARTIFACT_VERIFIED")

    def test_given_pptx_with_empty_slide_when_verified_then_failed(self, sandbox):
        make_pptx(sandbox / "deck.pptx", slides=3, empty_last=True)
        out = run(sandbox / "deck.pptx", {"min_slides": 3})
        assert out.startswith("ARTIFACT_FAILED")
        assert "empty" in out

    def test_given_pptx_when_below_min_slides_then_failed(self, sandbox):
        make_pptx(sandbox / "deck.pptx", slides=2)
        out = run(sandbox / "deck.pptx", {"min_slides": 6})
        assert "min_slides" in out and out.startswith("ARTIFACT_FAILED")

    def test_given_docx_when_word_count_ok_then_verified(self, sandbox):
        make_docx(sandbox / "report.docx", paragraphs=20)
        out = run(sandbox / "report.docx", {"min_words": 50})
        assert out.startswith("ARTIFACT_VERIFIED")

    def test_given_xlsx_when_sheets_and_rows_ok_then_verified(self, sandbox):
        make_xlsx(sandbox / "book.xlsx", sheets=2, rows=12)
        out = run(sandbox / "book.xlsx", {"min_sheets": 2, "min_rows": 10})
        assert out.startswith("ARTIFACT_VERIFIED")

    def test_given_xlsx_when_rows_below_min_then_failed(self, sandbox):
        make_xlsx(sandbox / "book.xlsx", sheets=1, rows=3)
        out = run(sandbox / "book.xlsx", {"min_rows": 50})
        assert out.startswith("ARTIFACT_FAILED")


class TestProjectGate:
    def test_given_complete_project_when_verified_then_passes(self, sandbox):
        make_project(sandbox / "proj")
        out = run(sandbox / "proj", {
            "kind": "project", "min_files": 4,
            "required_files": ["README.md", "src/main.py", "tests/test_main.py"],
        })
        assert out.startswith("ARTIFACT_VERIFIED")

    def test_given_project_with_missing_file_when_verified_then_failed(self, sandbox):
        make_project(sandbox / "proj")
        out = run(sandbox / "proj", {"kind": "project", "required_files": ["Dockerfile"]})
        assert out.startswith("ARTIFACT_FAILED")
        assert "Dockerfile" in out

    def test_given_project_with_empty_file_when_verified_then_failed(self, sandbox):
        make_project(sandbox / "proj", empty_file=True)
        out = run(sandbox / "proj", {"kind": "project", "min_files": 4})
        assert out.startswith("ARTIFACT_FAILED")
        assert "empty" in out

    def test_given_project_when_required_dir_exists_then_dir_prefix_matches(self, sandbox):
        make_project(sandbox / "proj")
        out = run(sandbox / "proj", {"kind": "project", "required_files": ["tests"]})
        assert out.startswith("ARTIFACT_VERIFIED")

    def test_given_project_when_ignores_caches(self, sandbox):
        make_project(sandbox / "proj")
        junk = sandbox / "proj" / "__pycache__"
        junk.mkdir(parents=True, exist_ok=True)
        (junk / "cache.pyc").write_bytes(b"junkjunkjunk")
        out = run(sandbox / "proj", {"kind": "project", "min_files": 5})
        # Only the 4 real files count; the __pycache__ entry must be excluded
        # (if it leaked, files would be 5 and the gate would wrongly verify).
        report = json.loads(out.split(": ", 1)[1])
        assert report["metrics"]["files"] == 4
        assert out.startswith("ARTIFACT_FAILED")


class TestSafetyAndEdges:
    def test_given_path_outside_allowed_roots_when_verified_then_failed(self, sandbox):
        out = run("/etc/hosts", {})
        assert out.startswith("ARTIFACT_FAILED")
        assert "outside allowed roots" in out

    def test_given_missing_path_when_verified_then_failed(self, sandbox):
        out = run(sandbox / "nope.pdf", {})
        assert "does not exist" in out

    def test_given_empty_file_when_verified_then_failed(self, sandbox):
        p = sandbox / "e.txt"
        p.write_text("")
        out = run(p, {})
        assert out.startswith("ARTIFACT_FAILED")
        assert "empty" in out

    def test_given_invalid_checks_json_when_verified_then_failed(self, sandbox):
        make_pdf(sandbox / "doc.pdf")
        out = asyncio.run(verify_artifact(str(sandbox / "doc.pdf"), "not-json"))
        assert out.startswith("ARTIFACT_FAILED")
        assert "checks" in out

    def test_given_plain_text_when_min_words_met_then_verified(self, sandbox):
        p = sandbox / "brief.md"
        p.write_text(" ".join(f"word{i}" for i in range(30)))
        out = run(p, {"min_words": 20})
        assert out.startswith("ARTIFACT_VERIFIED")

    def test_given_png_magic_when_kind_auto_then_image_verified(self, sandbox):
        p = sandbox / "pic.png"
        p.write_bytes(b"\x89PNG\x0d\x0a\x1a\x0a" + b"\x00" * 100)
        out = run(p, {})
        assert out.startswith("ARTIFACT_VERIFIED")
        assert '"kind": "image"' in out or '"kind":"image"' in out


class TestWorkspaceRelativeResolution:
    """I6 P3-7: write_file resolves relative paths against the active workspace
    (file_ops._resolve_against_workspace). verify_artifact must use the SAME
    base — the server process cwd is not the agent workspace, so the playbook
    flow write_file("ephe-demo/index.html") -> verify_artifact("ephe-demo")
    failed with 'Path does not exist' after every successful write."""

    def test_relative_project_resolves_against_workspace_not_cwd(self, tmp_path, monkeypatch):
        workspace = tmp_path / "workspace"
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        workspace.mkdir()
        project = workspace / "ephe-demo"
        project.mkdir()
        (project / "index.html").write_text("<html>" + "<p>content line</p>" * 20 + "</html>")
        (project / "README.md").write_text("# ephe demo\n" + "filler words here\n" * 20)
        monkeypatch.setattr(tools_base, "_resolve_allowed_roots", lambda: [workspace, elsewhere])
        import core.engine_config as engine_config
        monkeypatch.setattr(engine_config, "get_workspace_dir", lambda: str(workspace))
        monkeypatch.chdir(str(elsewhere))
        out = run("ephe-demo", {"kind": "project", "min_files": 2})
        assert out.startswith("ARTIFACT_VERIFIED"), out


class TestAllowedRootsAreReadWhereTheyAreUsed:
    """The roots are resolved per call; a snapshot taken at import would lie after a move."""

    def test_the_gate_holds_no_snapshot_of_the_roots(self):
        assert "ALLOWED_ROOTS" not in vars(verify_tools), (
            "an import-bound list is a snapshot: base resolves ALLOWED_ROOTS through "
            "core.tools.base.__getattr__ and this module has to ask it there"
        )

    def test_a_root_added_after_import_is_honoured(self, tmp_path, monkeypatch):
        """Given a root that appears after the module was imported; Then a path under it passes."""
        late = tmp_path / "late"
        late.mkdir()
        (late / "notes.txt").write_text("a short note\n", encoding="utf-8")

        monkeypatch.setattr(tools_base, "_resolve_allowed_roots", lambda: [late])

        out = run(late / "notes.txt", {"kind": "file", "min_words": 2})

        assert out.startswith("ARTIFACT_VERIFIED"), out
