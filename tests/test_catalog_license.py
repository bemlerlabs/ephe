"""Licence evidence must be stronger than a claim before an entry can be approved."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "catalog_license.py"


def _load():
    spec = importlib.util.spec_from_file_location("catalog_license_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


licence = _load()
MIT = "MIT License\n\nPermission is hereby granted, free of charge, to any person."
APACHE = "Apache License, Version 2.0"
GPL = "GNU GENERAL PUBLIC LICENSE, Version 3"


def test_an_artifact_permissive_licence_is_allowed():
    result = licence.classify(artifact_text=MIT)
    assert result.status == "allowed"
    assert result.spdx == "MIT"
    assert "artifact" in result.evidence


def test_an_apache_artifact_is_allowed():
    assert licence.classify(artifact_text=APACHE).spdx == "Apache-2.0"


def test_a_copyleft_artifact_is_refused():
    result = licence.classify(artifact_text=GPL)
    assert result.status == "copyleft"
    assert result.spdx == ""


def test_metadata_only_is_unproven_not_approved():
    result = licence.classify(metadata="MIT")
    assert result.status == "unproven"
    assert result.spdx == "MIT"


def test_artifact_and_metadata_conflict():
    result = licence.classify(artifact_text=MIT, metadata="Apache-2.0")
    assert result.status == "conflict"


def test_metadata_and_index_conflict_without_an_artifact():
    result = licence.classify(metadata="MIT", index_claim="Apache-2.0")
    assert result.status == "conflict"


def test_missing_evidence_is_missing():
    assert licence.classify().status == "missing"


def test_bsd_three_clause_is_detected_before_two_clause():
    text = "BSD 3-Clause License\nNeither the name of the copyright holder."
    assert licence.classify(artifact_text=text).spdx == "BSD-3-Clause"
