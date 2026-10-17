from __future__ import annotations

import re
import subprocess
from tests.toml_compat import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _git_ls_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.splitlines()


def test_given_git_tracked_files_when_checked_then_local_artifacts_are_not_tracked():
    """
    GIVEN the repository index
    WHEN open-source hygiene is checked
    THEN dependencies and local database artifacts are not tracked.
    """
    tracked = _git_ls_files()
    forbidden = [
        path
        for path in tracked
        if "/node_modules/" in f"/{path}/"
        or re.search(r"\.(db|sqlite|sqlite3|db-wal|db-shm)$", path)
        or re.search(r"(^|/)=\d", path)
    ]
    assert forbidden == []


BUSL_CARRIERS = {
    "pyproject.toml": 'license = "BUSL-1.1"',
    "app/package.json": '"license": "BUSL-1.1"',
    "app/src-tauri/Cargo.toml": 'license = "BUSL-1.1"',
    "packaging/npm/package.json": '"license": "BUSL-1.1"',
    "packaging/scoop/ephe.json": '"license": "BUSL-1.1"',
    "packaging/homebrew/ephe.rb": 'license "BUSL-1.1"',
}

CLAIM_SURFACES = [
    "landing/index.html",
]

BUSL_PROSE = [
    "README.md",
    "README.es.md",
    "README.zh-CN.md",
    "CONTRIBUTING.md",
    "NOTICE",
    "app/public/llms.txt",
    "docs/whitepaper-ephe.md",
    "landing/index.html",
    "COMMERCIAL.md",
]


def test_given_license_metadata_when_checked_then_the_business_source_license_is_consistent():
    """
    GIVEN the license this product ships under and every file that names it
    WHEN consistency is checked
    THEN BUSL-1.1 is declared in every carrier and none still sells Apache-2.0 as ours.
    """
    license = (ROOT / "LICENSE").read_text(encoding="utf-8")

    assert "Business Source License 1.1" in license
    assert "License text copyright (c) 2020 MariaDB Corporation Ab" in license, (
        "the text is MariaDB's template and keeps its copyright line"
    )
    assert "Parameters" in license and "Additional Use Grant:" in license
    assert re.search(r"Licensor:\s+Bemler Labs", license)
    assert "non-production use" in license
    assert "Change License:" in license and "Apache License" in license, (
        "the Change License is what each version falls to after four years"
    )

    # Every manifest a registry, a package manager or an installer reads.
    for path, expected in BUSL_CARRIERS.items():
        text = (ROOT / path).read_text(encoding="utf-8")
        assert expected in text, f"{path} does not declare {expected!r}"

    # Every surface a human reads.
    for path in BUSL_PROSE:
        if not (ROOT / path).exists():
            continue  # landing/ is a local surface in this checkout, and a clone need not have it
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "BUSL-1.1" in text or "BUSL 1.1" in text, (
            f"{path} does not name the license"
        )

    # Apache-2.0 stays named in exactly two legitimate places: as the Change License,
    # and in the attribution lists, which name dependencies that really are Apache-2.0.
    # What must not survive is a carrier presenting it as OUR license, and the badge is
    # the loudest such carrier. A raw substring check on the license name cannot tell
    # the two uses apart, so the claim forms are what get pinned.
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Apache License 2.0. See" not in readme
    assert "License-Apache" not in readme
    for path in BUSL_PROSE:
        if not (ROOT / path).exists():
            continue  # landing/ is a local surface in this checkout, and a clone need not have it
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "licensed under the Apache" not in text.lower(), (
            f"{path} still licenses this product under Apache-2.0"
        )
    # Surfaces that state the licence to a reader or a machine, where the old licence has no
    # business at all: naming it in the Change License is a fact about four years from now and
    # belongs in the README, not in a footer or a machine index.
    # A marketing surface has no business naming the licence the product left; a file that sells
    # commercial terms has every reason to say when the licence becomes Apache, so it is checked
    # only for naming the licence in force.
    for path in CLAIM_SURFACES:
        surface = ROOT / path
        if not surface.exists():
            continue  # a surface this checkout does not carry cannot be checked here
        text = surface.read_text(encoding="utf-8")
        assert "Apache" not in text, f"{path} still names the licence this product left"

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["license"] == "BUSL-1.1"
    assert not [
        c for c in pyproject["project"]["classifiers"] if c.startswith("License ::")
    ], "BUSL is not an OSI-approved license, so no License :: classifier can stand"


def test_given_the_license_when_a_reader_looks_for_the_terms_then_the_grant_is_stated():
    """
    GIVEN a source-available license
    WHEN a reader wants to know what they may do with this product
    THEN the README states the grant and the change date in the product's own words.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Business Source License 1.1" in readme
    assert "four years" in readme
    assert "commercial" in readme.lower()


LICENCE_COPIES = {
    "LICENSE": ["packaging/npm/LICENSE", "app/public/LICENSE"],
    "NOTICE": ["packaging/npm/NOTICE", "app/public/NOTICE"],
}


def test_given_the_licence_when_it_ships_with_a_copy_then_the_bytes_are_the_same():
    """
    GIVEN the licence and the places it travels inside a distributed artefact
    WHEN each copy is compared with the file in the repository root
    THEN they are byte-identical, so a correction cannot land in one and miss the others.
    """
    for name, copies in LICENCE_COPIES.items():
        canonical = (ROOT / name).read_bytes()
        for rel in copies:
            shipped = (ROOT / rel).read_bytes()
            assert shipped == canonical, f"{rel} has drifted from {name}"
