"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Package entry point exporting AgentLoop, Context, DadState, and SemanticMemory.

dadloop — a model-in-the-loop dad harness.

You talk to Dad in plain English; the model decides which tools and skills to
use, in a loop, until it's done. core/agent.py runs that loop.

    from dadloop import AgentLoop
    print(AgentLoop().turn("I'm hosting Saturday, what do I do?"))
"""
from .core.agent import AgentLoop
from .core.context import Context, DadState
from .core.memory import SemanticMemory

__all__ = ["AgentLoop", "Context", "DadState", "SemanticMemory"]
__version__ = "1.1.1"
