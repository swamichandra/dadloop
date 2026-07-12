"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
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

# Rough Claude Sonnet pricing, $ per million tokens. Adjust per model.
_COST_PER_MTOK_IN = 3.0
_COST_PER_MTOK_OUT = 15.0


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

    @property
    def cost(self) -> float:
        return (self.tokens_in / 1e6 * _COST_PER_MTOK_IN
                + self.tokens_out / 1e6 * _COST_PER_MTOK_OUT)

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


class Tracer:
    def __init__(self, sink=None):
        self._stack: list[Span] = []
        self._sink = sink or (lambda summary: print(summary))
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
                self._sink(_summarize(s))


def _walk(span: Span):
    yield span
    for c in span.children:
        yield from _walk(c)


def _summarize(root: Span) -> str:
    spans = list(_walk(root))
    tok_in = sum(s.attrs.get("tokens_in", 0) for s in spans)
    tok_out = sum(s.attrs.get("tokens_out", 0) for s in spans)
    llm_ms = sum(s.ms for s in spans if s.name == "llm.call")
    tool_ms = sum(s.ms for s in spans if s.name == "tool.execute")
    n_llm = sum(1 for s in spans if s.name == "llm.call")
    n_tool = sum(1 for s in spans if s.name == "tool.execute")
    cost = tok_in / 1e6 * _COST_PER_MTOK_IN + tok_out / 1e6 * _COST_PER_MTOK_OUT
    return (
        f"⎯ trace  {root.ms:.0f}ms total  |  "
        f"{n_llm} llm calls {llm_ms:.0f}ms · {n_tool} tools {tool_ms:.0f}ms  |  "
        f"tokens {tok_in}→{tok_out}  |  ~${cost:.4f}"
    )
