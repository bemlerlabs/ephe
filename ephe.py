"""
◑ Ephe – by Ephe
Bad Liebenzell · Schwarzwald · Germany

Privat. Lokal. Yours.

Entry Point: ephe [--model MODEL] [--reset]
"""

from __future__ import annotations

import argparse
import sys

from core._version import __version__


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ephe",
        description=(
            "◑ Ephe – Local AI Assistant\n"
            "   Privat. Lokal. Yours.\n"
            "   Ephe · Bad Liebenzell, Schwarzwald\n\n"
            "Slash commands:  /post  /debug  /idea  /explain  /commit\n"
            "Swarm agents:    /swarm <task>  (multi-agent parallel pipeline)\n"
            "Keyboard:        Ctrl+R=Reset  Ctrl+L=Clear  ↑↓=History  q=Quit"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  ephe\n"
            "  ephe --model <tag>            a tag your engine actually serves\n"
            "  ephe --reset\n\n"
            "No cloud. No tracking. ◑ Source-available under BUSL-1.1 · github.com/bemlerlabs/ephe"
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        metavar="MODEL",
        help="Model tag your engine serves. There is no default: without this flag "
             "the tag comes from the engine you chose with `ephe configure` "
             "(or from EPHE_MODEL).",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        metavar="URL",
        help="OpenAI-compatible engine base URL (e.g. http://your-engine-host:8000/v1). "
             "Default: the engine chosen with `ephe configure`.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear previous session on start",
    )
    # P0-1 E1: Tool-Approval-Flags (von `ephe tui --yes/--no/--dry-run` geforwardet)
    yes_no = parser.add_mutually_exclusive_group()
    yes_no.add_argument(
        "--yes",
        action="store_true",
        help="Explicitly approve execution of MUTATING/NETWORK tools",
    )
    yes_no.add_argument(
        "--no",
        action="store_true",
        help="Explicitly decline; MUTATING/NETWORK tools are NOT executed",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only; mutating tools are NOT executed (Approval-Gate)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"◑ Ephe v{__version__} – by Ephe",
    )

    args = parser.parse_args()

    try:
        from ui.app import EpheApp
    except ImportError as e:
        print(f"[Error] Failed to import Ephe: {e}", file=sys.stderr)
        print("Run: ./install.sh  or  pip install -e '.'", file=sys.stderr)
        sys.exit(1)

    app = EpheApp(
        model=args.model,
        reset=args.reset,
        api_url=args.api_url,
        auto_approve=args.yes,
        declined=args.no,
        dry_run=args.dry_run,
    )
    app.run()


if __name__ == "__main__":
    main()
