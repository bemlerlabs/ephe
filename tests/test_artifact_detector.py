"""
TDD Suite: Artifact Detection
Given-When-Then in BDD style
"""
import pytest
from core.artifact_detector import ArtifactDetector, ArtifactType


# Fixtures

PYTHON_BLOCK = """Ein Beispielskript:

```python
import os

def list_files(path):
    for f in os.listdir(path):
        print(f)

list_files('/tmp')
```

Das war alles."""

INLINE_CODE = "Setze `foo = 1` in deiner config."

HTML_BLOCK = """Hier die Webseite:

```html
<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
  <h1>Hello World</h1>
  <p>Test Paragraph</p>
</body>
</html>
```
"""

SHORT_CODE = """Kurz:

```python
x = 1
```
"""

MULTIPLE_BLOCKS = (
    "Erst Python:\n\n"
    "```python\n"
    "def foo():\n"
    "    # Returns the answer to life\n"
    "    answer = 42\n"
    "    print(f'Answer: {answer}')\n"
    "    return answer\n"
    "\n"
    "result = foo()\n"
    "print(result)\n"
    "```\n\n"
    "Dann Bash:\n\n"
    "```bash\n"
    "echo 'Hello from Ephe'\n"
    "ls -la /tmp\n"
    "cat ~/.bashrc\n"
    "grep -r 'foo' .\n"
    "find . -name '*.py' | head -10\n"
    "```\n"
)


# Test Suite 1: Type Detection

class TestArtifactTypeDetection:

    def test_python_block_recognized(self):
        """Given: an answer with a Python block of ≥5 lines When: detector.detect() Then: the type is CODE_PYTHON"""
        detector = ArtifactDetector()
        artifacts = detector.detect(PYTHON_BLOCK)
        assert len(artifacts) == 1
        assert artifacts[0].artifact_type == ArtifactType.CODE_PYTHON

    def test_html_block_recognized(self):
        """Given: an HTML block When: detect() Then: the type is HTML"""
        detector = ArtifactDetector()
        artifacts = detector.detect(HTML_BLOCK)
        assert len(artifacts) == 1
        assert artifacts[0].artifact_type == ArtifactType.HTML

    def test_multiple_blocks_detected(self):
        """Given: two code blocks in one answer Then: two artifacts"""
        detector = ArtifactDetector()
        artifacts = detector.detect(MULTIPLE_BLOCKS)
        assert len(artifacts) == 2

    def test_inline_code_not_artifact(self):
        """Given: an inline code span When: detect() Then: no artifact (too short)"""
        detector = ArtifactDetector()
        artifacts = detector.detect(INLINE_CODE)
        assert len(artifacts) == 0

    def test_short_code_below_threshold(self):
        """Given: a code block with <5 lines Then: no artifact"""
        detector = ArtifactDetector()
        artifacts = detector.detect(SHORT_CODE)
        assert len(artifacts) == 0


# Test Suite 2: Artifact Metadata

class TestArtifactMetadata:

    def test_artifact_has_title(self):
        """Given: a Python block Then: the artifact has an automatically generated title"""
        artifacts = ArtifactDetector().detect(PYTHON_BLOCK)
        assert artifacts[0].title
        assert isinstance(artifacts[0].title, str)

    def test_artifact_has_content(self):
        """Given: a Python block Then: Artifact.content holds the code without ```-fences"""
        artifacts = ArtifactDetector().detect(PYTHON_BLOCK)
        content = artifacts[0].content
        assert '```' not in content
        assert 'def list_files' in content

    def test_artifact_has_language(self):
        """Given: a ```python block Then: artifact.language == 'python'"""
        artifacts = ArtifactDetector().detect(PYTHON_BLOCK)
        assert artifacts[0].language == 'python'

    def test_chat_text_without_code_preserved(self):
        """Given: an answer with text plus code Then: text_parts holds only the non-code text"""
        artifacts = ArtifactDetector().detect(PYTHON_BLOCK)
        text = ArtifactDetector().extract_text(PYTHON_BLOCK)
        assert 'Ein Beispielskript:' in text
        assert 'Das war alles.' in text
        assert 'def list_files' not in text


# Test Suite 3: Markdown Replacement in the Chat Text

class TestChatTextReplacement:

    def test_code_block_replaced_without_placeholder(self):
        """Given: text with a code block When: extract_text() Then: the block is removed entirely, no fake placeholder (F-01)"""
        text = ArtifactDetector().extract_text(PYTHON_BLOCK)
        assert 'def list_files' not in text
        assert '[📄 Artifact:' not in text
        assert 'Ein Beispielskript:' in text
        assert 'Das war alles.' in text

    def test_text_only_response_unchanged(self):
        """Given: an answer without a code block Then: extract_text() returns the original"""
        plain = "Das ist eine normale Antwort ohne Code."
        text = ArtifactDetector().extract_text(plain)
        assert text == plain


class TestAskPayloadIsNotAFile:
    """QA-0.1.11 F6: an echoed ask_user payload drew a `data.json` card."""

    def _json_artifact(self, content: str):
        from core.artifact_detector import Artifact, ArtifactType

        return Artifact(
            artifact_type=ArtifactType.JSON,
            content=content,
            language="json",
            title="data.json",
            filename="data.json",
        )

    def test_a_question_payload_is_recognised(self):
        from core.artifact_detector import looks_like_ask_payload

        art = self._json_artifact('{"question": "Which file?", "options": ["a", "b"]}')
        assert looks_like_ask_payload(art) is True

    def test_an_ordinary_json_block_stays_an_artifact(self):
        from core.artifact_detector import looks_like_ask_payload

        assert looks_like_ask_payload(self._json_artifact('{"items": [1, 2, 3]}')) is False

    def test_invalid_json_is_not_mistaken_for_a_question(self):
        from core.artifact_detector import looks_like_ask_payload

        assert looks_like_ask_payload(self._json_artifact("{not: json")) is False

    def test_a_code_block_never_counts(self):
        from core.artifact_detector import Artifact, ArtifactType, looks_like_ask_payload

        art = Artifact(
            artifact_type=ArtifactType.CODE_OTHER,
            content='{"question": "x"}',
            language="text",
            title="t",
            filename="t.txt",
        )
        assert looks_like_ask_payload(art) is False
