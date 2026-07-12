"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Terminal user interface for auditing agent turns and harness activity.

The work surface — a terminal UI where the harness shows its work.

This is not a chat window with a scrollback. Every part of a turn is auditable
without leaving the screen: the plan Dad stated, each tool call he made (openable,
with its arguments and result), each intervention Mom raised, and what the turn
cost in tokens and time.

The design rule throughout: show the seams. A tool call that was not in Dad's
stated plan is appended and marked unplanned. A blocked call gets a card, not a
log line. If the model and the harness disagree, you see it.

Widget choices from the Textual gallery:
  * Header / Footer      title, live clock, key bindings
  * Horizontal + Vertical  the two-pane layout: plan panel + transcript
  * Static (plan panel)  the stated plan, checking off as calls resolve
  * Markdown             each user + Dad turn, properly rendered
  * LoadingIndicator     shown while Dad thinks
  * Static (review card) Mom's interventions — a bordered card, not a log
                         line, so governance cannot be scrolled past
  * Input / Footer       message bar and key bindings

The blocking model loop runs in a worker thread; harness events are marshalled
back to the UI thread with call_from_thread, so the plan panel fills in live.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll, Grid
from textual.screen import Screen
from textual.widgets import (
    Header, Footer, Input, Markdown, Static, LoadingIndicator, Collapsible,
)

from .core.agent import AgentLoop
from .theme import DADLOOP_THEME
from .core import tools as toolkit
from .core import skills as skill_lib

# Verb-first titles for reasoning steps — "Checking the grill", not check_grill().
_VERBS = {
    "check_weather": "Checking the weather",
    "check_grill": "Checking the grill",
    "check_pantry": "Checking the pantry",
    "check_hardware_store": "Checking the hardware store",
    "set_thermostat": "Adjusting the thermostat",
    "check_wallet": "Checking the budget",
    "find_tool": "Rummaging the toolbox",
    "web_search": "Searching the web",
    "remember": "Filing that away",
    "recall": "Checking memory",
    "load_skill": "Pulling up the playbook",
    "tell_joke": "Winding up",
}


class Thinking(Static):
    """A 'Dad is thinking' row wrapping a real LoadingIndicator."""

    def compose(self) -> ComposeResult:
        yield LoadingIndicator()


class PlanPanel(Static):
    """The plan checklist. Dad states a plan,
    each item goes from pending to done as its tool call resolves, and a
    tool call outside the stated plan appears live, marked unplanned."""

    def __init__(self) -> None:
        super().__init__("[dim]No active plan.[/dim]", id="plan-panel")
        self._lines: list[tuple[str, bool, bool]] = []  # (text, done, planned)

    def set_plan(self, steps: list[str]) -> None:
        self._lines = [(s, False, True) for s in steps]
        self.update(self._as_text())

    def mark_done(self, idx: int, text: str, planned: bool) -> None:
        if idx < len(self._lines):
            self._lines[idx] = (text, True, planned)
        else:
            # Appended live — grew past the stated plan.
            self._lines.append((text, True, planned))
        self.update(self._as_text())

    def clear(self) -> None:
        self._lines = []
        self.update("[dim]No active plan.[/dim]")

    def _as_text(self) -> str:
        """Build the display string. Never calls update() — this may run
        during Textual's own layout/measurement pass, and calling update()
        (which triggers a layout refresh) from inside that pass recurses
        into a widget the compositor hasn't finished placing yet."""
        if not self._lines:
            return "[dim]No active plan.[/dim]"
        rows = []
        for text, done, planned in self._lines:
            if not done:
                mark = "○"
            elif planned:
                mark = "[green]●[/green]"
            else:
                mark = "[yellow]+[/yellow]"
            tag = "" if planned else " [dim](unplanned)[/dim]"
            rows.append(f"{mark} {text}{tag}")
        return "[b]PLAN[/b]\n" + "\n".join(rows)


class StatsPanel(Static):
    """Dad's scoreboard — how the harness is performing this session, plus
    what he's accomplished across every session on disk. Separate job from
    the plan panel: that one tracks 'what's happening now', this one tracks
    'what has happened, ever'."""

    def __init__(self, dad: AgentLoop) -> None:
        super().__init__(id="stats-panel")
        self.dad = dad

    def refresh_stats(self) -> None:
        self.update(self._as_text())

    def on_mount(self) -> None:
        self.update(self._as_text())

    def _as_text(self) -> str:
        s = self.dad.ctx.state
        t = self.dad.tracer.totals
        ledger = self.dad.ctx.memory.ledger()
        return (
            "[b]DAD[/b]\n"
            f"{s.thermostat_setpoint}°F · {s.dad_jokes_told} jokes\n\n"
            "[b]THIS SESSION[/b]\n"
            f"{t.turns} turns · {t.llm_calls} llm · {t.tool_calls} tools\n"
            f"tokens {t.tokens_in}→{t.tokens_out} · ~${t.cost:.4f}\n"
            f"avg {t.avg_turn_ms:.0f}ms/turn\n\n"
            "[b]ALL TIME[/b]\n"
            f"{ledger['grievances']} grievances · {ledger['lessons']} lessons\n"
            f"{ledger['rulings']} rulings · {ledger['people']} people known"
        )


class ReviewCard(Static):
    """Mom's interventions — a bordered review card, not a toast. This is
    so a blocked or rewritten call cannot be scrolled past unnoticed."""

    def __init__(self, verb: str, name: str, reason: str) -> None:
        icon = "🛑" if verb == "vetoed" else "✋"
        super().__init__(
            f"{icon} [b]MOM {verb.upper()}[/b] — {name}\n{reason}",
            classes="review-card",
        )


class AdminScreen(Screen):
    """The harness as a system, not a chat. A separate full-screen view —
    toggled with ctrl+a — so the chat surface stays clean and this gets the
    width to actually lay out six sections instead of squeezing into a
    30-column sidebar. Everything here is read fresh when the screen mounts;
    it's a manifest of what the harness has, not a live feed of what's
    happening (that's the plan/stats panels' job, back in chat)."""

    BINDINGS = [
        Binding("f4", "app.pop_screen", "Back", show=True),
        Binding("escape", "app.pop_screen", "Back", show=False),
        Binding("tab", "focus_next", "Next pane", show=True),
        Binding("shift+tab", "focus_previous", "Prev", show=False),
    ]

    CSS = """
    AdminScreen { background: $background; }

    /* The constitution is 13 rules of prose; the others are short lists. A
       uniform grid gives every pane the same box, which crams the one that
       needs room and wastes space on the ones that don't. So: the constitution
       gets a full-height column of its own, and the five short panes share the
       rest. */
    #admin-grid {
        grid-size: 3 3;
        grid-columns: 1fr 1fr 1fr;
        grid-rows: 1fr 1fr 1fr;
        grid-gutter: 1 2;
        padding: 1 2;
    }
    .admin-box {
        border: round $harness-dim;
        background: $panel;
        padding: 1 2;
        height: 1fr;
        scrollbar-size-vertical: 1;
    }
    /* Row spans must add up: three columns of three rows is nine cells, and
       every pane needs one. Long panes take two rows, short ones take one.
         col 1: tools(2) + mom(1)
         col 2: skills(2) + memory(1)
         col 3: constitution(2) + telemetry(1)
       Get this wrong and a pane silently collapses to 0x0. */
    #box-tools { row-span: 2; }
    #box-skills { row-span: 2; }
    #box-constitution { row-span: 2; }

    /* The focused pane is unmistakable — you always know where Tab left you. */
    .admin-box:focus {
        border: round $dad;
        background: $dad 6%;
    }
    """

    def __init__(self, dad: AgentLoop, skills_loaded: list[str]) -> None:
        super().__init__()
        self.dad = dad
        self.skills_loaded = skills_loaded

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Grid(id="admin-grid"):
            # VerticalScroll (not Static) so each pane is focusable and can be
            # scrolled with the keyboard. A pane you cannot scroll is a pane you
            # cannot read, and several of these overflow by design.
            #
            # Grid order fills column by column: tools and skills take two rows
            # each in the left columns, the constitution takes all three on the
            # right, and the three short panes fill the gaps.
            panes = [
                ("box-tools", self._tools_text()),                  # col 1, rows 1-2
                ("box-skills", self._skills_text()),                # col 2, rows 1-2
                ("box-constitution", self._constitution_text()),    # col 3, rows 1-2
                ("box-mom", self._mom_text()),                      # col 1, row 3
                ("box-memory", self._memory_text()),                # col 2, row 3
                ("box-telemetry", self._observability_text()),      # col 3, row 3
            ]
            for pane_id, text in panes:
                with VerticalScroll(id=pane_id, classes="admin-box"):
                    yield Static(text)
        yield Footer()

    # --- six sections, each a pure string builder --------------------------
    def _tools_text(self) -> str:
        rows = [f"• {s['name']}" for s in toolkit.schemas()]
        return f"[b]TOOLS[/b] ({len(rows)})\n" + "\n".join(rows)

    def _skills_text(self) -> str:
        """All installed skills, with the ones pulled this session marked. The
        distinction is the point: the catalog is what he *could* reach for, the
        marks are what he actually did."""
        loaded = set(self.skills_loaded)
        rows = []
        for name in skill_lib.SKILLS:
            mark = "[$skill]●[/]" if name in loaded else "[dim]○[/dim]"
            rows.append(f"{mark} {name}")
        return (f"[b]SKILLS[/b] [dim]({len(loaded)}/{len(skill_lib.SKILLS)} "
                f"used)[/dim]\n\n" + "\n".join(rows))

    def _constitution_text(self) -> str:
        """The full constitution. It is longer than the pane — that is expected,
        and the header says so, because a silently truncated pane reads as the
        whole story."""
        from .core.agent import _constitution
        text = _constitution(self.dad.ctx)
        rules = [l.strip() for l in text.splitlines() if l.strip() and l.strip()[0].isdigit()]
        return (f"[b]CONSTITUTION[/b] ({len(rules)} rules)\n"
                f"[dim]tab here, then scroll[/dim]\n\n" + "\n\n".join(rules))

    def _mom_text(self) -> str:
        rows = []
        for p in self.dad.mom.policies:
            doc = (p.__doc__ or "").strip().splitlines()[0] if p.__doc__ else p.__name__
            rows.append(f"• {doc}")
        rows.append(f"• max reply: {self.dad.mom.max_reply_sentences} sentences")
        return f"[b]MOM'S POLICIES[/b] ({len(self.dad.mom.policies)})\n" + "\n".join(rows)

    def _memory_text(self) -> str:
        root = self.dad.ctx.memory.root
        rows = [f"• {name}  ({size}b)" for name, size in self.dad.ctx.memory.files()]
        return f"[b]MEMORY[/b]\n{root}\n" + "\n".join(rows)

    def _observability_text(self) -> str:
        t = self.dad.tracer.totals
        return (
            "[b]OBSERVABILITY[/b]\n"
            f"turns:      {t.turns}\n"
            f"llm calls:  {t.llm_calls}\n"
            f"tool calls: {t.tool_calls}\n"
            f"tokens:     {t.tokens_in}→{t.tokens_out}\n"
            f"cost:       ~${t.cost:.4f}\n"
            f"avg/turn:   {t.avg_turn_ms:.0f}ms"
        )


class DadApp(App):
    TITLE = "dadloop"
    SUB_TITLE = "an agent harness for knowledge work"

    # Colour is semantic here — see theme.py. $dad is amber, $mom is violet,
    # $harness is slate, $skill is teal, $problem is rust. Nothing in this
    # stylesheet should use a raw colour.
    CSS = """
    Screen { layout: vertical; background: $background; }

    #body { height: 1fr; }

    /* --- left rail: what he is doing, and how it is going ---------------- */
    #sidebar { width: 32; min-width: 28; }

    #plan-panel {
        height: 1fr;
        padding: 1 2;
        background: $panel;
        border-right: solid $harness-dim;
    }

    #stats-panel {
        height: auto;
        padding: 1 2;
        background: $panel;
        border-right: solid $harness-dim;
        border-top: solid $harness-dim;
        color: $harness;
    }

    /* --- the canvas ------------------------------------------------------ */
    #main { width: 1fr; }
    #log { padding: 1 2; }

    /* You: quiet. Dad: warm and prominent — he is the one talking. */
    Markdown.you {
        color: $harness;
        margin: 1 0 0 0;
        padding: 0 1;
        border-left: thick $harness-dim;
    }
    Markdown.dad {
        background: $dad 8%;
        border-left: thick $dad;
        margin: 1 0;
        padding: 0 1;
    }

    /* Reasoning steps. Collapsed by default; the focused one is unmistakable. */
    .step {
        margin: 0 0 0 2;
        border-left: solid $harness-dim;
    }
    .step-body {
        padding: 0 1;
        color: $text-muted;
        max-height: 12;      /* long tool output scrolls rather than flooding */
        overflow-y: auto;
    }
    Collapsible.step:focus-within {
        border-left: thick $dad;
        background: $dad 6%;
    }

    /* Skills being pulled off the shelf. */
    .skill-marker {
        margin: 0 0 0 2;
        padding: 0 1;
        color: $skill;
        text-style: bold;
    }

    /* Mom. Violet, not red: a veto is authority, not a crash. */
    .review-card {
        margin: 1 0 1 2;
        padding: 1 2;
        border: round $mom;
        background: $mom 10%;
        color: $text;
    }

    /* Telemetry sits at the bottom of the turn, deliberately quiet. */
    Markdown.trace { color: $harness-dim; margin: 0 0 1 2; }

    Thinking { height: 1; margin: 0 0 0 2; }

    /* Empty state: tell a new user what to actually type. */
    #empty-state {
        padding: 2 4;
        color: $text-muted;
        border: round $harness-dim;
        margin: 2 4;
    }

    #input {
        dock: bottom;
        margin: 1 2;
        border: tall $harness-dim;
    }
    #input:focus { border: tall $dad; }
    """

    # Function keys, not ctrl-combos. The Input widget claims ctrl+a, ctrl+e,
    # ctrl+c, ctrl+k and friends for line editing, and a focused Input *wins* —
    # so an app-level ctrl+e binding is silently dead while the user is typing,
    # which is exactly when they would reach for it. F-keys are unclaimed.
    BINDINGS = [
        Binding("tab", "focus_next", "Step", show=True),
        Binding("shift+tab", "focus_previous", "Back", show=False),
        Binding("f2", "expand_all", "Expand", show=True),
        Binding("f3", "collapse_all", "Collapse", show=True),
        Binding("f4", "admin", "Admin", show=True),
        Binding("f5", "clear", "Clear", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def __init__(self, dad: AgentLoop | None = None) -> None:
        super().__init__()
        # Register before the stylesheet is parsed — the CSS below references
        # $dad, $mom and friends, and Textual resolves those at parse time. Doing
        # this in on_mount is too late and raises UnresolvedVariableError.
        self.register_theme(DADLOOP_THEME)
        self.theme = "dadloop"
        self.dad = dad or AgentLoop()
        self._thinking: Thinking | None = None
        self._skills_loaded: list[str] = []

    # --- layout -----------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield PlanPanel()
                yield StatsPanel(self.dad)
            with Vertical(id="main"):
                yield VerticalScroll(id="log")
                yield Input(placeholder="Talk to Dad…  (e.g. 'are we ready for the cookout?')",
                            id="input")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = "online" if self.dad.online else "offline - no API key"

        if self.dad.online:
            # An empty canvas tells a new user nothing. Show them what to type,
            # and pick an example that actually exercises the harness rather than
            # a trivial one.
            self._mount(Static(
                "[b]Ask him something that has to be worked out, not just answered.[/b]\n\n"
                "  [$dad]Twelve people Saturday, and I've got forty bucks.[/]\n"
                "  [$dad]Grill's not lighting and people are coming at six.[/]\n"
                "  [$dad]Can we just get the nice grill? It's like $400.[/]\n\n"
                "[dim]Tab moves between his reasoning steps once he starts. "
                "f2 opens the admin view.[/dim]",
                id="empty-state"))
        else:
            self._mount(Static(
                "[b]Dad is asleep.[/b]\n\n"
                "Put a real key in [b]. env[/b] as ANTHROPIC_API_KEY and restart.\n"
                "[dim]The tests run without one: python tests/test_plan.py[/dim]",
                id="empty-state"))
        self.query_one("#input", Input).focus()

    def _clear_empty_state(self) -> None:
        """The empty state is guidance, not history — it goes as soon as there
        is real work on the canvas."""
        for w in self.query("#empty-state"):
            w.remove()

    # --- helpers ----------------------------------------------------------
    def _mount(self, widget, *, scroll: bool = True) -> None:
        """Add a widget to the canvas. `scroll=False` for the question that
        opened a turn — auto-scrolling past it means you can no longer see what
        was asked, which defeats the point of an auditable canvas."""
        self.query_one("#log", VerticalScroll).mount(widget)
        if scroll:
            widget.scroll_visible()

    # --- input ------------------------------------------------------------
    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        event.input.disabled = True
        self._clear_empty_state()
        self._mount(Markdown(f"**You** — {text}", classes="you"))
        self.query_one(PlanPanel).clear()
        self._thinking = Thinking()
        self._mount(self._thinking)
        self._run_turn(text)

    # --- the turn on a worker thread --------------------------------------
    def _run_turn(self, text: str) -> None:
        # call_id -> the Static holding that step's result, so the tool_result
        # event can fill in the body of the right Collapsible.
        bodies: dict[str, Static] = {}

        def on_event(kind: str, payload) -> None:
            if kind == "plan":
                self.call_from_thread(self.query_one(PlanPanel).set_plan, payload)
            elif kind == "plan_step_done":
                idx, step_text, planned = payload
                self.call_from_thread(
                    self.query_one(PlanPanel).mark_done, idx, step_text, planned)
            elif kind == "tool_call":
                name, args, call_id = payload
                if name == "load_skill":
                    skill_name = args.get("name")
                    if skill_name and skill_name not in self._skills_loaded:
                        self._skills_loaded.append(skill_name)
                    self.call_from_thread(self._mount_skill_marker, skill_name)
                self.call_from_thread(self._mount_step, name, args, call_id, bodies)
            elif kind == "tool_result":
                name, out, call_id = payload
                body = bodies.get(call_id)
                if body is not None:
                    self.call_from_thread(body.update, str(out))
            elif kind == "controller":
                name, action, reason = payload
                verb = "vetoed" if action == "deny" else "adjusted"
                target = "your reply" if name == "reply" else name
                self.call_from_thread(self._mount, ReviewCard(verb, target, reason))
            elif kind == "final":
                self.call_from_thread(self._show_final, payload)
            elif kind == "trace":
                self.call_from_thread(self._mount,
                                      Markdown(f"`{payload}`", classes="trace"))

        def work() -> None:
            self.dad.turn(text, on_event=on_event)
            self.call_from_thread(self._finish_turn)

        self.run_worker(work, thread=True, exclusive=True)

    def _mount_step(self, name: str, args: dict, call_id: str,
                    bodies: dict[str, Static]) -> None:
        """One reasoning step on the canvas — collapsed by default, Tab to it
        and Enter to expand. The CollapsibleTitle is focusable and has its own
        enter binding, so this is real keyboard navigation, not a scheme I
        invented on top."""
        verb = _VERBS.get(name, name)
        arg_str = ", ".join(f"{k}={v!r}" for k, v in (args or {}).items())
        title = f"{verb}  ({arg_str})" if arg_str else verb
        body = Static("[dim]running…[/dim]", classes="step-body")
        bodies[call_id] = body
        self._mount(Collapsible(body, title=title, collapsed=True,
                                classes="step"))

    def _mount_skill_marker(self, skill_name: str) -> None:
        """Skills assembling is the work — show it on the canvas, not just in
        the admin view."""
        self._mount(Static(f"📚 assembled skill: [b]{skill_name}[/b]",
                           classes="skill-marker"))

    def _show_final(self, text: str) -> None:
        if self._thinking is not None:
            self._thinking.remove()
            self._thinking = None
        self._mount(Markdown(f"**Dad** — {text}", classes="dad"))

    def _finish_turn(self) -> None:
        if self._thinking is not None:
            self._thinking.remove()
            self._thinking = None
        self.query_one(StatsPanel).refresh_stats()
        inp = self.query_one("#input", Input)
        inp.disabled = False
        inp.focus()

    # --- actions ----------------------------------------------------------
    def action_clear(self) -> None:
        self.query_one("#log", VerticalScroll).remove_children()
        self.query_one(PlanPanel).clear()
        self._mount(Markdown("*Cleared. Dad's memory, of course, is forever.*", classes="dad"))

    def action_admin(self) -> None:
        self.push_screen(AdminScreen(self.dad, self._skills_loaded))

    def action_expand_all(self) -> None:
        for c in self.query(Collapsible):
            c.collapsed = False

    def action_collapse_all(self) -> None:
        for c in self.query(Collapsible):
            c.collapsed = True


def launch(dad: AgentLoop | None = None) -> None:
    DadApp(dad).run()
