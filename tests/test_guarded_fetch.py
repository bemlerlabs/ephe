"""The marketplace fetch refuses non-HTTPS, private and redirecting targets."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import guarded_fetch


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/index.json",
        "https://127.0.0.1/index.json",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/index.json",
    ],
)
def test_non_public_or_plain_http_targets_are_refused(url):
    with pytest.raises(guarded_fetch.GuardedFetchError) as exc:
        guarded_fetch.fetch_https(url, timeout=0.1)
    assert exc.value.code == "untrusted_target"
