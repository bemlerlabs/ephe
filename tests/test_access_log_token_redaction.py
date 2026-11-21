"""The LAN token stays out of the access log the QR link would otherwise write into it.

`run_server.py` starts uvicorn with its access log on, and a paired phone carries the
LAN token as `?token=` on media and WebSocket URLs because those requests cannot carry
a header (server/middleware.py, `MEDIA_TOKEN_PREFIXES`). One unredacted request line is
a full API credential in a file that outlives the process which minted it, so the
redaction is checked here at the log record rather than trusted to a format string.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

import run_server

#: A token shaped like the one `server/middleware.py` mints: `secrets.token_urlsafe(32)`.
#: Not a credential shape on purpose: the tree-wide secret scan reads a 40-character base64
#: literal in an assignment as the thing it is looking for, and it is right to.
_SECRET = "lan-token-value-under-test"


@pytest.fixture
def access_logger() -> Iterator[logging.Logger]:
    """The real access logger, with this test's filters removed again afterwards."""
    logger = logging.getLogger("uvicorn.access")
    before = list(logger.filters)
    yield logger
    logger.filters = before


def test_given_a_media_url_carrying_the_token_when_the_record_is_rendered_then_the_secret_is_gone() -> None:
    """GIVEN an access line whose query carries the token WHEN the filter sees it THEN no copy of the token survives in the record."""
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "run_server.py",
        1,
        '%s - "GET /api/artifacts/7/file?token=%s HTTP/1.1" 200',
        ("127.0.0.1", _SECRET),
        None,
    )

    assert run_server.AccessTokenRedaction().filter(record) is True
    rendered = record.getMessage()
    assert _SECRET not in rendered
    assert "token=[redacted]" in rendered
    assert "GET /api/artifacts/7/file" in rendered and "200" in rendered


def test_given_a_websocket_handshake_carrying_the_token_when_the_record_is_rendered_then_the_secret_is_gone() -> None:
    """GIVEN a shell handshake whose query carries the token WHEN the filter sees it THEN the address keeps its shape without the credential."""
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "run_server.py",
        1,
        '%%s - "GET /api/shell/term?token=%s&session=4 HTTP/1.1" 101',
        (_SECRET,),
        None,
    )

    run_server.AccessTokenRedaction().filter(record)
    rendered = record.getMessage()
    assert _SECRET not in rendered and "session=4" in rendered


def test_given_a_record_without_a_token_when_the_filter_sees_it_then_the_record_is_untouched() -> None:
    """GIVEN an ordinary access line WHEN the filter sees it THEN its format and arguments stand, so uvicorn still formats it itself."""
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, "run_server.py", 1, '%s - "GET /api/health HTTP/1.1" 200', ("127.0.0.1",), None
    )
    args_before = record.args

    assert run_server.AccessTokenRedaction().filter(record) is True
    assert record.args is args_before
    assert record.getMessage() == '127.0.0.1 - "GET /api/health HTTP/1.1" 200'


def test_given_a_token_written_in_another_case_when_the_record_is_rendered_then_it_is_still_redacted() -> None:
    """GIVEN a sender that spells the parameter `Token=` WHEN the filter sees the line THEN the value is redacted regardless."""
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "run_server.py",
        1,
        'GET /images/a.png?Token=%s',
        (_SECRET,),
        None,
    )

    run_server.AccessTokenRedaction().filter(record)
    assert _SECRET not in record.getMessage()


def test_given_the_server_start_path_when_redaction_is_attached_then_the_access_logger_carries_it(
    access_logger: logging.Logger,
) -> None:
    """GIVEN a start of the product server WHEN the redaction is attached THEN the logger uvicorn writes to holds the filter and logs nothing carrying the token."""
    run_server.attach_access_log_redaction()
    assert any(isinstance(f, run_server.AccessTokenRedaction) for f in access_logger.filters)

    emitted: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: emitted.append(record.getMessage())  # type: ignore[method-assign]
    access_logger.addHandler(handler)
    access_logger.setLevel(logging.INFO)
    try:
        access_logger.info('%s - "GET /api/file/preview?token=%s HTTP/1.1" 200', "127.0.0.1", _SECRET)
    finally:
        access_logger.removeHandler(handler)

    assert len(emitted) == 1 and _SECRET not in emitted[0]
