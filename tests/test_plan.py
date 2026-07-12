"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Tests plan parsing, matching, and unplanned call detection.

Proves the merged plan design: Dad states a plan up front (Cowork-style),
each matching tool call checks off the right step, and a tool call that
wasn't in the stated plan is appended live and visibly marked unplanned —
drift between stated intent and actual behavior is shown, never hidden."""
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from dadloop import AgentLoop, Context, SemanticMemory


def test_stated_plan_is_parsed_and_matched():
    class FM:
        def __init__(self): self.n = 0
        def create(self, **kw):
            self.n += 1
            if self.n == 1:
                return NS(content=[
                    NS(type="text", text="1. Check the grill\n2. Check the weather\n3. Decide"),
                    NS(type="tool_use", id="a", name="check_grill", input={}),
                    NS(type="tool_use", id="b", name="check_weather", input={}),
                ])
            return NS(content=[NS(type="text", text="Grill's fine, 58 out.")])

    dad = AgentLoop(Context(memory=SemanticMemory(Path(tempfile.mkdtemp()) / "m")))
    dad._client = type("FC", (), {"messages": FM()})()

    events = []
    dad.turn("ready?", on_event=lambda k, p: events.append((k, p)))

    plan = next(p for k, p in events if k == "plan")
    assert plan == ["Check the grill", "Check the weather", "Decide"]

    done = [p for k, p in events if k == "plan_step_done"]
    assert (0, "Check the grill", True) in done
    assert (1, "Check the weather", True) in done
    print("PASS: stated plan parsed, both tool calls matched their planned steps")


def test_unplanned_tool_call_is_appended_not_hidden():
    class FM:
        def __init__(self): self.n = 0
        def create(self, **kw):
            self.n += 1
            if self.n == 1:
                return NS(content=[
                    NS(type="text", text="1. Check the grill\n2. Check the weather"),
                    NS(type="tool_use", id="a", name="check_grill", input={}),
                    NS(type="tool_use", id="b", name="check_weather", input={}),
                    NS(type="tool_use", id="c", name="check_wallet",
                       input={"amount": 30, "reason": "propane"}),
                ])
            return NS(content=[NS(type="text", text="All set, and it's in budget.")])

    dad = AgentLoop(Context(memory=SemanticMemory(Path(tempfile.mkdtemp()) / "m")))
    dad._client = type("FC", (), {"messages": FM()})()

    events = []
    dad.turn("ready?", on_event=lambda k, p: events.append((k, p)))

    done = [p for k, p in events if k == "plan_step_done"]
    unplanned = [d for d in done if d[2] is False]
    assert unplanned, "the wallet check wasn't in the stated plan and should show up as unplanned"
    assert unplanned[0][1] == "Check wallet"
    print("PASS: unplanned tool call appended live and marked unplanned, not hidden")


def test_no_stated_plan_falls_back_to_thinking():
    class FM:
        def __init__(self): self.n = 0
        def create(self, **kw):
            self.n += 1
            if self.n == 1:
                return NS(content=[
                    NS(type="text", text="Let me take a look."),
                    NS(type="tool_use", id="a", name="check_weather", input={}),
                ])
            return NS(content=[NS(type="text", text="58 out.")])

    dad = AgentLoop(Context(memory=SemanticMemory(Path(tempfile.mkdtemp()) / "m")))
    dad._client = type("FC", (), {"messages": FM()})()

    events = []
    dad.turn("weather?", on_event=lambda k, p: events.append((k, p)))

    assert not any(k == "plan" for k, _ in events), "no numbered plan was stated"
    assert any(k == "thinking" for k, _ in events)
    print("PASS: unstated-plan case falls back to plain thinking, no fake plan invented")




def test_duplicate_step_text_resolves_to_the_right_row():
    """A plan can legitimately repeat a step ("check the budget" twice, for two
    purchases). The old code looked the step up with list.index() after matching,
    which returns the FIRST equal element — so the second call would tick the
    wrong row. match() now returns the index it actually used."""
    from dadloop.core.plan import Plan, PlanStep

    plan = Plan(steps=[
        PlanStep(text="Check the budget"),
        PlanStep(text="Check the grill"),
        PlanStep(text="Check the budget"),   # same text, different row
    ])

    i1, s1 = plan.match("check_wallet", {"amount": 20})
    assert i1 == 0 and s1.done

    i2, s2 = plan.match("check_grill", {})
    assert i2 == 1

    # The second budget check must tick row 2, not row 0 again.
    i3, s3 = plan.match("check_wallet", {"amount": 50})
    assert i3 == 2, f"expected row 2, got {i3} — duplicate-text bug is back"
    assert all(s.done for s in plan.steps)
    print("PASS: duplicate step text ticks the correct row")


if __name__ == "__main__":
    test_stated_plan_is_parsed_and_matched()
    test_unplanned_tool_call_is_appended_not_hidden()
    test_no_stated_plan_falls_back_to_thinking()
    test_duplicate_step_text_resolves_to_the_right_row()
