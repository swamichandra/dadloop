"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: Loads and catalogs Markdown skill procedures for on-demand use.

Skills — Dad's know-how as Markdown. Progressive disclosure: the model always
sees the one-line descriptions (catalog), and pulls a skill's full body into
context only when it calls load_skill. Adding a skill is writing a .md file.

Tools are verbs; skills are the procedure the model applies using them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parent.parent / "skills"


@dataclass
class Skill:
    name: str
    description: str
    body: str


def _parse(path: Path) -> Skill:
    text = path.read_text()
    name, description = path.stem, ""
    body = text
    if text.startswith("---"):
        _, front, body = text.split("---", 2)
        for line in front.strip().splitlines():
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("description:"):
                description = line.split(":", 1)[1].strip()
    return Skill(name=name, description=description, body=body.strip())


def load_all() -> dict[str, Skill]:
    if not _SKILL_DIR.exists():
        return {}
    return {s.name: s for s in (_parse(p) for p in sorted(_SKILL_DIR.glob("*.md")))}


SKILLS: dict[str, Skill] = load_all()


def catalog() -> str:
    """The cheap part: one line per skill, always shown to the model."""
    if not SKILLS:
        return "(no skills installed)"
    return "\n".join(f"- {s.name}: {s.description}" for s in SKILLS.values())
