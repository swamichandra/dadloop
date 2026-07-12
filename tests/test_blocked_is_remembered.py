"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Tests that blocked governance actions are filed to memory.

A governance system that forgets every blocked request is a bad governance
system. When Mom denies a call, the ATTEMPT must still be filed to memory —
otherwise a vetoed action leaves no record and can't inform later sessions.

This was a real bug: grievance-filing lived inside set_thermostat(), and Mom's
deny short-circuits before the tool runs, so vetoed attempts vanished.
"""
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from dadloop import AgentLoop, Context, SemanticMemory
from dadloop.core.agent import _system_prompt


def test_blocked_call_is_filed_and_survives_restart():
    root = Path(tempfile.mkdtemp()) / "m"

    class FM:
        def __init__(self): self.n = 0
        def create(self, **kw):
            self.n += 1
            if self.n == 1:
                return NS(content=[NS(type="tool_use", id="a", name="set_thermostat",
                                      input={"setpoint": 78})],
                          usage=NS(input_tokens=400, output_tokens=20))
            return NS(content=[NS(type="text", text="Fine.")],
                      usage=NS(input_tokens=300, output_tokens=10))

    # Session 1 — the attempt gets vetoed.
    dad = AgentLoop(Context(memory=SemanticMemory(root)))
    dad._client = type("FC", (), {"messages": FM()})()
    events = []
    dad.turn("set it to 78", on_event=lambda k, p: events.append((k, p)))

    assert any(k == "controller" and p[1] == "deny" for k, p in events), "Mom should veto 78"

    # The blocked attempt must be on disk even though the tool never ran.
    filed = SemanticMemory(root).recall("grievances")
    assert filed, "a blocked call left NO record — the bug is back"
    assert "set_thermostat" in filed[0].text

    # Session 2 — fresh process, and it comes back unprompted.
    fresh = Context(memory=SemanticMemory(root))
    assert "set_thermostat" in _system_prompt(fresh), \
        "the blocked attempt did not carry into a new session"

    print("PASS: a vetoed call is filed to memory and resurfaces in the next session")


if __name__ == "__main__":
    test_blocked_call_is_filed_and_survives_restart()
