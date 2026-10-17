"""
◑ Ephe – W4 S4: logger scopes (get_logger, the scope field, the level contract).
tests/test_r52_logger_scopes.py

RULE: these tests were written BEFORE the implementation.

Pins:
1. get_logger('skills').name == 'ephe.skills'; identical calls return
   identical logger objects (cache).
2. structured_log carries the required field 'scope' (default 'obs'); the
   JSON line contains "scope":"skills".
3. Prod handler filter: debug falls through the filter, info passes it.
4. The ErrorCode enum stays stable (append-only: skills_lock_mismatch).
"""
from __future__ import annotations

import json
import logging

from core.observability import (
    ErrorCode,
    get_logger,
    make_prod_handler,
    structured_log,
)


def test_get_logger_names_and_identity():
    a = get_logger("skills")
    b = get_logger("skills")
    assert a.name == "ephe.skills"
    assert a is b
    assert get_logger().name == "ephe.obs"


def test_structured_log_carries_scope_field():
    logger = get_logger("skills")
    buf: list[str] = []

    class _H(logging.Handler):
        def emit(self, record):
            buf.append(record.getMessage())

    handler = _H()
    logger.addHandler(handler)
    try:
        structured_log("info", "evt", scope="skills")
        assert buf, "keine Zeile emittiert"
        record = json.loads(buf[-1])
        assert record["scope"] == "skills"
        assert '"scope":"skills"' in buf[-1]
    finally:
        logger.removeHandler(handler)


def test_structured_log_default_scope_is_obs():
    logger = get_logger()
    buf: list[str] = []

    class _H(logging.Handler):
        def emit(self, record):
            buf.append(record.getMessage())

    handler = _H()
    logger.addHandler(handler)
    try:
        structured_log("info", "evt")
        record = json.loads(buf[-1])
        assert record["scope"] == "obs"
    finally:
        logger.removeHandler(handler)


def test_prod_handler_filter_semantics():
    handler = make_prod_handler()
    debug_record = logging.LogRecord(
        "ephe.engine", logging.DEBUG, "f", 1, "d", None, None
    )
    info_record = logging.LogRecord(
        "ephe.engine", logging.INFO, "f", 1, "i", None, None
    )
    assert handler.level == logging.INFO
    assert handler.filter(debug_record) is False
    assert bool(handler.filter(info_record))


def test_error_code_enum_backcompat():
    values = {e.value for e in ErrorCode}
    assert "skills_lock_mismatch" in values
    # The pre-existing codes, unchanged (append-only):
    for stable in ("usage_error", "runtime_error", "validation_error",
                   "auth_error", "stream_error", "upstream_error",
                   "internal_error", "not_found", "setup_required"):
        assert stable in values

