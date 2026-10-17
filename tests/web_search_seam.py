"""The DDGS seam for tests: the module, never the same-named function.

`core/tools/__init__.py` re-exports the tool *function* under the name `web_search`, so
the package attribute and the submodule share one name. `mock.patch` resolves that
differently per interpreter: Python 3.10 looks the target up with `_importer` and
getattr-first, which lands on the function and raises
`AttributeError: <function web_search ...> does not have the attribute 'DDGS'`, while
3.11+ switched to `pkgutil.resolve_name`, which imports the submodule first. The same
patch string therefore worked on three CI legs and broke nine tests on the 3.10 leg.

`importlib.import_module` returns the module on every version, and `patch.object` needs
no dotted lookup at all. The same trap applies to `from core.tools import web_search`
(the function) and to `import core.tools.web_search as ws` — which also binds the
function, not the module.
"""
from __future__ import annotations

import importlib

web_search_module = importlib.import_module("core.tools.web_search")

__all__ = ["web_search_module"]
