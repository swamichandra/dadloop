"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Tests grievances persist and inject into new session prompts.

Proves memory is cognition: a grievance filed in one session is injected
into a fresh session's system prompt, so Dad can raise it unprompted."""
import tempfile
from pathlib import Path
from dadloop import Context, SemanticMemory
from dadloop.core.agent import _system_prompt


def test_grievance_persists_into_next_session_prompt():
    tmp = Path(tempfile.mkdtemp()) / "mem"
    Context(memory=SemanticMemory(tmp)).memory.remember(
        "grievances", "someone changed the thermostat from 68 to 74")

    prompt = _system_prompt(Context(memory=SemanticMemory(tmp)))  # fresh session
    assert "thermostat" in prompt and "74" in prompt
    print("PASS: memory cognition — grievance injected into next session's prompt")


if __name__ == "__main__":
    test_grievance_persists_into_next_session_prompt()
