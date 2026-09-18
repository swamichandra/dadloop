"""Author: Mike Bell
Last Modified: 2026-09-18
Purpose: Tests the placeholder key in .env.example is treated as no key.

Proves that copying .env.example to .env verbatim leaves Dad asleep with the
"set your key" message, instead of reporting [online] and dying on the first
turn with a raw 401 traceback. The guard in AgentLoop and the placeholder in
.env.example had drifted apart: the guard looked for "sk-ant-..." while the
example shipped "sk-ant-"."""
import os
import tempfile
from pathlib import Path
from dadloop import AgentLoop, Context, SemanticMemory

ROOT = Path(__file__).resolve().parent.parent


def _example_key() -> str:
    for line in (ROOT / ".env.example").read_text().splitlines():
        line = line.strip()
        if line.startswith("ANTHROPIC_API_KEY="):
            return line.partition("=")[2].strip().strip('"').strip("'")
    raise AssertionError(".env.example no longer ships an ANTHROPIC_API_KEY line")


def _loop_with_key(key: str) -> AgentLoop:
    saved = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = key
    try:
        return AgentLoop(Context(memory=SemanticMemory(Path(tempfile.mkdtemp()) / "m")))
    finally:
        if saved is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = saved


def test_example_placeholder_leaves_dad_asleep():
    key = _example_key()
    dad = _loop_with_key(key)
    assert not dad.online, \
        f"the .env.example placeholder {key!r} was accepted as a real key"
    print(f"PASS: the shipped placeholder {key!r} leaves Dad offline, not mid-401")


def test_real_looking_key_still_wakes_dad():
    dad = _loop_with_key("sk-ant-api03-not-a-real-key-but-shaped-like-one")
    assert dad.online, "a real-shaped key must still bring Dad online"
    print("PASS: a real-shaped key still wakes Dad")


if __name__ == "__main__":
    test_example_placeholder_leaves_dad_asleep()
    test_real_looking_key_still_wakes_dad()
