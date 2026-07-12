"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Textual UI color theme and design system for the TUI.

The dadloop design system.

Colour in this UI carries meaning, so it is defined once, here, rather than being
guessed at each call site. The rule: a reader should be able to tell *what kind of
thing* they are looking at from its colour alone, before reading a word of it.

The palette is a workshop at dusk — warm light over a cold bench:

    amber    Dad. His replies, his voice. The warm light in the garage.
    slate    the harness itself. Plumbing, plan, telemetry. Cool and quiet.
    violet   Mom. Governance. Deliberately NOT red: a veto is authority, not an
             error. Red would say "something broke"; the correct signal is
             "someone with standing overruled you."
    teal     skills. Knowledge being pulled off the shelf.
    rust     genuine problems the world reports back (empty propane, closed store).
             This is where red belongs — a fact that blocks the work.

The distinction between violet and rust is the one that matters most, and it is the
one the old styling got wrong. Mom blocking a call is *the system working*. An empty
propane tank is *the world refusing to cooperate*. Those are not the same event and
they should not be the same colour.
"""

from __future__ import annotations

from textual.theme import Theme

# --- primitives -------------------------------------------------------------
# Raw values. Nothing outside this file should reference these directly.
_AMBER = "#e0a458"      # dad
_AMBER_DIM = "#8a6538"
_SLATE = "#7c93a8"      # harness
_SLATE_DIM = "#2a3138"
_VIOLET = "#9d7cd8"     # mom / governance
_TEAL = "#5ac8b0"       # skills
_RUST = "#d1685e"       # problems reported by the world
_INK = "#12151a"        # background
_PAPER = "#e8e6e3"      # foreground text
_PANEL = "#1a1f26"      # raised surfaces


DADLOOP_THEME = Theme(
    name="dadloop",
    dark=True,
    # Textual's slots, mapped to our semantics.
    primary=_SLATE,        # the harness: plan panel, structure, chrome
    secondary=_TEAL,       # skills
    accent=_AMBER,         # Dad
    warning=_VIOLET,       # Mom — see the module docstring on why not error
    error=_RUST,           # a problem the world reported, not a governance action
    success=_TEAL,
    foreground=_PAPER,
    background=_INK,
    surface=_INK,
    panel=_PANEL,
    # Component tokens. Widgets reference these names, never the hex above, so a
    # palette change is a one-file edit.
    variables={
        "dad": _AMBER,
        "dad-dim": _AMBER_DIM,
        "harness": _SLATE,
        "harness-dim": _SLATE_DIM,
        "mom": _VIOLET,
        "skill": _TEAL,
        "problem": _RUST,
        # Textual's own component slots we want to control:
        "footer-key-foreground": _AMBER,
        "block-cursor-background": _AMBER,
        "block-cursor-foreground": _INK,
        "input-selection-background": f"{_AMBER} 35%",
    },
)
