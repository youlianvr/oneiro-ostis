"""The skill catalog as an agent tool: look for a ready-made contract first.

Owner decision (2026-09-22): the harness searches the catalog itself instead of
us describing to it, in prose, which skill it should have reached for. The
catalog is the workspace's own index of ~320 contracts (101 routers plus their
parts), each carrying hand-reviewed semantics: when to use it, what it covers,
what it must never be used for.

Two things are deliberate here:

* the ranking is **the same deterministic arithmetic** the ``find-skills`` skill
  runs by hand: term overlap over ``purpose``, ``use_cases``, ``keywords`` and
  ``trigger_phrases``, no embeddings, no network. Same catalog and same query
  always give the same ranking, which is what makes "did the lookup pay for
  itself?" a measurable question instead of an opinion;
* a contract is read from the same ``SKILL.md`` file a person would open, so
  the agent and the human are looking at one document, not two.

What the module does not do: decide anything. It returns candidates and text;
whether looking in the catalog was worth the tokens is for the judge to settle.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

TERM_RE = re.compile(r"[a-z0-9:.\-]{3,}")
CATALOG_REL = Path("knowledge") / "wiki" / "skills-catalog.json"
CONTRACT_CHARS = 8000

# The four semantic fields the catalog reviews, in the order the skill weights
# them. Kept as data so the weighting below stays readable.
FIELDS = ("use_cases", "keywords", "trigger_phrases")


class CatalogError(RuntimeError):
    """The catalog is missing or malformed; the tool says so instead of lying."""


@dataclass(frozen=True)
class Hit:
    """One catalog candidate, with the provenance needed to judge it."""

    name: str          # "browser" or "browser/parts/agent-browser"
    score: int
    confidence: str    # the semantic review's confidence, or "n/a"
    status: str        # Active / Uncertain / Candidate-non-relevant
    path: str
    kind: str          # router | part
    purpose: str

    def line(self) -> str:
        purpose = " ".join(self.purpose.split())
        if len(purpose) > 200:
            purpose = purpose[:197] + "..."
        return (f"{self.name}  (match {self.score}, review {self.confidence}, "
                f"{self.status})\n    {purpose}")


def workspace_root(start: Path | None = None) -> Path:
    """The directory holding ``knowledge/wiki/skills-catalog.json``.

    Searched upward from this file so the project can be moved without a
    constant to edit, and overridable for tests and for a different checkout.
    """
    env = os.environ.get("ONEIRO_WORKSPACE")
    if env and (Path(env) / CATALOG_REL).exists():
        return Path(env)
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if (parent / CATALOG_REL).exists():
            return parent
    raise CatalogError(f"no skill catalog found above {here}")


class Catalog:
    """The reviewed skill index, plus the contracts it points at."""

    def __init__(self, records: list[dict], root: Path, catalog_path: Path):
        self.root = Path(root)
        self.path = Path(catalog_path)
        self.records = records
        self._by_name: dict[str, dict] = {}
        for record in records:
            name = str(record.get("name") or "").strip()
            if name:
                self._by_name[name] = record
            for part in record.get("parts") or []:
                part_name = str(part.get("name") or "").strip()
                if name and part_name:
                    self._by_name[f"{name}/parts/{part_name}"] = part

    @property
    def size(self) -> int:
        """Contracts addressable by name: routers plus their parts."""
        return len(self._by_name)

    # -- ranking --

    def search(self, query: str, limit: int = 4) -> list[Hit]:
        """Rank the catalog against a natural-language query.

        The arithmetic is the skill's own, reproduced exactly: three points for
        a term that is a catalogue keyword, two for a term the curated trigger
        phrases contain, one for a term anywhere in the reviewed text.
        """
        terms = [t for t in TERM_RE.findall(str(query).lower()) if t]
        if not terms:
            return []
        scored: list[tuple[int, str, Hit]] = []
        for name, record in self._by_name.items():
            semantic = record.get("semantic") or {}
            blob = " ".join(str(record.get("purpose") or "").lower().split())
            blob += " " + " ".join(
                str(item).lower()
                for field in FIELDS for item in (semantic.get(field) or []))
            score = 0
            for term in terms:
                if term in (semantic.get("keywords") or []):
                    score += 3
                elif any(term in str(x).lower()
                         for x in (semantic.get("trigger_phrases") or [])):
                    score += 2
                elif term in blob:
                    score += 1
            if not score:
                continue
            hit = Hit(
                name=name,
                score=score,
                confidence=str((semantic.get("review") or {}).get("confidence") or "n/a"),
                status=str(record.get("status") or "unknown"),
                path=str(record.get("path") or ""),
                kind="part" if "/parts/" in name else "router",
                purpose=str(record.get("purpose") or ""),
            )
            scored.append((score, name, hit))
        # Ties break on the name so two runs of the same query cannot differ.
        scored.sort(key=lambda row: (-row[0], row[1]))
        return [hit for _, _, hit in scored[:max(1, int(limit))]]

    # -- contracts --

    def contract_path(self, name: str) -> Path:
        key = str(name).strip()
        record = self._by_name.get(key)
        if record is None:
            raise CatalogError(f"no such skill in the catalog: {key}")
        raw = str(record.get("path") or "")
        if raw:
            return (self.root / raw).resolve()
        if "/parts/" in key:
            router, part = key.split("/parts/", 1)
            return (self.root / ".agents" / "skills" / router / "parts" / part
                    / "SKILL.md")
        return self.root / ".agents" / "skills" / key / "SKILL.md"

    def contract(self, name: str, chars: int = CONTRACT_CHARS) -> str:
        """The contract itself, bounded, with an honest note when it is cut."""
        path = self.contract_path(name)
        if not path.exists():
            raise CatalogError(f"the catalog points at a missing file: {path}")
        text = path.read_text(encoding="utf-8", errors="replace")
        limit = max(500, int(chars or CONTRACT_CHARS))
        note = ""
        if len(text) > limit:
            note = (f"\n... [{len(text) - limit} characters of this contract "
                    f"were not shown; call read_skill again with a larger chars "
                    f"value if the part you need is below]")
            text = text[:limit]
        return f"{name} ({path})\n\n{text}{note}"


def load(workspace: Path | None = None, catalog_path: Path | None = None) -> Catalog:
    """Read the catalog from disk. Raises CatalogError when it cannot."""
    root = Path(workspace) if workspace else workspace_root()
    path = Path(catalog_path) if catalog_path else root / CATALOG_REL
    if not path.exists():
        raise CatalogError(f"skill catalog not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CatalogError(f"skill catalog is not valid JSON: {exc}") from exc
    records = raw.get("skills") if isinstance(raw, dict) else raw
    if not isinstance(records, list) or not records:
        raise CatalogError(f"skill catalog has no records: {path}")
    return Catalog(records, root, path)


# -- what the agent sees --


def render_search(catalog: Catalog, query: str, limit: int = 4) -> str:
    hits = catalog.search(query, limit)
    if not hits:
        return (f"No catalog match for {query!r} in {catalog.size} contracts. "
                f"Nothing ready-made covers this; solve it directly.")
    header = f"{len(hits)} of {catalog.size} contracts, best first:"
    return header + "\n\n" + "\n\n".join(hit.line() for hit in hits)


def render_contract(catalog: Catalog, name: str, chars: int = CONTRACT_CHARS) -> str:
    return catalog.contract(name, chars)


TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "find_skills",
            "description": (
                "Search the workspace skill catalog for a ready-made procedure "
                "for this task (a contract that already says how to do it, what "
                "to avoid, and when not to use it). Returns ranked candidates "
                "with their review confidence. Use it before inventing an "
                "approach from scratch."),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "what you need to do"},
                    "limit": {"type": "integer",
                              "description": "how many candidates to show (default 4)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_skill",
            "description": (
                "Read the full contract of one catalog entry by the exact name "
                "find_skills returned (a router, or 'router/parts/part')."),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "chars": {"type": "integer",
                              "description": "how much of it to read (default 8000)"},
                },
                "required": ["name"],
            },
        },
    },
]

TOOL_NAMES = tuple(schema["function"]["name"] for schema in TOOL_SCHEMAS)

# The lookup cost, counted in characters the model was charged for, is what the
# judge compares against the tokens saved. Named constants keep the report from
# inventing a denominator later.
CATALOG_TOOL_NAME = "find_skills"
CONTRACT_TOOL_NAME = "read_skill"


def evidence(actions: list[dict], catalog: Catalog | None) -> dict:
    """What the catalog gave this episode, and what it cost to ask."""
    lookups = [a for a in actions if a.get("tool") == CATALOG_TOOL_NAME]
    reads = [a for a in actions if a.get("tool") == CONTRACT_TOOL_NAME]
    chars = sum(len(str(a.get("observation") or "")) for a in lookups + reads)
    return {
        "available": catalog is not None,
        "contracts": catalog.size if catalog is not None else 0,
        "lookups": len(lookups),
        "contracts_read": len(reads),
        "observation_chars": chars,
        "queries": [str((a.get("args") or {}).get("query") or "")[:120] for a in lookups],
        "read": [str((a.get("args") or {}).get("name") or "")[:120] for a in reads],
    }
