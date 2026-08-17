"""Author: Swami Chandrasekaran
Last Modified: 2026-08-15
Purpose: Tests harness-level RSI — grounded scoring, enforced walls, replay, and the human gate.

Recursive self-improvement is the one feature here where a passing-but-wrong
implementation is actively dangerous, so these tests pin the properties that make
it honest rather than just present:

  * The score comes from grounded facts, and immature skills are refused, not
    guessed at.
  * The walls are enforced in code: RSI can write a skill file and nothing else,
    and a path that tries to escape the skills directory is blocked at the point
    of the write, not merely discouraged in a comment.
  * Replay discriminates on BEHAVIOUR — a rewrite that makes the model complete
    the plan scores higher; a rewrite that only reads nicer does not.
  * Promotion is gated: the loop never applies a change on its own, and a winning
    proposal still requires the caller to say yes.

If any of these break, the loop has quietly turned into self-congratulation,
which is the exact failure the design exists to prevent.
"""

import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dadloop import AgentLoop, Context, SemanticMemory
from dadloop.core import improve
from dadloop.core import improve_loop as il
from dadloop.core import skills as skill_lib
from dadloop.core.improve import OutcomeRecord, SkillScore, can_touch, score_skill


def _stalling_client(complete_steps: int = 1):
    """A client whose grilling turn loads the skill then completes only
    `complete_steps` of a 3-step plan — a knob for manufacturing under- and
    well-performing skills deterministically."""
    class FM:
        def __init__(self): self.n = 0
        def create(self, **kw):
            self.n += 1
            if not kw.get("tools"):        # a proposer call
                return NS(content=[NS(type="text", text="(no change)")],
                          usage=NS(input_tokens=10, output_tokens=5))
            if self.n == 1:
                calls = [NS(type="text", text="1. Load grilling\n2. Check\n3. Light"),
                         NS(type="tool_use", id="a", name="load_skill",
                            input={"name": "grilling"})]
                for i in range(complete_steps):
                    calls.append(NS(type="tool_use", id=f"c{i}", name="check_grill",
                                    input={}))
                return NS(content=calls, usage=NS(input_tokens=1000, output_tokens=80))
            return NS(content=[NS(type="text", text="Done.")],
                      usage=NS(input_tokens=200, output_tokens=20))
    return type("FC", (), {"messages": FM()})()


def _seed(memory, n, complete_steps=1):
    for i in range(n):
        dad = AgentLoop(Context(memory=memory))
        dad._client = _stalling_client(complete_steps)
        dad.turn(f"grill something #{i}")


def test_score_is_grounded_and_refuses_immature_skills():
    """Two grilling turns is not evidence. The scorer must say so rather than
    hand back a confident health number on noise."""
    mem = SemanticMemory(Path(tempfile.mkdtemp()) / "m")
    _seed(mem, 2, complete_steps=1)
    score = score_skill(mem, "grilling")
    assert score.samples == 2
    assert not score.mature, "two samples should not be judged mature"
    assert "not enough evidence" in score.verdict

    _seed(mem, 3, complete_steps=1)        # now 5 total, all stalling
    mature = score_skill(mem, "grilling")
    assert mature.mature
    assert mature.health < 0.85, "a skill that keeps stalling should score below healthy"
    assert mature.verdict in ("underperforming", "mixed"), \
        f"a stalling skill should not read as healthy, got {mature.verdict}"
    print("PASS: scoring is grounded and refuses to judge immature skills")


def test_walls_block_everything_but_skill_files():
    """The core safety property: can_touch permits a skill .md and refuses
    everything else — the constitution, the policy code, the loop, a path that
    tries to climb out with ../."""
    skills_dir = Path(skill_lib._SKILL_DIR)

    ok, _ = can_touch(skills_dir / "grilling.md", skills_dir)
    assert ok, "a real skill file must be writable"

    for forbidden in ["../core/agent.py", "../core/controller.py",
                      "../../etc/passwd", "grilling.txt", "../__init__.py"]:
        ok, reason = can_touch(skills_dir / forbidden, skills_dir)
        assert not ok, f"can_touch should refuse {forbidden}, reason={reason}"

    # And the wall list itself names governance explicitly — it must be visible.
    names = [n for n, _ in improve.WALLS]
    assert any("polic" in n for n in names), "Mom's policies must be a named wall"
    assert any("constitution" in n for n in names)
    print("PASS: walls permit skill files only; governance is a named, enforced wall")


def test_replay_rewards_behaviour_not_prose():
    """A rewrite that makes the model actually complete the plan must score
    higher than one that only reads better. Replay measures what the body causes,
    not how it sounds."""
    # Candidate body contains the tool name; the make_agent below completes the
    # extra step only when the live body contains 'check_grill'. So the score
    # gap is caused by behaviour the body induces, exactly as in production.
    def make_agent():
        mem = SemanticMemory(Path(tempfile.mkdtemp()) / "m")
        has_check = "check_grill" in skill_lib.SKILLS["grilling"].body
        class FM:
            def __init__(self): self.n = 0
            def create(self, **kw):
                self.n += 1
                if self.n == 1:
                    calls = [NS(type="text", text="1. Load grilling\n2. Check"),
                             NS(type="tool_use", id="a", name="load_skill",
                                input={"name": "grilling"})]
                    if has_check:
                        calls.append(NS(type="tool_use", id="b",
                                        name="check_grill", input={}))
                    return NS(content=calls, usage=NS(input_tokens=800, output_tokens=60))
                return NS(content=[NS(type="text", text="Done.")],
                          usage=NS(input_tokens=200, output_tokens=20))
        a = AgentLoop(Context(memory=mem))
        a._client = type("FC", (), {"messages": FM()})()
        return a

    prop = il.Proposal(
        skill="grilling",
        before_score=SkillScore("grilling", 5, 0.5, 0.5, 0.01),
        old_body="---\nname: grilling\ndescription: x\n---\n- Just wing it.",
        new_body="---\nname: grilling\ndescription: x\n---\n- Check the grill (check_grill).")
    result = il.replay_proposal(prop, make_agent, ["grill a", "grill b", "grill c"])

    assert result.candidate_health > result.baseline_health, \
        "the behaviour-improving rewrite should win on replay"
    assert result.delta >= il.IMPROVEMENT_MARGIN
    assert prop.recommend.startswith("PROMOTE")
    print("PASS: replay rewards behaviour that completes plans, not nicer prose")


def test_replay_is_honest_when_it_cannot_tell():
    """Identical bodies must produce an inconclusive verdict, never a fake win.
    A loop that always claims improvement is the failure mode."""
    def make_agent():
        mem = SemanticMemory(Path(tempfile.mkdtemp()) / "m")
        a = AgentLoop(Context(memory=mem))
        a._client = _stalling_client(1)
        return a

    body = "---\nname: grilling\ndescription: x\n---\n- Same body both ways."
    prop = il.Proposal(skill="grilling",
                       before_score=SkillScore("grilling", 5, 0.5, 0.5, 0.01),
                       old_body=body, new_body=body)
    result = il.replay_proposal(prop, make_agent, ["a", "b"])
    assert not result.conclusive or abs(result.delta) < il.IMPROVEMENT_MARGIN
    assert "inconclusive" in result.verdict or "HOLD" in prop.recommend
    print("PASS: replay reports inconclusive instead of manufacturing a win")


def test_promotion_is_gated_and_walled():
    """Promotion writes the file, keeps a backup, reloads the catalog — and
    refuses a proposal whose target escapes the skills directory."""
    tmp = Path(tempfile.mkdtemp()) / "skills"
    shutil.copytree(skill_lib._SKILL_DIR, tmp)
    saved_dir, saved_skills = skill_lib._SKILL_DIR, skill_lib.SKILLS
    try:
        skill_lib._SKILL_DIR = tmp
        skill_lib.SKILLS = skill_lib.load_all()
        agent = AgentLoop(Context(memory=SemanticMemory(Path(tempfile.mkdtemp()) / "m")))

        good = il.Proposal(
            skill="grilling",
            before_score=SkillScore("grilling", 5, 0.5, 0.5, 0.01),
            old_body=skill_lib.SKILLS["grilling"].body,
            new_body="---\nname: grilling\ndescription: x\n---\n- Lid down, always.")
        ok, msg = il.promote(agent, good)
        assert ok, f"a valid promotion should succeed: {msg}"
        assert (tmp / "grilling.md.bak").exists(), "promotion must keep a backup"
        assert "Lid down, always." in skill_lib.SKILLS["grilling"].body, \
            "the catalog should reload so the change takes effect"

        evil = il.Proposal(skill="../core/agent",
                           before_score=SkillScore("x", 5, 0.5, 0.5, 0.01),
                           old_body="", new_body="pwned")
        ok, msg = il.promote(agent, evil)
        assert not ok and "refused" in msg, \
            f"an escaping promotion must be refused at the write: {msg}"
    finally:
        skill_lib._SKILL_DIR, skill_lib.SKILLS = saved_dir, saved_skills
    print("PASS: promotion is backed up, reloads the catalog, and is walled at the write")


def test_pick_target_waits_for_evidence():
    """With no mature underperformer, the loop correctly proposes nothing —
    doing nothing when there's nothing to do is the honest default."""
    mem = SemanticMemory(Path(tempfile.mkdtemp()) / "m")
    assert il.pick_target(mem, skill_lib.SKILLS.keys()) is None, \
        "empty history should yield no target"
    _seed(mem, 2, complete_steps=1)        # immature
    assert il.pick_target(mem, skill_lib.SKILLS.keys()) is None, \
        "an immature skill is not a target"
    print("PASS: the loop waits for evidence and proposes nothing on thin data")


def test_held_streak_counts_and_resets_on_promote():
    """A skill that keeps landing on HOLD builds a visible streak — the same
    'same command, no change, stop' signal a person would otherwise only catch
    by remembering. A PROMOTE resets it, since something actually changed."""
    mem = SemanticMemory(Path(tempfile.mkdtemp()) / "m")

    assert improve.held_streak(mem, "grilling") == 0, \
        "a skill with no gate history has no streak"

    improve.record_gate_outcome(mem, "grilling", "HOLD — replay could not tell the difference")
    assert improve.held_streak(mem, "grilling") == 1

    improve.record_gate_outcome(mem, "grilling", "HOLD — replay could not tell the difference")
    improve.record_gate_outcome(mem, "grilling", "REJECT — regresses on replayed cases")
    assert improve.held_streak(mem, "grilling") == 3, \
        "HOLD and REJECT both count toward the stuck streak"

    improve.record_gate_outcome(mem, "grilling", "PROMOTE — beats the incumbent on replayed cases")
    assert improve.held_streak(mem, "grilling") == 0, \
        "a promotion resets the streak — something about the skill actually changed"

    improve.record_gate_outcome(mem, "bedtime", "HOLD — replay could not tell the difference")
    assert improve.held_streak(mem, "grilling") == 0, \
        "one skill's gate history must not leak into another's streak"
    assert improve.held_streak(mem, "bedtime") == 1
    print("PASS: held_streak counts consecutive non-promotions and resets per-skill on PROMOTE")


if __name__ == "__main__":
    test_score_is_grounded_and_refuses_immature_skills()
    test_walls_block_everything_but_skill_files()
    test_replay_rewards_behaviour_not_prose()
    test_replay_is_honest_when_it_cannot_tell()
    test_promotion_is_gated_and_walled()
    test_pick_target_waits_for_evidence()
    test_held_streak_counts_and_resets_on_promote()
