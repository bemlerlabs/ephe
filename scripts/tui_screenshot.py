"""TUI screenshot: generate the Black-Forest theme as an SVG (visual evidence).

Renders the EpheApp in headless test mode and stores the SVG produced by
export_screenshot(). The SVG is then rasterized via a browser (PNG) for
the evidence.
"""
import asyncio
from pathlib import Path

OUT = Path("/work/ephe/docs/media/tui-black-forest.svg")


async def main():
    from ui.app import EpheApp
    from ui.widgets import ChatView

    # Real engine selection — exactly as in a real start (W18: the same source
    # as CLI/server: engine.json → env → onboarding, otherwise fail-closed instead
    # of a silent default).
    from ephe_cli import resolve_engine_choice

    choice = resolve_engine_choice()
    print("Engine:", choice.provider, choice.model, choice.api_url)
    app = EpheApp(model=choice.model, api_url=choice.api_url)
    async with app.run_test() as pilot:
        await pilot.pause(2.0)  # real DGX health check + render

        chat = app.query_one("#chat-view", ChatView)
        chat.post_message(ChatView.AddUserMessage("Wie geht's?"))
        chat.post_message(ChatView.BeginAssistantMessage())
        chat.post_message(ChatView.AppendChunk("Alles top! Ready für deinen Sprint. "))
        chat.post_message(ChatView.FinalizeAssistantMessage())
        await pilot.pause(0.7)

        svg = app.export_screenshot(title="Ephe — Black Forest")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(svg, encoding="utf-8")
        print(f"SVG gespeichert: {OUT} ({len(svg)} chars)")


asyncio.run(main())
