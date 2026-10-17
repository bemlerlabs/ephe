"""◑ Ephe – core package."""

# P0-4 (Versions-SSOT): one number, one source. `core._version` reads the
# installed distribution metadata (pip/Docker) and falls back to the
# pyproject-coupled fallback value — every UI reading (Sidebar, Onboarding,
# About tab) takes its version from this value via /api/health.
from core._version import __version__

__edition__  = "◑ Ephe"
__product__  = "Ephe"
__author__   = "Ephe – Bad Liebenzell"
__tagline__  = "Runs locally. Everything else is a decision."
__github__   = "https://github.com/bemlerlabs/ephe"

__all__ = ["__version__", "__edition__", "__product__", "__author__", "__tagline__", "__github__"]
