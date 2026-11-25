"""
◑ Ephe – Which language this installation speaks.
core/language.py

The choice is one field of the deep register (`appearance.language`), the saved answer
behind the `POST /api/settings` form. A process can still name a language for itself
through `EPHE_LANGUAGE`, which is what a shell session, a test, or a support reply means
when it says "run it in English" — the override covers the process, the register covers
the device.

Read the language through `active_language()` rather than the field directly: a surface
that reads the field alone ignores the override, and a surface that reads the environment
alone answers to whichever process set it last. Both mistakes happened to the thinking
titles before this module existed.
"""
from __future__ import annotations

import os

from core.settings_schema import deep_select

#: The environment that overrides the saved choice for one process. The field it
#: overrides is `appearance.language`, named at the read below.
LANGUAGE_OVERRIDE_ENV = "EPHE_LANGUAGE"


def active_language() -> str:
    """The language to show product text in: process override, saved choice, register default."""
    override = (os.environ.get(LANGUAGE_OVERRIDE_ENV) or "").strip()
    if override:
        return override
    # The field key stands here in full: the register counts an accessor call written out
    # as the proof that a field is a control (tests/test_settings_surface_is_real.py).
    return deep_select("appearance.language")
