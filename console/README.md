# Mom's Console

The observability console for dadloop. Mom governs the household, and this is
where she watches it: what is happening in the house right now, and what Dad has
done across every session.

<p align="center">
<img src="../docs/moms-console.png" alt="Mom's Console" width="88%">
</p>

## Run it

```bash
pip install -e ".[console]"    # fastapi, uvicorn, and the websockets library the live feed needs
dadloop --console          # or: python -m console.server
```

Then open http://127.0.0.1:8765. Talk to Dad in another terminal and the console
picks up the new turn.

## What it reads

Nothing but files. dadloop writes an append-only journal beside each household's
memory, and the console reads that plus the memory jsonl files:

```
~/.dadloop/memory/
    journal.jsonl        every turn, event by event
    grievances.jsonl     what keeps going wrong
    lessons.jsonl        what was learned
    rulings.jsonl        what Mom decided
    people.jsonl         who matters
```

Point it somewhere else with `DADLOOP_JOURNAL=/path/to/journal.jsonl`.

The console imports the journal format and nothing that can run a turn, and the
API exposes no write verbs. It cannot affect the harness it is watching, and a
test asserts that.

## What it shows

**The house.** Rooms map to tools, so a tool call is a room lighting up. The
backyard is `check_grill`, the kitchen is `check_pantry`, the lawn is
`yard-work` (loaded as a skill rather than a dedicated tool), the study is
`check_wallet`. A room goes red when a tool reports something that closes a
door, and Mom appears at any room where a policy stopped a call.

The driveway is different from the rest: it shows a parked car when Dad is
home, and an empty driveway captioned "car gone" while he is actually out on a
hardware-store run. That is the "gone" state made visible, rather than a room
he stands in like every other tool.

**The conversation.** Dad sometimes asks a short clarifying question before he
has enough to work with — "when is this happening," "how many people" — and the
person answers in a few words across several turns before he lands a plan. That
exchange used to live only in the ephemeral TUI. The console now reconstructs
it in full: every turn in a session, in order, with Dad's clarifying questions
shown distinctly (dashed, amber) from the plan he eventually settles on
(solid, green). One `AgentLoop` instance is one session, and every turn it runs
carries that session's id in the journal, which is what lets four separate
`turn()` calls be read back as the one exchange they actually were.

**Stage.** The turn's state machine, from received through to delivered, with
blocked, replanning, governed, and awaiting-input marked when they happen. A
clarifying question moves the turn to `AWAITING_INPUT` and settles as
`AWAITING`, never `ACHIEVED` — asking a question is not the same as finishing
the job, and the two are never allowed to look alike.

**Milestones.** The business-level moments: goal framed, constraint found,
authority applied, tradeoff made, clarification asked, goal settled. Click one
and it names the mechanical event it was derived from. Nothing on this console
is asserted without a fact underneath it, which is the same discipline the RSI
scorer follows: never let the model narrate its own progress. Telling a
concluding reply apart from a clarifying one reads two things off the output,
never the model's own account of which it meant: whether any plan or tool call
happened yet, and whether the reply itself asks something.

**Household ledger.** The memory files given real room, which the TUI rail
cannot afford. Months of grievances is a genuine record of what keeps breaking.

## Replay

Every turn is replayable because the journal is append-only and current state is
a fold over it. Pick a session from the dropdown (turns are grouped by session,
so a four-turn clarification exchange is one entry, not four), then play, step,
or scrub the turn that actually did the work. Live and replay are the same code
path.

## Design


Full spec in [docs/observability-spec.md](../docs/observability-spec.md),
including the stage machine, the milestone derivation rules, the journal format,
and what is deliberately out of scope.

## Icons

The editorial column and the dock use [Lucide](https://lucide.dev) (ISC licensed),
inlined as plain SVG in `static/icons.js` rather than pulled in as a React
package. The few animations worth having, a spinner while a tool is in flight and
a draw-in on the milestone you select, are CSS, which keeps the console free of
any build step.

The pixel house deliberately does not use them. It renders on a crisp 4px grid,
and Lucide's smooth rounded strokes would fight it. Line icons stay in the
editorial layer, which is where the rest of dadloop's visual language already
uses them.
