# dadloop

An agent harness, explained through the most capable system you already understand: Dad.

## Why I built this

When asked what is an "agent harness", everyone repeats the same equation: "Agent = Model + Harness". Gets explained as everything that isn't the model. That has always bothered me. It's a lazy kitchen-sink definition. It tells us what a harness isn't, but almost nothing about what it actually does. If we're going to talk about agent harnesses, we should be able to explain what they actually are.

So I built dadloop: a minimal, executable agent harness that makes those pieces visible.

Most agent harnesses today are demonstrated through coding. That makes sense because code provides immediate feedback through compilers, tests and linters. But knowledge work is a different animal. They involve budgets, policies, trade-offs, institutional know-how, and work that unfolds over days or weeks instead of a single interaction.

I wanted to show what an agent harness would look like for that kind of domain work. dadloop is an agent harness for that kind of work. Its domain happens to be a suburban dad, because everyone already knows the rules, controlled by mom. dadloop is also my homage to [pi.dev](https://pi.dev) — small core, tools as the model's hands, memory you own, no framework in the way.

<p align="center">
<img src="docs/dadloop1.png" alt="dadloop - parts of the agent harness" width="60%">
</p>

## What it looks like

Ask him something that has to be worked out, not just answered:

```
Twelve people Saturday, and I've got forty bucks.
```

He states a plan, then loads `hosting`, which pulls in `money-decisions`, `grilling`, and `yard-work`. The menu he'd default to costs more than the budget allows. Mom caps the spend before the call runs. Something has to give, and the priority order in the skill decides what — budget wins, then timing, then menu.

Every one of those moves is on screen: the plan checking off, each tool call openable, Mom's veto as a card, the token cost at the bottom. Swap the cookout for a procurement request and none of the machinery changes.

## Install

Requires Python 3.10+ and an [Anthropic API key](https://console.anthropic.com).

```bash
git clone https://github.com/you/dadloop && cd dadloop
pip install -e .
cp .env.example .env    # add your key to this file
```

## Usage

```bash
dadloop                   # terminal UI
dadloop --repl            # plain REPL
python -m dadloop.demos   # five scripted scenarios
```

`ctrl+q` quits. Every other key is shown in the footer.

## What it is made of

Six core sub-systems, and that is the whole harness.

| part | what it does | file |
|---|---|---|
| **Loop** | the model picks a tool, sees the result, decides again, stops when done | `core/agent.py` |
| **Tools** | twelve verbs. Some report facts, some report problems to work around | `core/tools.py` |
| **Skills** | fifteen Markdown procedures, loaded on demand. `hosting` composes three others | `skills/*.md` |
| **Governance** | Mom. Every call clears a policy layer that can allow, block, or rewrite it | `core/controller.py` |
| **Memory** | grievances, lessons, rulings, people — persisted, and re-injected each turn | `core/memory.py` |
| **Observability** | tokens, dollar cost, and the split between model time and tool time | `core/trace.py` |

The twelve tools: `check_weather` `check_grill` `check_pantry` `check_hardware_store` `check_wallet` `set_thermostat` `find_tool` `web_search` `remember` `recall` `load_skill` `tell_joke`

The fifteen skills: `answering-big-questions` `bedtime` `breaking-up-fights` `comforting-a-kid` `fixing-things` `grilling` `grocery-runs` `hosting` `money-decisions` `road-trips` `saying-no` `snow-shoveling` `teaching-kids-stuff` `the-thermostat` `yard-work`

Skills only put their one-line descriptions in the prompt; bodies load on demand, so fifteen cost about a quarter of pasting them all in. Blocked calls are still written to memory — the job outlives the session, so the harness carries the refusals across restarts, or long-horizon work is impossible.

<p align="center">
<img src="docs/dadloop-skills.png" alt="dadloop agent skills" width="60%">
</p>

Full detail in [docs/architecture.md](docs/architecture.md).

## Dad, and the constitution Mom holds him to

Dad is not a persona bolted on for charm. He runs on a written constitution, injected every turn — thirteen rules in three parts:

- **Values** — steady and clever; say what's true, not what's easy to hear; provide and do, don't lecture.
- **Process** — state the plan before touching a tool; check the world before ruling on it; load the skill before improvising; notice what's going on for the person before answering.
- **Voice** — lead with the decision, not the reasoning. Three sentences carry an answer, a fourth can carry the care. Warmth is not wordiness; brevity is not coldness.

Mom holds the pen. She owns amendments Dad cannot override, and three rules are not prompt text at all — they are code:

| rule | what happens |
|---|---|
| Thermostat cap | 74F summer, 70F winter, by the calendar. Ask for 78 in July and the call never executes. |
| Spend ceiling | $100 on any purchase. Dad can intend to say yes; the call is rewritten on the way out. |
| Four sentences | A long reply is trimmed before you see it — but a line carrying real acknowledgment is protected from the cut, not lopped off for coming last. |

Governance is not a disclaimer in the system prompt. It is a layer above the model that can overrule it.

## The work surface

The TUI is where the harness shows its work. It is the work surface. Any part of a turn is auditable without leaving it.

<p align="center">
<img src="docs/tui-main.png" alt="Work surface for the dadloop agent harness" width="40%">
</p>


- **Canvas** — every tool call is a collapsible step: the arguments passed, the result returned. Skills appear as he pulls them, so a four-skill reconciliation reads as four visible moves. `Tab` walks them, `Enter` opens one, `f2`/`f3` open and close them all.
- **Plan panel** — Dad's stated plan, checking off as calls resolve. A call that was *not* in the plan is appended and marked unplanned, so intent and behavior stay side by side.
- **Review cards** — Mom's blocks and rewrites land on the canvas as bordered cards: the call, the verdict, the reason. Not a log line.
- **Scoreboard** — session totals (turns, tools, tokens, cost, latency) and what has accumulated across every session.
- **Admin view** (`f4`) — the harness inspecting itself: tools and schemas, skills and which are loaded, the constitution, Mom's live policies, the memory files on disk, the telemetry.

<p align="center">
<img src="docs/tui-admin-panel.png" alt="Work surface admin panel" width="40%">
</p>


## Other things it has to survive

The cookout is one shape. Here are the others.

**A dead end.** *"Grill's not lighting and people are coming at six."* Propane is empty, so refill it — except the hardware store is closed. Both facts are true and together they shut the obvious door. A coding agent gets a stack trace here; a domain agent has to find a third way.

**An outside fact against an internal limit.** *"What's a propane swap run these days?"* Nothing in the house knows, so he searches the live web, then checks the answer against the real budget.

**A job that spans sessions.** Ask for 78 degrees in July. Governance denies it, and the blocked attempt is filed anyway. Come back tomorrow, ask about something else, and it surfaces unprompted. Nothing that matters in domain work finishes in one sitting.

**Being overruled.** *"Can we just get the nice grill? It's like $400."* Dad does not get the final word. The spend cap runs before the tool executes, so the call is rewritten on the way out no matter what he intended.

## Documentation

- [Architecture](docs/architecture.md) — the loop, tools, skills, governance, memory, tracing
- [Writing skills](docs/skills.md) — how to add one, and how they compose
- [Contributing](docs/contributing.md) — tests, lint, adding tools and policies

## Troubleshooting

**`APIConnectionError` on Windows while curl works.** Python is not trusting your organization's root CA. Run `pip install pip-system-certs`.

## License

MIT
