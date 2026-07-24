"""Author: Swami Chandrasekaran
Last Modified: 2026-07-20
Purpose: Terminal user interface for auditing agent turns and harness activity.

The work surface — a calmer, long-horizon terminal UI where the harness shows
its work. Three screens on one shell, all plain Textual widgets:

  * Main loop     a left rail (plan + progress, Dad state, session, memory) and a
                  canvas of the transcript: user turns, collapsible tool-step
                  groups, gold skill-assembly markers, per-turn trace lines, and a
                  docked prompt.
  * Admin (F4)    the harness as a system — a tool registry, the skill catalog,
                  Mom's policies, memory on disk, the constitution, and live
                  telemetry. A manifest of what the harness *has*, laid out so no
                  pane is squeezed out of existence.
  * Governance    when Mom holds an action, a gold-bordered card names the
    hold        proposed call and her reasoning over a dimmed transcript.

This is not a chat window with a scrollback. Every part of a turn is auditable
without leaving the screen: the plan Dad stated, each tool call (openable, with
arguments and result), each intervention Mom raised, and what the turn cost.

The design rule throughout: show the seams. A tool call that was not in Dad's
stated plan is appended and marked unplanned. A blocked call gets a card, not a
log line. If the model and the harness disagree, you see it.

Colour is semantic and defined once in theme.py — coral is Dad and the single
accent, olive is "went right", gold is skills-and-governance-attention, rust is
real trouble, and a five-stop neutral ramp does the structural work. Nothing in
this file uses a raw colour; every style resolves a $token.

The blocking model loop runs in a worker thread; harness events are marshalled
back to the UI thread with call_from_thread, so the rail and canvas fill in live.
"""

from __future__ import annotations

import os

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll, Grid
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    Input, Markdown, Static, Collapsible, Button,
)

from .core.agent import AgentLoop
from .launch import LaunchScreen
from .theme import DADLOOP_THEME, paint, markup as _mk
from .core import tools as toolkit
from .core import skills as skill_lib


class _S(Static):
    """A Static that resolves our theme tokens in its content.

    Rich renders content markup, and Rich knows nothing about Textual theme
    variables — so [$dad]…[/] would print literally (or worse, be rejected) on
    any Textual version that doesn't pre-resolve them. Substituting here means
    every label in this file can keep writing semantic names instead of hex,
    and it behaves the same on old and new Textual alike.
    """

    def __init__(self, content: str = "", **kwargs) -> None:
        super().__init__(_mk(content) if isinstance(content, str) else content,
                         **kwargs)

    def update(self, content: str = "") -> None:  # type: ignore[override]
        super().update(_mk(content) if isinstance(content, str) else content)

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

# One-line descriptions for the admin tool registry. Falls back to the tool's
# own schema description when a verb isn't listed here.
_TOOL_BLURB = {
    "check_weather": "current weather via web",
    "check_grill": "equipment status",
    "check_pantry": "inventory lookup",
    "check_hardware_store": "store availability",
    "set_thermostat": "climate control",
    "check_wallet": "wallet & spend guard",
    "find_tool": "toolbox search",
    "web_search": "external lookup",
    "remember": "grievance / lesson store",
    "recall": "memory search",
    "load_skill": "assemble a skill playbook",
    "tell_joke": "deploy a dad joke",
}


class StatusLine(_S):
    """The live "he's working" line: a spinner, what he's doing, and a dim hint
    of what it's for. Replaces a bare LoadingIndicator because a spinner alone
    says "busy" — this says *what* he's busy with, which is the whole point of a
    surface that shows its work.

    The frames animate on a timer rather than a LoadingIndicator so the label can
    change mid-turn as the loop moves on to the next thing."""

    _FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self) -> None:
        super().__init__(id="status-line")
        self._i = 0
        self._label = "Thinking"
        self._hint = ""

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.08, self._tick)

    def set_activity(self, label: str, hint: str = "") -> None:
        self._label, self._hint = label, hint

    def _tick(self) -> None:
        self._i = (self._i + 1) % len(self._FRAMES)
        frame = self._FRAMES[self._i]
        # Three dots that breathe with the spinner, as in the design.
        phase = (self._i // 3) % 4
        dots = "".join(
            "[$dad]·[/]" if d < phase else "[$faint]·[/]" for d in range(3)
        )
        hint = f"  [$muted-2]{self._hint}[/]" if self._hint else ""
        self.update(f"[$dad]{frame}[/] [$dad]{self._label}[/] {dots}{hint}")


# ------------------------------------------------------------------ rail panels
class TitleBar(_S):
    """The shell's top strip: app identity, session, model, status, clock.

    The content is built to fit the width it actually has. A fixed string here
    is a layout bug waiting to happen — at 123 characters it wrapped to a second
    row on any terminal narrower than about 130 columns, stealing a row from the
    canvas and pushing the chrome around. So the bar drops its least important
    parts as space runs out, rather than wrapping.
    """

    def __init__(self, dad: AgentLoop) -> None:
        super().__init__(id="titlebar")
        self.dad = dad
        # The session name is the memory directory — the thing that actually
        # distinguishes one run's accumulated state from another's. Use the
        # parent when the leaf is a bare store folder like ".../picnic-plan/m".
        root = getattr(dad.ctx.memory, "root", None)
        if root is None:
            self.session = "default"
        else:
            name = root.name
            if len(name) <= 2 and root.parent.name:
                name = root.parent.name
            self.session = name

    def on_mount(self) -> None:
        self.set_interval(1.0, self.refresh_bar)
        self.refresh_bar()

    def on_resize(self) -> None:
        # Re-fit when the terminal changes size.
        self.refresh_bar()

    def refresh_bar(self) -> None:
        from datetime import datetime

        width = self.size.width or 80
        now = datetime.now()
        clock = now.strftime("%H:%M:%S")
        status = "online" if self.dad.online else "offline"
        status_c = "$done" if self.dad.online else "$problem"

        # Parts in priority order — identity first, then what it costs to lose.
        # Each is (plain text for measuring, marked-up text for display).
        name = ("dadloop", "[b $dad]dadloop[/]")
        tag = (" — an agent harness, explained through Dad",
               " [$muted-2]— an agent harness, explained through Dad[/]")
        sess = (f"  session {self.session}",
                f"  [$muted]session[/] [$ink-text]{self.session}[/]")
        model = (f" · {self.dad.model}", f" [$faint]·[/] [$muted]{self.dad.model}[/]")
        stat = (f"  ● {status}", f"  [{status_c}]● {status}[/]")
        time_ = (f" · {clock}", f" [$faint]·[/] [$muted-2]{clock}[/]")

        # Always show the dot, name and status; add the rest while it fits.
        dot = ("● ", f"[{status_c}]●[/] ")
        chosen = [dot, name, stat]
        for part in (tag, sess, model, time_):
            candidate = chosen + [part]
            if sum(len(p[0]) for p in candidate) <= width - 2:
                # keep display order stable: everything sits before status/time
                chosen.insert(len(chosen) - 1, part)
        self.update("".join(p[1] for p in chosen))


class PlanPanel(_S):
    """The plan checklist with a progress bar. Dad states a plan; each item goes
    from pending to done as its tool call resolves, and a tool call outside the
    stated plan appears live, marked unplanned. The active step is highlighted so
    you always know where the loop is."""

    def __init__(self) -> None:
        super().__init__(id="plan-panel")
        self._lines: list[tuple[str, bool, bool]] = []  # (text, done, planned)

    def on_mount(self) -> None:
        self.update(self._as_text())

    def set_plan(self, steps: list[str]) -> None:
        self._lines = [(s, False, True) for s in steps]
        self.update(self._as_text())

    def mark_done(self, idx: int, text: str, planned: bool) -> None:
        if idx < len(self._lines):
            self._lines[idx] = (text, True, planned)
        else:
            self._lines.append((text, True, planned))
        self.update(self._as_text())

    def clear(self) -> None:
        self._lines = []
        self.update(self._as_text())

    def _bar(self, done: int, total: int) -> str:
        """A slim coral progress bar drawn with block glyphs — cheaper than a
        ProgressBar widget for a one-line rail element, and it themes cleanly."""
        width = 22
        filled = 0 if total == 0 else round(width * done / total)
        return f"[$dad]{'━' * filled}[/][$hair-2]{'━' * (width - filled)}[/]"

    def _as_text(self) -> str:
        """Build the display string. Never calls update() — this may run during
        Textual's own layout pass, and update() from inside that pass recurses
        into a widget the compositor hasn't finished placing."""
        header = "[$dad]PLAN[/]"
        if not self._lines:
            return f"{header}\n[$muted-2]No active plan.[/]"

        total = len(self._lines)
        done = sum(1 for _, d, _ in self._lines if d)
        active_marked = False
        rows = []
        for text, is_done, planned in self._lines:
            if is_done:
                mark = "[$done]✓[/]"
                body = f"[$muted-2 strike]{text}[/]"
                rows.append(f"{mark} {body}")
            elif not active_marked:
                # First pending line is where the loop is working right now. The
                # design gives it a filled band; in a terminal the equivalent is
                # a reverse-video wash on the whole row, which reads the same way
                # at a glance.
                active_marked = True
                tag = "" if planned else " [$muted-2](unplanned)[/]"
                rows.append(f"[on $dad 20%][$dad]▸[/] [$paper]{text}[/]{tag}[/]")
            else:
                mark = "[$faint]○[/]"
                tag = "" if planned else " [$muted-2](unplanned)[/]"
                rows.append(f"{mark} [$muted]{text}[/]{tag}")

        return (
            f"{header}   [$muted-2]{done} / {total} done[/]\n"
            f"{self._bar(done, total)}\n\n" + "\n".join(rows)
        )


class RailStats(_S):
    """The rail's lower half: Dad's state, this session's telemetry, and the
    all-time memory ledger. Separate job from the plan panel — that tracks
    'what's happening now', this tracks 'what has happened'."""

    def __init__(self, dad: AgentLoop) -> None:
        super().__init__(id="rail-stats")
        self.dad = dad

    def on_mount(self) -> None:
        self.update(self._as_text())

    def refresh_stats(self) -> None:
        self.update(self._as_text())

    def _row(self, label: str, value: str, accent: str = "$ink-text") -> str:
        return f"[$muted-2]{label}[/]  [{accent}]{value}[/]"

    def _as_text(self) -> str:
        s = self.dad.ctx.state
        t = self.dad.tracer.totals
        led = self.dad.ctx.memory.ledger()
        jokes = f"{s.dad_jokes_told} joke" + ("s" if s.dad_jokes_told != 1 else "")
        return (
            "[$muted]DAD[/]\n"
            # This is the house thermostat, not the weather outside — label it,
            # or a bare "68°F" next to a Dallas-based agent reads as a wrong
            # forecast. Outdoor weather is fetched live by check_weather.
            f"[$muted-2]thermostat[/] [$ink-text]{s.thermostat_setpoint}°F[/] "
            f"[$faint]·[/] [$muted]mood[/] [$done]easygoing[/]\n"
            f"[$muted-2]{jokes} told[/]\n\n"
            "[$muted]THIS SESSION[/]\n"
            f"{self._row('turns', str(t.turns))}\n"
            f"{self._row('llm calls', str(t.llm_calls))}\n"
            f"{self._row('tools run', str(t.tool_calls))}\n"
            f"{self._row('tokens', f'{t.tokens_in}↑ {t.tokens_out}↓')}\n"
            f"{self._row('spend', f'${t.cost:.4f}', '$dad')}\n"
            f"{self._row('avg / turn', f'{t.avg_turn_ms:.0f}ms')}\n\n"
            + self._accomplishments(led)
            + self._top_skills()
            + "[$muted]MEMORY[/]\n"
            f"{self._row('grievances', str(led['grievances']))}\n"
            f"{self._row('rulings', str(led['rulings']))}\n"
            f"{self._row('lessons', str(led['lessons']))}\n"
            f"{self._row('people', str(led['people']))}"
        )

    def _accomplishments(self, led: dict[str, int]) -> str:
        """What Dad has actually got done, across every session.

        The MEMORY block below counts rows in files; this says what those rows
        MEAN. A ruling is a decision that stuck, a lesson is something he won't
        get wrong twice, a grievance is a problem he logged rather than dropped.
        Same numbers, read as accomplishments instead of storage — which is the
        thing you actually want to know after a week of using this.
        """
        rulings = led.get("rulings", 0)
        lessons = led.get("lessons", 0)
        grievances = led.get("grievances", 0)
        decided = rulings + lessons

        if decided == 0 and grievances == 0:
            return ("[$muted]ACCOMPLISHMENTS[/]\n"
                    "[$muted-2]nothing filed yet — ask him something[/]\n\n")

        lines = ["[$muted]ACCOMPLISHMENTS[/]"]
        if rulings:
            lines.append(f"[$done]✓[/] [$ink-text]{rulings}[/] "
                         f"[$muted-2]call{'s' if rulings != 1 else ''} settled[/]")
        if lessons:
            lines.append(f"[$done]✓[/] [$ink-text]{lessons}[/] "
                         f"[$muted-2]lesson{'s' if lessons != 1 else ''} learned[/]")
        if grievances:
            lines.append(f"[$hold]•[/] [$ink-text]{grievances}[/] "
                         f"[$muted-2]carried forward[/]")
        return "\n".join(lines) + "\n\n"

    def _top_skills(self) -> str:
        """Which playbooks this household actually reaches for.

        Read from disk, so it describes the household over time rather than the
        last ten minutes. A skill nobody ever loads is a skill worth deleting;
        this is the panel that tells you which those are.
        """
        try:
            top = self.dad.ctx.memory.top_skills(limit=4)
        except Exception:
            return ""
        if not top:
            return ("[$muted]TOP SKILLS[/]\n"
                    "[$muted-2]none loaded yet[/]\n\n")

        busiest = top[0][1]
        lines = ["[$muted]TOP SKILLS[/]"]
        for name, count in top:
            # A tiny bar makes the ranking readable at a glance; the count alone
            # forces you to compare numbers in your head.
            width = max(1, round(6 * count / busiest))
            bar = f"[$skill]{'▪' * width}[/][$hair-2]{'▪' * (6 - width)}[/]"
            label = name if len(name) <= 15 else name[:14] + "…"
            lines.append(f"{bar} [$ink-text]{label}[/] [$muted-2]{count}[/]")
        return "\n".join(lines) + "\n\n"


class KeyBar(_S):
    """The footer.

    Textual's stock Footer renders whatever bindings are active on the focused
    widget. In this app focus lives in the Input almost all of the time, and an
    Input's own binding chain is thirty-odd line-editing keys, all show=False —
    so the Footer ends up drawing nothing at all. The keys the user actually
    needs (admin, clear, quit) are app-level, and they never make the list.

    So the key bar is written out directly. It is a fixed set of keys that are
    always true regardless of focus, which is also the honest thing to show: F4
    opens admin whether you are typing or not.
    """

    KEYS = [
        ("Tab", "step"),
        ("F2", "expand"),
        ("F3", "collapse"),
        ("F4", "admin"),
        ("F5", "clear"),
        ("^Q", "quit"),
    ]

    # The admin screen has a different way out and no canvas to expand.
    ADMIN_KEYS = [
        ("Tab", "next pane"),
        ("↑↓", "scroll"),
        ("Esc", "back"),
        ("F4", "back"),
        ("^Q", "quit"),
    ]

    def __init__(self, keys: list[tuple[str, str]] | None = None, **kwargs) -> None:
        self.KEYS = keys or self.KEYS
        super().__init__(self._bar(), **kwargs)

    def _bar(self) -> str:
        parts = [f"[$dad]{key}[/] [$muted-2]{label}[/]" for key, label in self.KEYS]
        return "  ".join(parts)


class ReviewCard(_S):
    """Mom's lighter-touch interventions — a rewritten argument or a trimmed
    reply — as a bordered card so a change can't be scrolled past unnoticed.
    A full hold (a denied call) gets the GovernanceHold modal instead.

    Subclasses _S so the $hold / $ink-text tokens resolve on every Textual
    version rather than printing as literal markup.
    """

    def __init__(self, verb: str, name: str, reason: str) -> None:
        super().__init__(
            f"[$hold]⚖ MOM {verb.upper()}[/] [$muted-2]—[/] [$ink-text]{name}[/]\n"
            f"[$ink-text]{reason}[/]",
            classes="review-card",
        )


# ----------------------------------------------------------- governance modal
class GovernanceHold(ModalScreen):
    """Mom holds an action for review. A gold-bordered card over a dimmed
    transcript names the proposed call and her reasoning, with Approve / Revise /
    Veto.

    The buttons are a deliberate placeholder, not dead wiring: the loop reviews
    calls synchronously and has already blocked this one by the time the modal
    appears, so today the buttons only dismiss it and the outcome is already
    logged on the canvas. They are kept — rather than hidden — because the shape
    of the eventual interaction is worth showing now, and because the async
    version only needs to make the loop await this screen's result, with nothing
    else in the UI changing. Until then, treat it as an explanation of the block,
    not a live decision."""

    BINDINGS = [
        Binding("ctrl+y", "decide('approve')", "Approve", show=True),
        Binding("ctrl+e", "decide('revise')", "Revise", show=True),
        Binding("ctrl+n", "decide('veto')", "Veto", show=True),
        Binding("escape", "decide('dismiss')", "Close", show=False),
    ]

    CSS = paint("""
    GovernanceHold { align: center middle; background: $background 55%; }

    #hold-card {
        width: 76; max-width: 90%;
        background: $row-alt;
        border: round $hold;
        padding: 0;
    }
    #hold-head {
        background: $hold-bg;
        color: $hold;
        text-style: bold;
        padding: 1 2;
        border-bottom: solid $hair;
    }
    #hold-body { padding: 1 2; }
    #hold-action {
        background: $bar-low;
        border: round $hair;
        color: $ink-text;
        padding: 1 2;
        margin: 1 0;
    }
    #hold-reason { color: $ink-text; margin: 1 0; }
    #hold-buttons { height: auto; align: center middle; margin-top: 1; }
    #hold-buttons Button { margin: 0 1; min-width: 16; }
    Button#approve { background: $done; color: $background; }
    Button#veto { color: $problem; }
    """)

    def __init__(self, name: str, args: dict, reason: str) -> None:
        super().__init__()
        self._name = name
        self._args = args or {}
        self._reason = reason

    def compose(self) -> ComposeResult:
        arg_lines = "\n".join(
            f"  [$muted]{k}[/]=[$ink-text]{v!r}[/]" for k, v in self._args.items()
        ) or "  [$muted-2](no arguments)[/]"
        with Vertical(id="hold-card"):
            yield _S("⚖  GOVERNANCE · HELD FOR REVIEW", id="hold-head")
            with Vertical(id="hold-body"):
                yield _S("[$muted-2]PROPOSED ACTION[/]")
                yield _S(f"[$paper]{self._name}[/][$muted-2]([/]\n"
                             f"{arg_lines}\n[$muted-2])[/]", id="hold-action")
                yield _S(f"[$hold]Mom —[/] {self._reason}", id="hold-reason")
                with Horizontal(id="hold-buttons"):
                    yield Button("Approve  ^Y", id="approve")
                    yield Button("Revise  ^E", id="revise")
                    yield Button("Veto  ^N", id="veto")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id)

    def action_decide(self, choice: str) -> None:
        self.dismiss(choice)


# ---------------------------------------------------------------- admin screen
class AdminScreen(Screen):
    """The harness as a system, not a chat. A separate full-screen view — pushed
    with F4 — so the canvas stays clean and this gets the width to lay out six
    sections instead of squeezing into the rail. Everything here is read fresh
    when the screen mounts; it's a manifest of what the harness has, not a live
    feed (that's the rail's job, back on the main screen)."""

    BINDINGS = [
        Binding("f4", "app.pop_screen", "Back", show=True),
        Binding("escape", "app.pop_screen", "Back", show=False),
        Binding("tab", "focus_next", "Next pane", show=True),
        Binding("shift+tab", "focus_previous", "Prev", show=False),
    ]

    CSS = paint("""
    AdminScreen { background: $background; }

    #keybar {
        dock: bottom; height: 1; padding: 0 2;
        background: $bar-low; color: $muted-2;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }

    #admin-titlebar {
        dock: top; height: 2; padding: 0 2;   /* 2 = one row of text + border */
        background: $bar; color: $ink-text;
        border-bottom: solid $hair;
    }

    /* The constitution is a page of prose rules; the others are short lists. A
       uniform grid would cram the long pane and waste the short ones, so the
       constitution takes a full-height column and the five short panes fill
       the rest. Row-spans must add up to nine cells — see the comment below. */
    #admin-grid {
        grid-size: 3 3;
        grid-columns: 1fr 1fr 1fr;
        grid-rows: 1fr 1fr 1fr;
        grid-gutter: 1 2;
        padding: 1 2;
    }
    .admin-box {
        border: round $hair;
        background: $rail;
        padding: 1 2;
        height: 1fr;
        scrollbar-size-vertical: 1;
    }
    /* col 1: tools(2) + mom(1) · col 2: skills(2) + memory(1) ·
       col 3: constitution(2) + telemetry(1). Get this wrong and a pane
       silently collapses to 0x0. */
    #box-tools { row-span: 2; }
    #box-skills { row-span: 2; }
    #box-constitution { row-span: 2; }

    /* The focused pane is unmistakable — you always know where Tab left you. */
    .admin-box:focus {
        border: round $dad;
        background: $dad 6%;
    }
    """)

    def __init__(self, dad: AgentLoop, skills_loaded: list[str]) -> None:
        super().__init__()
        self.dad = dad
        self.skills_loaded = skills_loaded

    def compose(self) -> ComposeResult:
        yield _S(
            "[b]dadloop[/b] [$faint]│[/] [$dad]admin[/]"
            "    [$muted-2]tools · skills · governance · memory · esc to return[/]",
            id="admin-titlebar",
        )
        with Grid(id="admin-grid"):
            # VerticalScroll (not Static) so each pane is focusable and can be
            # scrolled with the keyboard. Grid fills column by column: tools and
            # skills take two rows in the left columns, the constitution takes
            # its column, and the three short panes fill the gaps.
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
                    yield _S(text)
        yield KeyBar(KeyBar.ADMIN_KEYS, id="keybar")

    # --- six sections, each a pure string builder --------------------------
    def _tools_text(self) -> str:
        """The tool registry — every verb the model can call, with a one-line
        blurb. This is the manifest; the rail's session counts track use."""
        schemas = toolkit.schemas()
        rows = []
        for s in schemas:
            name = s["name"]
            blurb = _TOOL_BLURB.get(name) or s.get("description", "").split(".")[0][:34]
            rows.append(f"[$done]●[/] [$ink-text]{name}[/]  [$muted-2]{blurb}[/]")
        return (f"[$dad]TOOL REGISTRY[/] [$muted-2]· {len(rows)} registered[/]\n\n"
                + "\n".join(rows))

    def _skills_text(self) -> str:
        """All installed skills, with the ones assembled this session marked. The
        distinction is the point: the catalog is what he *could* reach for, the
        marks are what he actually pulled off the shelf."""
        loaded = set(self.skills_loaded)
        rows = []
        for name, skill in skill_lib.SKILLS.items():
            if name in loaded:
                mark, state = "[$skill]●[/]", "[$done]loaded[/]"
            else:
                mark, state = "[dim]○[/dim]", "[$muted-2]available[/]"
            desc = (skill.description or "").strip()
            if len(desc) > 40:
                desc = desc[:39] + "…"
            # Mark and name stay adjacent (mark + space + name) so the loaded /
            # unloaded distinction survives a simple markup strip.
            rows.append(f"{mark} {name}  {state}\n   [$muted-2]{desc}[/]")
        return (f"[$dad]SKILLS[/] [$muted-2]· {len(loaded)}/{len(skill_lib.SKILLS)} "
                f"assembled[/]\n\n" + "\n".join(rows))

    def _constitution_text(self) -> str:
        """The full constitution. It is longer than the pane — expected, and the
        header says so, because a silently truncated pane reads as the whole
        story. Tab here, then scroll."""
        from .core.agent import _constitution
        text = _constitution(self.dad.ctx)
        # Rules wrap across several indented lines, and the grounding section at
        # the top is all continuation. Keeping only the first line of each rule
        # truncates half of them mid-sentence, so gather each rule with the lines
        # that belong to it.
        rules: list[str] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line[0].isdigit() and "." in line[:3]:
                rules.append(line)
            elif rules and not line.endswith(("Values", "Constraints")) \
                    and not line[:3].isupper():
                # a continuation of the rule we're already building
                rules[-1] += " " + line
        body = "\n\n".join(f"[$ink-text]{r}[/]" for r in rules)
        return (f"[$dad]CONSTITUTION[/] [$muted-2]· {len(rules)} rules[/]\n"
                f"[$muted-2]tab here, then scroll[/]\n\n" + body)

    def _mom_text(self) -> str:
        rows = []
        for p in self.dad.mom.policies:
            doc = (p.__doc__ or "").strip().splitlines()[0] if p.__doc__ else p.__name__
            rows.append(f"[$hold]•[/] [$ink-text]{doc}[/]")
        rows.append(f"[$hold]•[/] [$ink-text]max reply: "
                    f"{self.dad.mom.max_reply_sentences} sentences[/]")
        return (f"[$dad]MOM'S POLICIES[/] [$muted-2]· {len(self.dad.mom.policies)}[/]\n\n"
                + "\n".join(rows))

    def _memory_text(self) -> str:
        root = self.dad.ctx.memory.root
        rows = [f"[$muted-2]•[/] [$ink-text]{name}[/]  [$muted-2]({size}b)[/]"
                for name, size in self.dad.ctx.memory.files()]
        return (f"[$dad]MEMORY[/]\n[$muted-2]{root}[/]\n\n" + "\n".join(rows))

    def _observability_text(self) -> str:
        t = self.dad.tracer.totals
        def row(label, value, accent="$ink-text"):
            tag = f"{label}:"
            return f"[$muted-2]{tag:<12}[/][{accent}]{value}[/]"
        return (
            "[$dad]OBSERVABILITY[/]\n\n"
            f"{row('turns', t.turns)}\n"
            f"{row('llm calls', t.llm_calls)}\n"
            f"{row('tool calls', t.tool_calls)}\n"
            f"{row('tokens', f'{t.tokens_in}→{t.tokens_out}')}\n"
            f"{row('cost', f'~${t.cost:.4f}', '$dad')}\n"
            f"{row('avg/turn', f'{t.avg_turn_ms:.0f}ms')}"
        )


# ------------------------------------------------------------------- main app
class DadApp(App):
    TITLE = "dadloop"
    SUB_TITLE = "an agent harness for knowledge work"

    # Colour is semantic here — see theme.py. $dad is coral, $done olive,
    # $skill/$hold gold, $problem rust, and $paper..$faint the neutral ramp.
    # Nothing in this stylesheet uses a raw colour.
    # The design draws the app as a rounded card floating on a darker backdrop,
    # with a drop shadow. A terminal has no shadows and no rounded outer corner,
    # so there are two honest readings of that intent:
    #
    #   framed     inset the whole shell by one cell and give it a round border,
    #              so it reads as a card on a backdrop. Closest to the design;
    #              costs two rows and two columns of usable space.
    #   full       let the shell fill the terminal edge to edge. Loses the card
    #              metaphor, gains the space back — the conventional TUI choice.
    #
    # DADLOOP_SHELL=full switches to the second. Framed is the default because it
    # is what the design asked for.
    SHELL_FRAMED = os.environ.get("DADLOOP_SHELL", "framed").lower() != "full"

    # The landing page is shown on a real launch. DADLOOP_NO_LAUNCH=1 skips it
    # for anyone who has seen it enough times.
    #
    # It is also skipped automatically under `run_test`, where a modal screen
    # over the canvas would swallow the keys a test sends and every TUI test
    # would fail on a landing page it never asked for. Detecting that here means
    # a future test author never has to know this screen exists — the
    # alternative is an opt-out env var in every test file, which is the kind of
    # thing that gets forgotten and then blamed on the test.
    _NO_LAUNCH_ENV = os.environ.get("DADLOOP_NO_LAUNCH", "") in ("1", "true", "yes")

    @property
    def SHOW_LAUNCH(self) -> bool:
        if self._NO_LAUNCH_ENV:
            return False
        # App.is_headless is True under run_test() and False in a real terminal.
        return not self.is_headless

    CSS = paint("""
    Screen { layout: vertical; background: $background; }

    /* --- the shell -------------------------------------------------------
       In framed mode #shell is an inset card on a darker backdrop, echoing the
       design's floating panel. In full mode the border and margin drop away. */
    #shell {
        height: 1fr;
        background: $shell;
        border: round $hair;
        margin: 1 2;
    }
    .full #shell {
        border: none;
        margin: 0;
    }

    /* --- title bar -------------------------------------------------------
       height 2, not 1: the bottom border needs a row of its own, and with
       height:1 the border eats the content and the bar renders as an invisible
       strip — present in the tree, zero pixels tall. */
    /* The title bar is a single row. A border on a height:1 widget consumes
       that row for the border itself and leaves nothing for the text — the bar
       is then present in the tree but zero pixels tall, which looks exactly
       like "the app has no title". Separation comes from the background colour
       instead, which costs no rows. */
    /* A one-row bar with a border-top has no rows left for its text — the
       border eats the single row and the content collapses to height 0, which
       is exactly why the keys were invisible. No border; the $bar-low
       background is enough to set it apart from the prompt above. */
    #keybar {
        height: 1; padding: 0 2;
        background: $bar-low; color: $muted-2;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }

    #titlebar {
        dock: top; height: 2; max-height: 2; padding: 0 2;
        background: $bar; color: $ink-text;
        text-wrap: nowrap;      /* a wrapped title bar steals a row from the canvas */
        text-overflow: ellipsis;
        /* Coral, not a hairline. At the top of a framed shell a $hair border is
           indistinguishable from the frame itself, so the banner disappears into
           the border and the app looks untitled. */
        border-bottom: solid $dad;
    }

    #body { height: 1fr; }

    /* --- left rail: what he's doing, and how it's going ------------------ */
    #rail {
        width: 34; min-width: 30;
        background: $rail;
        border-right: solid $hair;
        overflow-y: auto;          /* the rail now carries more than fits at 24 rows */
        scrollbar-size-vertical: 1;
    }
    #plan-panel {
        height: auto;
        padding: 1 2;
    }
    #rail-stats {
        height: auto;              /* auto, not 1fr — the parent rail scrolls */
        padding: 1 2;
        border-top: solid $hair-2;
        color: $ink-text;
    }

    /* --- the canvas ------------------------------------------------------ */
    #main { width: 1fr; }
    #log { padding: 1 2; }

    /* What he actually DID, sitting directly above what he said. Quiet, but
       always present — it is the line you scan when you want to know whether
       the agent merely looked things up or changed something. */
    .action-taken {
        margin: 1 0 0 0;
        padding: 0 1;
        border-left: thick $skill;
        background: $skill 8%;
        color: $ink-text;
    }

    /* You: quiet, a coral tick. Dad: warm and prominent — he's the one talking. */
    Markdown.you {
        color: $ink-text;
        margin: 1 0 0 0;
        padding: 0 1;
        border-left: thick $dad;
    }
    Markdown.dad {
        background: $dad 8%;
        border-left: thick $dad;
        margin: 1 0;
        padding: 0 1;
    }

    /* Reasoning steps, drawn as a tight grouped rail rather than stacked cards.
       Textual's Collapsible ships with a top hairline and bottom padding that
       turn seven tool calls into seven boxes; both are stripped here so the
       group reads as one indented list under a single left rail. */
    .step {
        margin: 0 0 0 3;
        padding: 0;
        padding-bottom: 0;
        border-top: none;
        border-left: solid $hair-2;
        background: transparent;
    }
    .step CollapsibleTitle {
        padding: 0 1;
        color: $ink-text;
    }
    .step CollapsibleTitle:focus {
        background: $dad 15%;
        color: $paper;
        text-style: none;
    }
    .step Contents {
        padding: 0 0 0 3;
    }
    .step-body {
        padding: 0 1;
        color: $muted;
        max-height: 12;      /* long tool output scrolls rather than flooding */
        overflow-y: auto;
    }
    Collapsible.step:focus-within {
        border-left: thick $dad;
    }

    /* Skills assembling off the shelf — gold, the attention colour, sitting in
       the same rail as the steps so the sequence reads in order. */
    .skill-marker {
        margin: 0 0 0 3;
        padding: 0 1;
        border-left: solid $hair-2;
        color: $skill;
    }

    /* Mom's lighter touch. Gold, not red: a hold is authority, not a crash. */
    .review-card {
        margin: 1 0 1 3;
        padding: 1 2;
        border: round $hold;
        background: $hold 10%;
        color: $ink-text;
    }

    /* Per-turn trace sits at the bottom of a turn, deliberately quiet — one dim
       line, not a code block. */
    Static.trace {
        color: $faint;
        margin: 0 0 1 3;
        padding: 0 1;
    }

    /* The live status line: spinner, what he's doing, and a dim hint. */
    #status-line {
        height: 1;
        margin: 0 0 0 3;
        padding: 0 1;
        color: $dad;
    }

    /* Empty state: tell a new user what to actually type. */
    #empty-state {
        padding: 2 4;
        color: $muted;
        border: round $hair;
        margin: 2 4;
    }

    /* The prompt: a coral › and a send hint, framed like the design's input. */
    #prompt-wrap {
        dock: bottom;
        height: auto;
        background: $rail;
        border-top: solid $hair;
        padding: 1 2;
    }
    #input {
        border: round $hair;
        background: $bar-low;
        padding: 0 1;
    }
    #input:focus { border: round $dad; }
    #input-hint {
        height: 1;
        color: $faint;
        padding: 0 1;
    }
    """)

    # Function keys, not ctrl-combos, for the canvas. The Input widget claims
    # ctrl+a, ctrl+e, ctrl+c, ctrl+k and friends for line editing, and a focused
    # Input *wins* — so an app-level ctrl+e is silently dead while the user is
    # typing, which is exactly when they'd reach for it. F-keys are unclaimed.
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
        # Register before the stylesheet is parsed — the CSS references $dad,
        # $hold and friends, and Textual resolves those at parse time. Doing this
        # in on_mount is too late and raises UnresolvedVariableError.
        self.register_theme(DADLOOP_THEME)
        self.theme = "dadloop"
        self.dad = dad or AgentLoop()
        self._status: StatusLine | None = None
        self._skills_loaded: list[str] = []
        # What happened in the current turn, for the ACTION TAKEN line.
        self._turn_actions: list[str] = []
        self._turn_skills: list[str] = []
        self._turn_holds: list[tuple[str, str]] = []

    # --- layout -----------------------------------------------------------
    def compose(self) -> ComposeResult:
        # The key bar goes INSIDE the shell, as the last child. Docked to the
        # Screen it lands below the frame, floating in the outer margin, visually
        # detached from the app — the keys are on screen but read as though they
        # belong to the terminal rather than to dadloop. Inside, it sits directly
        # under the prompt where it belongs.
        with Vertical(id="shell"):
            yield TitleBar(self.dad)
            with Horizontal(id="body"):
                with Vertical(id="rail"):
                    yield PlanPanel()
                    yield RailStats(self.dad)
                with Vertical(id="main"):
                    yield VerticalScroll(id="log")
                    with Vertical(id="prompt-wrap"):
                        yield Input(placeholder="Talk to Dad…  (e.g. 'are we ready for the cookout?')",
                                    id="input")
                        yield _S("[$faint]⏎ send  ·  ⇧⏎ newline  ·  tab walks his steps[/]",
                                     id="input-hint")
            yield KeyBar(id="keybar")

    def on_mount(self) -> None:
        if not self.SHELL_FRAMED:
            self.screen.add_class("full")
        self._fit_shell_to_terminal()
        self.sub_title = "online" if self.dad.online else "offline - no API key"

        if self.dad.online:
            # An empty canvas tells a new user nothing. Show what to type, and
            # pick examples that actually exercise the harness.
            self._mount(_S(
                "[b]Ask him something that has to be worked out, not just answered.[/b]\n\n"
                "  [$dad]Twelve people Saturday, and I've got forty bucks.[/]\n"
                "  [$dad]Grill's not lighting and people are coming at six.[/]\n"
                "  [$dad]Can we just get the nice grill? It's like $400.[/]\n\n"
                "[$muted-2]Tab moves between his reasoning steps once he starts. "
                "F4 opens the admin view.[/]",
                id="empty-state"))
        else:
            self._mount(_S(
                "[b]Dad is asleep.[/b]\n\n"
                "Put a real key in [b].env[/b] as ANTHROPIC_API_KEY and restart.\n"
                "[$muted-2]The tests run without one: python tests/test_plan.py[/]",
                id="empty-state"))

        # The landing page goes on top of the built work surface, not instead of
        # it — so dismissing it reveals a canvas that is already composed and
        # ready, with no second load. Whatever was typed there comes back here.
        if self.SHOW_LAUNCH:
            self.push_screen(LaunchScreen(self.dad.online), self._start_from_launch)
        else:
            self.query_one("#input", Input).focus()

    def _fit_shell_to_terminal(self) -> None:
        """Drop the frame when the terminal is too short to spare the rows.

        The framed shell costs four rows and four columns — fine at 40 rows,
        expensive at 24, where it leaves an eleven-row canvas and pushes the
        title bar and footer hard against the border, so the chrome reads as
        part of the frame rather than as a banner and a key strip. Below the
        threshold the frame is the first thing to go: knowing the app's name and
        which keys work matters more than a card.
        """
        if not self.SHELL_FRAMED:
            return                              # already full-bleed by choice
        self.screen.set_class(self.size.height < 32, "full")

    def on_resize(self) -> None:
        # Re-evaluate on resize, so a window dragged taller gets the frame back
        # and one dragged shorter gives up the frame, never the chrome.
        self._fit_shell_to_terminal()

    def _start_from_launch(self, first_prompt: str | None) -> None:
        """Pick up where the landing page left off.

        If they typed a question there, run it as the first turn rather than
        making them type it twice — the landing page was the first interaction,
        not a gate in front of it. If they skipped, just focus the prompt.
        """
        if not first_prompt:
            self.query_one("#input", Input).focus()
            return
        self._begin_turn(first_prompt)

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
        self._begin_turn(text)

    def _begin_turn(self, text: str) -> None:
        """Put the question on the canvas and start the loop.

        Both entry points come through here — the prompt at the bottom of the
        work surface, and the one on the landing page. Two copies of this
        sequence would drift the first time either changed.
        """
        self.query_one("#input", Input).disabled = True
        self._clear_empty_state()
        self._mount(Markdown(f"**You** — {text}", classes="you"))
        self.query_one(PlanPanel).clear()
        # Reset the per-turn record. What Dad DID is a different question from
        # what he said, and the answer to it is assembled here as the turn runs.
        self._turn_actions = []
        self._turn_skills = []
        self._turn_holds = []
        self._status = StatusLine()
        self._mount(self._status)
        self._run_turn(text)

    # --- the turn on a worker thread --------------------------------------
    def _run_turn(self, text: str) -> None:
        # call_id -> the Static holding that step's result, so the tool_result
        # event can fill in the body of the right Collapsible.
        bodies: dict[str, Static] = {}
        titles: dict[str, Collapsible] = {}

        def on_event(kind: str, payload) -> None:
            if kind == "plan":
                self.call_from_thread(self.query_one(PlanPanel).set_plan, payload)
            elif kind == "plan_step_done":
                idx, step_text, planned = payload
                self.call_from_thread(
                    self.query_one(PlanPanel).mark_done, idx, step_text, planned)
            elif kind == "tool_call":
                name, args, call_id = payload
                self._turn_actions.append(_VERBS.get(name, name))
                if name == "load_skill":
                    skill_name = args.get("name")
                    if skill_name and skill_name not in self._skills_loaded:
                        self._skills_loaded.append(skill_name)
                    if skill_name:
                        self._turn_skills.append(skill_name)
                    self.call_from_thread(self._mount_skill_marker, skill_name)
                self.call_from_thread(self._mount_step, name, args, call_id,
                                      bodies, titles)
                # Keep the status line honest about what he's doing right now.
                if self._status is not None:
                    self.call_from_thread(
                        self._status.set_activity,
                        _VERBS.get(name, name), "working the request")
            elif kind == "tool_result":
                # (name, out, call_id, ms) — ms was added so steps can show a
                # right-aligned duration; tolerate the 3-tuple form too.
                name, out, call_id = payload[0], payload[1], payload[2]
                ms = payload[3] if len(payload) > 3 else None
                body = bodies.get(call_id)
                if body is not None:
                    self.call_from_thread(body.update, str(out))
                if ms is not None:
                    self.call_from_thread(self._finish_step, call_id, ms, titles)
            elif kind == "controller":
                # (name, action, reason[, args]) — args ride along on tool
                # holds so the modal can show the actual proposed call; the
                # reply-trim case has none.
                name, action, reason = payload[0], payload[1], payload[2]
                args = payload[3] if len(payload) > 3 else {}
                target = "your reply" if name == "reply" else name
                self._turn_holds.append((target, action))
                if action == "deny":
                    # A full hold gets the modal, over the dimmed canvas.
                    self.call_from_thread(
                        self.push_screen, GovernanceHold(target, args, reason))
                else:
                    self.call_from_thread(
                        self._mount, ReviewCard("adjusted", target, reason))
            elif kind == "final":
                self.call_from_thread(self._show_final, payload)
            elif kind == "trace":
                self.call_from_thread(self._mount,
                                      _S(f"[$faint]└ {payload}[/]", classes="trace"))

        def work() -> None:
            self.dad.turn(text, on_event=on_event)
            self.call_from_thread(self._finish_turn)

        self.run_worker(work, thread=True, exclusive=True)

    def _mount_step(self, name: str, args: dict, call_id: str,
                    bodies: dict[str, Static], titles: dict[str, Collapsible]) -> None:
        """One reasoning step, drawn as a tight rail line rather than a fat card:

            ✓  Checking the budget   amount=40 · reason='picnic food for 10'   210ms

        It is still a real Collapsible — Tab reaches it, Enter opens it, f2/f3
        drive them all — but the chrome is stripped down to a single line so a
        seven-tool turn reads as a compact list of moves instead of seven boxes.
        The check mark starts dim and turns olive when the result lands, so you
        can watch the loop work down the list.
        """
        verb = _VERBS.get(name, name)
        arg_str = " · ".join(f"{k}={v!r}" for k, v in (args or {}).items())
        body = _S("[$muted-2]running…[/]", classes="step-body")
        bodies[call_id] = body
        step = Collapsible(
            body,
            title=self._step_title(verb, arg_str, None, done=False),
            collapsed=True,
            classes="step",
            collapsed_symbol="›",
            expanded_symbol="⌄",
        )
        titles[call_id] = step
        step._dl_verb, step._dl_args = verb, arg_str   # for the later re-title
        self._mount(step)

    def _step_title(self, verb: str, arg_str: str, ms: float | None,
                    *, done: bool) -> str:
        """Compose one step line. The duration is right-aligned by padding the
        middle, which is how you right-align inside a width:auto title — there is
        no CSS hook for it on CollapsibleTitle."""
        mark = "[$done]✓[/]" if done else "[$faint]•[/]"
        head = f"{mark} [$ink-text]{verb}[/]"
        tail = f"[$faint]{ms:.0f}ms[/]" if ms is not None else ""
        mid = f"  [$muted-2]{arg_str}[/]" if arg_str else ""

        # Pad to push the timing right. Widths are measured on the visible text,
        # not the markup, so strip the tags when counting.
        visible = len(f"{'✓' if done else '•'} {verb}") + (len(arg_str) + 2 if arg_str else 0)
        target = 84
        pad = max(2, target - visible - (len(f"{ms:.0f}ms") if ms is not None else 0))
        return f"{head}{mid}{' ' * pad}{tail}"

    def _finish_step(self, call_id: str, ms: float,
                     titles: dict[str, Collapsible]) -> None:
        """Turn the step's mark olive and stamp the duration, once the tool
        actually returned."""
        step = titles.get(call_id)
        if step is None:
            return
        step.title = self._step_title(
            getattr(step, "_dl_verb", ""), getattr(step, "_dl_args", ""),
            ms, done=True)

    def _mount_skill_marker(self, skill_name: str) -> None:
        """Skills assembling is the work — show it on the canvas, gold, not just
        buried in the admin view."""
        self._mount(_S(f"⬡ assembled skill: [b]{skill_name}[/b]",
                           classes="skill-marker"))

    def _show_final(self, text: str) -> None:
        if self._status is not None:
            self._status.remove()
            self._status = None
        summary = self._action_summary()
        if summary:
            self._mount(_S(summary, classes="action-taken"))
        self._mount(Markdown(f"**Dad** — {text}", classes="dad"))

    def _action_summary(self) -> str:
        """One line naming what Dad actually DID this turn.

        His reply says what he concluded; the steps above say how he got there.
        Neither answers "what did this thing just do on my behalf" at a glance —
        you have to read the whole turn to find out whether it merely looked
        things up or actually changed something. For an agent that can spend
        money and set the thermostat, that question deserves its own line rather
        than being reconstructible from the transcript.
        """
        actions, skills, holds = self._turn_actions, self._turn_skills, self._turn_holds
        if not actions and not skills and not holds:
            return ""

        parts = []
        checks = [a for a in actions if a not in ("Pulling up the playbook",)]
        if checks:
            n = len(checks)
            parts.append(f"[$done]✓[/] [$ink-text]{n} "
                         f"{'check' if n == 1 else 'checks'} run[/]")
        if skills:
            named = ", ".join(dict.fromkeys(skills))
            parts.append(f"[$skill]⬡[/] [$ink-text]{named}[/]")
        for target, action in holds:
            verb = "blocked" if action == "deny" else "rewrote"
            parts.append(f"[$hold]⚖[/] [$hold]Mom {verb} {target}[/]")

        return ("[$muted-2]ACTION TAKEN[/]  " + "   [$faint]·[/]   ".join(parts))

    def _finish_turn(self) -> None:
        if self._status is not None:
            self._status.remove()
            self._status = None
        self.query_one(RailStats).refresh_stats()
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
