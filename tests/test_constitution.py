"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Tests Mom enforces constitution voice rules on final replies.

Proves the constitution's voice rules are mechanically enforced by Mom on
the final reply, not just asserted in the prompt — including that warmth
survives the trim instead of getting amputated for coming last."""
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from dadloop import AgentLoop, Context, SemanticMemory


def test_mom_trims_long_winded_reply():
    class FM:
        def create(self, **kw):
            speech = (
                "First I checked the weather. Then I checked the grill. "
                "Then I thought about the budget. Then I considered the yard. "
                "Finally, here is my answer: yes, we are ready."
            )
            return NS(content=[NS(type="text", text=speech)])

    dad = AgentLoop(Context(memory=SemanticMemory(Path(tempfile.mkdtemp()) / "m")))
    dad._client = type("FC", (), {"messages": FM()})()

    events = []
    reply = dad.turn("are we ready", on_event=lambda k, p: events.append((k, p)))

    sentence_count = reply.count(".") + reply.count("!") + reply.count("?")
    assert sentence_count <= 4, f"reply has {sentence_count} sentences, constitution caps at 4"

    mom_notes = [p for k, p in events if k == "controller" and p[0] == "reply"]
    assert mom_notes, "Mom should have logged her trim"
    print(f"PASS: Mom trimmed a 6-sentence reply to {sentence_count} — constitution enforced")


def test_short_reply_passes_untouched():
    class FM:
        def create(self, **kw):
            return NS(content=[NS(type="text", text="Ready. Grill's full, jacket weather.")])

    dad = AgentLoop(Context(memory=SemanticMemory(Path(tempfile.mkdtemp()) / "m")))
    dad._client = type("FC", (), {"messages": FM()})()

    events = []
    reply = dad.turn("ready?", on_event=lambda k, p: events.append((k, p)))

    assert reply == "Ready. Grill's full, jacket weather."
    mom_notes = [p for k, p in events if k == "controller" and p[0] == "reply"]
    assert not mom_notes, "Mom shouldn't touch a reply that's already within the rule"
    print("PASS: a compliant short reply passes through untouched")


def test_mom_protects_care_sentence_from_the_cut():
    """The new behavior: a warm/acknowledging sentence buried past the cap
    should survive the trim instead of being amputated for coming last."""
    class FM:
        def create(self, **kw):
            speech = (
                "First I checked the weather. Then I checked the grill. "
                "The propane is empty. The store is closed today too. "
                "Hosting alone this weekend is rough, hang in there. "
                "Anyway here is the plan."
            )
            return NS(content=[NS(type="text", text=speech)])

    dad = AgentLoop(Context(memory=SemanticMemory(Path(tempfile.mkdtemp()) / "m")))
    dad._client = type("FC", (), {"messages": FM()})()

    reply = dad.turn("what do I do, hosting alone this weekend and the grill's acting up")

    assert "hang in there" in reply.lower(), \
        "the care sentence was cut instead of protected"
    print("PASS: Mom protected the acknowledgment sentence instead of cutting it for coming last")


if __name__ == "__main__":
    test_mom_trims_long_winded_reply()
    test_short_reply_passes_untouched()
    test_mom_protects_care_sentence_from_the_cut()
