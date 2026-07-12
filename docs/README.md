<!--
Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Documentation for README asset files and screenshots.
-->

# Assets referenced by the main README

Three files go here. The README links them already — drop them in and they render.

| file | what it should show | how to capture |
|--|--|--|
| `demo.gif` | a short loop of Dad working a real request | record the TUI with [asciinema](https://asciinema.org) + [agg](https://github.com/asciinema/agg), or any screen recorder |
| `screenshot-canvas.png` | the main canvas with a reasoning step expanded | run `python -m dadloop`, expand a step with `Enter`, screenshot |
| `screenshot-admin.png` | the admin view (`f4`) | run `python -m dadloop`, press `f4`, screenshot |

Suggested demo script for the gif — it exercises constraint reconciliation, a Mom veto,
and multi-skill assembly in one go:

```
I'm hosting twelve people Saturday and I've got forty bucks
```

Then set the world to make it interesting first, in `core/tools.py`:

```python
WORLD = {"propane": "empty", "hardware_store_open": False,
         "weather_f": 58, "pantry_has_veggies": False, "budget": 40}
```
