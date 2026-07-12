<!--
Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Detailed architecture of the harness components.
-->

# Architecture

```
model decides -> harness executes -> results feed back -> loop continues
```

The model runs the loop. The harness marshals context in, runs the tool calls the model
asks for, feeds results back, manages memory across turns, and knows when to stop.

| concept | file |
|---|---|
| the loop | `core/agent.py` |
| tools | `core/tools.py` |
| skills | `core/skills.py`, `skills/*.md` |
| governance | `core/controller.py` |
| memory | `core/memory.py` |
| tracing | `core/trace.py` |
| plan tracking | `core/plan.py` |

## Tools

Twelve verbs the model can call:

`check_weather` `check_grill` `check_pantry` `check_hardware_store` `check_wallet`
`set_thermostat` `find_tool` `web_search` `remember` `recall` `load_skill` `tell_joke`

House state (propane, pantry, budget) is a `WORLD` dict in `core/tools.py` you set to stage
a scenario. `web_search` makes a real call to the live web.

## Skills

Markdown procedures, not verbs. Only the one-line descriptions sit in the system prompt;
full bodies load on demand via the `load_skill` tool. With fifteen skills installed, this
keeps the prompt about 73% smaller than pasting every body in, and the gap widens as you
add more.

`hosting` is an orchestrator: its body instructs the model to consult `money-decisions`,
`grilling`, and `yard-work`, then reconcile them under a priority order. One request, four
skills. See [writing skills](skills.md).

## Governance

Every proposed tool call passes through `Mom` before it executes. She returns a verdict:

- `allow` — run as-is
- `deny` — block it; the model sees the reason instead of a result
- `modify` — run it with rewritten arguments (e.g. cap the spend)

Two policies ship by default: a seasonal thermostat cap (74F cooling, 70F heating, chosen
by the calendar) and a $100 ceiling on any single purchase. Policies are plain callables;
add your own to `Mom.policies`.

Blocked calls are still written to memory. A governance layer that forgets what it blocked
cannot inform later sessions.

### Constitution

Mom also enforces Dad's constitution — values, a thinking process, and voice rules. The
voice rules are mechanical, not advisory: replies over four sentences are trimmed before
they reach the user, but a line carrying genuine acknowledgment is protected from the cut
rather than amputated for coming last.

## Memory

One append-only `.jsonl` per category under `~/.dadloop/memory/`: grievances, lessons,
rulings, people. Recent grievances are injected into the system prompt every turn, so a
blocked thermostat change in one session resurfaces unprompted in the next.

## Tracing

An OpenTelemetry-shaped tracer with no dependencies. Each turn is a root span; `llm.call`
and `tool.execute` are children.

```
trace  1840ms total  |  2 llm calls 1590ms, 3 tools 240ms  |  tokens 2550->180  |  ~$0.010
```

Session totals accumulate across turns and are visible in the UI sidebar and the admin
view. Swapping the emitter for the real OTel SDK is a small, local change to `core/trace.py`.

## Interface

The main screen is a canvas, not a chat log. Each tool call lands as a collapsible
reasoning step showing the arguments passed and the result returned. Skills assemble
visibly on the canvas. The left panel tracks the model's stated plan, checking off steps as
their tool calls resolve; a tool call that was not in the stated plan is appended and
marked unplanned, so drift between intent and behavior stays visible.

| key | |
|--|--|
| `Tab` / `Shift+Tab` | move between reasoning steps |
| `Enter` | expand or collapse the focused step |
| `f2` / `f3` | expand all / collapse all |
| `f4` | admin view: tools, skills, constitution, policies, memory, telemetry |
| `f5` | clear the canvas |
| `ctrl+q` | quit |

Function keys, not ctrl-combos. Textual's `Input` widget claims `ctrl+a`, `ctrl+e`,
`ctrl+c` and others for line editing, and a focused input wins over app-level
bindings — so a `ctrl+e` shortcut is silently dead exactly when the user is typing.
