"""Author: Mike Bell
Last Modified: 2026-09-18
Purpose: Tests the console's declared install set can actually serve its live feed.

Proves that every way the docs tell someone to install Mom's Console brings in
a WebSocket protocol library. uvicorn only speaks WebSocket through `websockets`
or `wsproto`, and neither is a dependency of fastapi or uvicorn themselves. On a
fresh install of just those two, the console's page loads but `/ws` returns 404,
the browser retries forever, and the house never draws. The README also pointed
at a `[console]` extra that pyproject never defined."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WS_LIBS = ("websockets", "wsproto")


def _console_extra() -> str:
    text = (ROOT / "pyproject.toml").read_text()
    m = re.search(r'^console\s*=\s*\[(.*?)\]', text, re.S | re.M)
    assert m, "pyproject.toml defines no [console] extra, but README.md tells people to install it"
    return m.group(1)


def _names(spec_block: str) -> set[str]:
    return {re.split(r"[><=~!\[; ]", s.strip().strip('"\''))[0].lower()
            for s in re.split(r"[,\n]", spec_block) if s.strip() and not s.strip().startswith("#")}


def test_console_extra_exists_and_speaks_websocket():
    names = _names(_console_extra())
    assert {"fastapi", "uvicorn"} <= names, f"[console] extra is missing the server itself: {sorted(names)}"
    assert names & set(WS_LIBS), \
        f"[console] extra installs a server that cannot upgrade to WebSocket: {sorted(names)}"
    print(f"PASS: pyproject [console] extra = {sorted(names)}")


def test_console_requirements_speak_websocket():
    names = _names((ROOT / "console" / "requirements.txt").read_text())
    assert names & set(WS_LIBS), \
        f"console/requirements.txt installs a server that cannot upgrade to WebSocket: {sorted(names)}"
    print(f"PASS: console/requirements.txt = {sorted(names)}")


if __name__ == "__main__":
    test_console_extra_exists_and_speaks_websocket()
    test_console_requirements_speak_websocket()
