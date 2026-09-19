"""Author: Swami Chandrasekaran
Last Modified: 2026-09-18
Purpose: Lightweight OpenTelemetry-style tracer for tokens, cost, and latency.

A tiny OpenTelemetry-shaped tracer — zero dependencies.

Not OpenTelemetry, but the same mental model: nested spans, each with a name,
attributes, and a duration. A turn is the root span; llm.call and tool.execute
are children. On close, the root prints a one-line summary — tokens, estimated
cost, and the model-vs-tool latency split, the numbers everyone underestimates
about agents.

Swapping this for the real OTel SDK is small: make `span()` return an SDK span
and forward attributes. The instrumentation points in agent.py don't change.

    with tracer.span("turn") as t:
        with tracer.span("llm.call") as s:
            s["tokens_in"], s["tokens_out"] = 1200, 80
        with tracer.span("tool.execute", tool="check_grill"):
            ...
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field

# List prices, $ per million tokens: (input, output, cache read). Cache writes
# are 1.25x input on every row. Keyed by model id prefix, so the dated ids the
# API echoes back ("claude-haiku-4-5-20251001") match their family. A model
# not in this table is UNPRICED: the summary says so and shows tokens only.
# A wrong dollar figure is worse than none, because it looks like a measurement.
# Snapshot of the public price list; when a rate changes, change it here.
_PRICES: dict[str, tuple[float, float, float]] = {
    "claude-fable-5-1": (10.0, 50.0, 0.25),
    "claude-fable-5": (10.0, 50.0, 1.0),
    "claude-opus-5": (5.0, 25.0, 0.5),
    "claude-opus-4-8": (5.0, 25.0, 0.5),
    "claude-opus-4-7": (5.0, 25.0, 0.5),
    "claude-opus-4-6": (5.0, 25.0, 0.5),
    "claude-sonnet-5": (2.0, 10.0, 0.2),
    "claude-sonnet-4-6": (3.0, 15.0, 0.3),
    "claude-haiku-4-5": (1.0, 5.0, 0.1),
}


def rates_for(model: str | None) -> tuple[float, float, float] | None:
    """The (in, out, cache-read) $/MTok for a model id, or None if unknown.
    Longest matching prefix wins, so "claude-sonnet-5" does not shadow a
    hypothetical "claude-sonnet-5-1" once that row exists."""
    if not model:
        return None
    best = None
    for key, rates in _PRICES.items():
        if model == key or model.startswith(key + "-"):
            if best is None or len(key) > len(best):
                best = key
    return _PRICES[best] if best else None


def cost_for(model: str | None, tokens_in: int, tokens_out: int, *,
             cache_read: int = 0, cache_write: int = 0) -> float | None:
    """Dollars for one call at the model's own rates, or None if unpriced."""
    rates = rates_for(model)
    if rates is None:
        return None
    rate_in, rate_out, rate_cache = rates
    return (tokens_in / 1e6 * rate_in
            + tokens_out / 1e6 * rate_out
            + cache_read / 1e6 * rate_cache
            + cache_write / 1e6 * rate_in * 1.25)


def turn_cost(spans) -> tuple[float, int]:
    """Sum the priced llm.call spans; count the ones with no known rate.
    Returns (dollars, unpriced_calls). Dollars covers only the priced calls, so
    a nonzero second element means the first is a floor, not a total."""
    total, unpriced = 0.0, 0
    for s in spans:
        if s.name != "llm.call":
            continue
        c = cost_for(s.attrs.get("model"),
                     s.attrs.get("tokens_in", 0), s.attrs.get("tokens_out", 0),
                     cache_read=s.attrs.get("cache_read", 0),
                     cache_write=s.attrs.get("cache_write", 0))
        if c is None:
            unpriced += 1
        else:
            total += c
    return total, unpriced


@dataclass
class Span:
    name: str
    attrs: dict = field(default_factory=dict)
    ms: float = 0.0
    children: list["Span"] = field(default_factory=list)

    def __setitem__(self, key, value):  # span["tokens_in"] = 1200
        self.attrs[key] = value


@dataclass
class SessionTotals:
    """Running totals across every turn this session — what the sidebar shows
    under 'how dadloop is performing'. Rebuilt from spans, not estimated."""
    turns: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    total_ms: float = 0.0
    llm_ms: float = 0.0
    tool_ms: float = 0.0
    cost: float = 0.0            # dollars across the PRICED calls only
    unpriced_calls: int = 0      # calls on a model with no known rate

    @property
    def avg_turn_ms(self) -> float:
        return self.total_ms / self.turns if self.turns else 0.0

    def add(self, root: "Span") -> None:
        spans = list(_walk(root))
        self.turns += 1
        self.llm_calls += sum(1 for s in spans if s.name == "llm.call")
        self.tool_calls += sum(1 for s in spans if s.name == "tool.execute")
        self.tokens_in += sum(s.attrs.get("tokens_in", 0) for s in spans)
        self.tokens_out += sum(s.attrs.get("tokens_out", 0) for s in spans)
        self.total_ms += root.ms
        self.llm_ms += sum(s.ms for s in spans if s.name == "llm.call")
        self.tool_ms += sum(s.ms for s in spans if s.name == "tool.execute")
        dollars, unpriced = turn_cost(spans)
        self.cost += dollars
        self.unpriced_calls += unpriced


class Tracer:
    """`sink(summary, root)` fires when a root span closes: the one-line
    summary for humans, and the root span itself so a consumer can record
    the numbers as numbers (see `trace_fields`) instead of parsing prose."""
    def __init__(self, sink=None):
        self._stack: list[Span] = []
        self._sink = sink or (lambda summary, root=None: print(summary))
        self.totals = SessionTotals()

    @contextmanager
    def span(self, name: str, **attrs):
        s = Span(name=name, attrs=dict(attrs))
        if self._stack:
            self._stack[-1].children.append(s)
        self._stack.append(s)
        start = time.perf_counter()
        try:
            yield s
        finally:
            s.ms = (time.perf_counter() - start) * 1000
            self._stack.pop()
            if not self._stack:                 # root closed → summarize
                self.totals.add(s)
                self._sink(_summarize(s), s)


def _walk(span: Span):
    yield span
    for c in span.children:
        yield from _walk(c)


def trace_fields(root: Span) -> dict:
    """The turn's numbers as fields: what a benchmark or the console should
    read, rather than regexing `_summarize`'s prose. Same spans, same sums."""
    spans = list(_walk(root))
    llm = [s for s in spans if s.name == "llm.call"]
    dollars, unpriced = turn_cost(spans)
    return {
        "llm_calls": len(llm),
        "tool_calls": sum(1 for s in spans if s.name == "tool.execute"),
        "tokens_in": sum(s.attrs.get("tokens_in", 0) for s in llm),
        "tokens_out": sum(s.attrs.get("tokens_out", 0) for s in llm),
        "cache_read": sum(s.attrs.get("cache_read", 0) for s in llm),
        "cache_write": sum(s.attrs.get("cache_write", 0) for s in llm),
        "total_ms": round(root.ms, 1),
        "llm_ms": round(sum(s.ms for s in llm), 1),
        "tool_ms": round(sum(s.ms for s in spans if s.name == "tool.execute"), 1),
        "cost": round(dollars, 6),
        "unpriced_calls": unpriced,
        "models": sorted({str(s.attrs.get("model")) for s in llm}),
    }


def _summarize(root: Span) -> str:
    spans = list(_walk(root))
    tok_in = sum(s.attrs.get("tokens_in", 0) for s in spans)
    tok_out = sum(s.attrs.get("tokens_out", 0) for s in spans)
    llm_ms = sum(s.ms for s in spans if s.name == "llm.call")
    tool_ms = sum(s.ms for s in spans if s.name == "tool.execute")
    n_llm = sum(1 for s in spans if s.name == "llm.call")
    n_tool = sum(1 for s in spans if s.name == "tool.execute")
    dollars, unpriced = turn_cost(spans)
    if unpriced:
        models = sorted({str(s.attrs.get("model")) for s in spans
                         if s.name == "llm.call" and rates_for(s.attrs.get("model")) is None})
        money = f"unpriced (no rate for {', '.join(models)})"
    else:
        money = f"~${dollars:.4f}"
    return (
        f"⎯ trace  {root.ms:.0f}ms total  |  "
        f"{n_llm} llm calls {llm_ms:.0f}ms · {n_tool} tools {tool_ms:.0f}ms  |  "
        f"tokens {tok_in}→{tok_out}  |  {money}"
    )
