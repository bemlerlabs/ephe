"""
tests/test_finding_05_svg_xss_sanitizer.py

Finding 5: create_svg() wrote RAW SVG to disk without sanitizing.
Fix: the XSS-relevant tags and attributes are removed before saving.

Given-When-Then Tests:
  1. GIVEN SVG with <script> WHEN create_svg() THEN script tags stripped
  2. GIVEN SVG with onclick handler WHEN create_svg() THEN handler stripped
  3. GIVEN SVG with javascript: URL WHEN create_svg() THEN URL neutralized
  4. GIVEN SVG with <foreignObject> WHEN create_svg() THEN foreignObject stripped
  5. GIVEN clean SVG WHEN create_svg() THEN content preserved unchanged
"""
import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def downloads_dir(tmp_path):
    d = tmp_path / "Downloads"
    d.mkdir()
    return d


# Test 1: GIVEN script tags WHEN create_svg THEN stripped

@pytest.mark.asyncio
async def test_given_script_tag_when_create_svg_then_stripped(downloads_dir):
    """GIVEN SVG contains <script>alert('xss')</script> WHEN create_svg() THEN script removed."""
    from core.tools import create_svg

    malicious_svg = '<svg xmlns="http://www.w3.org/2000/svg"><circle r="10"/><script>alert("xss")</script></svg>'

    with patch("core.tools.system_tools.Path.home", return_value=downloads_dir.parent):
        result = await create_svg(malicious_svg, "test.svg")

    assert "SVG_FILE:" in result
    output_path = result.split("SVG_FILE:")[1]
    content = Path(output_path).read_text()

    assert "<script" not in content.lower()
    assert "alert" not in content
    assert "<circle" in content  # Legitimate content preserved


# Test 2: GIVEN onclick handler WHEN create_svg THEN stripped

@pytest.mark.asyncio
async def test_given_onclick_when_create_svg_then_stripped(downloads_dir):
    """GIVEN SVG element has onclick handler WHEN create_svg() THEN handler removed."""
    from core.tools import create_svg

    svg_with_handler = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="100" height="100" onclick="alert(1)"/></svg>'

    with patch("core.tools.system_tools.Path.home", return_value=downloads_dir.parent):
        result = await create_svg(svg_with_handler, "test.svg")

    content = Path(result.split("SVG_FILE:")[1]).read_text()
    assert "onclick" not in content.lower()
    assert "<rect" in content  # Element itself preserved


# Test 3: GIVEN javascript URL WHEN create_svg THEN neutralized

@pytest.mark.asyncio
async def test_given_javascript_url_when_create_svg_then_neutralized(downloads_dir):
    """GIVEN SVG has href="javascript:..." WHEN create_svg() THEN URL replaced with #."""
    from core.tools import create_svg

    svg_with_js_url = '<svg xmlns="http://www.w3.org/2000/svg"><a href="javascript:alert(1)"><text>Click</text></a></svg>'

    with patch("core.tools.system_tools.Path.home", return_value=downloads_dir.parent):
        result = await create_svg(svg_with_js_url, "test.svg")

    content = Path(result.split("SVG_FILE:")[1]).read_text()
    assert "javascript:" not in content.lower()
    assert 'href="#"' in content


# Test 4: GIVEN foreignObject WHEN create_svg THEN stripped

@pytest.mark.asyncio
async def test_given_foreign_object_when_create_svg_then_stripped(downloads_dir):
    """GIVEN SVG contains <foreignObject> WHEN create_svg() THEN foreignObject removed."""
    from core.tools import create_svg

    svg_with_foreign = '<svg xmlns="http://www.w3.org/2000/svg"><foreignObject><body><script>alert(1)</script></body></foreignObject><circle r="5"/></svg>'

    with patch("core.tools.system_tools.Path.home", return_value=downloads_dir.parent):
        result = await create_svg(svg_with_foreign, "test.svg")

    content = Path(result.split("SVG_FILE:")[1]).read_text()
    assert "foreignObject" not in content
    assert "<circle" in content


# Test 5: GIVEN clean SVG WHEN create_svg THEN preserved

@pytest.mark.asyncio
async def test_given_clean_svg_when_create_svg_then_preserved(downloads_dir):
    """GIVEN legitimate SVG WHEN create_svg() THEN content preserved exactly."""
    from core.tools import create_svg

    clean_svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40" fill="#22c55e"/></svg>'

    with patch("core.tools.system_tools.Path.home", return_value=downloads_dir.parent):
        result = await create_svg(clean_svg, "test.svg")

    content = Path(result.split("SVG_FILE:")[1]).read_text()
    assert content.strip() == clean_svg
