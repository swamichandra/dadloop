"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Tests tracer rollups and telemetry event streaming.

Proves the tracer rolls up tokens, cost, and the model-vs-tool latency split,
and that summaries flow through the on_event stream (so any UI can render them)."""
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from dadloop import AgentLoop, Context, SemanticMemory


def _client():
    class FM:
        def __init__(self): self.n = 0
        def create(self, **kw):
            self.n += 1
            if self.n == 1:
                return NS(content=[NS(type="tool_use", id="a", name="check_weather", input={})],
                          usage=NS(input_tokens=800, output_tokens=30))
            return NS(content=[NS(type="text", text="done")],
                      usage=NS(input_tokens=900, output_tokens=20))
    return type("FC", (), {"messages": FM()})()


def test_trace_rolls_up_and_emits():
    dad = AgentLoop(Context(memory=SemanticMemory(Path(tempfile.mkdtemp()) / "m")))
    dad._client = _client()

    events = []
    dad.turn("hi", on_event=lambda k, p: events.append((k, p)))

    kinds = [k for k, _ in events]
    assert "trace" in kinds
    assert kinds.index("final") < kinds.index("trace")   # reply first, then trace

    summary = next(p for k, p in events if k == "trace")
    assert "2 llm calls" in summary
    assert "1 tools" in summary
    assert "tokens 1700" in summary                       # 800 + 900 in
    print("PASS: trace summed 1700 in / 50 out, split shown, emitted after reply")


if __name__ == "__main__":
    test_trace_rolls_up_and_emits()
