"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Tests TUI canvas keyboard navigation and focus behavior.

Proves the main screen is a navigable knowledge-work canvas, not a chat log.

This test exists because a previous version shipped with NOTHING focusable
except the input box — you literally could not Tab to anything. Every claim
here is driven by actual keypresses, not by inspecting widget state.
"""
import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from textual.widgets import Collapsible
from textual.widgets._collapsible import CollapsibleTitle
from dadloop import AgentLoop, Context, SemanticMemory
from dadloop.tui import DadApp
from dadloop.core import tools as tk


def _dad_with_two_steps():
    class FM:
        def __init__(self): self.n = 0
        def create(self, **kw):
            self.n += 1
            if self.n == 1:
                return NS(content=[
                    NS(type="text", text="1. Pull up hosting\n2. Check the grill"),
                    NS(type="tool_use", id="a", name="load_skill", input={"name": "hosting"}),
                    NS(type="tool_use", id="b", name="check_grill", input={}),
                ], usage=NS(input_tokens=900, output_tokens=40))
            return NS(content=[NS(type="text", text="Propane's out.")],
                      usage=NS(input_tokens=800, output_tokens=30))

    dad = AgentLoop(Context(memory=SemanticMemory(Path(tempfile.mkdtemp()) / "m")))
    dad._client = type("FC", (), {"messages": FM()})()
    return dad


def test_canvas_is_keyboard_navigable():
    async def scenario():
        tk.WORLD.update(propane="empty")
        app = DadApp(_dad_with_two_steps())

        async with app.run_test() as pilot:
            app.query_one("#input").value = "ready?"
            await pilot.press("enter")
            for _ in range(50):
                await asyncio.sleep(0.05)
                if not app.query_one("#input").disabled:
                    break
            await pilot.pause()

            # A reasoning step per tool call, on the canvas.
            steps = list(app.query(Collapsible))
            assert len(steps) == 2, f"expected 2 reasoning steps, got {len(steps)}"

            # The regression this test exists for: things must be focusable.
            focusable = [w for w in app.query("*") if w.can_focus]
            assert len(focusable) > 2, "nothing to navigate to — the old bug is back"

            # Tab must actually land on a reasoning step.
            reached = []
            for _ in range(6):
                await pilot.press("tab")
                if isinstance(app.focused, CollapsibleTitle):
                    reached.append(str(app.focused.label))
            assert reached, "Tab never reached a reasoning step"

            # Enter expands the focused step.
            title = app.query(CollapsibleTitle).first()
            title.focus()
            await pilot.pause()
            assert title.parent.collapsed is True
            await pilot.press("enter")
            await pilot.pause()
            assert title.parent.collapsed is False, "Enter did not expand the step"

            # Expand-all / collapse-all. F-keys, not ctrl-combos: see the
            # focused-input test below for why.
            await pilot.press("f3")
            await pilot.pause()
            assert all(c.collapsed for c in app.query(Collapsible))
            await pilot.press("f2")
            await pilot.pause()
            assert all(not c.collapsed for c in app.query(Collapsible))

            # Skills assembled are visible on the canvas, not only in admin.
            assert app.query(".skill-marker"), "skill assembly not shown on the canvas"

        print("PASS: canvas is keyboard navigable — Tab reaches steps, Enter expands, "
              "f2/f3 work, skill assembly visible")

    asyncio.run(scenario())




def test_keys_work_while_the_input_has_focus():
    """The Input widget claims ctrl+a/ctrl+e/ctrl+c/enter for line editing, and a
    focused Input WINS over app-level bindings. An earlier version bound
    expand-all to ctrl+e, which meant the key was silently dead whenever the user
    was typing — which is always. This drives the keys with the Input focused,
    the state the app is actually in after every turn.
    """
    async def scenario():
        from textual.widgets import Input
        from dadloop.tui import AdminScreen

        app = DadApp(_dad_with_two_steps())
        async with app.run_test() as pilot:
            app.query_one("#input").value = "ready?"
            await pilot.press("enter")
            for _ in range(50):
                await asyncio.sleep(0.05)
                if not app.query_one("#input").disabled:
                    break
            await pilot.pause()

            assert isinstance(app.focused, Input), "input should hold focus after a turn"

            await pilot.press("f2")
            await pilot.pause()
            assert all(not c.collapsed for c in app.query(Collapsible)), "f2 did not expand"

            await pilot.press("f3")
            await pilot.pause()
            assert all(c.collapsed for c in app.query(Collapsible)), "f3 did not collapse"

            await pilot.press("f4")
            await pilot.pause()
            assert isinstance(app.screen, AdminScreen), "f4 did not open admin"

        print("PASS: f2/f3/f4 all fire with the Input focused")

    asyncio.run(scenario())


if __name__ == "__main__":
    test_canvas_is_keyboard_navigable()
    test_keys_work_while_the_input_has_focus()
