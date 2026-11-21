"""Make a bracketed IPv6 bypass safe before an HTTP client reads the environment.

The installed client is 0.28.1, which is also the newest release on the index.
Its ``get_environment_proxies`` splits ``NO_PROXY`` on commas. A bare IPv6
address is recognised and mounted as ``all://[::1]``. A bracketed entry is not:
``[::1]`` falls through to ``all://*[::1]``, and ``normalize_port`` then raises
``InvalidURL: Invalid port: ':1]'``. The same function is unchanged on the
current upstream source. The 1.0.dev6 wheel is an older preview and does not
contain this parser, so no published upgrade stops the raise.

``normalize_proxy_environment`` rewrites the process environment. A bracketed
entry whose inside is an IPv6 address loses the brackets and keeps any suffix,
so ``[::1]`` becomes ``::1`` and the bypass still names that host.
``install_proxy_normalizer`` applies that rewrite at the start of both client
constructors, which is the one place every default ``trust_env`` client passes
through, including the guarded fetch the bridge uses.
"""
from __future__ import annotations

import importlib.util
import ipaddress
import os
import sys

_PROXY_KEYS = (
    "NO_PROXY",
    "no_proxy",
)
_INSTALLED = False


def _unbracket(entry: str) -> str:
    text = entry.strip()
    if not text.startswith("[") or "]" not in text:
        return text
    inside, _, suffix = text[1:].partition("]")
    candidate = inside.split("%", 1)[0].split("/", 1)[0]
    try:
        ipaddress.IPv6Address(candidate)
    except ValueError:
        return text
    return inside + suffix


def normalize_proxy_environment() -> None:
    """Rewrite bracketed IPv6 entries in the proxy bypass lists.

    See the module docstring for the measured parser failure this prevents.
    """
    for key in _PROXY_KEYS:
        raw = os.environ.get(key)
        if not raw:
            continue
        cleaned = ",".join(_unbracket(part) for part in raw.split(","))
        if cleaned != raw:
            os.environ[key] = cleaned


def install_proxy_normalizer() -> None:
    """Reach both client constructors without loading the client at core import.

    The environment rewrite runs here, on the standard library alone. The
    constructor patch waits for the import that loads the client, because that
    package imports a renderer the CLI startup budget counts as heavy. A client
    cannot be built before its package has loaded, so the patch is in place for
    every constructor call this process makes.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    normalize_proxy_environment()
    _INSTALLED = True
    loaded = sys.modules.get("httpx")
    if loaded is not None:
        _patch_constructors(loaded)
    else:
        sys.meta_path.insert(0, _PatchOnLoad())


def _patch_constructors(httpx: object) -> None:
    def _wrap(init):
        def wrapped(self, *args, **kwargs):
            normalize_proxy_environment()
            return init(self, *args, **kwargs)

        return wrapped

    httpx.Client.__init__ = _wrap(httpx.Client.__init__)  # type: ignore[attr-defined,method-assign]
    httpx.AsyncClient.__init__ = _wrap(httpx.AsyncClient.__init__)  # type: ignore[attr-defined,method-assign]


class _PatchOnLoad:
    """The import hook that patches the constructors as the client package loads."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "httpx":
            return None
        sys.meta_path.remove(self)
        spec = importlib.util.find_spec(fullname)
        if spec is None or spec.loader is None:
            return None
        loader = spec.loader

        class _Loader:
            def create_module(self, spec):
                return loader.create_module(spec)

            def exec_module(self, module):
                loader.exec_module(module)
                _patch_constructors(module)

        spec.loader = _Loader()
        return spec
