"""The macOS bundle declares every privacy purpose the WebView can ask for.

WKWebView terminates the host process when a page requests a protected resource
and the bundle carries no matching usage description. The shipped 0.1.8 bundle
was built without `NSMicrophoneUsageDescription` while the composer calls
`getUserMedia({audio: true})`, so pressing the microphone ended the app.

The scan reads the source, collects the constraints the app actually requests and
refuses a bundle that declares fewer of them.
"""
from __future__ import annotations

import plistlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLIST = ROOT / "app" / "src-tauri" / "Info.plist"
SOURCE_ROOTS = (ROOT / "app" / "src",)

#: getUserMedia constraint name → the Info.plist key macOS demands for it.
USAGE_KEY = {
    "audio": "NSMicrophoneUsageDescription",
    "video": "NSCameraUsageDescription",
}

GET_USER_MEDIA = re.compile(r"getUserMedia\(\s*\{(?P<body>[^}]*)\}")


def requested_usage_keys() -> set[str]:
    keys: set[str] = set()
    for root in SOURCE_ROOTS:
        for path in root.rglob("*"):
            if path.suffix not in (".ts", ".tsx") or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in GET_USER_MEDIA.finditer(text):
                body = match.group("body")
                for constraint, key in USAGE_KEY.items():
                    if re.search(rf"\b{constraint}\s*:\s*true\b", body):
                        keys.add(key)
    return keys


def test_the_bundle_declares_every_requested_usage_string():
    requested = requested_usage_keys()
    assert requested, "no getUserMedia constraint found — the scan has gone blind"

    declared = plistlib.loads(PLIST.read_bytes())
    missing = sorted(key for key in requested if not str(declared.get(key) or "").strip())

    assert not missing, (
        "the bundle requests these protected resources without a usage description: "
        + ", ".join(missing)
    )


def test_every_declared_usage_string_names_the_app():
    declared = plistlib.loads(PLIST.read_bytes())
    purpose_keys = {key for key in declared if key.endswith("UsageDescription")}
    assert purpose_keys, "Info.plist carries no usage description at all"
    for key in sorted(purpose_keys):
        text = str(declared[key]).strip()
        assert text.startswith("Ephe "), f"{key} does not name the app: {text!r}"
        assert text.endswith("."), f"{key} is not a sentence: {text!r}"
