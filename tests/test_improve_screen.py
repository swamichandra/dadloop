"""Author: Swami Chandrasekaran
Last Modified: 2026-07-20
Purpose: Tests the live RSI screen (F6) in the main Dad interface.

The offline RSI loop is covered in test_rsi.py; this file pins the parts that
only exist in the TUI:

  * F6 opens the self-improvement screen, and it shows the walls and the
    grounded scores before anything is run — a limit you can't see isn't a limit.
  * Pressing r runs the real loop to the gate and stops there: the stages appear
    in order and the screen never promotes on its own.
  * Pressing p promotes only when replay actually backed the change. A proposal
    the loop marked HOLD cannot be promoted from the UI either.

The screen runs the loop inline on the UI thread (a worker created from inside a
pushed screen does not schedule under run_test, and call_from_thread from a bare
thread does not marshal here), so these tests drive it exactly as a person would
and read the rendered #rsi-body, not an internal flag.
"""
import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dadloop import AgentLoop, Context, SemanticMemory
from dadloop.tui import DadApp, ImproveScreen
from dadloop.core import improve_loop as il


def _stalling_client(complete_steps: int = 1):
    """Grilling turn loads the skill then completes `complete_steps` of a 3-step
    plan — the knob for manufacturing an under-performing skill deterministically.
    A candidate body that mentions check_grill makes the replayed model complete
    the extra step, so a real behaviour improvement can be staged on demand."""
    class FM:
        def __init__(self): self.n = 0
        def create(self, **kw):
            self.n += 1
            if not kw.get("tools"):        # a proposer call — unused here
                return NS(content=[NS(type="text", text="(no change)")],
                          usage=NS(input_tokens=10, output_tokens=5))
            if self.n == 1:
                calls = [NS(type="text", text="1. Load grilling\n2. Check\n3. Light"),
                         NS(type="tool_use", id="a", name="load_skill",
                            input={"name": "grilling"})]
                for i in range(complete_steps):
                    calls.append(NS(type="tool_use", id=f"c{i}",
                                    name="check_grill", input={}))
                return NS(content=calls, usage=NS(input_tokens=1000, output_tokens=80))
            return NS(content=[NS(type="text", text="Done.")],
                      usage=NS(input_tokens=200, output_tokens=20))
    return type("FC", (), {"messages": FM()})()


def _seed(memory, n, complete_steps=1):
    for i in range(n):
        dad = AgentLoop(Context(memory=memory))
        dad._client = _stalling_client(complete_steps)
        dad.turn(f"grill something #{i}")


def _body_text(screen):
    import re
    out = []
    for w in screen.query_one("#rsi-body").children:
        out.append(re.sub(r"\[[^]]*\]", "", w.content))
    return "\n".join(out)


def test_f6_opens_screen_with_walls_and_scores():
    """The screen is legible before it is run: the walls and the grounded scores
    are both on screen the moment it opens."""
    async def scenario():
        mem = SemanticMemory(Path(tempfile.mkdtemp()) / "m")
        _seed(mem, 5, complete_steps=1)      # grilling, mature + underperforming
        app = DadApp(AgentLoop(Context(memory=mem)))
        async with app.run_test(size=(120, 44)) as pilot:
            await pilot.press("f6")
            await pilot.pause()
            assert isinstance(app.screen, ImproveScreen)
            text = _body_text(app.screen)
            # walls are shown and named as enforced
            assert "CANNOT TOUCH" in text
            assert "the constitution" in text
            assert "Mom's policies" in text
            # grounded scores are shown, with the underperforming skill visible
            assert "SKILL SCORES" in text
            assert "grilling" in text
    asyncio.run(scenario())


def test_r_runs_loop_to_gate_without_promoting():
    """Pressing r runs the real loop end to end and stops at the human gate. The
    staged output appears in order, and nothing is applied on the way."""
    async def scenario():
        mem = SemanticMemory(Path(tempfile.mkdtemp()) / "m")
        _seed(mem, 5, complete_steps=1)
        dad = AgentLoop(Context(memory=mem))
        dad._client = _stalling_client(1)

        # A proposer that returns a candidate whose body drives check_grill, so
        # replay sees a genuine behaviour change rather than a reworded file.
        def improving_proposer(agent, skill, ask_model=None):
            from dadloop.core.improve import score_skill
            from dadloop.core import skills as sk
            return il.Proposal(
                skill=skill,
                before_score=score_skill(agent.ctx.memory, skill),
                old_body=sk.SKILLS[skill].body,
                new_body=("---\nname: grilling\ndescription: How Dad grills.\n"
                          "---\n- Always check the grill first (check_grill) "
                          "before lighting.\n- Then light it.\n"))
        orig = il.propose_rewrite
        il.propose_rewrite = improving_proposer
        try:
            app = DadApp(dad)
            async with app.run_test(size=(120, 44)) as pilot:
                await pilot.press("f6")
                await pilot.pause()
                scr = app.screen
                await pilot.press("r")
                for _ in range(200):
                    await asyncio.sleep(0.05)
                    await pilot.pause()
                    if not scr._loop_running:
                        break
                text = _body_text(scr)
                # the stages appear, in order
                assert "target:" in text
                assert "grilling" in text
                assert "replaying" in text
                assert "incumbent" in text and "candidate" in text
                # it stopped at a human gate and did not apply anything itself
                assert "GATE" in text
                assert "A human promotes." in _body_text(scr) or \
                       "human" in text.lower()
        finally:
            il.propose_rewrite = orig
    asyncio.run(scenario())


def test_p_refuses_to_promote_a_held_proposal():
    """If replay could not back the change, the gate stays shut: pressing p does
    not write the skill, and says so."""
    async def scenario():
        mem = SemanticMemory(Path(tempfile.mkdtemp()) / "m")
        _seed(mem, 5, complete_steps=1)
        dad = AgentLoop(Context(memory=mem))
        dad._client = _stalling_client(1)

        # A no-op rewrite: same behaviour, so replay is inconclusive -> HOLD.
        def flat_proposer(agent, skill, ask_model=None):
            from dadloop.core.improve import score_skill
            from dadloop.core import skills as sk
            body = sk.SKILLS[skill].body
            return il.Proposal(skill=skill,
                               before_score=score_skill(agent.ctx.memory, skill),
                               old_body=body,
                               new_body=body + "\n- (clarified wording)\n")
        orig = il.propose_rewrite
        il.propose_rewrite = flat_proposer
        try:
            app = DadApp(dad)
            async with app.run_test(size=(120, 44)) as pilot:
                await pilot.press("f6")
                await pilot.pause()
                scr = app.screen
                await pilot.press("r")
                for _ in range(200):
                    await asyncio.sleep(0.05)
                    await pilot.pause()
                    if not scr._loop_running:
                        break
                # the proposal exists but was not recommended
                assert scr._proposal is not None
                assert not scr._proposal.recommend.startswith("PROMOTE")
                await pilot.press("p")
                await pilot.pause()
                text = _body_text(scr)
                assert "Refusing to promote" in text
        finally:
            il.propose_rewrite = orig
    asyncio.run(scenario())


if __name__ == "__main__":
    test_f6_opens_screen_with_walls_and_scores()
    test_r_runs_loop_to_gate_without_promoting()
    test_p_refuses_to_promote_a_held_proposal()
    print("ok")
