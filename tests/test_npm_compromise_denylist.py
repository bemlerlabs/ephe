"""Known compromised npm packages stay out of the lock.

`pnpm audit` sees advisories, not a package name that was briefly published under
a compromised maintainer account. The owner named the set that matters for this
wave; the old `keyv@4.5.4` is the eslint dev chain and stays.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "app" / "pnpm-lock.yaml"

DENY = {
    "axios 1.14.1": r"axios@1\.14\.1",
    "axios 0.30.4": r"axios@0\.30\.4",
    "plain-crypto-js": r"plain-crypto-js@",
    "keyv 6.0.0": r"keyv@6\.0\.0",
    "@cacheable/net": r"@cacheable/net@",
    "ecto 5.0.1": r"ecto@5\.0\.1",
    "@redhat-cloud-services": r"@redhat-cloud-services/",
}


def test_the_lock_carries_no_owner_named_compromised_package():
    text = LOCK.read_text(encoding="utf-8")
    hits = [name for name, pattern in DENY.items() if re.search(pattern, text)]
    assert hits == [], f"known compromised npm packages in the lock: {hits}"


def test_the_old_keyv_is_the_eslint_dev_chain_not_the_compromised_release():
    text = LOCK.read_text(encoding="utf-8")
    assert "keyv@4.5.4" in text
    assert not re.search(r"keyv@6\.0\.0", text)
