"""
◑ Ephe – Artifact Detector
Detects code blocks and other structured content in LLM output
and wraps them as artifacts (like the artifact panel of leading AI clients).

Specified through TDD in tests/test_artifact_detector.py
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum


# Types

class ArtifactType(str, Enum):
    CODE_PYTHON = "code_python"
    CODE_BASH   = "code_bash"
    CODE_JS     = "code_js"
    CODE_TS     = "code_typescript"
    CODE_RUST   = "code_rust"
    CODE_GO     = "code_go"
    CODE_SQL    = "code_sql"
    CODE_OTHER  = "code_other"
    HTML        = "html"
    SVG         = "svg"
    MARKDOWN    = "markdown"
    JSON        = "json"
    YAML        = "yaml"
    DIFF        = "diff"


# Minimum lines (~5 code lines) needed before an artifact is created
ARTIFACT_LINE_THRESHOLD = 5

# Mapping: language → ArtifactType
_LANG_MAP = {
    "python":     ArtifactType.CODE_PYTHON,
    "py":         ArtifactType.CODE_PYTHON,
    "bash":       ArtifactType.CODE_BASH,
    "sh":         ArtifactType.CODE_BASH,
    "shell":      ArtifactType.CODE_BASH,
    "javascript": ArtifactType.CODE_JS,
    "js":         ArtifactType.CODE_JS,
    "typescript": ArtifactType.CODE_TS,
    "ts":         ArtifactType.CODE_TS,
    "rust":       ArtifactType.CODE_RUST,
    "go":         ArtifactType.CODE_GO,
    "sql":        ArtifactType.CODE_SQL,
    "html":       ArtifactType.HTML,
    "svg":        ArtifactType.SVG,
    "json":       ArtifactType.JSON,
    "yaml":       ArtifactType.YAML,
    "yml":        ArtifactType.YAML,
    "diff":       ArtifactType.DIFF,
    "patch":      ArtifactType.DIFF,
    "markdown":   ArtifactType.MARKDOWN,
    "md":         ArtifactType.MARKDOWN,
}

# Sensible default file names per type
_DEFAULT_FILENAMES = {
    ArtifactType.CODE_PYTHON: "script.py",
    ArtifactType.CODE_BASH:   "script.sh",
    ArtifactType.CODE_JS:     "script.js",
    ArtifactType.CODE_TS:     "script.ts",
    ArtifactType.CODE_RUST:   "main.rs",
    ArtifactType.CODE_GO:     "main.go",
    ArtifactType.CODE_SQL:    "query.sql",
    ArtifactType.CODE_OTHER:  "code.txt",
    ArtifactType.HTML:        "page.html",
    ArtifactType.SVG:         "image.svg",
    ArtifactType.MARKDOWN:    "document.md",
    ArtifactType.JSON:        "data.json",
    ArtifactType.YAML:        "config.yaml",
    ArtifactType.DIFF:        "changes.diff",
}


# Artifact Dataclass

@dataclass
class Artifact:
    artifact_type: ArtifactType
    content:       str
    language:      str
    title:         str
    filename:      str
    id:            str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict:
        return {
            "id":            self.id,
            "artifact_type": self.artifact_type.value,
            "content":       self.content,
            "language":      self.language,
            "title":         self.title,
            "filename":      self.filename,
        }


def looks_like_ask_payload(artifact: Artifact) -> bool:
    """Is this JSON block the turn's own question rather than a file?

    An answer that explains an `ask_user` call can echo the payload as a fenced
    JSON block; the reader then showed a `data.json` artifact card for a file
    that was never written (QA-0.1.11, F6). Only the two keys that mark a
    question count, so an ordinary JSON artifact stays what it is.
    """
    if artifact.artifact_type is not ArtifactType.JSON:
        return False
    try:
        data = json.loads(artifact.content)
    except (TypeError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    return "question" in data or "options" in data


# ArtifactDetector

# Regex for Markdown code fences: ```lang\n...\n```
_FENCE_RE = re.compile(
    r"```(?P<lang>[a-zA-Z0-9+\-#]*)\n(?P<code>.*?)```",
    re.DOTALL
)


class ArtifactDetector:
    """
    Detects artifacts in a finished or partial LLM answer.
    Returns the artifacts and delivers the cleaned chat text (without code).
    """

    def detect(self, text: str) -> list[Artifact]:
        """
        Returns every artifact with ≥ ARTIFACT_LINE_THRESHOLD lines.
        Short inline blocks (```short```) are ignored.
        """
        artifacts: list[Artifact] = []
        for m in _FENCE_RE.finditer(text):
            lang = m.group("lang").strip().lower()
            code = m.group("code")

            # Ignore blocks that are too short
            code_lines = [l for l in code.split("\n") if l.strip()]
            if len(code_lines) < ARTIFACT_LINE_THRESHOLD:
                continue

            artifact_type = _LANG_MAP.get(lang, ArtifactType.CODE_OTHER)
            filename      = _DEFAULT_FILENAMES.get(artifact_type, "code.txt")
            title         = self._generate_title(code, artifact_type, filename)

            artifacts.append(Artifact(
                artifact_type = artifact_type,
                content       = code.rstrip(),
                language      = lang or "text",
                title         = title,
                filename      = filename,
            ))

        return artifacts

    def extract_text(self, text: str) -> str:
        """
        Returns the chat text without the large code blocks.
        Blocks ≥ threshold are removed completely — the artifact itself is
        delivered as an SSE 'artifact' event and rendered inline by the UI
        (no more fake placeholder text, which used to make the code unreachable).
        """
        def replace_block(m: re.Match) -> str:
            m.group("lang").strip().lower()
            code = m.group("code")
            code_lines = [l for l in code.split("\n") if l.strip()]

            if len(code_lines) < ARTIFACT_LINE_THRESHOLD:
                return m.group(0)  # Leave short blocks unchanged

            return ""  # The artifact event takes over the rendering

        return _FENCE_RE.sub(replace_block, text).strip()

    def split(self, text: str) -> list[dict]:
        """
        Returns an ordered list of {"type": "text"|"artifact", "content": ...}.
        Useful for step-by-step streaming.
        """
        result: list[dict] = []
        last_end = 0

        for m in _FENCE_RE.finditer(text):
            lang = m.group("lang").strip().lower()
            code = m.group("code")
            code_lines = [l for l in code.split("\n") if l.strip()]

            # Text before the block
            before = text[last_end:m.start()].strip()
            if before:
                result.append({"type": "text", "content": before})

            if len(code_lines) >= ARTIFACT_LINE_THRESHOLD:
                artifact_type = _LANG_MAP.get(lang, ArtifactType.CODE_OTHER)
                filename      = _DEFAULT_FILENAMES.get(artifact_type, "code.txt")
                result.append({
                    "type":     "artifact",
                    "artifact": Artifact(
                        artifact_type = artifact_type,
                        content       = code.rstrip(),
                        language      = lang or "text",
                        title         = self._generate_title(code, artifact_type, filename),
                        filename      = filename,
                    ).to_dict()
                })
            else:
                # Emit short blocks as text
                result.append({"type": "text", "content": m.group(0)})

            last_end = m.end()

        # Remaining text after the last block
        after = text[last_end:].strip()
        if after:
            result.append({"type": "text", "content": after})

        return result

    # Internal

    def _generate_title(
        self,
        code:          str,
        artifact_type: ArtifactType,
        filename:      str,
    ) -> str:
        """Tries to extract a sensible title from the code content."""
        first_lines = [l.strip() for l in code.split("\n") if l.strip()][:5]

        # Python: first def or class
        for line in first_lines:
            if line.startswith("def ") or line.startswith("class "):
                name = line.split("(")[0].split(" ")[1]
                return f"{name}() — {filename}"
            if line.startswith("# "):
                return line[2:].strip()

        # HTML: <title>
        title_match = re.search(r"<title>(.*?)</title>", code, re.IGNORECASE)
        if title_match:
            return title_match.group(1).strip()

        # Fallback: file name
        return filename
