"""Author: Swami Chandrasekaran
Last Modified: 2026-07-18
Purpose: Textual UI color theme and design system for the TUI.

The dadloop design system — "a calmer, long-horizon work surface."

Colour here carries meaning, so it is defined once, in this file, rather than
guessed at each call site. The rule: a reader should be able to tell *what kind
of thing* they are looking at from its colour alone, before reading a word.

The palette is a warm near-black workshop at dusk — one coral light over a cold
bench, everything else muted so the accent means something:

    coral    Dad, and the single accent. His voice, the active plan step, the
             prompt caret, the one number that matters (spend). Used sparingly —
             if everything is coral, nothing is.
    olive    things that went right: a completed step, an enabled tool, budget
             headroom. Calm green, not a neon "success" toast.
    gold     two related jobs — skills being assembled off the shelf, AND Mom
             holding an action for review. Both are "pay attention, but nothing
             broke." A governance hold is authority pausing the loop, not an
             error; gold says wait, red would lie.
    rust     genuine trouble: a veto, a tool that needs review, a real problem
             the world reports back. This is the only place red belongs.
    paper..dim  a five-stop neutral ramp (bright -> dim) that does all the
             structural work: headings, body, labels, chrome, hairlines.

The distinction that matters most is gold vs rust. Mom pausing the loop to ask
is the system *working*. A vetoed spend or an empty propane tank is something
*refusing to proceed*. Different events, different colours.
"""

from __future__ import annotations

from textual.theme import Theme

# --- primitives -------------------------------------------------------------
# Raw values from the design. Nothing outside this file references these.
_CORAL = "#d97757"      # Dad / the one accent
_CORAL_DIM = "#a85c44"  # coral, spent (over-budget spend, pressed accent)
_OLIVE = "#8ba86a"      # success — done, enabled, headroom
_GOLD = "#c9a24c"       # skills assembling + governance hold (attention, not error)
_RUST = "#c96f5a"       # veto / needs-review / a real problem

# Neutral ramp — bright text down to the faintest hairline.
_PAPER = "#e9e3d6"      # brightest: headings, Dad's words, focused text
_PAPER_2 = "#c9c1b3"    # primary body text
_MUTE = "#9a9184"       # secondary labels, inactive tabs
_MUTE_2 = "#6b6459"     # tertiary: arg hints, captions, footer text
_FAINT = "#4f4941"      # faintest: pending marks, separators-in-text, timings

# Surfaces — warm near-black, layered.
_INK = "#100e0a"        # deepest: app backdrop behind the shell
_INK_BAR = "#161310"    # footer / lowest chrome
_PANEL = "#1b1915"      # the shell body
_PANEL_2 = "#201d18"    # raised: rail, right column, input bar
_PANEL_3 = "#211d18"    # title bar
_HAIR = "#34302a"       # borders
_HAIR_2 = "#2e2a24"     # inner hairlines / separators
_ROW = "#232019"        # DataTable zebra / selected-row wash
_HOLD_BG = "#2a2114"    # governance modal header wash (warm gold-tinted)


DADLOOP_THEME = Theme(
    name="dadloop",
    dark=True,
    # Textual's slots, mapped to our semantics.
    primary=_CORAL,        # the accent: Dad, active step, prompt
    secondary=_GOLD,       # skills / governance attention
    accent=_CORAL,
    warning=_GOLD,         # a hold is gold — see the module docstring
    error=_RUST,           # veto / needs-review / a world problem
    success=_OLIVE,
    foreground=_PAPER,
    background=_INK,
    surface=_PANEL,
    panel=_PANEL_2,
    # Component tokens. Widgets reference these names, never the hex above, so a
    # palette change stays a one-file edit.
    variables={
        # semantic roles
        "dad": _CORAL,
        "dad-dim": _CORAL_DIM,
        "done": _OLIVE,
        "skill": _GOLD,
        "hold": _GOLD,
        "problem": _RUST,
        # neutral ramp
        "paper": _PAPER,
        "ink-text": _PAPER_2,
        "muted": _MUTE,
        "muted-2": _MUTE_2,
        "faint": _FAINT,
        # surfaces
        "shell": _PANEL,
        "rail": _PANEL_2,
        "bar": _PANEL_3,
        "bar-low": _INK_BAR,
        "hair": _HAIR,
        "hair-2": _HAIR_2,
        "row-alt": _ROW,
        "hold-bg": _HOLD_BG,
        # Textual's own component slots we want to control:
        "footer-key-foreground": _CORAL,
        "footer-description-foreground": _MUTE_2,
        "block-cursor-background": _CORAL,
        "block-cursor-foreground": _INK,
        "input-selection-background": f"{_CORAL} 35%",
        "scrollbar": _HAIR,
        "scrollbar-hover": _MUTE_2,
        "scrollbar-active": _CORAL,
    },
)


# --- version-proof token substitution ---------------------------------------
# Textual only began resolving a Theme's custom `variables` inside App.CSS in
# recent versions. On older ones every $dad / $rail / $shell is an undefined
# variable and the app dies at stylesheet-parse time. Rather than depend on that
# behaviour, we substitute the tokens into the CSS ourselves before Textual ever
# sees it — which works on every version, including the ones that would have
# resolved them anyway.
#
# TOKENS is the same map the Theme carries, minus Textual's own component slots
# (footer-key-foreground and friends), which Textual does understand natively.
TOKENS: dict[str, str] = {
    "dad": _CORAL,
    "dad-dim": _CORAL_DIM,
    "done": _OLIVE,
    "skill": _GOLD,
    "hold": _GOLD,
    "problem": _RUST,
    "paper": _PAPER,
    "ink-text": _PAPER_2,
    "muted": _MUTE,
    "muted-2": _MUTE_2,
    "faint": _FAINT,
    "shell": _PANEL,
    "rail": _PANEL_2,
    "bar": _PANEL_3,
    "bar-low": _INK_BAR,
    "hair": _HAIR,
    "hair-2": _HAIR_2,
    "row-alt": _ROW,
    "hold-bg": _HOLD_BG,
    "ink": _INK,
}


def paint(css: str) -> str:
    """Replace every $token in a stylesheet with its hex value.

    Longest names first, so $hair-2 is not clobbered by $hair, and $dad-dim not
    by $dad. Textual's own variables ($background, $surface, $primary…) are left
    alone — they are not in TOKENS, so they pass straight through to Textual,
    which resolves them from the active theme as usual.
    """
    for name in sorted(TOKENS, key=len, reverse=True):
        css = css.replace(f"${name}", TOKENS[name])
    return css


def markup(text: str) -> str:
    """Same substitution for Rich console markup like [$dad]…[/].

    Content markup is resolved by Rich at render time, not by the CSS parser, and
    Rich has no notion of Textual theme variables at all — so these need the same
    treatment as the stylesheet.
    """
    for name in sorted(TOKENS, key=len, reverse=True):
        text = text.replace(f"[${name}]", f"[{TOKENS[name]}]")
        text = text.replace(f"[on ${name}", f"[on {TOKENS[name]}")
        text = text.replace(f"${name}", TOKENS[name])
    return text
