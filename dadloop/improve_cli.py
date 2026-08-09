"""Author: Swami Chandrasekaran
Last Modified: 2026-07-20
Purpose: `dadloop --improve` — run the RSI loop deliberately, with the walls in plain sight.

`dadloop --improve` — the recursive self-improvement loop, run by hand.

This is the deliberate, inspectable entry point: no background magic, no
auto-applied changes. You run it, it shows you what it measured, what it
proposes, whether replay backs the proposal up, and — only if you say so — it
promotes the change. Every step prints, because the whole point of this feature
is that the loop is legible.

It opens by printing the walls. A limit you cannot see is indistinguishable from
one that is not there, so the first thing the command does is state, out loud,
what RSI cannot touch and why. Then it scores the skills, picks the one most
worth improving, asks the model to rewrite it, replays the rewrite against frozen
past cases, and stops at the gate. Promotion is a separate keystroke a human
presses, never a step the loop takes on its own.
"""

from __future__ import annotations

from .core.agent import AgentLoop
from .core import skills as skill_lib
from .core import improve
from .core import improve_loop as il


def _rule(title: str = "") -> None:
    line = "─" * 66
    print(f"\n{line}\n{title}\n{line}" if title else line)


def _print_walls() -> None:
    _rule("WHAT THIS LOOP CANNOT TOUCH  (and why)")
    print("Recursive self-improvement here rewrites SKILLS and nothing else.")
    print("These boundaries are enforced in code, not promised in prose:\n")
    for name, reason in improve.WALLS:
        print(f"  ✗ {name}")
        for chunk in _wrap(reason, 60):
            print(f"      {chunk}")
    print("\nThe loop can measure, propose, and prove. A human promotes.")


def _wrap(text: str, width: int) -> list[str]:
    words, line, out = text.split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out


def _print_scores(memory) -> None:
    _rule("SKILL SCORES  (grounded — from what turns actually did)")
    scores = improve.score_all(memory, skill_lib.SKILLS.keys())
    if not any(s.samples for s in scores):
        print("No skill outcomes recorded yet. Use dadloop, then come back —")
        print("the loop scores skills on real turns, not invented ones.")
        return
    print(f"  {'skill':<24} {'samples':>7}  {'health':>6}  verdict")
    for s in scores:
        health = f"{s.health:.0%}" if s.samples else "  —"
        print(f"  {s.skill:<24} {s.samples:>7}  {health:>6}  {s.verdict}")


def run_improve(agent: AgentLoop | None = None, *, auto_confirm: bool = False) -> int:
    """Run one pass of the improvement loop, interactively.

    Returns a process exit code. `auto_confirm` exists only for tests and demos —
    a real run always asks a human before promoting, because that gate is one of
    the walls, not a convenience to skip.
    """
    agent = agent or AgentLoop()

    print("dadloop · recursive self-improvement")
    _print_walls()
    _print_scores(agent.ctx.memory)

    target = il.pick_target(agent.ctx.memory, skill_lib.SKILLS.keys())
    if target is None:
        _rule("NOTHING TO PROPOSE")
        print("No skill is both mature (enough evidence) and underperforming.")
        print("That is a normal, common, correct answer — the honest version of")
        print("this loop does nothing when there is nothing worth changing.")
        return 0

    _rule(f"TARGET: {target.skill}")
    print(f"Worst mature skill — health {target.health:.0%} over "
          f"{target.samples} turns ({target.verdict}).")

    if not agent.online:
        print("\nDad is asleep (no API key), so the loop can score and pick but")
        print("cannot draft a rewrite. Set ANTHROPIC_API_KEY to go further.")
        return 0

    print("\nAsking Dad to rewrite the procedure to fix the measured problem…")
    prop = il.propose_rewrite(agent, target.skill)
    if prop.new_body == prop.old_body:
        print("Dad returned no change. Nothing to promote.")
        return 0

    _rule("PROPOSED REWRITE")
    print(prop.diff or "(no textual diff)")

    _rule("REPLAY  (candidate vs incumbent, on frozen past cases)")
    cases = il._frozen_cases(agent.ctx.memory, target.skill, il.REPLAY_CASES)
    if len(cases) < il.REPLAY_MIN:
        print(f"Only {len(cases)} replayable case(s) on record — below the "
              f"{il.REPLAY_MIN} needed to draw a conclusion.")
        print("Reporting INCONCLUSIVE rather than guessing. Use the skill more,")
        print("then re-run; the loop refuses to recommend on thin evidence.")
        return 0

    def make_agent() -> AgentLoop:
        # A fresh agent per replay case, sharing this run's client so replay uses
        # the same model — but its own memory, so cases don't contaminate.
        fresh = AgentLoop()
        fresh._client = agent._client
        fresh.model = agent.model
        return fresh

    print(f"Replaying {len(cases)} case(s)…")
    result = il.replay_proposal(prop, make_agent, cases)
    print(f"  incumbent health {result.baseline_health:.0%} "
          f"(${result.baseline_cost:.4f}/turn)")
    print(f"  candidate health {result.candidate_health:.0%} "
          f"(${result.candidate_cost:.4f}/turn)")
    print(f"  → {result.verdict}")

    _rule("GATE  (a human decides — the loop cannot promote itself)")
    print(f"Recommendation: {prop.recommend}")

    if prop.recommend.startswith("REJECT") or prop.recommend.startswith("HOLD"):
        print("Not promoting. The proposal and its replay are logged either way.")
        return 0

    if auto_confirm:
        approved = True
    else:
        try:
            answer = input("\nPromote this rewrite? [y/N] ").strip().lower()
        except EOFError:
            answer = "n"
        approved = answer in ("y", "yes")

    if not approved:
        print("Held. Nothing changed — the rewrite is on record, not applied.")
        return 0

    ok, msg = il.promote(agent, prop)
    print(f"\n{'✓' if ok else '✗'} {msg}")
    return 0 if ok else 1
