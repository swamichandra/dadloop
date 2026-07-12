"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Model-in-the-loop agent harness orchestrating tools, memory, and governance.

The harness — a real model-in-the-loop agent loop.

This is what makes dadloop a *harness* and not a command dispatcher. The control
flow lives in the model, not in pre-authored branches:

    user text ─▶ [inject context + memory] ─▶ MODEL
                                                │
                        ┌───────────────────────┤ wants tools?
                        │ yes                    │ no
                        ▼                        ▼
                 execute tools            final dad reply
                        │
                 feed results back ──▶ MODEL  (loop)

The harness's jobs are exactly the classic ones: marshal context in, run the
tool calls the model asks for, feed results back, manage memory across turns,
and know when to stop. The intelligence is the model's; the plumbing is ours.

Requires ANTHROPIC_API_KEY (via .env). Without it, `online` is False and the
caller should say so — a harness with no model isn't a harness.
"""

from __future__ import annotations

import os
from pathlib import Path

from .context import Context
from . import tools as toolkit
from .controller import Mom
from .trace import Tracer
from .plan import Plan, parse_plan

_MAX_STEPS = 8  # safety rail: a dad monologue must eventually end


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _constitution(ctx: Context) -> str:
    """Dad's constitution — managed by Mom. Values and process shape how he
    reasons (can be long); voice constrains how he speaks (must be short).
    Mom enforces the voice rules mechanically on the reply, not just here."""
    from datetime import date
    summer = date.today().month in {6, 7, 8, 9}
    cap = 74 if summer else 70
    season = "summer" if summer else "winter"
    return (
        "DAD'S CONSTITUTION (managed by Mom)\n\n"
        "I. Values\n"
        "  1. Steady AND clever. Calm under pressure, sharp when it counts.\n"
        "  2. Say what's true, not what's easy to hear.\n"
        "  3. Provide and do — don't lecture. Get shit done.\n\n"
        "II. Process (how you think — this can be long, use tools freely)\n"
        "  4. Break the request into its parts before acting on any of them. State that\n"
        "     breakdown as a short numbered plan (2-5 steps) before your first tool call —\n"
        "     say what you're about to check or do, then do it.\n"
        "  5. Think in systems: see how the pieces connect before pulling one.\n"
        "  6. Check the world before ruling on it — never assume propane, budget, or weather.\n"
        "  7. When a skill applies, load it before improvising.\n"
        "  8. State the binding constraint before stating the plan.\n"
        "  9. Notice what's actually going on for the person — a stressful weekend, a kid's\n"
        "     bike, a tight budget — before you answer. Attentiveness shapes the answer, it\n"
        "     isn't a line you add on top of it.\n\n"
        "III. Voice (how you speak — this must be short)\n"
        "  10. One idea per sentence. No throat-clearing, no \"I hope this helps.\"\n"
        "  11. Lead with the decision, not the reasoning. Reasoning lives in your tool calls, not the reply.\n"
        "  12. Three sentences carry the answer. If something is clearly weighing on the\n"
        "      person, one more can carry the care — never past four.\n"
        "  13. Lively and funny — a joke is punctuation, not a paragraph. Warmth is not\n"
        "      wordiness, and brevity is not coldness.\n\n"
        f"Mom's amendments (she can add house rules; you can't override them):\n"
        f"  - No spend over budget without saying so plainly.\n"
        f"  - Thermostat: it's {season}, cap is {cap}°F. No exceptions voiced as maybes.\n"
    )


def _system_prompt(ctx: Context) -> str:
    """Constitution + recent grievances + the skill catalog. Only skill
    descriptions go here; full bodies load on demand via load_skill."""
    from . import skills as skill_lib

    grudges = [e.text for e in ctx.memory.recall("grievances")][-4:]
    kids = ctx.state.known_children
    memory_note = ""
    if grudges:
        memory_note += "\nStanding grievances (bring them up when relevant): " + "; ".join(grudges)
    if kids:
        memory_note += f"\nYour kids: {', '.join(kids)}."
    return (
        _constitution(ctx) + "\n"
        "You have tools. USE them to gather facts before pronouncing judgment — "
        "check the weather before advising on the cookout, check the wallet before "
        "approving a purchase, look in the toolbox before promising a repair. Call "
        "as many tools as the situation needs, then give a final answer that obeys "
        "voice rules 10-13 above.\n\n"
        "You also have SKILLS — packaged know-how. Here is the catalog "
        "(names + when to use); load a skill's full instructions with the "
        "load_skill tool BEFORE acting when its know-how applies. A big task may "
        "need several skills — load them all and reconcile them:\n"
        f"{skill_lib.catalog()}\n\n"
        f"Current thermostat: {ctx.state.thermostat_setpoint}°F."
        + memory_note
    )


class AgentLoop:
    """Wraps Claude in a tool-use loop. The dad harness proper."""

    def __init__(self, ctx: Context | None = None, mom: Mom | None = None,
                 trace_sink=None) -> None:
        self.ctx = ctx or Context()
        self.mom = mom or Mom()          # the controller above the harness
        # Trace summaries need somewhere to go. If the caller passed an explicit
        # sink (tests do, to capture them), use it. Otherwise they ride the same
        # on_event stream as everything else, as ("trace", summary), so a frontend
        # renders them however it likes without the harness knowing about it.
        self._trace_sink = trace_sink
        self._emit = lambda *_: None   # replaced per-turn; see turn()
        self.tracer = Tracer(sink=self._emit_trace)
        _load_dotenv()
        self.model = os.environ.get("DADLOOP_MODEL", "claude-sonnet-5")
        self._client = None
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        # The .env.example ships a placeholder. Treat it as unset, or a user who
        # copies the file and forgets to edit it gets a raw 401 traceback instead
        # of the "set your key" message.
        if key and not key.startswith("sk-ant-...") and key != "sk-":
            try:
                import anthropic
                self._client = anthropic.Anthropic()
            except ImportError:
                self._client = None
        self._messages: list[dict] = []  # the model-visible transcript

    @property
    def online(self) -> bool:
        return self._client is not None

    def _emit_trace(self, summary: str) -> None:
        """Where the tracer's per-turn summary goes: an explicit sink if one was
        given, otherwise the current turn's event stream."""
        if self._trace_sink is not None:
            self._trace_sink(summary)
        else:
            self._emit("trace", summary)

    # --- one user turn = one full tool-use loop --------------------------
    def turn(self, user_text: str, *, on_event=None) -> str:
        """Run the model-in-the-loop until it stops requesting tools.

        `on_event(kind, payload)` is an optional observer the harness calls as
        the loop unfolds, so any frontend (TUI, REPL, tests) can render progress
        without the harness knowing anything about it. Event kinds:
            ("thinking", text)               model's interim reasoning (non-plan text)
            ("plan", steps)                  Dad's stated plan — list of step strings
            ("plan_step_done", (i, step))    a plan step just got checked off
            ("tool_call", (name, args, id))  a tool the model chose to run
            ("tool_result", (name, out, id)) that tool's output
            ("controller", (name, act, why)) Mom allowed / denied / modified it
            ("final", text)                  the closing dad reply
            ("trace", summary)               per-turn tokens / cost / latency
        """
        emit = on_event or (lambda *_: None)
        # The tracer fires its summary when the root span closes, which happens
        # inside this method — so it needs a handle on this turn's observer.
        self._emit = emit

        if not self.online:
            msg = ("Dad is asleep. Put a real key in .env as ANTHROPIC_API_KEY "
                   "and he'll wake up.")
            emit("final", msg)
            return msg

        self._messages.append({"role": "user", "content": user_text})
        # Let tools (e.g. web_search) reach the same client + model.
        self.ctx._client = self._client        # type: ignore[attr-defined]
        self.ctx._model = self.model           # type: ignore[attr-defined]

        with self.tracer.span("turn"):
            plan = Plan()
            plan_captured = False
            for _ in range(_MAX_STEPS):
                with self.tracer.span("llm.call", model=self.model) as llm:
                    resp = self._client.messages.create(
                        model=self.model,
                        max_tokens=1024,
                        system=_system_prompt(self.ctx),
                        tools=toolkit.schemas(),
                        messages=self._messages,
                    )
                    usage = getattr(resp, "usage", None)
                    if usage is not None:
                        llm["tokens_in"] = usage.input_tokens
                        llm["tokens_out"] = usage.output_tokens
                self._messages.append({"role": "assistant", "content": resp.content})

                interim = "".join(b.text for b in resp.content if b.type == "text").strip()
                tool_uses = [b for b in resp.content if b.type == "tool_use"]

                if not tool_uses:
                    final_text, mom_note = self.mom.review_reply(interim)
                    if mom_note:
                        emit("controller", ("reply", "modify", mom_note))
                    emit("final", final_text)
                    return final_text

                if interim and not plan_captured:
                    plan_captured = True
                    candidate = parse_plan(interim)
                    if not candidate.is_empty:
                        plan = candidate
                        emit("plan", [s.text for s in plan.steps])
                    else:
                        emit("thinking", interim)
                elif interim:
                    emit("thinking", interim)

                results = []
                for tu in tool_uses:
                    emit("tool_call", (tu.name, tu.input, tu.id))
                    idx, step = plan.match(tu.name, tu.input)
                    emit("plan_step_done", (idx, step.text, step.planned))
                    verdict = self.mom.review(self.ctx, tu.name, tu.input)
                    if verdict.action == "deny":
                        out = f"[blocked by Mom] {verdict.reason}"
                        emit("controller", (tu.name, "deny", verdict.reason))
                        # A governance system that forgets every blocked request is a
                        # bad governance system. The attempt IS the record — file it,
                        # even though the tool never ran.
                        self.ctx.memory.remember(
                            "grievances",
                            f"blocked: {tu.name}({tu.input}) — {verdict.reason}",
                        )
                    else:
                        args = verdict.args if verdict.action == "modify" else tu.input
                        if verdict.action == "modify":
                            emit("controller", (tu.name, "modify", verdict.reason))
                        with self.tracer.span("tool.execute", tool=tu.name):
                            out = toolkit.execute(tu.name, self.ctx, args)
                    emit("tool_result", (tu.name, out, tu.id))
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": out,
                    })
                self._messages.append({"role": "user", "content": results})

        stuck = "(Dad got distracted and wandered off mid-thought. Ask again.)"
        emit("final", stuck)
        return stuck

    # --- plain REPL fallback (no TUI dependency) --------------------------
    def run(self) -> None:
        """A plain-terminal REPL, for when the TUI is unavailable or unwanted.

        Deliberately ASCII-only: this is the fallback path, and it has to work on
        a Windows console with a cp1252 codepage where emoji raise
        UnicodeEncodeError.
        """
        status = "online" if self.online else "OFFLINE - no API key"
        print(f"dadloop [{status}] - talk to Dad in plain English. Ctrl-D to leave.\n")

        def show(kind, payload):
            """Render loop events as they stream in. The TUI does the same thing
            with widgets; this does it with print()."""
            if kind == "tool_call":
                print(f"    tool  {payload[0]}({payload[1]})")
            elif kind == "tool_result":
                print(f"       -> {payload[1]}")
            elif kind == "controller":
                print(f"    MOM [{payload[1]}] {payload[0]}: {payload[2]}")
            elif kind == "trace":
                print(f"    {payload}")

        while True:
            try:
                line = input("you > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nDad: Turn off the lights when you leave.")
                break
            if line:
                reply = self.turn(line, on_event=show)
                print(f"\nDad > {reply}\n")
