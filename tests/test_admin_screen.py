"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Tests admin screen toggle and harness data display.

Proves the admin screen: toggled via f2, shows six sections of real
harness data (not a live feed — a manifest of what the harness has), and
correctly distinguishes 'skills loaded this session' from the full catalog."""
import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from dadloop import AgentLoop, Context, SemanticMemory
from dadloop.tui import DadApp, AdminScreen


def test_admin_screen_toggles_and_shows_real_data():
    async def scenario():
        class FM:
            def __init__(self): self.n = 0
            def create(self, **kw):
                self.n += 1
                if self.n == 1:
                    return NS(content=[
                        NS(type="tool_use", id="a", name="load_skill", input={"name": "hosting"}),
                    ], usage=NS(input_tokens=500, output_tokens=20))
                return NS(content=[NS(type="text", text="Let's plan it.")],
                          usage=NS(input_tokens=400, output_tokens=15))

        mem = SemanticMemory(Path(tempfile.mkdtemp()) / "m")
        mem.remember("grievances", "thermostat pushed past cap")
        dad = AgentLoop(Context(memory=mem))
        dad._client = type("FC", (), {"messages": FM()})()

        app = DadApp(dad)
        async with app.run_test() as pilot:
            app.query_one("#input").value = "host something"
            await pilot.press("enter")
            for _ in range(50):
                await asyncio.sleep(0.05)
                if not app.query_one("#input").disabled:
                    break

            assert "hosting" in app._skills_loaded

            await pilot.press("f4")
            await pilot.pause()
            assert isinstance(app.screen, AdminScreen), "f4 should push the admin screen"

            admin = app.screen
            assert "check_weather" in admin._tools_text()          # a real tool present
            # Assert the *distinction*, not the markup — a loaded skill must be
            # marked differently from an unloaded one. Pinning the colour string
            # makes the test break every time the theme changes, which teaches
            # you nothing.
            skills = admin._skills_text()
            assert "● hosting" in skills.replace("[$skill]", "").replace("[/]", "")
            assert "○ grilling" in skills.replace("[dim]", "").replace("[/dim]", "")
            assert "Steady AND clever" in admin._constitution_text()   # real rule text
            assert "$100" in admin._mom_text()                      # real policy value
            assert "grievances.jsonl" in admin._memory_text()        # real file on disk
            assert "tokens:" in admin._observability_text()          # real session totals

            await pilot.press("f4")
            await pilot.pause()
            assert not isinstance(app.screen, AdminScreen), "f4 should pop back to chat"

        print("PASS: admin screen toggles via f4 and all six sections show real data")

    asyncio.run(scenario())


def test_admin_sections_are_keyboard_navigable():
    """The admin boxes must be focusable and scrollable — the constitution
    and skills lists both overflow, and a box you can't scroll is a box you
    can't read."""
    async def scenario():
        dad = AgentLoop(Context(memory=SemanticMemory(Path(tempfile.mkdtemp()) / "m")))
        app = DadApp(dad)
        async with app.run_test() as pilot:
            await pilot.press("f4")
            await pilot.pause()

            focusable = [w for w in app.screen.query("*") if w.can_focus]
            assert len(focusable) == 6, f"expected 6 focusable sections, got {len(focusable)}"

            # Tab reaches a section.
            await pilot.press("tab")
            assert app.focused is not None
            assert "admin-box" in app.focused.classes

            # Arrow keys scroll the focused (long) section.
            const_box = list(app.screen.query(".admin-box"))[2]
            const_box.focus()
            await pilot.pause()
            before = const_box.scroll_offset.y
            for _ in range(5):
                await pilot.press("down")
            await pilot.pause()
            assert const_box.scroll_offset.y > before, "arrow keys did not scroll the section"

        print("PASS: admin sections are focusable, Tab-navigable, and arrow-scrollable")

    asyncio.run(scenario())




def test_no_admin_pane_collapses_to_zero():
    """Grid row-spans have to add up. An earlier version spanned
    constitution(3) + tools(2) + skills(2) + three singles = 10 cells in a
    9-cell grid, and Textual silently squeezed the telemetry pane to 0x0 — it
    was simply not there, with no error. Measure, don't eyeball.
    """
    async def scenario():
        for size in [(110, 38), (150, 45), (90, 30)]:
            dad = AgentLoop(Context(memory=SemanticMemory(Path(tempfile.mkdtemp()) / "m")))
            app = DadApp(dad)
            async with app.run_test(size=size) as pilot:
                await pilot.press("f4")
                await pilot.pause()

                boxes = list(app.screen.query(".admin-box"))
                assert len(boxes) == 6, f"expected 6 panes, got {len(boxes)}"

                for b in boxes:
                    assert b.size.width > 0, f"{b.id} collapsed to zero width at {size}"
                    assert b.content_size.height > 0, f"{b.id} collapsed to zero height at {size}"

        print("PASS: all six admin panes have real size at every terminal size tested")

    asyncio.run(scenario())


if __name__ == "__main__":
    test_admin_screen_toggles_and_shows_real_data()
    test_admin_sections_are_keyboard_navigable()
    test_no_admin_pane_collapses_to_zero()
