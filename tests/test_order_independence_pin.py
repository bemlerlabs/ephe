"""The order-dependence that broke twice, pinned in the order that broke it.

The class, measured twice in the wave: a test called
``importlib.reload(core.model_config)`` to read the tier table under different environment
variables. A reload mints a *second* ``ModelTier`` class while ``core.model_router`` keeps
the first, so ``route.tier is LOOP_TIER`` fails between two objects whose reprs are
identical — and only when the reloader runs *before* the file that compares by identity.
The alphabetical suite never meets it because ``test_hybrid_loop_router`` sorts first.

No single test can observe a cross-file ordering defect: whichever file this lives in, the
reload happens in another session. So this pins it the way the defect is reachable — by
running the three files together, reloader first, as one narrow child pytest. The child is
three files (~1 s), never the suite.

Fix lineage: ``4779925c`` (``test_model_config`` stops reloading, builds the table under
``patch.dict``) and ``7f804af5`` (``test_model_router`` states its own tier table). This
file is the regression guard for both.

The same class also lived in ``tests/test_hybrid_loop_router.py``'s ``separate_hosts``
fixture, whose teardown reloaded the modules before ``monkeypatch.undo()`` had put the
environment back, leaving them rebuilt for a foreign host; that teardown now restores the
variables itself first.

A third occurrence, found while closing the register sweep: four files reload
``core.model_provider`` to read the provider choice under different environment variables,
and a reload re-executes the module into the same dict, which mints a second
``ProviderMessage``. The converter's ``isinstance`` guard resolves its class name through
that dict at call time, so it sees the second class while a test file that imported the
name at collection time builds messages of the first. The message then falls to the dict
branch and dies as ``'ProviderMessage' object has no attribute 'get'``. The wire test
resolved every provider name up front; it now resolves them from the live module when it
needs them, so whichever generation the reloader left behind is the one both sides use.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The order that reproduced the failure: the reloader first, the identity pin last.
BREAK_ORDER = (
    "tests/test_model_config.py",
    "tests/test_model_router.py",
    "tests/test_hybrid_loop_router.py",
)


def test_the_model_tier_identity_holds_in_the_order_that_used_to_break() -> None:
    """GIVEN three files sharing the core.model_config/model_router globals
    WHEN they run together with the reloader first
    THEN every tier identity comparison still holds (the child exits green).

    Unlike `test_bench_gate_switch`'s hermetic child, this one keeps the parent's
    environment on purpose: the defect depends on the real import path and venv, so a
    scrubbed child would measure the machine instead of the ordering. Only
    `PYTEST_ADDOPTS` is dropped, so a developer's shell default cannot change the child.
    """
    env = {**os.environ}
    env.pop("PYTEST_ADDOPTS", None)
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest", "-q", "--no-header",
            "-p", "no:cacheprovider", *BREAK_ORDER,
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        "the model tier identity broke under selection order again — an "
        "importlib.reload(core.model_config) that mints a second ModelTier class is the "
        "cause; build the tier table under patch.dict instead of reloading:\n"
        + result.stdout
        + result.stderr
    )


def test_loop_tier_is_the_config_module_fast_tier() -> None:
    """GIVEN the router and the config imported once
    WHEN the loop tier is compared by identity
    THEN it is the config module's own FAST member — the exact invariant a reload broke."""
    import core.model_config as model_config
    import core.model_router as model_router

    assert model_router.LOOP_TIER is model_config.ModelTier.FAST


# The order that reproduced the provider-message defect: the reloader first, the wire
# test last. One reloader is enough to prove the class, and the four files that reload
# core.model_provider (test_model_provider, test_generation_reaches_request_i25,
# test_openai_provider_tools, test_thinking_passthrough) all reach it the same way.
BREAK_ORDER_PROVIDER = (
    "tests/test_model_provider.py",
    "tests/test_subagent_tool_wire.py",
)


def test_the_provider_message_identity_holds_in_the_order_that_breaks() -> None:
    """GIVEN a file that reloads core.model_provider ahead of the wire test
    WHEN the two run together as one child pytest
    THEN the converter still recognises the messages the helper sends."""
    env = {**os.environ}
    env.pop("PYTEST_ADDOPTS", None)
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest", "-q", "--no-header",
            "-p", "no:cacheprovider", *BREAK_ORDER_PROVIDER,
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        "the provider message identity broke under selection order again — an "
        "importlib.reload(core.model_provider) mints a second ProviderMessage in the "
        "same module dict, so a test that imported the name at collection time sends "
        "messages the reloaded converter no longer recognises: resolve the provider "
        "names from the live module at call time:\n"
        + result.stdout
        + result.stderr
    )
