"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Tests Mom vetoes tool calls per thermostat policy rules.

Proves Mom is a real controller: she reviews every proposed tool call and
can veto it before it runs, per the seasonal thermostat rule in Dad's
constitution (74F cool in summer, 70F heat in winter)."""
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from datetime import date
from dadloop import AgentLoop, Context, SemanticMemory


def _fake_client(tool_name, tool_input):
    class FM:
        def __init__(self): self.n = 0
        def create(self, **kw):
            self.n += 1
            if self.n == 1:
                return NS(content=[NS(type="tool_use", id="x",
                                      name=tool_name, input=tool_input)])
            return NS(content=[NS(type="text", text="okay.")])
    return type("FC", (), {"messages": FM()})()


def test_mom_vetoes_over_seasonal_cap():
    summer = date.today().month in {6, 7, 8, 9}
    cap = 74 if summer else 70
    over_cap = cap + 1

    tmp = Path(tempfile.mkdtemp()) / "m"
    dad = AgentLoop(Context(memory=SemanticMemory(tmp)))
    dad._client = _fake_client("set_thermostat", {"setpoint": over_cap})

    events = []
    dad.turn(f"set it to {over_cap}", on_event=lambda k, p: events.append((k, p)))

    controller = [e for e in events if e[0] == "controller"]
    assert controller and controller[0][1][1] == "deny"
    assert dad.ctx.state.thermostat_setpoint == 68   # default never changed
    print(f"PASS: Mom vetoed {over_cap}°F (cap is {cap}°F this season)")


def test_mom_allows_at_seasonal_cap():
    summer = date.today().month in {6, 7, 8, 9}
    cap = 74 if summer else 70

    tmp = Path(tempfile.mkdtemp()) / "m"
    dad = AgentLoop(Context(memory=SemanticMemory(tmp)))
    dad._client = _fake_client("set_thermostat", {"setpoint": cap})

    events = []
    dad.turn(f"set it to {cap}", on_event=lambda k, p: events.append((k, p)))

    controller = [e for e in events if e[0] == "controller"]
    assert not controller, "Mom should allow exactly the cap, not just under it"
    assert dad.ctx.state.thermostat_setpoint == cap
    print(f"PASS: Mom allowed {cap}°F (right at this season's cap)")


if __name__ == "__main__":
    test_mom_vetoes_over_seasonal_cap()
    test_mom_allows_at_seasonal_cap()
