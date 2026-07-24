"""Author: Swami Chandrasekaran
Last Modified: 2026-07-18
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
                "Then I double-checked the pantry. "
                "Finally, here is my answer: yes, we are ready."
            )
            return NS(content=[NS(type="text", text=speech)])

    dad = AgentLoop(Context(memory=SemanticMemory(Path(tempfile.mkdtemp()) / "m")))
    dad._client = type("FC", (), {"messages": FM()})()

    events = []
    reply = dad.turn("are we ready", on_event=lambda k, p: events.append((k, p)))

    sentence_count = reply.count(".") + reply.count("!") + reply.count("?")
    assert sentence_count <= 5, f"reply has {sentence_count} sentences, constitution caps at 5"

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


def test_dad_is_grounded_in_identity_place_and_time():
    """Dad must know who he is, where he is, and when 'today' is.

    Without this the agent answers "I want to watch Odyssey in theaters today"
    as though the date were unknowable — asking the user what day it is, or
    deflecting to "check your local listings". A harness that has a clock and a
    location and still does that is just being unhelpful on purpose.
    """
    from datetime import datetime
    from dadloop.core.agent import _constitution
    from dadloop.core.context import Context

    text = _constitution(Context())

    assert "Swami Chandrasekaran" in text, "Dad should know his own name"
    assert "Dallas, TX" in text, "Dad should know where home is"

    now = datetime.now()
    assert str(now.year) in text and now.strftime("%A") in text, \
        "Dad should know today's date, not just that a date exists"

    lowered = text.lower()
    assert "showtimes" in lowered, "time-sensitive lookups should be called out"
    assert "never ask what today's date is" in lowered
    print("PASS: Dad knows his name, his city, and what day it is")


if __name__ == "__main__":
    test_mom_trims_long_winded_reply()
    test_short_reply_passes_untouched()
    test_mom_protects_care_sentence_from_the_cut()
    test_dad_is_grounded_in_identity_place_and_time()
