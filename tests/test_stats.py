"""Author: Swami Chandrasekaran
Last Modified: 2026-07-17
Purpose: Tests session totals and cross-session stats accumulation.

Proves the two data sources behind the stats panel: session totals
accumulate correctly across turns (not just per-turn), and the cross-session
ledger reads real counts from disk, independent of the current session."""
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from dadloop import AgentLoop, Context, SemanticMemory


def test_session_totals_accumulate_across_turns():
    dad = AgentLoop(Context(memory=SemanticMemory(Path(tempfile.mkdtemp()) / "m")))

    class FM:
        def __init__(self): self.n = 0
        def create(self, **kw):
            # check_weather now runs a nested web_search model call. It's a
            # separate concern from the outer loop being measured here, so the
            # fake answers those inline without consuming a scripted turn.
            if any(t.get("type", "").startswith("web_search") for t in (kw.get("tools") or [])):
                return NS(content=[NS(type="text", text="Clear, 58°F.")],
                          usage=NS(input_tokens=0, output_tokens=0))
            self.n += 1
            if self.n == 1:
                return NS(content=[NS(type="tool_use", id="a", name="check_weather", input={})],
                          usage=NS(input_tokens=800, output_tokens=30))
            if self.n == 2:
                return NS(content=[NS(type="text", text="58 out.")],
                          usage=NS(input_tokens=900, output_tokens=20))
            if self.n == 3:
                return NS(content=[NS(type="tool_use", id="b", name="check_grill", input={})],
                          usage=NS(input_tokens=400, output_tokens=10))
            return NS(content=[NS(type="text", text="Grill's fine.")],
                      usage=NS(input_tokens=300, output_tokens=15))

    dad._client = type("FC", (), {"messages": FM()})()

    dad.turn("weather?")
    dad.turn("grill ok?")

    t = dad.tracer.totals
    assert t.turns == 2
    assert t.llm_calls == 4
    assert t.tool_calls == 2
    assert t.tokens_in == 800 + 900 + 400 + 300
    assert t.tokens_out == 30 + 20 + 10 + 15
    assert t.cost > 0
    print(f"PASS: totals accumulated over 2 turns — {t.turns} turns, "
          f"{t.tokens_in}->{t.tokens_out} tokens, ~${t.cost:.4f}")


def test_ledger_reads_cross_session_counts_from_disk():
    tmp = Path(tempfile.mkdtemp()) / "m"

    # Session 1: file some memory, then "close" it (just drop the reference).
    mem1 = SemanticMemory(tmp)
    mem1.remember("grievances", "thermostat touched")
    mem1.remember("lessons", "tofu needs 5 min a side")
    mem1.remember("rulings", "$30 for propane: approved")

    # Session 2: a brand new SemanticMemory pointed at the same disk root —
    # the ledger should see what session 1 wrote, with no session 2 activity.
    mem2 = SemanticMemory(tmp)
    ledger = mem2.ledger()

    assert ledger["grievances"] == 1
    assert ledger["lessons"] == 1
    assert ledger["rulings"] == 1
    assert ledger["people"] == 0
    print(f"PASS: ledger read cross-session counts from disk — {ledger}")


if __name__ == "__main__":
    test_session_totals_accumulate_across_turns()
    test_ledger_reads_cross_session_counts_from_disk()
