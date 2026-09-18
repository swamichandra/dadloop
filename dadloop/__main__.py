"""Author: Swami Chandrasekaran
Last Modified: 2026-09-05
Purpose: CLI entry point for launching the TUI, REPL, house, or console.

Entry point.

    python -m dadloop                    the TUI. Joins the house running for this
                                         machine's memory, or opens one and is
                                         its first person
    python -m dadloop --solo             the single-user TUI, no house
    python -m dadloop --repl             force the plain terminal REPL
    python -m dadloop --improve          run the recursive self-improvement loop
    python -m dadloop --console          serve Mom's Console in a browser
    python -m dadloop --serve [host:port] run one Dad that several people can join
    python -m dadloop --join [host:port] open a TUI on a running house (no address:
                                         find the one on this machine)
    --as NAME                            who you are (default: your login name)
    dadloop                              console script (after `pip install -e .`)

The session is the unit. Two terminals on one machine, or two machines, are
in the same session when they are joined to the same house; where they run is
not the criterion.
"""
import os
import sys

from dadloop import AgentLoop


def _flag_value(name: str) -> str | None:
    """`--name value` or `--name=value`, else None."""
    for i, a in enumerate(sys.argv):
        if a == name and i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("--"):
            return sys.argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


def main() -> None:
    who = _flag_value("--as")
    if who:
        # One knob for identity, read by AgentLoop.turn() and the house client.
        os.environ["DADLOOP_USER"] = who

    passive = any(f in sys.argv for f in ("--console", "--improve", "--repl", "--serve"))
    if "--join" in sys.argv or (not passive and "--solo" not in sys.argv):
        # The shared path, and the default. Join the house for this machine's
        # memory if one is running; otherwise open one here and be its first
        # person. Either way this TUI is a client of a house, so the next
        # `dadloop` on the machine lands in the same session instead of a
        # second Dad writing the same files. `--join host:port` reaches a
        # house elsewhere; `--solo` is the old single-user TUI.
        from dadloop.house import open_or_join, find_house
        addr = _flag_value("--join")
        try:
            from dadloop.tui import launch
        except ImportError:
            if "--join" in sys.argv:
                raise SystemExit("Joining a house needs the TUI: pip install textual")
            launch = None
        if launch is None:
            pass                                  # no TUI: REPL below, single-user
        else:
            try:
                client, house = open_or_join(address=addr)
            except OSError as e:
                where = addr or "this machine"
                raise SystemExit(f"No house at {where} ({e}).\n"
                                 "Start one first:  dadloop --serve")
            except RuntimeError as e:             # lost a race with another starter
                found = find_house()
                if found is None:
                    raise SystemExit(str(e))
                client, house = open_or_join(address=f"{found['host']}:{found['port']}")
            try:
                launch(client)
            finally:
                client.close()
                if house is not None:
                    house.stop()
            return

    dad = AgentLoop()

    if "--serve" in sys.argv:
        from dadloop.house import serve, parse_address, DEFAULT_PORT
        host, port = parse_address(_flag_value("--serve"), default_port=DEFAULT_PORT)
        host = _flag_value("--host") or host
        port = int(_flag_value("--port") or port)
        serve(dad, host, port)
        return

    if "--console" in sys.argv:
        # Mom's Console reads the journal and never touches the harness, so it
        # runs on its own rather than alongside a turn.
        try:
            from console.server import main as run_console
        except ImportError:
            raise SystemExit("Mom's Console needs fastapi, uvicorn, and websockets:\n"
                             "    pip install -e '.[console]'")
        raise SystemExit(run_console())

    if "--improve" in sys.argv:
        from dadloop.improve_cli import run_improve
        raise SystemExit(run_improve(dad))

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
