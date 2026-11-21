"""A port nobody holds, for a test that starts a server of its own.

The suite runs beside an installed Ephe, and CI runs it with `-n auto`: a test that
binds the product port loses to the running app, and two workers that name the same
number lose to each other. Port 0 asks the kernel for one, the close hands it back,
the caller binds it for real a moment later.

`run_server.select_free_port` is the product's own and does a different job: it walks
off a busy base port toward the next free one, which is what a server starting on 8765
wants and what a test must not accept — the caller asserts against the number it got.
`tests/test_playwright_port_hygiene.py` holds the same distinction for the e2e leg.
"""

from __future__ import annotations

import socket


def free_port() -> int:
    """One loopback port chosen by the kernel, released before it is returned."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])
