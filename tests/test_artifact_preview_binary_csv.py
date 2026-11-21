"""Task #80 — binary files are refused, CSV is parsed with the csv module.

The preview renderer used to turn binary files into mojibake (`errors="replace"`) and
parse CSV with a naive `line.split(",")` which breaks on quoted fields, embedded commas,
and newlines. The lane already renders CSV as a table with its bytes, so these tests pin
a correctness fix to an existing surface.

Binary detection uses the classic null-byte heuristic: read the first 8KB and check for
`\\x00`. Images, PDFs and compiled code contain null bytes, so the preview refuses them
with `mode: "none", reason: "binary-file"`. The zip-container office formats (xlsx, docx,
pptx) are exempt because their own renderer reads their bytes on purpose.

CSV parsing uses the stdlib `csv` module which handles RFC 4180 correctly: quoted fields,
embedded commas, embedded newlines, and escaped quotes (`""` inside a quoted field).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestBinaryFileRefusal:
    """A binary file answers with a refusal and the card never draws mojibake."""

    def test_a_binary_file_answers_mode_none_with_reason(self, tmp_path):
        """GIVEN a PNG image
        WHEN preview_payload
        THEN mode=none, reason=binary-file."""
        from core.artifact_preview import preview_payload

        p = tmp_path / "photo.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        result = preview_payload(p, "png")
        assert result["mode"] == "none"
        assert result["reason"] == "binary-file"

    def test_a_pdf_answers_mode_none_not_mojibake(self, tmp_path):
        """GIVEN a PDF
        WHEN preview_payload
        THEN mode=none with a refusal reason the card can read."""
        from core.artifact_preview import preview_payload

        p = tmp_path / "doc.pdf"
        p.write_bytes(b"%PDF-1.4\n" + b"\x00\x01\x02" * 50)
        result = preview_payload(p, "pdf")
        assert result["mode"] == "none"

    def test_a_text_file_still_comes_back_as_text(self, tmp_path):
        """GIVEN a .txt
        WHEN preview_payload
        THEN mode=text (regression guard)."""
        from core.artifact_preview import preview_payload

        p = tmp_path / "notes.txt"
        p.write_text("Hello world", encoding="utf-8")
        result = preview_payload(p, "txt")
        assert result["mode"] == "text"
        assert "Hello world" in result["text"]


class TestCsvParsing:
    """CSV goes through the stdlib csv module, so quoted fields survive."""

    def test_a_csv_with_quoted_commas_parses_correctly(self, tmp_path):
        """GIVEN 'a,\"b,c\",d'
        WHEN preview_payload
        THEN header has 3 cells where a naive split would answer 4."""
        from core.artifact_preview import preview_payload

        p = tmp_path / "data.csv"
        p.write_text('name,value,note\n"Smith, John",42,"a, b"\n', encoding="utf-8")
        result = preview_payload(p, "csv")
        assert result["mode"] == "table"
        assert result["header"] == ["name", "value", "note"]
        assert result["rows"] == [["Smith, John", "42", "a, b"]]

    def test_a_csv_with_embedded_newlines_parses_correctly(self, tmp_path):
        """GIVEN a field with \\n inside quotes
        WHEN preview_payload
        THEN it stays one cell."""
        from core.artifact_preview import preview_payload

        p = tmp_path / "multi.csv"
        p.write_text('col\n"line1\nline2"\n', encoding="utf-8")
        result = preview_payload(p, "csv")
        assert result["mode"] == "table"
        assert result["header"] == ["col"]
        assert result["rows"] == [["line1\nline2"]]

    def test_a_csv_with_quoted_quotes_parses_correctly(self, tmp_path):
        """GIVEN 'a,"b""c",d'
        WHEN preview_payload
        THEN the middle cell is 'b"c'."""
        from core.artifact_preview import preview_payload

        p = tmp_path / "escaped.csv"
        p.write_text('a,b,c\n1,"he said ""hi""",3\n', encoding="utf-8")
        result = preview_payload(p, "csv")
        assert result["rows"] == [["1", 'he said "hi"', "3"]]

    def test_a_csv_respects_max_rows(self, tmp_path):
        """GIVEN 100 rows
        WHEN preview_payload
        THEN truncated=True at MAX_ROWS."""
        from core.artifact_preview import MAX_ROWS, preview_payload

        p = tmp_path / "big.csv"
        lines = ["col"] + [str(i) for i in range(MAX_ROWS + 10)]
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = preview_payload(p, "csv")
        assert result["truncated"] is True
