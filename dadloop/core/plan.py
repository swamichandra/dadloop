"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Parses and reconciles stated plans against actual tool calls.

Plan tracking — the model states its intent, the harness checks it off.

The constitution asks Dad to state a numbered plan before his first tool call.
This module parses that plan and reconciles it against what he *actually* does,
one tool call at a time.

The reconciliation is the point. A tool call that matches a stated step ticks it
off; a tool call that matches nothing is appended and flagged `planned=False`.
So the gap between what the model said it would do and what it did stays visible
instead of being quietly smoothed over — which is the thing you most need to see
when you are deciding whether to trust an agent.

Matching is deliberately dumb: keyword hints, not NLP. A wrong match here costs a
mislabeled checkbox, not a wrong action, so the simple thing is the right thing.

    plan = parse_plan(first_interim_text)   # "1. Check the grill  2. ..."
    step = plan.match(tool_name, tool_args) # as each tool call arrives
    plan.steps                              # render as a checklist
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUMBERED_LINE = re.compile(r"^\s*\d+[\.\)]\s*(.+)$", re.MULTILINE)

# Loose keyword hints so a stated step like "check the grill" matches the
# tool call check_grill(). Good enough for a teaching demo, not NLP.
_TOOL_HINTS = {
    "check_weather": ("weather",),
    "check_grill": ("grill", "propane"),
    "check_pantry": ("pantry", "fridge", "food"),
    "check_hardware_store": ("hardware", "store"),
    "set_thermostat": ("thermostat", "heat", "cool"),
    "check_wallet": ("wallet", "budget", "afford", "money", "cost"),
    "find_tool": ("tool", "toolbox", "garage"),
    "web_search": ("search", "look up", "find out"),
    "remember": ("remember", "file", "note"),
    "recall": ("recall", "remember"),
    "load_skill": ("skill", "playbook"),
    "tell_joke": ("joke",),
}


@dataclass
class PlanStep:
    text: str
    tool: str | None = None      # matched tool name, once resolved
    done: bool = False
    planned: bool = True         # False if this step was appended, not stated


@dataclass
class Plan:
    steps: list[PlanStep] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.steps

    def match(self, tool_name: str, tool_args: dict) -> tuple[int, PlanStep]:
        """Reconcile one tool call against the plan. Returns (index, step).

        Ticks off the first not-yet-done step whose text plausibly refers to this
        tool. If nothing matches, the call was unplanned: append it as a new step
        flagged `planned=False` rather than dropping it, so the drift is visible.

        Returning the index matters — the caller needs it to update the right row,
        and looking it up afterwards with .index() would find the wrong step when
        two steps share the same text.
        """
        hints = _TOOL_HINTS.get(tool_name, ())
        for i, step in enumerate(self.steps):
            if step.done:
                continue
            if any(h in step.text.lower() for h in hints):
                step.done = True
                step.tool = tool_name
                return i, step

        unplanned = PlanStep(text=_default_label(tool_name, tool_args),
                             tool=tool_name, done=True, planned=False)
        self.steps.append(unplanned)
        return len(self.steps) - 1, unplanned


def _default_label(tool_name: str, tool_args: dict) -> str:
    """A human-readable label for a tool call the model did not plan for."""
    if tool_name == "load_skill":
        return f"Load the {tool_args.get('name', '?')} skill"
    words = tool_name.replace("_", " ")
    return words[0].upper() + words[1:]


def parse_plan(text: str) -> Plan:
    """Parse Dad's stated numbered plan out of his first interim text block.
    Returns an empty Plan if he didn't state one — the harness falls back to
    building the checklist live from tool calls alone."""
    matches = _NUMBERED_LINE.findall(text or "")
    return Plan(steps=[PlanStep(text=m.strip()) for m in matches])
