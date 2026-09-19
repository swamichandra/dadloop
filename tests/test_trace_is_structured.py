"""Author: Mike Bell
Last Modified: 2026-09-18
Purpose: Tests the journal's trace event carries the numbers as fields, not just prose.

Proves that round trips, model time, tool time, wall clock, tokens, and cost
land in the journal as structured fields on the trace event. Before this the
journal stored only the formatted summary string, so anything comparing turns
(a benchmark, the console, a before/after on a skill rewrite) had to regex the
prose back apart and broke the moment the wording moved."""
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from dadloop import AgentLoop, Context, SemanticMemory
from dadloop.core.trace import cost_for

MODEL = "claude-haiku-4-5-20251001"


def _client():
    class FM:
        def __init__(self): self.n = 0
        def create(self, **kw):
            if any(t.get("type", "").startswith("web_search") for t in (kw.get("tools") or [])):
                return NS(model=MODEL, content=[NS(type="text", text="Clear, 58°F.")],
                          usage=NS(input_tokens=0, output_tokens=0))
            self.n += 1
            if self.n == 1:
                return NS(model=MODEL,
                          content=[NS(type="tool_use", id="a", name="check_weather", input={})],
                          usage=NS(input_tokens=800, output_tokens=30))
            return NS(model=MODEL, content=[NS(type="text", text="done")],
                      usage=NS(input_tokens=900, output_tokens=20))
    return type("FC", (), {"messages": FM()})()


def test_trace_event_carries_structured_numbers():
    dad = AgentLoop(Context(memory=SemanticMemory(Path(tempfile.mkdtemp()) / "m")))
    dad._client = _client()
    dad.turn("what's the weather")

    traces = [r for r in dad.journal.read_all() if r.get("kind") == "trace"]
    assert len(traces) == 1, f"expected one trace event, got {len(traces)}"
    t = traces[0]

    assert "summary" in t, "the human-readable line must still be there for the console"
    assert t["llm_calls"] == 2, t
    assert t["tool_calls"] == 1, t
    assert t["tokens_in"] == 1700 and t["tokens_out"] == 50, t
    assert t["cost"] == cost_for(MODEL, 1700, 50), t
    assert t["unpriced_calls"] == 0, t
    assert t["models"] == [MODEL], t
    for key in ("total_ms", "llm_ms", "tool_ms"):
        assert isinstance(t[key], (int, float)) and t[key] >= 0, (key, t)
    assert t["llm_ms"] + t["tool_ms"] <= t["total_ms"] + 1, "children cannot outlast the turn"
    print("PASS: trace event has llm_calls, tool_calls, tokens, cost, models, and the ms split as fields")


def test_unpriced_model_is_visible_in_the_fields():
    dad = AgentLoop(Context(memory=SemanticMemory(Path(tempfile.mkdtemp()) / "m")))
    class FM:
        def create(self, **kw):
            return NS(model="claude-someday-9", content=[NS(type="text", text="hi")],
                      usage=NS(input_tokens=10, output_tokens=5))
    dad._client = type("FC", (), {"messages": FM()})()
    dad.turn("hi")
    t = next(r for r in dad.journal.read_all() if r.get("kind") == "trace")
    assert t["unpriced_calls"] == 1 and t["cost"] == 0.0 and t["models"] == ["claude-someday-9"], t
    print("PASS: an unpriced call is counted in the fields, with the model named")


if __name__ == "__main__":
    test_trace_event_carries_structured_numbers()
    test_unpriced_model_is_visible_in_the_fields()
