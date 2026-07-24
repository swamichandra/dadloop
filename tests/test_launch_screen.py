"""Author: Swami Chandrasekaran
Last Modified: 2026-07-18
Purpose: Tests the launch screen renders, always exits, and stays out of the way.

The launch screen is the one part of the app that sits between the user and the
thing they came for. That makes two properties non-negotiable:

  1. It always lets you out. Any key goes through to the work surface. A landing
     page that swallows a keystroke and leaves you staring at it is worse than
     no landing page at all.
  2. It never appears under test. Every TUI test drives the canvas with synthetic
     keys; a modal screen on top would eat them and fail tests that have nothing
     to do with this feature. The skip is automatic (App.is_headless), so nobody
     writing a future test has to know this screen exists.
"""

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dadloop.launch import LaunchScreen, block_text
from dadloop.tui import DadApp


def test_block_headline_renders():
    """The hand-built alphabet covers the wordmark, and every glyph row lines up
    — a short row shears the whole headline when the letters are joined."""
    rows = block_text("dadloop")
    assert len(rows) == 5, "headline should be five rows tall"
    assert all(r.strip() for r in rows), "no row of the wordmark should be blank"
    assert "█" in rows[0], "expected block glyphs"

    # An unknown character must degrade to a space, never raise — decoration
    # should not be able to stop the app from starting.
    assert block_text("dad!!") is not None
    print("PASS: block headline renders and tolerates unknown glyphs")


def test_launch_screen_shows_the_real_pitch():
    """The sample card should show the harness doing its actual job — a real
    constraint being reconciled — not a generic chat exchange."""
    screen = LaunchScreen(online=True)
    sample = re.sub(r"\[[^]]*\]", "", screen._sample())

    assert "forty bucks" in sample.lower(), "sample should pose a real constraint"
    assert "Mom capped the spend" in sample, "sample should show governance acting"
    assert "assembled skill" in sample, "sample should show a skill being loaded"

    # The offline state must be honest on the landing page itself, not one
    # screen later — that copy lives in the footer and the input placeholder now.
    online_foot = re.sub(r"\[[^]]*\]", "", screen._foot())
    offline = LaunchScreen(online=False)
    offline_foot = re.sub(r"\[[^]]*\]", "", offline._foot())
    offline_hint = re.sub(r"\[[^]]*\]", "", offline._placeholder())
    assert "ENTER" in online_foot.upper() or "ask" in online_foot.lower()
    combined = (offline_foot + " " + offline_hint).lower()
    assert "api key" in combined or "api_key" in combined, \
        "offline should say the key is missing here, not one screen later"
    print("PASS: launch screen pitches the real product, and is honest when offline")


def test_typing_on_the_landing_page_starts_the_first_turn():
    """The landing page is the first interaction, not a gate in front of it.

    Whatever is typed there must arrive on the canvas as the opening question —
    if the user has to retype it after the screen changes, the page was a
    speed bump wearing a pitch.
    """
    async def scenario():
        app = DadApp()
        async with app.run_test(size=(120, 46)) as pilot:
            screen = LaunchScreen(online=True)
            captured = {}
            app.push_screen(screen, lambda result: captured.update(text=result))
            await pilot.pause()

            screen.query_one("#launch-input").value = "twelve people saturday"
            await pilot.press("enter")
            await pilot.pause()

            assert not isinstance(app.screen, LaunchScreen), \
                "submitting should leave the landing page"
            assert captured.get("text") == "twelve people saturday", \
                f"the typed question should be handed on, got {captured!r}"
        print("PASS: typing on the landing page carries into the first turn")

    asyncio.run(scenario())


def test_empty_submit_and_escape_both_just_go_in():
    """Pressing Enter on an empty box means 'take me in' — not an error, and
    not a scolding. Escape does the same."""
    async def scenario():
        app = DadApp()
        async with app.run_test(size=(120, 46)) as pilot:
            for how in ("enter", "escape"):
                captured = {}
                app.push_screen(LaunchScreen(online=True),
                                lambda r: captured.update(text=r))
                await pilot.pause()
                await pilot.press(how)
                await pilot.pause()

                assert not isinstance(app.screen, LaunchScreen), \
                    f"'{how}' left the user stuck on the landing page"
                assert captured.get("text") is None, \
                    f"'{how}' on an empty box should start no turn, got {captured!r}"
        print("PASS: empty Enter and Escape both go straight in, starting no turn")

    asyncio.run(scenario())


def test_launch_screen_is_skipped_under_test():
    """Headless runs must not get the launch screen, or every other TUI test
    breaks on a modal it never asked for."""
    async def scenario():
        app = DadApp()
        async with app.run_test(size=(120, 46)) as pilot:
            await pilot.pause()
            assert not isinstance(app.screen, LaunchScreen), \
                "launch screen should be skipped in headless/test mode"
            assert app.SHOW_LAUNCH is False, "SHOW_LAUNCH should be False under test"
            assert app.query_one("#input").has_focus, "prompt should have focus"
        print("PASS: launch screen stays out of the way under test")

    asyncio.run(scenario())




def test_action_taken_line_names_what_dad_did():
    """Dad's reply says what he concluded; this line says what he DID.

    For an agent that can spend money and change the thermostat, "did it just
    look things up, or did it act?" should be answerable at a glance rather than
    by reading the whole transcript.
    """
    import re
    import tempfile
    from pathlib import Path
    from types import SimpleNamespace as NS

    from dadloop import AgentLoop, Context, SemanticMemory

    class FakeMessages:
        def __init__(self): self.n = 0

        def create(self, **kw):
            if any(t.get("type", "").startswith("web_search")
                   for t in (kw.get("tools") or [])):
                return NS(content=[NS(type="text", text="Sunny")],
                          usage=NS(input_tokens=0, output_tokens=0))
            self.n += 1
            if self.n == 1:
                return NS(content=[
                    NS(type="text", text="1. Check budget\n2. Load hosting"),
                    NS(type="tool_use", id="a", name="check_wallet",
                       input={"amount": 40, "reason": "food"}),
                    NS(type="tool_use", id="b", name="load_skill",
                       input={"name": "hosting"}),
                    NS(type="tool_use", id="c", name="set_thermostat",
                       input={"setpoint": 78}),      # over the cap — Mom blocks
                ], usage=NS(input_tokens=2000, output_tokens=100))
            return NS(content=[NS(type="text", text="Forty feeds ten.")],
                      usage=NS(input_tokens=500, output_tokens=40))

    async def scenario():
        mem = SemanticMemory(Path(tempfile.mkdtemp()) / "m")
        dad = AgentLoop(Context(memory=mem))
        dad._client = type("FC", (), {"messages": FakeMessages()})()

        app = DadApp(dad)
        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one("#input").value = "twelve people saturday"
            await pilot.press("enter")
            for _ in range(60):
                await asyncio.sleep(0.05)
                if not app.query_one("#input").disabled:
                    break
            await pilot.pause()

            cards = app.query(".action-taken")
            assert cards, "a turn that ran tools should produce an ACTION TAKEN line"
            text = re.sub(r"\[[^]]*\]", "", cards.first().content)

            assert "ACTION TAKEN" in text
            assert "check" in text, f"should count the checks run: {text}"
            assert "hosting" in text, f"should name the skill assembled: {text}"
            assert "Mom" in text, f"governance should be visible in the summary: {text}"
        print("PASS: ACTION TAKEN names checks, skills, and Mom's interventions")

    asyncio.run(scenario())


def test_landing_page_prompt_is_visible_on_short_terminals():
    """The box you are told to type into must be on screen.

    The full page — wordmark, headline, subhead, a fourteen-row sample card,
    input and hint — needs about forty rows. In a 24-row terminal the input was
    landing at y=29, below the fold, on a page whose entire purpose is "type
    here". Decoration is shed until the prompt and the way out both fit.
    """
    async def scenario():
        for height in (16, 20, 24, 30, 44):
            app = DadApp()
            async with app.run_test(size=(120, height)) as pilot:
                screen = LaunchScreen(online=True)
                app.push_screen(screen)
                await pilot.pause()

                box = screen.query_one("#launch-input").region
                foot = screen.query_one("#launch-foot").region

                assert box.height > 0, f"input collapsed at {height} rows"
                assert box.y + box.height <= height, (
                    f"at {height} rows the prompt is off-screen at y={box.y}")
                assert foot.y + foot.height <= height, (
                    f"at {height} rows the exit hint is off-screen at y={foot.y}")
        print("PASS: the landing page prompt stays on screen when space is tight")

    asyncio.run(scenario())


if __name__ == "__main__":
    test_block_headline_renders()
    test_launch_screen_shows_the_real_pitch()
    test_typing_on_the_landing_page_starts_the_first_turn()
    test_empty_submit_and_escape_both_just_go_in()
    test_launch_screen_is_skipped_under_test()
    test_action_taken_line_names_what_dad_did()
    test_landing_page_prompt_is_visible_on_short_terminals()
