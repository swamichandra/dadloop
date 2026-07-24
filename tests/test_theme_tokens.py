"""Author: Swami Chandrasekaran
Last Modified: 2026-07-18
Purpose: Tests theme tokens resolve to hex so the TUI runs on any Textual version.

Textual only began resolving a Theme's custom `variables` inside App.CSS in
recent releases. On an older one, every $dad / $rail / $shell in the stylesheet
is an undefined variable and the app dies at parse time with

    Error in stylesheet: reference to undefined variable '$shell'

before a single frame renders. That is a hard crash on the user's machine that
never reproduces on a newer dev box — the worst kind of bug.

So dadloop does not rely on that behaviour: theme.paint() substitutes tokens
into the stylesheet, and theme.markup() does the same for Rich content markup,
both before Textual or Rich ever see them. These tests hold that line.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dadloop.theme import TOKENS, paint, markup
from dadloop.tui import AdminScreen, DadApp, GovernanceHold

# Textual's own variables. These are fine to leave in the stylesheet — every
# version resolves them from the active theme.
_TEXTUAL_BUILTINS = {
    "background", "foreground", "surface", "panel", "primary", "secondary",
    "accent", "warning", "error", "success", "boost", "text", "text-muted",
    "text-disabled", "block-cursor-background", "block-cursor-foreground",
}


def test_no_custom_tokens_survive_in_css():
    """Every stylesheet in the app must be free of our custom tokens."""
    for name, cls in [("DadApp", DadApp),
                      ("AdminScreen", AdminScreen),
                      ("GovernanceHold", GovernanceHold)]:
        # Comments explain which variables to avoid and why, and naming one in
        # prose should not fail the test that enforces it.
        css = re.sub(r"/\*.*?\*/", "", cls.CSS, flags=re.S)
        leaked = sorted(t for t in TOKENS if f"${t}" in css)
        assert not leaked, f"{name}.CSS still references custom tokens: {leaked}"

        # Anything left must be a Textual builtin, or it will fail to resolve.
        found = set(re.findall(r"\$([a-z0-9-]+)", css))
        unknown = found - _TEXTUAL_BUILTINS
        assert not unknown, f"{name}.CSS has unresolvable variables: {sorted(unknown)}"
    print("PASS: no custom theme tokens survive in any stylesheet")


def test_paint_and_markup_substitute():
    """paint() handles CSS, markup() handles Rich content — including the
    longest-name-first ordering that keeps $hair-2 from being eaten by $hair."""
    assert paint("border: round $hair-2;") == f"border: round {TOKENS['hair-2']};"
    assert paint("background: $hair;") == f"background: {TOKENS['hair']};"
    assert "$" not in paint("a: $dad; b: $dad-dim; c: $hair-2; d: $shell;")

    out = markup("[$dad]Dad[/] [on $dad 20%]active[/]")
    assert "$" not in out, f"markup left a token behind: {out}"
    assert TOKENS["dad"] in out
    print("PASS: paint() and markup() resolve tokens, longest name first")


def test_rendered_widget_content_has_no_tokens():
    """The widgets people actually look at must not print raw [$token] text."""
    import asyncio

    async def scenario():
        app = DadApp()
        async with app.run_test(size=(120, 40)):
            for sel in ("#titlebar", "#plan-panel", "#input-hint"):
                content = app.query_one(sel).content
                assert "[$" not in content, f"{sel} shows a raw token: {content[:80]}"
        print("PASS: rendered widget content carries no unresolved tokens")

    asyncio.run(scenario())


if __name__ == "__main__":
    test_no_custom_tokens_survive_in_css()
    test_paint_and_markup_substitute()
    test_rendered_widget_content_has_no_tokens()
