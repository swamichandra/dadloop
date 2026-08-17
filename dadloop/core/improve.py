"""Author: Swami Chandrasekaran
Last Modified: 2026-08-15
Purpose: Harness-level recursive self-improvement — grounded scoring and hard walls.

Recursive self-improvement, at the harness level, honestly.

The idea in one line: the system uses its current capability to improve the
machinery that produces its capability. Here that machinery is the *skills* —
the Markdown playbooks Dad loads on demand — because they are the one part of
the cognitive stack that is external to the weights and editable as text. dadloop
can rewrite its own skills; it cannot rewrite anything else.

The load-bearing part of any RSI loop is the measurement. If the same model both
proposes an improvement and grades it, you do not get self-improvement, you get
self-congratulation: the scores climb while the capability does not. So the whole
design turns on one rule — **the score comes from signals the model cannot
fabricate.** dadloop already produces those: whether a plan step actually
completed, whether a tool call actually resolved, how many times the governance
layer had to intervene, what the turn actually cost. None of those are "did the
answer seem good." They are facts the harness recorded while the turn ran.

This module is deliberately small and does three things:

  * OutcomeRecord / record_outcome — capture the grounded result of a turn that
    used a skill, and persist it (append-only, survives restarts).
  * SkillScore / score_skill — compute a skill's rolling performance from those
    records. This is the scorer, and it is NOT the model. It is arithmetic over
    facts.
  * WALLS — the explicit, enforced boundaries. The RSI loop may touch skill files
    and nothing else. The constitution, Mom's policies, the tools, the loop
    itself: all out of reach, in code, not in comments. can_touch() is the
    single gate every write goes through.

The propose / replay / gate machinery is in improve_loop.py. This file is the
part that has to be trustworthy for any of it to mean anything, so it has no
model in it at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path


# ---------------------------------------------------------------------------
# The walls. This is the honest-limits core: what RSI may and may not touch,
# enforced here rather than promised in prose.
# ---------------------------------------------------------------------------

# The ONLY directory the improvement loop may write to. A rewrite whose path
# does not resolve inside here is refused — see can_touch(). Skills are the
# editable cognitive machinery; everything else is off-limits by construction.
_SKILLS_DIRNAME = "skills"

# Named walls, each with the reason it exists. These are surfaced verbatim in the
# TUI and the CLI, because a limit you cannot see is indistinguishable from a
# limit that is not there. The point of this feature is to show the walls, not
# to have them.
WALLS: list[tuple[str, str]] = [
    ("the constitution",
     "Dad's values and process are Mom's to amend, not Dad's. A system that can "
     "edit its own principles has no principles."),
    ("Mom's policies",
     "The thermostat cap, the spend ceiling, the reply limit — the governance "
     "layer is the thing RSI is constrained BY. Letting the loop weaken its own "
     "guardrails is the canonical failure mode, so it cannot reach them."),
    ("the tools",
     "The verbs Dad can call are the harness's contract with the world. "
     "Self-improvement rewrites playbooks, not capabilities."),
    ("the agent loop",
     "The loop that runs all of this stays fixed. RSI improves what the loop "
     "loads, never the loop itself — that boundary is what keeps it bounded."),
    ("promotion",
     "A winning rewrite is PROPOSED, never auto-applied. A human commits the "
     "change. The loop can measure and prove; it cannot promote itself."),
]


def can_touch(path: Path, skills_dir: Path) -> tuple[bool, str]:
    """The single gate for every write the improvement loop attempts.

    Returns (allowed, reason). A path is allowed only if it resolves to a .md
    file physically inside skills_dir — so no amount of ``..`` or symlink games
    lets a rewrite escape into the constitution, the policy code, or anywhere
    else. Refusing here, in code, is the difference between a wall and a wish.
    """
    try:
        resolved = path.resolve()
        root = skills_dir.resolve()
    except OSError as exc:
        return False, f"path could not be resolved ({exc})"

    if resolved.suffix != ".md":
        return False, "RSI may only edit skill files (.md); this is not one"
    if root not in resolved.parents:
        return False, (
            f"outside the skills directory — RSI is walled to {root.name}/ and "
            "cannot touch the constitution, policies, tools, or the loop")
    return True, "within the skills directory"


# ---------------------------------------------------------------------------
# Grounded outcomes. The facts the scorer runs on — recorded by the harness
# while a turn ran, not judged after the fact by the model.
# ---------------------------------------------------------------------------

@dataclass
class OutcomeRecord:
    """What actually happened on one turn that loaded a skill.

    Every field is something the harness observed mechanically. There is no
    "quality" score here on purpose: the moment you let the model rate its own
    output, the measurement is gameable and the whole loop is theatre. Plan
    completion, tool errors, governance vetoes and cost are not opinions.
    """
    skill: str
    plan_steps: int              # how many steps Dad committed to
    plan_done: int               # how many actually completed
    tool_calls: int
    tool_errors: int             # tool results that came back an error/blocked
    vetoes: int                  # times Mom denied or rewrote a call this turn
    tokens: int
    cost: float
    prompt: str = ""             # the user turn this skill was used on — the
                                 # frozen case replay re-runs the rewrite against
    ts: float = field(default_factory=lambda: __import__("time").time())

    @property
    def completion(self) -> float:
        """Fraction of the stated plan that got done. The single most honest
        signal: did the procedure carry the turn to the end, or stall?"""
        return self.plan_done / self.plan_steps if self.plan_steps else 1.0

    @property
    def clean(self) -> bool:
        """A turn with no tool errors and no governance intervention. Not
        'good' — just 'nothing went visibly wrong', which is all we can claim
        from grounded signals."""
        return self.tool_errors == 0 and self.vetoes == 0


@dataclass
class SkillScore:
    """A skill's rolling performance, computed from its OutcomeRecords.

    'samples' matters as much as the score: a skill judged on two turns is not
    judged at all, and the loop refuses to propose rewrites for skills it cannot
    yet evaluate. Surfacing low-sample skills as 'not enough evidence' rather
    than scoring them anyway is part of being honest about the limits.
    """
    skill: str
    samples: int
    completion: float            # mean plan-completion across samples
    clean_rate: float            # fraction of turns that went clean
    mean_cost: float

    # A skill needs at least this many grounded outcomes before the loop will
    # form an opinion. Below it, the score exists but is marked immature and no
    # rewrite is proposed.
    MIN_SAMPLES = 4

    # Composite health in [0, 1]. Weighted toward completion (did the procedure
    # work) over cleanliness (did it avoid trouble), with cost left OUT of the
    # health score on purpose — see the note in score_skill.
    @property
    def health(self) -> float:
        return 0.7 * self.completion + 0.3 * self.clean_rate

    @property
    def mature(self) -> bool:
        return self.samples >= self.MIN_SAMPLES

    @property
    def verdict(self) -> str:
        if not self.mature:
            return f"not enough evidence ({self.samples}/{self.MIN_SAMPLES})"
        if self.health >= 0.85:
            return "healthy"
        if self.health >= 0.6:
            return "mixed"
        return "underperforming"


def record_outcome(memory, rec: OutcomeRecord) -> None:
    """Persist one grounded outcome to the append-only store.

    Stored as JSON in the 'outcomes' category so the structured fields survive a
    round-trip; the scorer reads them straight back. Best-effort: a telemetry
    write must never be the reason a turn fails, so callers wrap this.
    """
    memory.remember("outcomes", json.dumps(asdict(rec)), tags=["outcome", rec.skill])


def _load_outcomes(memory, skill: str | None = None) -> list[OutcomeRecord]:
    out: list[OutcomeRecord] = []
    for entry in memory.recall("outcomes"):
        try:
            data = json.loads(entry.text)
            rec = OutcomeRecord(**data)
        except (json.JSONDecodeError, TypeError):
            continue          # a malformed line is dropped, never fatal
        if skill is None or rec.skill == skill:
            out.append(rec)
    return out


def score_skill(memory, skill: str) -> SkillScore:
    """Compute a skill's rolling score from its grounded outcomes.

    Cost is reported but deliberately kept OUT of the health number. If cost
    counted toward health, the cheapest way to 'improve' a skill would be to make
    it do less — a reward-hack that looks like progress. Health is about whether
    the procedure works; cost is shown alongside so a human weighing a promotion
    sees both, and can reject a rewrite that got cheaper by getting lazier.
    """
    recs = _load_outcomes(memory, skill)
    n = len(recs)
    if n == 0:
        return SkillScore(skill, 0, 1.0, 1.0, 0.0)
    completion = sum(r.completion for r in recs) / n
    clean_rate = sum(1 for r in recs if r.clean) / n
    mean_cost = sum(r.cost for r in recs) / n
    return SkillScore(skill, n, completion, clean_rate, mean_cost)


def score_all(memory, skill_names) -> list[SkillScore]:
    """Every named skill's score, worst health first — the order a human would
    want to review them in."""
    scores = [score_skill(memory, name) for name in skill_names]
    return sorted(scores, key=lambda s: (s.mature, s.health))


# ---------------------------------------------------------------------------
# Gate outcomes. Recorded so a repeated HOLD is visible instead of silent — the
# same "same command, no change, three times, stop" signal Addy Osmani's loop
# engineering piece names as the tell that a loop is spinning in place. This
# is not a new memory category: it reuses 'usage', the same append-only store
# record_use() already writes skill-load counts to, so there is nothing new
# for a reader of memory.py to learn.
# ---------------------------------------------------------------------------

def record_gate_outcome(memory, skill: str, verdict: str) -> None:
    """Log one gate result — HOLD, REJECT, or PROMOTE — for a skill.

    Called once per completed propose/replay/gate pass, regardless of what the
    human decides to do about it. This is what makes held_streak() possible;
    without it a repeated HOLD is invisible, you'd only notice by remembering.
    """
    kind = verdict.split()[0].upper()   # "HOLD", "REJECT", or "PROMOTE"
    memory.record_use("rsi-gate", f"{skill}:{kind}")


def held_streak(memory, skill: str) -> int:
    """How many gate passes in a row have NOT promoted this skill.

    Counts back from the most recent gate outcome until it hits a PROMOTE (the
    streak resets there) or runs out of history. A rising number on the same
    skill is the "stuck" signal — the loop keeps proposing, replay keeps
    failing to back it, and re-running is unlikely to change that on its own.
    """
    prefix = f"rsi-gate:{skill}:"
    kinds = [e.text[len(prefix):] for e in memory.recall("usage")
             if e.text.startswith(prefix)]
    streak = 0
    for kind in reversed(kinds):        # most recent first
        if kind == "PROMOTE":
            break
        streak += 1
    return streak

