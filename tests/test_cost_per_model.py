"""Author: Mike Bell
Last Modified: 2026-09-18
Purpose: Tests the dollar figure is priced for the model that actually answered.

Proves the tracer prices tokens at the rate of the model the API reports it
ran, not a single hard-coded Sonnet rate. The old constants ($3/$15) were
Sonnet 4.6 prices; the code's default is Sonnet 5 ($2/$10) and the example
.env pins Haiku 4.5 ($1/$5), so every dollar figure on screen was wrong by
1.5x to 3x. And a model the table does not know must produce no dollar figure
at all rather than a confident wrong one — the same rule as everything else
the harness shows: derived, never asserted."""
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from dadloop import AgentLoop, Context, SemanticMemory

MTOK = 1_000_000


def _client(model: str, tokens_in: int, tokens_out: int):
    class FM:
        def create(self, **kw):
            return NS(model=model,
                      content=[NS(type="text", text="done")],
                      usage=NS(input_tokens=tokens_in, output_tokens=tokens_out))
    return type("FC", (), {"messages": FM()})()


def _trace_for(model: str, tokens_in: int, tokens_out: int) -> str:
    dad = AgentLoop(Context(memory=SemanticMemory(Path(tempfile.mkdtemp()) / "m")))
    dad._client = _client(model, tokens_in, tokens_out)
    events = []
    dad.turn("hi", on_event=lambda k, p: events.append((k, p)))
    return next(p for k, p in events if k == "trace")


def test_haiku_turn_is_priced_at_haiku_rates():
    # A dated id is what the API actually echoes back for this model.
    summary = _trace_for("claude-haiku-4-5-20251001", MTOK, 0)
    assert "$1.0000" in summary, f"1M Haiku input tokens should cost $1.00, got: {summary}"
    print("PASS: a Haiku turn is priced at $1/MTok in, not the old Sonnet $3")


def test_sonnet5_output_is_priced_at_sonnet5_rates():
    summary = _trace_for("claude-sonnet-5", 0, MTOK)
    assert "$10.0000" in summary, f"1M Sonnet 5 output tokens should cost $10.00, got: {summary}"
    print("PASS: Sonnet 5 output priced at $10/MTok, not the old $15")


def test_unknown_model_gets_no_dollar_figure():
    summary = _trace_for("claude-someday-9", MTOK, MTOK)
    assert "$" not in summary, f"an unknown model must not be given a made-up price: {summary}"
    assert "unpriced" in summary, f"the summary should say the turn is unpriced: {summary}"
    print("PASS: an unknown model id shows tokens and 'unpriced', never a guessed dollar figure")


def test_cache_tokens_are_priced_at_their_own_rates():
    from dadloop.core.trace import cost_for
    assert cost_for("claude-haiku-4-5", 0, 0, cache_read=MTOK) == 0.1, "cache reads are 10% of input"
    assert cost_for("claude-haiku-4-5", 0, 0, cache_write=MTOK) == 1.25, "cache writes are 125% of input"
    assert cost_for("nope", 1, 1) is None
    print("PASS: cache reads and writes carry their own rates; unknown model returns None")


if __name__ == "__main__":
    test_haiku_turn_is_priced_at_haiku_rates()
    test_sonnet5_output_is_priced_at_sonnet5_rates()
    test_unknown_model_gets_no_dollar_figure()
    test_cache_tokens_are_priced_at_their_own_rates()
