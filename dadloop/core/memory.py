"""Author: Swami Chandrasekaran
Last Modified: 2026-07-18
Purpose: File-based semantic memory for grievances, lessons, people, rulings, and skill usage.

Semantic memory — file-based, one JSONL per category.

Not a vector DB. A dad doesn't recall a blob; he recalls grievances, lessons,
people, and rulings. Each category is its own append-only file under
~/.dadloop/memory/, so recall is by kind and search is a keyword scan. Swap in
embeddings later without touching callers.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

CATEGORIES = ("grievances", "lessons", "people", "rulings", "usage")


@dataclass
class MemoryEntry:
    text: str
    category: str
    tags: list[str] = field(default_factory=list)
    ts: float = field(default_factory=time.time)


class SemanticMemory:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (Path.home() / ".dadloop" / "memory")
        self.root.mkdir(parents=True, exist_ok=True)

    def _file(self, category: str) -> Path:
        if category not in CATEGORIES:
            raise ValueError(f"Unknown memory category: {category!r}")
        return self.root / f"{category}.jsonl"

    def remember(self, category: str, text: str, tags: list[str] | None = None) -> MemoryEntry:
        entry = MemoryEntry(text=text, category=category, tags=tags or [])
        with self._file(category).open("a") as f:
            f.write(json.dumps(asdict(entry)) + "\n")
        return entry

    def recall(self, category: str) -> list[MemoryEntry]:
        path = self._file(category)
        if not path.exists():
            return []
        return [MemoryEntry(**json.loads(line)) for line in path.read_text().splitlines() if line]

    def search(self, query: str) -> list[MemoryEntry]:
        q = query.lower()
        return [e for cat in CATEGORIES for e in self.recall(cat)
                if q in e.text.lower() or any(q in t.lower() for t in e.tags)]

    def ledger(self) -> dict[str, int]:
        """Counts per category, read fresh from disk — what Dad has actually
        accomplished across every session, not just this one.

        Deliberately excludes 'usage', which is telemetry about the harness
        rather than something Dad learned about the household. Mixing a skill
        load counter in with grievances and rulings would make the ledger a
        worse answer to "what does he know now".
        """
        return {cat: len(self.recall(cat)) for cat in CATEGORIES if cat != "usage"}

    def record_use(self, kind: str, name: str) -> None:
        """Note that a skill (or anything else worth counting) was used.

        Written to the same append-only store as everything else so it survives
        a restart. Without this, "top skills" can only ever describe the current
        session, which is the least interesting version of that question — the
        useful one is which playbooks this household actually reaches for.
        """
        self.remember("usage", f"{kind}:{name}", tags=[kind, name])

    def top_skills(self, limit: int = 5) -> list[tuple[str, int]]:
        """(skill, times loaded) across every session, most used first."""
        counts: dict[str, int] = {}
        for entry in self.recall("usage"):
            if entry.text.startswith("skill:"):
                name = entry.text.split(":", 1)[1]
                counts[name] = counts.get(name, 0) + 1
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]

    def files(self) -> list[tuple[str, int]]:
        """(filename, size in bytes) per category file, for the admin view —
        where memory actually lives on disk, not just how many entries."""
        out = []
        for cat in CATEGORIES:
            path = self._file(cat)
            size = path.stat().st_size if path.exists() else 0
            out.append((path.name, size))
        return out
