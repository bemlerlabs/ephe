"""The PWA mount: static files, with the app shell behind an unknown path.

`mount_frontend` served `StaticFiles(..., html=True)` at `/`, which resolves a
real file and answers everything else with a 404. The frontend routes with
`HashRouter`, so a refresh, a bookmark or a pasted link to a client-side route
reaches the server as a bare path with no file behind it — and got the API's
404 envelope back. The app existed only at `/`.

Two things the fallback deliberately does **not** catch:

- ``/api/*`` and ``/v1/*``. An unknown API route that answers HTML breaks every
  client (a fetch that asked for JSON parses a document), which is a worse bug
  than the 404 it replaces. Those keep the JSON envelope the exception handler
  builds.
- a path that names a file. A missing ``/assets/app-4f2a.js`` is a broken build,
  and handing it ``index.html`` hides that — and fails a module request with a
  MIME error that names the wrong cause.
"""
from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

# Prefixes the API owns. Mounted at `/`, StaticFiles sees the path relative to
# the mount root, so `/api/x` arrives here as `api/x`.
API_PREFIXES = ("api/", "v1/")


class SPAStaticFiles(StaticFiles):
    """``StaticFiles(html=True)`` plus the app shell for a navigation path."""

    async def get_response(self, path: str, scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or not _is_navigation(path):
                raise
            # mount_frontend only mounts when index.html exists, so this resolves.
            return await super().get_response("index.html", scope)


def _is_navigation(path: str) -> bool:
    """True when the path could be a route the frontend router owns.

    A path whose last segment carries a dot names a file — those keep their 404.
    """
    if path.startswith(API_PREFIXES):
        return False
    return "." not in path.rsplit("/", 1)[-1]
