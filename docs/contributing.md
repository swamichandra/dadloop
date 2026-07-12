<!--
Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Contributor guide for linting, testing, and extending dadloop.
-->

# Contributing

```bash
pip install -e ".[dev]"
python -m pyflakes dadloop/                 # lint
for t in tests/*.py; do python3 $t; done    # 20 tests
```

Tests run against a fake model, so no API key is needed to develop.

## Adding a tool

Decorate a function in `core/tools.py`. The model can call it on the next turn.

```python
@tool("check_mailbox", "Look in the mailbox.", {"type": "object", "properties": {}})
def check_mailbox(ctx):
    return "Bills, a catalog, and a postcard from your aunt."
```

## Adding a skill

Drop a `.md` in `skills/`. See [writing skills](skills.md).

## Adding a policy

Write a callable that returns a `Verdict` and add it to `Mom.policies`.

```python
def no_calls_after_nine(ctx, name, args) -> Verdict:
    if name == "call_neighbor" and datetime.now().hour >= 21:
        return Verdict("deny", reason="It's after nine. Nobody calls after nine.")
    return Verdict("allow")
```

## Tests

Each test exists because something broke. Keep it that way — a test that guards nothing is
worse than no test, because it implies coverage that is not there.

| test | the bug it guards |
|--|--|
| `test_navigation.py` | shipped once with nothing focusable but the input box |
| `test_blocked_is_remembered.py` | vetoed calls vanished without a trace |
| `test_plan.py` | stated plan and actual tool calls could silently drift |
| `test_constitution.py` | the reply trimmer amputated warmth for coming last |
| `test_skill_orchestration.py` | skills retrieved but did not compose |

If a change teaches a harness concept honestly, it belongs. If it is decoration that looks
like a capability, it does not.
