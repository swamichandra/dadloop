<!--
Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Guide for writing and composing Markdown skills.
-->

# Writing skills

A skill is a Markdown file in `skills/`. No registration; the loader picks it up.

```markdown
---
name: snow-shoveling
description: How Dad clears the drive. Load when snow, ice, or the driveway comes up.
---
# Snow shoveling

- Check the weather (`check_weather`) before you bother.
- Salt first, shovel second. Beat the sun before it turns the walk to a rink.
- Push, don't lift. Your back is not the tool here; the shovel is.
```

The `description` is what the model sees in every prompt, so write it as a trigger: say
when to load this, not what it contains. The body only enters context once the model calls
`load_skill`.

## Tools vs skills

Tools are verbs: `check_grill` does something and returns a result. Skills are procedure:
they tell the model when and how to use those verbs. `grilling` is a skill; it instructs
the model to call `check_grill` before promising anything.

Keep this line clean. A "skill" that just wraps one tool call should be a tool.

## Composition

A skill body can instruct the model to load other skills. `hosting` does this:

```markdown
1. Load `money-decisions` and settle the budget first. Everything downstream obeys it.
2. Load `grilling` for the menu and cook plan, kept inside that budget.
3. Load `yard-work` and schedule the mow the day before, weather permitting.

If they conflict: budget wins, then timing, then menu.
```

One request pulls in four skills and reconciles them. The priority order matters — without
it the model has no way to break a tie between a menu it wants and a budget it cannot
exceed.

## The fifteen that ship

`answering-big-questions` `bedtime` `breaking-up-fights` `comforting-a-kid` `fixing-things`
`grilling` `grocery-runs` `hosting` `money-decisions` `road-trips` `saying-no`
`snow-shoveling` `teaching-kids-stuff` `the-thermostat` `yard-work`

They were chosen on one test: is this a recurring situation with a practiced response?
That is what makes something a dad skill rather than a dad fact.
