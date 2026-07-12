"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: CLI entry point for launching the TUI or REPL.

Entry point.

    python -m dadloop            launch the TUI (falls back to REPL if needed)
    python -m dadloop --repl     force the plain terminal REPL
    dadloop                      console script (after `pip install -e .`)
"""
import sys

from dadloop import AgentLoop


def main() -> None:
    dad = AgentLoop()

    if "--repl" in sys.argv:
        dad.run()
        return

    try:
        from dadloop.tui import launch
    except ImportError:
        print("(Textual not installed — falling back to REPL. "
              "`pip install textual` for the full TUI.)\n")
        dad.run()
        return

    launch(dad)


if __name__ == "__main__":
    main()
