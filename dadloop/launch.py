"""Author: Swami Chandrasekaran
Last Modified: 2026-07-20
Purpose: Launch screen shown before the work surface — the landing page, in a terminal.

A product landing page, rendered in a terminal.

The shape is the one every app launch page uses: wordmark, a headline big enough
to be the only thing you read, a subhead that says what it does, a sample of the
actual interaction, and a way in. That structure survives the move to a terminal
intact — the only thing that changes is that the "screenshot" of the product is
not a screenshot. It is the product, drawn in the same characters the app itself
uses, because here they are the same medium.

Two deliberate departures from the reference:

  * The headline is set in block letters assembled by hand rather than a figlet
    dependency. A landing page is not worth a package on the install path, and
    the alphabet below is only the characters this one headline needs.
  * The sample prompt shows the harness doing its actual job — reconciling a
    real constraint — rather than the "make up an excuse for my boss" framing
    that ad copy tends to reach for. If the demo interaction is the product
    promise, the promise should be one worth making.

Press any key to go through to the work surface. It is a door, not a wall.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Middle, Vertical
from textual.screen import Screen
from textual.widgets import Input, Static

from .theme import markup as _mk, paint


# A block alphabet, only the glyphs the headline needs. Each entry is five rows
# tall; every row in a glyph must be the same width or the letters will shear
# when they are zipped together side by side.
_GLYPHS: dict[str, list[str]] = {
    "A": ["  ██  ", " ████ ", "██  ██", "██████", "██  ██"],
    "C": [" █████", "██    ", "██    ", "██    ", " █████"],
    "D": ["█████ ", "██  ██", "██  ██", "██  ██", "█████ "],
    "E": ["██████", "██    ", "█████ ", "██    ", "██████"],
    "F": ["██████", "██    ", "█████ ", "██    ", "██    "],
    "G": [" █████", "██    ", "██ ███", "██  ██", " █████"],
    "H": ["██  ██", "██  ██", "██████", "██  ██", "██  ██"],
    "I": ["██", "██", "██", "██", "██"],
    "K": ["██  ██", "██ ██ ", "████  ", "██ ██ ", "██  ██"],
    "L": ["██    ", "██    ", "██    ", "██    ", "██████"],
    "M": ["██   ██", "███ ███", "███████", "██ █ ██", "██   ██"],
    "N": ["██   ██", "███  ██", "██ █ ██", "██  ███", "██   ██"],
    "O": [" ████ ", "██  ██", "██  ██", "██  ██", " ████ "],
    "P": ["█████ ", "██  ██", "█████ ", "██    ", "██    "],
    "R": ["█████ ", "██  ██", "█████ ", "██ ██ ", "██  ██"],
    "S": [" █████", "██    ", " ████ ", "    ██", "█████ "],
    "T": ["██████", "  ██  ", "  ██  ", "  ██  ", "  ██  "],
    "U": ["██  ██", "██  ██", "██  ██", "██  ██", " ████ "],
    "W": ["██   ██", "██   ██", "██ █ ██", "███████", "██   ██"],
    "Y": ["██  ██", "██  ██", " ████ ", "  ██  ", "  ██  "],
    "?": [" ████ ", "██  ██", "   ██ ", "      ", "   ██ "],
    " ": ["    ", "    ", "    ", "    ", "    "],
}

_GLYPH_ROWS = 5


def block_text(words: str) -> list[str]:
    """Render a word in block capitals, as a list of five lines.

    Unknown characters fall back to a space rather than raising — a headline is
    decoration, and a missing glyph should never be the thing that stops the app
    from starting.
    """
    rows = [""] * _GLYPH_ROWS
    for ch in words.upper():
        glyph = _GLYPHS.get(ch, _GLYPHS[" "])
        for i in range(_GLYPH_ROWS):
            rows[i] += glyph[i] + " "
    return [r.rstrip() for r in rows]


class LaunchScreen(Screen[str | None]):
    """The landing page, and the place the first turn actually starts.

    This is not a splash screen you dismiss to get to the real one. The prompt
    here is live: type the first thing you want Dad to work out, press Enter,
    and the screen hands that text to the work surface, which starts the turn
    immediately. The landing page IS the first interaction, so nothing is
    re-typed and nothing is wasted.

    It returns the typed text (or None if skipped) through dismiss(), which the
    app awaits — so the caller decides what to do with it rather than this
    screen reaching into the app to start a turn itself.
    """

    BINDINGS = [
        Binding("escape", "skip", "Skip", show=True),
        Binding("ctrl+q", "app.quit", "Quit", show=True),
    ]

    CSS = paint("""
    LaunchScreen {
        background: $ink;
        align: center middle;
    }

    #launch-col {
        width: 88;
        height: auto;
        align: center middle;
    }

    /* The wordmark: small, quiet, above the fold. */
    #launch-mark {
        width: 100%;
        content-align: center middle;
        color: $muted;
        margin-bottom: 1;
    }

    /* The headline. Coral, because it is the one thing on screen that should
       pull the eye — the same rule the accent colour follows everywhere else. */
    #launch-head {
        width: 100%;
        content-align: center middle;
        color: $dad;
        text-style: bold;
    }

    #launch-sub {
        width: 100%;
        content-align: center middle;
        color: $muted;
        margin-top: 1;
        margin-bottom: 2;
    }

    /* The sample interaction, framed like the app's own canvas so the launch
       screen is showing the real thing rather than an illustration of it. */
    #launch-card {
        width: 100%;
        height: auto;
        border: round $hair;
        background: $rail;
        padding: 1 2;
    }

    /* The live prompt. Coral border because this is the one thing on the page
       you are meant to act on — the CTA is an input, not a button. */
    #launch-input {
        width: 100%;
        margin-top: 2;
        border: round $dad;
        background: $bar-low;
        padding: 0 1;
    }
    #launch-input:focus { border: round $dad; }

    #launch-foot {
        width: 100%;
        content-align: center middle;
        color: $faint;
        margin-top: 1;
    }
    """)

    def __init__(self, online: bool = True) -> None:
        super().__init__()
        self.online = online

    def compose(self) -> ComposeResult:
        headline = "\n".join(block_text("dadloop"))

        with Middle():
            with Center():
                with Vertical(id="launch-col"):
                    yield Static("◍  d a d l o o p", id="launch-mark")
                    yield Static(headline, id="launch-head")
                    yield Static(
                        _mk("[$ink-text]Why are you still prompting into the "
                            "dark in 2026?[/]\n"
                            "[$muted]An agent harness that shows its work — the plan, "
                            "every tool call, who overruled whom, and what it cost.[/]"),
                        id="launch-sub",
                    )
                    yield Static(self._sample(), id="launch-card")
                    yield Input(placeholder=self._placeholder(), id="launch-input")
                    yield Static(_mk(self._foot()), id="launch-foot")

    def on_mount(self) -> None:
        # Focus the prompt, not a button — the page is ready to be typed into
        # the moment it appears.
        self.query_one("#launch-input", Input).focus()
        self._fit_to_terminal()

    def on_resize(self) -> None:
        self._fit_to_terminal()

    def _fit_to_terminal(self) -> None:
        """Shed decoration until the prompt fits on screen.

        The full page — wordmark, five-row headline, subhead, a fourteen-row
        sample card, the input and a hint — needs about forty rows. In a
        24-row terminal that pushed the input itself below the fold: a landing
        page whose whole point is "type here" with the box off-screen.

        So the parts come off in order of what can be spared. The sample card is
        the biggest block and the most decorative, so it goes first; the headline
        is next. The input and the way out are never dropped.
        """
        height = self.size.height
        card = self.query_one("#launch-card")
        head = self.query_one("#launch-head")
        sub = self.query_one("#launch-sub")

        card.display = height >= 34      # the demo is a luxury, not the point
        head.display = height >= 20      # the wordmark still names the app
        sub.display = height >= 16

    def _placeholder(self) -> str:
        if self.online:
            return "Twelve people Saturday, and I've got forty bucks…"
        return "No API key found — press Enter to look around anyway"

    def _foot(self) -> str:
        if self.online:
            return ("[$faint]⏎ ask and go straight in  ·  ESC to skip  ·  "
                    "RUNS IN ANY TERMINAL[/]")
        # Being honest on the landing page beats a dead end one screen later.
        return ("[$problem]No ANTHROPIC_API_KEY[/][$faint] — Dad will be asleep.  "
                "ESC to look around.[/]")

    def _sample(self) -> str:
        """The sample interaction — a real turn, not a mock-up.

        It shows the one thing that distinguishes this harness from a chat box:
        a constraint the model cannot simply agree its way past. Dad wants to say
        yes; the budget says no; the governance layer settles it before the call
        runs. That is the product in four lines.
        """
        return _mk(
            "[$dad]›[/] [$ink-text]Twelve people Saturday, and I've got forty "
            "bucks.[/]\n\n"
            "  [$done]✓[/] [$muted]Checking the budget[/]"
            "        [$faint]$40 · tight[/]\n"
            "  [$done]✓[/] [$muted]Checking the pantry[/]\n"
            "  [$skill]⬡[/] [$skill]assembled skill[/] [$muted]hosting[/]"
            "     [$faint]+3 more[/]\n"
            "  [$hold]⚖[/] [$hold]Mom capped the spend[/] [$muted]before the "
            "call ran[/]\n\n"
            "[$skill]Dad[/] [$ink-text]— Forty feeds ten if you skip the fancy "
            "cheese, so corn,[/]\n"
            "[$ink-text]    peppers and a couple pounds of chicken. Propane's "
            "dead and[/]\n"
            "[$ink-text]    the store's shut, so borrow a tank before six.[/]"
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter carries the typed question into the work surface.

        An empty box means "just take me in", which is the same as skipping —
        so a user who presses Enter without typing is not scolded for it.
        """
        text = event.value.strip()
        event.stop()
        self.dismiss(text or None)

    def action_skip(self) -> None:
        self.dismiss(None)
