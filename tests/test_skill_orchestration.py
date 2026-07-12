"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Tests skill composition and orchestration for hosting.

Proves skills compose: one request loads several skills and the model can
weave them. This is the 'assemble and orchestrate' claim — the whole point.
A filing cabinet retrieves one file; a harness combines several."""
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from dadloop import AgentLoop, Context, SemanticMemory


def test_hosting_composes_three_skills():
    # Fake model that behaves like a real one following hosting's body:
    # load the orchestrator, then load the three it names, then answer.
    class FM:
        def __init__(self): self.n = 0; self.seen = []
        def create(self, **kw):
            for m in kw["messages"]:
                if isinstance(m.get("content"), list):
                    for b in m["content"]:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            self.seen.append(b["content"])
            self.n += 1
            step = {
                1: "hosting",
                2: "money-decisions",
                3: "grilling",
                4: "yard-work",
            }.get(self.n)
            if step:
                return NS(content=[NS(type="tool_use", id=f"s{self.n}",
                                      name="load_skill", input={"name": step})])
            # Final: prove it actually saw the three bodies before answering.
            joined = "\n".join(self.seen)
            assert "budget" in joined.lower() and "grill" in joined.lower() and "lawn" in joined.lower()
            return NS(content=[NS(type="text",
                text="Budget's the boss: ~$4/head. Grill veg within it, mow Saturday-eve. Plan set.")])

    dad = AgentLoop(Context(memory=SemanticMemory(Path(tempfile.mkdtemp()) / "m")))
    dad._client = type("FC", (), {"messages": FM()})()

    loaded = []
    dad.turn("I'm hosting Saturday, what do I do?",
             on_event=lambda k, p: loaded.append(p[1].get("name"))
             if k == "tool_call" else None)

    assert loaded == ["hosting", "money-decisions", "grilling", "yard-work"]
    print("PASS: one request loaded 4 skills — orchestrator + the 3 it consults")
    print("      loads:", " → ".join(loaded))


if __name__ == "__main__":
    test_hosting_composes_three_skills()
