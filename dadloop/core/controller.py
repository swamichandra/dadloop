"""Author: Swami Chandrasekaran
Last Modified: 2026-08-15
Purpose: Mom governance layer that reviews and overrules tool calls and replies.

Mom — the governance layer that sits above the model.

This is the part most agent demos skip. Governance is not a disclaimer in the
system prompt asking the model nicely; it is a layer with the authority to
overrule it. Mom sees every tool call *before* it executes and returns a Verdict:

    allow   run it as the model asked
    deny    block it; the model is told why, and gets to react
    modify  run it with rewritten arguments (e.g. cap a $400 spend at $100)

She also reviews the final reply against the constitution's voice rules, so a
rambling answer is trimmed before it reaches the person. The distinction that
matters: the model can *intend* anything, but Mom decides what actually happens.

Policies are plain callables — see `Mom.policies`. Adding one requires no change
to the loop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Callable

from .context import Context


@dataclass
class Verdict:
    action: str            # "allow" | "deny" | "modify"
    args: dict | None = None   # replacement args when action == "modify"
    reason: str = ""       # what the model (and user) is told


# A policy inspects a proposed call and returns a Verdict.
Policy = Callable[[Context, str, dict], Verdict]

_SUMMER_MONTHS = {6, 7, 8, 9}   # Jun-Sep: cooling season, cap 74°F
_MAX_REPLY_SENTENCES = 5        # constitution III.12: up to 4 for the answer, +1 for care

# Loose markers that a sentence is doing acknowledgment/care, not fact-reporting.
# Not sentiment analysis — just enough signal to stop Mom amputating warmth
# for the crime of coming last.
_CARE_MARKERS = (
    "sounds", "know", "get it", "rough", "stressful", "proud", "hang in",
    "you got this", "that's a lot", "no small thing", "worth it", "well done",
    "good on you", "i hear", "that's tough", "glad", "here for", "with you",
)


def _seasonal_thermostat_cap(ctx: Context, name: str, args: dict) -> Verdict:
    """Mom's house rule: 74°F cool in summer, 70°F heat in winter."""
    if name != "set_thermostat":
        return Verdict("allow")
    setpoint = int(args.get("setpoint", 0))
    summer = date.today().month in _SUMMER_MONTHS
    cap = 74 if summer else 70
    season = "summer" if summer else "winter"
    if setpoint > cap:
        return Verdict("deny",
                       reason=f"Mom says: it's {season}, cap is {cap}°F. Put on a sweater.")
    return Verdict("allow")


def _spend_cap(ctx: Context, name: str, args: dict) -> Verdict:
    """Mom caps any single purchase at $100, no matter what Dad approves."""
    if name == "check_wallet" and float(args.get("amount", 0)) > 100:
        capped = dict(args, amount=100)
        return Verdict("modify", args=capped,
                       reason="Mom capped this at $100. We're not made of money.")
    return Verdict("allow")


def _is_care(sentence: str) -> bool:
    low = sentence.lower()
    return any(marker in low for marker in _CARE_MARKERS)


def _trim_to_sentences(text: str, limit: int) -> str:
    """Keep `limit` sentences, protecting a care/acknowledgment sentence from
    being cut just for coming last. If over budget with no care sentence in
    play, trim from the tail as before — the blunt case is still blunt."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(parts) <= limit:
        return text

    care_idx = next((i for i, p in enumerate(parts) if _is_care(p)), None)
    if care_idx is None or care_idx < limit:
        # No care sentence, or it already fits — trim the tail, unchanged behavior.
        return " ".join(parts[:limit])

    # Care sentence got pushed past the cap by earlier fact sentences — keep
    # it, and drop from the middle/tail instead of amputating the warmth.
    kept = parts[:limit - 1] + [parts[care_idx]]
    return " ".join(kept)


class Mom:
    """The controller. Her authority is over *actions*: every proposed tool call
    runs past her policies, and she can allow, block, or rewrite it before it
    executes. That is governance, and it fires only when a real threshold is
    crossed.

    She also tightens Dad's final reply against his voice rules, but that is
    editing rather than authority — it happens quietly, raises no event, and is
    kept deliberately separate so a rare, meaningful veto never looks like a
    routine style note.
    """

    def __init__(self, policies: list[Policy] | None = None,
                 max_reply_sentences: int = _MAX_REPLY_SENTENCES) -> None:
        self.policies = policies if policies is not None else [
            _seasonal_thermostat_cap,
            _spend_cap,
        ]
        self.max_reply_sentences = max_reply_sentences

    def review(self, ctx: Context, name: str, args: dict) -> Verdict:
        """First policy to say something other than 'allow' wins."""
        for policy in self.policies:
            verdict = policy(ctx, name, args)
            if verdict.action != "allow":
                return verdict
        return Verdict("allow")

    def enforce_voice(self, text: str) -> str:
        """Tighten Dad's final reply to the constitution's voice rules.

        This is NOT governance, and deliberately does not look like it. Mom's
        authority — review() — is about *actions with consequences*: a spend
        over the cap, a thermostat past the seasonal limit, a call that must be
        blocked or rewritten before it executes. Those are thresholds, they are
        rare, and when one fires the human should see it.

        Trimming a long reply is a different kind of thing entirely. It is
        editing, against Dad's own voice rules, and it would fire on nearly
        every thorough answer. Surfacing it with the same weight as a veto made
        Dad look supervised on every turn and made real vetoes indistinguishable
        from style notes. So this runs quietly and reports nothing: the reply
        gets tighter, and no governance event is raised.

        She still protects one line of warmth from the cut; she doesn't protect
        padding.
        """
        sentence_count = len(re.split(r"(?<=[.!?])\s+", text.strip()))
        if sentence_count > self.max_reply_sentences:
            return _trim_to_sentences(text, self.max_reply_sentences)
        return text
