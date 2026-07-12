"""Author: Swami Chandrasekaran
Last Modified: 2026-07-12
Purpose: File-based semantic memory for grievances, lessons, people, and rulings.

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

CATEGORIES = ("grievances", "lessons", "people", "rulings")


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
        accomplished across every session, not just this one."""
        return {cat: len(self.recall(cat)) for cat in CATEGORIES}

    def files(self) -> list[tuple[str, int]]:
        """(filename, size in bytes) per category file, for the admin view —
        where memory actually lives on disk, not just how many entries."""
        out = []
        for cat in CATEGORIES:
            path = self._file(cat)
            size = path.stat().st_size if path.exists() else 0
            out.append((path.name, size))
        return out
