"""Author: Swami Chandrasekaran
Last Modified: 2026-07-20
Purpose: RSI propose/replay/gate loop — the model rewrites skills, replay decides, a human promotes.

The propose / replay / gate half of harness-level RSI.

improve.py holds the trustworthy part — grounded scoring and the walls. This
file is where the model re-enters the loop, and it does so under three
constraints that are the whole point of the "honest limits" framing:

  1. It can only propose rewrites of *skills*, and every write is checked by
     improve.can_touch() before it lands. The constitution, Mom's policies, the
     tools, and the loop itself are unreachable, in code.

  2. A proposal is judged by REPLAY against frozen past cases, not by the model's
     opinion of its own draft. The replay reuses the grounded scorer: did the
     rewritten skill complete more of the plan, error less, get vetoed less? A
     draft that only *reads* better and does not move those numbers is not an
     improvement, and the loop says so.

  3. Nothing is auto-applied. The loop produces a Proposal — the diff, the
     before/after replay scores, and a recommendation — and stops. A human
     promotes it. The loop can measure and prove; it cannot commit.

The honest part is admitting when the loop cannot tell. Replay re-runs a real
model, which is nondeterministic and costs money, so a proposal is often
inconclusive: too few frozen cases, or the two versions score within noise. The
loop reports "inconclusive" rather than manufacturing a verdict, because a
confident wrong answer here is exactly the reward-hack the design exists to
avoid. An RSI system that always claims it improved is the failure mode, not the
feature.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from . import improve
from . import skills as skill_lib
from .improve import SkillScore, score_skill, score_all


# How many frozen past prompts to replay a proposal against. Kept small: replay
# costs a real model call per case per version, and the point is a signal, not a
# benchmark suite. Below MIN the loop refuses to draw a conclusion.
REPLAY_CASES = 4
REPLAY_MIN = 2

# A proposed rewrite must beat the incumbent's health by at least this margin on
# replay to be recommended. Anything smaller is inside model-variance noise and
# gets reported as inconclusive, not as a win.
IMPROVEMENT_MARGIN = 0.08


@dataclass
class ReplayResult:
    """How a proposal fared against the frozen cases: the incumbent's replayed
    health vs the candidate's, and whether the gap clears the noise margin."""
    cases: int
    baseline_health: float
    candidate_health: float
    baseline_cost: float
    candidate_cost: float

    @property
    def delta(self) -> float:
        return self.candidate_health - self.baseline_health

    @property
    def conclusive(self) -> bool:
        return self.cases >= REPLAY_MIN and abs(self.delta) >= IMPROVEMENT_MARGIN

    @property
    def verdict(self) -> str:
        if self.cases < REPLAY_MIN:
            return f"inconclusive — only {self.cases} case(s) to replay"
        if self.delta >= IMPROVEMENT_MARGIN:
            return f"improves health by {self.delta:+.0%}"
        if self.delta <= -IMPROVEMENT_MARGIN:
            return f"REGRESSES health by {self.delta:+.0%} — reject"
        return f"inconclusive — {self.delta:+.0%} is inside the noise"


@dataclass
class Proposal:
    """A completed, un-applied improvement proposal.

    Everything a human needs to decide, and nothing applied yet: which skill,
    the current score, the proposed body, a readable diff, and the replay result.
    `recommend` is the loop's read; the decision is not the loop's to make.
    """
    skill: str
    before_score: SkillScore
    old_body: str
    new_body: str
    replay: ReplayResult | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def diff(self) -> str:
        return "".join(difflib.unified_diff(
            self.old_body.splitlines(keepends=True),
            self.new_body.splitlines(keepends=True),
            fromfile=f"{self.skill}.md (current)",
            tofile=f"{self.skill}.md (proposed)",
        ))

    @property
    def recommend(self) -> str:
        if self.replay is None:
            return "no replay run — cannot recommend"
        if self.replay.delta >= IMPROVEMENT_MARGIN:
            return "PROMOTE — beats the incumbent on replayed cases"
        if self.replay.delta <= -IMPROVEMENT_MARGIN:
            return "REJECT — regresses on replayed cases"
        return "HOLD — replay could not tell the difference"


def pick_target(memory, skill_names) -> SkillScore | None:
    """The skill most worth improving: the worst-health *mature* one.

    Immature skills are skipped on purpose — proposing a rewrite for a skill you
    have four data points on is guessing, and the honest-limits stance is to wait
    for evidence rather than act on noise. Returns None when nothing is both
    mature and underperforming, which is the correct, common answer.
    """
    for score in score_all(memory, skill_names):
        if score.mature and score.health < 0.85:
            return score
    return None


def _frozen_cases(memory, skill: str, limit: int) -> list[str]:
    """The user prompts from this skill's past outcomes — the frozen replay set.

    These are real turns the skill was used on, so a rewrite is judged on the
    work it actually has to do, not on invented examples. Deduplicated and
    capped; prompts that weren't captured (empty string) are skipped, and the
    replay then reports the smaller, honest count.
    """
    seen: list[str] = []
    for rec in improve._load_outcomes(memory, skill):
        p = (rec.prompt or "").strip()
        if p and p not in seen:
            seen.append(p)
        if len(seen) >= limit:
            break
    return seen


def _score_body_on_cases(make_agent, skill: str, body: str,
                         cases: list[str]) -> tuple[float, float]:
    """Run one skill body against the frozen cases and return (health, mean cost).

    The candidate body is swapped into the live catalog for the duration of the
    replay and restored afterward — a temporary, in-memory substitution, never a
    file write (that only happens on promote). Each case runs on a FRESH agent so
    prior turns can't leak in. Health is the grounded scorer's number over the
    replayed outcomes, so the candidate is judged by exactly the same yardstick
    as the incumbent.
    """
    original = skill_lib.SKILLS.get(skill)
    if original is None:
        return 0.0, 0.0

    saved_body = original.body
    completions: list[float] = []
    cleans: list[bool] = []
    costs: list[float] = []
    try:
        original.body = body            # temporary in-memory swap
        for prompt in cases:
            agent = make_agent()         # fresh memory + client per case
            agent.turn(prompt)
            recs = improve._load_outcomes(agent.ctx.memory, skill)
            if not recs:
                continue
            rec = recs[-1]               # the outcome this replay just produced
            completions.append(rec.completion)
            cleans.append(rec.clean)
            costs.append(rec.cost)
    finally:
        original.body = saved_body       # always restore, even on error

    if not completions:
        return 0.0, 0.0
    completion = sum(completions) / len(completions)
    clean_rate = sum(1 for c in cleans if c) / len(cleans)
    mean_cost = sum(costs) / len(costs)
    health = 0.7 * completion + 0.3 * clean_rate
    return health, mean_cost


def replay_proposal(prop: Proposal, make_agent, cases: list[str]) -> ReplayResult:
    """The measurement that decides a proposal — incumbent vs candidate on the
    same frozen cases, scored by the same grounded yardstick.

    `make_agent` builds a fresh, isolated agent (its own memory, its own scripted
    or live client). Passing it in — rather than reaching for a global — is what
    keeps replay deterministic under test and honest in production: both bodies
    face identical cases on identical fresh state, so the only variable is the
    skill text itself.
    """
    n = len(cases)
    if n == 0:
        return ReplayResult(0, 0.0, 0.0, 0.0, 0.0)
    base_health, base_cost = _score_body_on_cases(
        make_agent, prop.skill, prop.old_body, cases)
    cand_health, cand_cost = _score_body_on_cases(
        make_agent, prop.skill, prop.new_body, cases)
    result = ReplayResult(n, base_health, cand_health, base_cost, cand_cost)
    prop.replay = result
    return result


def propose_rewrite(agent, skill: str, *, ask_model=None) -> Proposal:
    """Ask the model to rewrite one skill, given its grounded score.

    The model is told the skill's actual measured weaknesses (low completion,
    frequent vetoes) and asked to revise the PROCEDURE to address them — not to
    make it read better. The prompt deliberately withholds any way to score
    itself: the draft's only judge is replay, downstream.

    `ask_model` is injectable so tests can drive this without a live client and
    so replay stays deterministic. In production it wraps the agent's client.
    """
    score = score_skill(agent.ctx.memory, skill)
    current = skill_lib.SKILLS.get(skill)
    old_body = current.body if current else ""

    weaknesses = []
    if score.completion < 0.85:
        weaknesses.append(
            f"plans only complete {score.completion:.0%} of the time — steps stall")
    if score.clean_rate < 0.85:
        weaknesses.append(
            f"{1 - score.clean_rate:.0%} of turns hit a tool error or a Mom veto")
    weakness_text = "; ".join(weaknesses) or "no specific grounded weakness"

    prompt = (
        "You are revising a dadloop skill — a Markdown procedure Dad follows.\n"
        f"Skill: {skill}\n"
        f"Measured problem: {weakness_text}.\n\n"
        "Current procedure:\n"
        f"{old_body}\n\n"
        "Rewrite the procedure to fix the measured problem. Keep the same "
        "frontmatter (name, description). Change the STEPS — order them so the "
        "checks that block everything else come first, make each step map to a "
        "real tool Dad has, and cut anything that invites a governance veto. "
        "Return only the new Markdown, no commentary."
    )

    if ask_model is None:
        def ask_model(p: str) -> str:
            client = getattr(agent, "_client", None)
            if client is None:
                return old_body
            resp = client.messages.create(
                model=getattr(agent, "model", "claude-sonnet-5"),
                max_tokens=1024,
                messages=[{"role": "user", "content": p}],
            )
            return "".join(b.text for b in resp.content
                           if getattr(b, "type", "") == "text").strip()

    new_body = ask_model(prompt).strip() or old_body
    prop = Proposal(skill=skill, before_score=score,
                    old_body=old_body, new_body=new_body)
    if new_body == old_body:
        prop.notes.append("model returned no change")
    return prop


def promote(agent, prop: Proposal) -> tuple[bool, str]:
    """Apply a proposal — the ONE write RSI can make, and only when a human asks.

    Every promotion goes through improve.can_touch() first: the target must be a
    .md file inside the skills directory, or the write is refused with the reason.
    This is the wall, enforced at the point of action. On success the skill
    catalog is reloaded so the change takes effect, and the promotion is logged
    to memory as a durable record of what RSI changed and when.
    """
    skills_dir = Path(skill_lib._SKILL_DIR)
    target = skills_dir / f"{prop.skill}.md"

    ok, reason = improve.can_touch(target, skills_dir)
    if not ok:
        return False, f"refused: {reason}"

    # Keep the old version recoverable — a promotion you cannot undo is not a
    # gate, it is a cliff.
    try:
        backup = target.with_suffix(".md.bak")
        if target.exists():
            backup.write_text(target.read_text())
        target.write_text(prop.new_body if prop.new_body.endswith("\n")
                          else prop.new_body + "\n")
    except OSError as exc:
        return False, f"write failed: {exc}"

    # Reload the catalog so the promoted skill is what Dad loads next.
    skill_lib.SKILLS = skill_lib.load_all()
    try:
        agent.ctx.memory.remember(
            "lessons",
            f"RSI promoted a rewrite of skill '{prop.skill}' "
            f"(health was {prop.before_score.health:.0%})",
            tags=["rsi", "promotion", prop.skill])
    except Exception:
        pass
    return True, f"promoted {prop.skill} (backup at {backup.name})"
