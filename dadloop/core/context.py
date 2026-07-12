"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Session state and context bundle passed between turns and tools.

Context — what the harness carries between turns.

`DadState` is the mutable state a turn can change (the thermostat he was pushed
to, the jokes he has told). `Context` bundles that state with the durable memory
handle, and is what gets passed to the loop and to every tool.

The split matters: state is cheap and in-memory, memory is on disk and outlives
the process. A grievance filed today has to be readable by a run next Tuesday, so
it goes to memory, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .memory import SemanticMemory


@dataclass
class DadState:
    """Mutable per-session state. Anything that must survive a restart belongs
    in SemanticMemory instead."""

    name: str = "Dad"
    dad_jokes_told: int = 0
    thermostat_setpoint: int = 68

    # Hydrated from disk on startup so the system prompt can reference them.
    grievances: list[str] = field(default_factory=list)
    known_children: list[str] = field(default_factory=list)


@dataclass
class Context:
    """The live state handed to the loop and to every tool.

    On construction it hydrates the in-memory view from whatever is already on
    disk, so a fresh process starts out knowing what it was told last week.
    """

    state: DadState = field(default_factory=DadState)
    memory: SemanticMemory = field(default_factory=SemanticMemory)

    def __post_init__(self) -> None:
        self.state.grievances = [e.text for e in self.memory.recall("grievances")]
        for kid in (e.text for e in self.memory.recall("people")):
            if kid not in self.state.known_children:
                self.state.known_children.append(kid)
