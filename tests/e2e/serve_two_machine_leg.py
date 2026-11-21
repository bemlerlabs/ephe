"""The serve side of the W3-61 two-machine path, run in its own interpreter.

`ephe serve` binds ``server.openai.create_openai_app`` under uvicorn. This program
binds the same app the same way, so the parent test reaches the shipped serve
surface over a real loopback socket instead of an in-process ASGI transport. The
one substitution is the engine behind the boundary ``server.openai`` reads at call
time: the test host runs no Ollama, so a deterministic async chunk source stands
in for it. Everything else is shipped — routes, middleware, SSE framing, the auth
gate and shutdown.

Usage, from the repo root with the checkout on PYTHONPATH:

    python tests/e2e/serve_two_machine_leg.py --port 8766 [--token T] [--model M]

The process serves until it is terminated (SIGTERM), the way `ephe serve` runs
until the user stops it.
"""

from __future__ import annotations

import argparse
import sys
from types import SimpleNamespace

#: The answer the stand-in engine streams. The test joins the same tuple, so the
#: streamed and the collected responses are one string by construction.
CHUNKS = ("Ephe ", "serves ", "the ", "two-machine ", "path.")

#: The served model id. `ephe serve` advertises the ids the user configured; here
#: the stand-in engine carries this one, and the test names it in every request.
DEFAULT_MODEL = "w3-61-served"


class _ChunkEngine:
    """Async chat source with the shape the serve route consumes.

    ``_chat_stream`` (server/openai.py) calls ``client.chat(model, messages,
    stream=True)`` and reads ``chunk["message"]["content"]``; this yields exactly
    that, in CHUNKS order.
    """

    async def chat(self, *, model, messages, stream=False, **_):
        async def _frames():
            for piece in CHUNKS:
                yield {"message": {"content": piece}}

        return _frames()


def _install_engine(engine, model: str) -> None:
    """Bind the three names the routes read at call time to the stand-in engine.

    The route module imports ``build_provider_client``, ``get_active_provider`` and
    ``TIER_MAP`` into its own namespace and resolves them there per request, so the
    module attributes are what a substitution has to replace. The WG-49 in-process
    test swaps the same three.
    """
    from core.model_config import ModelConfig, ModelTier

    engine.build_provider_client = lambda *_, **__: _ChunkEngine()
    engine.get_active_provider = lambda: SimpleNamespace(
        provider="local_ollama", model=model, base_url=""
    )
    engine.TIER_MAP = {ModelTier.FAST: ModelConfig(name=model, tier=ModelTier.FAST)}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", default="")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args(argv[1:])

    import uvicorn

    import server.openai as engine

    _install_engine(engine, args.model)
    app = engine.create_openai_app(api_token=args.token or None)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
