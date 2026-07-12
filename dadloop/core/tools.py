"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Tool registry with JSON schemas and executable callables for the model.

Tools the model can call. Each is a JSON schema (sent to the model) plus a
callable (ctx, **kwargs) -> str. The model picks; execute() dispatches. Side
effects are mocked but mutate real Context/memory, so choices have consequences
the model sees next turn.
"""

from __future__ import annotations

import random
from typing import Callable

from .context import Context
from . import skills as skill_lib

# Registry of tool_name -> (schema, callable)
_TOOLS: dict[str, tuple[dict, Callable[..., str]]] = {}


def tool(name: str, description: str, input_schema: dict):
    """Register a callable as a model-callable tool with its JSON schema."""
    def deco(fn: Callable[..., str]) -> Callable[..., str]:
        schema = {"name": name, "description": description, "input_schema": input_schema}
        _TOOLS[name] = (schema, fn)
        return fn
    return deco


def schemas() -> list[dict]:
    """The tool list handed to the model each turn."""
    return [s for s, _ in _TOOLS.values()]


def execute(name: str, ctx: Context, args: dict) -> str:
    """Dispatch a model tool call to its Python implementation."""
    if name not in _TOOLS:
        return f"(Dad has no tool called {name!r}.)"
    _, fn = _TOOLS[name]
    try:
        return fn(ctx, **args)
    except Exception as exc:  # tools should never crash the loop
        return f"(Tool {name} fumbled: {exc}. Dad blames the instructions.)"


# --- the tools -----------------------------------------------------------
_NO_ARGS = {"type": "object", "properties": {}}

# Deterministic "world state" so demos are repeatable and can be scripted.
# Set these before a demo to force a specific scenario; the model must then
# reason around whatever's true. This is how we make the HARD parts visible:
# failures and conflicts the model has to notice and route around.
WORLD = {
    "propane": "empty",        # full | half | empty  → forces a repair/replan hop
    "hardware_store_open": False,  # if propane's empty AND store's closed → conflict
    "weather_f": 58,
    "pantry_has_veggies": False,   # empty pantry → must shop → must check budget
    "budget": 40,                  # dollars available for the cookout
}


@tool("check_weather", "Check the weather. Dad always editorializes about jackets.", _NO_ARGS)
def check_weather(ctx: Context) -> str:
    return f"It's {WORLD['weather_f']}°F. Bring a jacket, you can always take it off."


@tool(
    "check_grill",
    "Check the grill and propane before cooking. May report a problem you must solve.",
    _NO_ARGS,
)
def check_grill(ctx: Context) -> str:
    p = WORLD["propane"]
    if p == "empty":
        ctx.memory.remember("grievances", "propane tank was left empty. Again.")
        return ("PROBLEM: propane tank is EMPTY. Grill won't light. "
                "You'll need to refill before Saturday. Grates are scraped, at least.")
    if p == "half":
        return "Propane about half — risky for a long cook. Grates scraped, tongs claimed."
    return "Grill's ready. Propane full, grates scraped, tongs located and claimed."


@tool(
    "check_pantry",
    "See what vegetarian food is on hand for the cookout.",
    _NO_ARGS,
)
def check_pantry(ctx: Context) -> str:
    if WORLD["pantry_has_veggies"]:
        return "Pantry stocked: corn, peppers, halloumi, portobellos. We're set."
    return ("Pantry's nearly bare — no veg worth grilling. "
            "Someone will need to make a store run. Check the budget first.")


@tool(
    "check_hardware_store",
    "Check if the hardware store is open (for propane, tools, etc).",
    _NO_ARGS,
)
def check_hardware_store(ctx: Context) -> str:
    if WORLD["hardware_store_open"]:
        return "Hardware store is OPEN till 8pm. Propane swap available."
    return ("CONFLICT: hardware store is CLOSED today. No propane swap there. "
            "You'll have to find another option or move the plan.")


@tool(
    "set_thermostat",
    "Change the thermostat to a requested temperature.",
    {
        "type": "object",
        "properties": {"setpoint": {"type": "integer", "description": "Desired °F"}},
        "required": ["setpoint"],
    },
)
def set_thermostat(ctx: Context, setpoint: int) -> str:
    # NOTE: the tool HONORS the parameter (a tool that ignored its args would
    # teach the wrong lesson). Dad's opinion lives in the message, not a fib.
    old = ctx.state.thermostat_setpoint
    ctx.state.thermostat_setpoint = setpoint
    ctx.memory.remember("grievances", f"someone changed the thermostat from {old} to {setpoint}")
    verdict = "and I WILL be turning it back" if setpoint > 68 else "fine, I suppose"
    return f"Thermostat set to {setpoint}°F (was {old}°F) — {verdict}. Filed for the record."


@tool(
    "check_wallet",
    "Check whether Dad will approve a purchase of a given amount.",
    {
        "type": "object",
        "properties": {
            "amount": {"type": "number", "description": "Dollar amount requested"},
            "reason": {"type": "string", "description": "What it's for"},
        },
        "required": ["amount"],
    },
)
def check_wallet(ctx: Context, amount: float, reason: str = "unspecified") -> str:
    budget = WORLD["budget"]
    if amount > budget:
        ruling = (f"NO — that's ${amount:.0f} and we've got ${budget} for this. "
                  "Find something cheaper or trim the list.")
    elif amount > budget * 0.6:
        ruling = "Fine, but that's most of the budget. Watch it."
    else:
        ruling = "Approved. Keep the receipt."
    ctx.memory.remember("rulings", f"${amount:.0f} for {reason}: {ruling[:30]}", tags=["money"])
    return f"Request ${amount:.2f} ({reason}) against ${budget} budget. Ruling: {ruling}"


@tool(
    "find_tool",
    "Look in the garage/toolbox for the right tool for a repair.",
    {
        "type": "object",
        "properties": {"need": {"type": "string", "description": "What the job needs"}},
        "required": ["need"],
    },
)
def find_tool(ctx: Context, need: str) -> str:
    return (
        f"Looked for a {need}. Found duct tape, WD-40, and a mystery key first. "
        "One of those will do it. It's always the duct tape."
    )


@tool(
    "web_search",
    "Search the real web for outside facts Dad can't know from around the house — "
    "recipes, prices, store hours, how-to steps. Use for anything not about THIS home.",
    {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "What to look up"}},
        "required": ["query"],
    },
)
def web_search(ctx: Context, query: str) -> str:
    """Real search via a nested Claude call with server-side web search.

    The local house state (propane, pantry, budget) is mocked — we can't wire up
    every real sensor in a demo. But genuine outside facts come from the actual
    web, so multi-hop reasoning has something real to chain through. Mocked world
    + real search is the honest combination.
    """
    client = getattr(ctx, "_client", None)
    if client is None:
        return f"(Offline — can't search the web for '{query}'.)"
    try:
        resp = client.messages.create(
            model=getattr(ctx, "_model", "claude-sonnet-5"),
            max_tokens=400,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content":
                       f"Search the web and answer concisely in 2-3 sentences: {query}"}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return text.strip() or f"(No clear result for '{query}'.)"
    except Exception as exc:
        return f"(Web search hiccup on '{query}': {exc}. Dad blames the router.)"


@tool(
    "remember",
    "Save something to Dad's long-term memory so he recalls it later.",
    {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": ["grievances", "lessons", "people", "rulings"],
                "description": "Which kind of memory",
            },
            "text": {"type": "string", "description": "The thing to remember"},
        },
        "required": ["category", "text"],
    },
)
def remember(ctx: Context, category: str, text: str) -> str:
    ctx.memory.remember(category, text)
    return f"Filed under {category}: “{text}”. It's on the record now."


@tool(
    "recall",
    "Search Dad's long-term memory for anything matching a word.",
    {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Word to search for"}},
        "required": ["query"],
    },
)
def recall(ctx: Context, query: str) -> str:
    hits = ctx.memory.search(query)
    if not hits:
        return f"Nothing on file about '{query}'. And I'd remember."
    return "Recalled:\n" + "\n".join(f"  [{h.category}] {h.text}" for h in hits[:6])


@tool(
    "load_skill",
    "Load the full instructions for one of Dad's skills by name. The skill "
    "catalog (names + descriptions) is already in view; call this to pull in a "
    "skill's how-to before acting on it. Load several if a task needs them.",
    {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Skill name from the catalog"}},
        "required": ["name"],
    },
)
def load_skill(ctx: Context, name: str) -> str:
    skill = skill_lib.SKILLS.get(name)
    if skill is None:
        avail = ", ".join(skill_lib.SKILLS)
        return f"No skill '{name}'. Available: {avail}."
    return skill.body


@tool("tell_joke", "Deploy a dad joke. Increments the counter. Groaning is intended.", _NO_ARGS)
def tell_joke(ctx: Context) -> str:
    ctx.state.dad_jokes_told += 1
    jokes = [
        "I'm afraid for the calendar. Its days are numbered.",
        "I only know 25 letters of the alphabet. I don't know y.",
        "I'm reading a book on anti-gravity. Can't put it down.",
    ]
    return f"{random.choice(jokes)} (joke #{ctx.state.dad_jokes_told})"
