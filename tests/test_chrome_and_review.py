"""Author: Swami Chandrasekaran
Last Modified: 2026-07-20
Purpose: Tests the chrome renders and Mom's rewrites don't crash the turn.

Two bugs this file exists to prevent, both of which shipped silently:

  1. ReviewCard was referenced by the event handler but its class definition was
     lost in an edit. Nothing failed at import — the NameError only fired when
     Mom actually rewrote a call, which needs a real over-cap spend to reproduce.
     A crash that only appears when the governance layer does its job is the
     worst possible place for one.

  2. The key bar was written, styled, and never mounted. compose() still yielded
     Textual's stock Footer, which renders nothing here because focus lives in
     the Input and an Input's bindings are all show=False. The app looked like it
     had no keyboard shortcuts at all.

Both are the same class of failure: the code is present and reads correctly, but
is not connected to anything. Only rendering the real screen catches that.
"""

import asyncio
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dadloop import AgentLoop, Context, SemanticMemory
from dadloop.tui import DadApp, KeyBar, ReviewCard


def _strip(markup: str) -> str:
    return re.sub(r"\[[^]]*\]", "", str(markup))


def test_key_bar_is_actually_on_screen():
    """The keys must be visible, not merely defined.

    Checks the rendered widget rather than the class, because the bug was that
    a perfectly good KeyBar existed and nothing ever mounted it.
    """
    async def scenario():
        app = DadApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            bar = app.query_one("#keybar")
            text = _strip(bar.content)
            for key in ("F4", "F5", "^Q"):
                assert key in text, f"{key} missing from the key bar: {text}"
            assert "admin" in text and "quit" in text

            assert bar.region.height == 1, "key bar should occupy its row"

            # The bug this guards against: the bar had content and an allotted
            # region, but rendered at height 0 because a border-top ate its only
            # row. .content and .region both looked fine; only the painted height
            # revealed it. So assert the widget actually occupies its row AND
            # that its keys land in the rendered screen.
            assert bar.size.height >= 1, (
                "key bar rendered at height 0 — its text is invisible even though "
                "the content is set (a border on a 1-row bar does this)")
            painted = _strip(app.export_screenshot()).replace(" ", "")
            assert "F4" in painted and "admin" in painted, (
                "key bar text is not in the rendered screen")

            # It must sit INSIDE the shell, under the prompt — not docked to the
            # screen bottom, which in framed mode puts it out in the margin below
            # the border where it reads as terminal chrome instead of as part of
            # the app. Assert the relationship, not a row number: a hard-coded y
            # would have passed for the very layout this is guarding against.
            shell = app.query_one("#shell").region
            hint = app.query_one("#input-hint").region
            assert shell.y <= bar.region.y < shell.y + shell.height, (
                f"key bar at y={bar.region.y} is outside the shell "
                f"({shell.y}..{shell.y + shell.height - 1})")
            assert bar.region.y > hint.y, "key bar should sit below the prompt"

            # Finally, the real user path: through the launch screen and out.
            # This is where the zero-height bug actually bit — the direct mount
            # looked fine, the post-launch render did not.
            from dadloop.launch import LaunchScreen
            app.push_screen(LaunchScreen(online=True), app._start_from_launch)
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            post = _strip(app.export_screenshot()).replace(" ", "")
            assert "F4" in post and "admin" in post, (
                "after the launch screen, the key bar keys are not on screen")

            # The admin screen gets its own keys — Esc out, no F5 clear.
            await pilot.press("f4")
            await pilot.pause()
            admin_text = _strip(app.screen.query_one("#keybar").content)
            assert "back" in admin_text, f"admin key bar should show the way out: {admin_text}"
        print("PASS: the key bar is mounted and visible on both screens")

    asyncio.run(scenario())


def test_mom_rewriting_a_call_does_not_crash_the_turn():
    """An over-cap spend makes Mom rewrite the call, which renders a ReviewCard.

    This is the path that raised NameError in the wild: the turn ran, the tools
    ran, and the UI died at the moment governance acted.
    """
    class FakeMessages:
        def __init__(self): self.n = 0

        def create(self, **kw):
            if any(t.get("type", "").startswith("web_search")
                   for t in (kw.get("tools") or [])):
                return NS(content=[NS(type="text", text="Playing at 7:40pm")],
                          usage=NS(input_tokens=0, output_tokens=0))
            self.n += 1
            if self.n == 1:
                return NS(content=[
                    NS(type="text", text="1. Find showtimes\n2. Check the wallet"),
                    # Over Mom's $100 cap, so the verdict is 'modify', not 'deny'.
                    NS(type="tool_use", id="b", name="check_wallet",
                       input={"amount": 140, "reason": "dinner and a movie for 4"}),
                ], usage=NS(input_tokens=4135, output_tokens=548))
            return NS(content=[NS(type="text", text="Forty each covers tickets.")],
                      usage=NS(input_tokens=800, output_tokens=90))

    async def scenario():
        mem = SemanticMemory(Path(tempfile.mkdtemp()) / "m")
        dad = AgentLoop(Context(memory=mem))
        dad._client = type("FC", (), {"messages": FakeMessages()})()

        app = DadApp(dad)
        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one("#input").value = "dinner and odyssey for 4"
            await pilot.press("enter")
            for _ in range(80):
                await asyncio.sleep(0.05)
                if not app.query_one("#input").disabled:
                    break
            await pilot.pause()

            cards = app.query(".review-card")
            assert cards, "Mom rewriting a call should leave a review card on the canvas"
            text = _strip(cards.first().content)
            assert "check_wallet" in text, f"the card should name the call: {text}"
            assert "100" in text, f"the card should give Mom's reason: {text}"
        print("PASS: Mom rewriting a call renders a card instead of crashing")

    asyncio.run(scenario())


def test_review_card_builds_standalone():
    """Cheap guard on the class itself, so a lost definition fails fast at
    import time rather than only when governance happens to fire."""
    card = ReviewCard("adjusted", "check_wallet", "Mom capped this at $100.")
    text = _strip(card.content)
    assert "MOM ADJUSTED" in text
    assert "check_wallet" in text
    assert KeyBar.ADMIN_KEYS != KeyBar.KEYS, "admin needs its own key set"
    print("PASS: ReviewCard exists and renders")


if __name__ == "__main__":
    test_review_card_builds_standalone()
    test_key_bar_is_actually_on_screen()
    test_mom_rewriting_a_call_does_not_crash_the_turn()
