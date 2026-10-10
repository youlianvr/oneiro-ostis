"""Skills inside the product: the reviewed catalog, its ranking, and its contracts.

A skill is a written procedure — a ``SKILL.md`` a person or an agent can follow. This
module is the migration of ``python/skills_index.py`` into the product, plus the two
things the standalone module could assume and a product cannot: where its catalog comes
from, and where the contracts are.

Three properties, and each of them is a sentence the settings page makes:

* **The catalog travels with the product.** An empty ``skills.catalog`` means the asset
  built into the package (``assets/skills-catalog.json``, produced from the reviewed
  workspace catalog by ``scripts/build-skills-asset.py`` and measured before shipping).
  Setting the key reads the owner's own catalog instead, in the same shape, so a person
  may keep a reviewed index of their own.
* **Ranking is the reviewed arithmetic, offline and deterministic.** The same catalog and
  the same query always give the same order: a term that is a curated keyword scores
  three, one the curated trigger phrases contain two, one anywhere in the reviewed text
  one, and ties break on the name. No embeddings and no network, which is what makes "did
  the lookup pay for itself?" a measurable question instead of an opinion.
* **A skill that cannot be resolved refuses by name.** An unknown name, a catalog whose
  JSON is broken, a catalog that is not there, and a contract file that is missing each
  produce a sentence saying what failed and where it was looked for. Nothing here answers
  an empty success.

``skills.paths`` are the folders skills are looked for in, on top of the product's own
``<data root>/skills``: each folder is scanned for ``<skill>/SKILL.md`` and
``<skill>/parts/<part>/SKILL.md``. An entry found only on disk is searchable and readable
too — its own description stands in for the review it never had, and its status says so
in as many words.

The module owns its whole surface, because ``web.py`` and ``cli.py`` are over the plan's
size guideline and only hand it over: :func:`add_routes` from the application and
:func:`skills_command` from the command line.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from oneiro import config
from oneiro.tools import ROLES, Tool, ToolError

TERM_RE = re.compile(r"[a-z0-9:.\-]{3,}")
#: The reviewed fields the ranking weighs, in the order the skill's arithmetic uses them.
FIELDS = ("use_cases", "keywords", "trigger_phrases")
SKILL_FILE = "SKILL.md"
CONTRACT_CHARS = 8000
#: The compact catalog that ships in the package. It is the same shape a person's own
#: catalog has, so one reader serves both.
ASSET = Path(__file__).resolve().parent / "assets" / "skills-catalog.json"
#: A ``skills.paths`` entry may be the folder of skills itself, or a parent folder that
#: keeps them here — the shape this workspace uses, and the one agent clients install to.
NESTED = (Path(".agents") / "skills",)
#: Bounds, so a folder pointed at by mistake cannot make a turn walk a whole disk.
MAX_ROOTS = 16
MAX_SCANNED = 5000
ON_DISK = "On disk (not in the reviewed catalog)"
SHIPPED = "the catalog that ships with Oneiro"


class CatalogError(RuntimeError):
    """The catalog or one of its contracts cannot be read; the message says which."""


@dataclass(frozen=True)
class Hit:
    """One catalog candidate, with the provenance needed to judge it."""

    name: str          # "browser" or "browser/parts/stealth"
    score: int
    confidence: str    # the semantic review's confidence, or "n/a"
    status: str        # Active / Uncertain / Candidate-non-relevant / On disk …
    path: str
    kind: str          # router | part
    purpose: str

    def line(self) -> str:
        purpose = " ".join(self.purpose.split())
        if len(purpose) > 200:
            purpose = purpose[:197] + "..."
        return (f"{self.name}  (match {self.score}, review {self.confidence}, "
                f"{self.status})\n    {purpose}")

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "score": self.score, "confidence": self.confidence,
                "status": self.status, "path": self.path, "kind": self.kind,
                "purpose": self.purpose}


@dataclass
class Root:
    """One folder skills are looked for in, and what reading it found.

    A root that is not there is normal — a fresh install has no skills folder yet — so it
    is reported rather than treated as a failure. A root that *is* there and cannot be
    read is a problem, and a problem that is not named is one the owner cannot fix: the
    scan writes it back onto the root it belongs to.
    """

    path: Path
    named_by: str
    exists: bool
    problem: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"path": str(self.path), "named_by": self.named_by, "exists": self.exists,
                "problem": self.problem}


@dataclass
class Catalog:
    """The reviewed skill index, plus the contracts the folders hold."""

    records: list[dict[str, Any]]
    path: Path
    origin: str
    roots: list[Root] = field(default_factory=list)
    contracts: dict[str, Path] = field(default_factory=dict)
    scanned: int = 0
    truncated: bool = False

    def __post_init__(self) -> None:
        self._by_name: dict[str, dict[str, Any]] = {}
        for record in self.records:
            parent = self._index(record)
            for part in record.get("parts") or []:
                self._index(part, parent=parent)

    def _index(self, record: dict[str, Any], parent: str = "") -> str:
        """Index one record under the name a caller addresses it by."""
        name = str(record.get("name") or "").strip()
        if not name:
            return ""
        key = f"{parent}/parts/{name}" if parent else name
        self._by_name[key] = record
        return key

    def absorb(self, entries: list[dict[str, Any]]) -> int:
        """Take the entries the reviewed catalog does not know, and count them.

        A name the catalog already has keeps its review, because the review is the reason
        the catalog exists; a name only the folders have becomes an entry of its own, with
        the honesty its status carries.
        """
        added = 0
        for entry in entries:
            name = str(entry.get("name") or "")
            if not name or name in self._by_name:
                continue
            self._by_name[name] = entry
            added += 1
        return added

    @property
    def size(self) -> int:
        """Contracts addressable by name: routers, their parts, and disk-only entries."""
        return len(self._by_name)

    @property
    def parts(self) -> int:
        return sum(len(record.get("parts") or []) for record in self.records)

    def names(self) -> list[str]:
        return sorted(self._by_name)

    # -- ranking --

    def search(self, query: str, limit: int = 4) -> list[Hit]:
        """Rank the catalog against a natural-language query.

        The arithmetic is the migrated one, reproduced exactly: three points for a term
        that is a curated keyword, two for a term a curated trigger phrase contains, one
        for a term anywhere in the reviewed text.
        """
        terms = [term for term in TERM_RE.findall(str(query).lower()) if term]
        if not terms:
            return []
        scored: list[tuple[int, str, Hit]] = []
        for name, record in self._by_name.items():
            semantic = record.get("semantic") or {}
            blob = " ".join(str(record.get("purpose") or "").lower().split())
            blob += " " + " ".join(
                str(item).lower()
                for reviewed in FIELDS for item in (semantic.get(reviewed) or []))
            score = 0
            for term in terms:
                if term in (semantic.get("keywords") or []):
                    score += 3
                elif any(term in str(value).lower()
                         for value in (semantic.get("trigger_phrases") or [])):
                    score += 2
                elif term in blob:
                    score += 1
            if not score:
                continue
            scored.append((score, name, Hit(
                name=name, score=score,
                confidence=str((semantic.get("review") or {}).get("confidence") or "n/a"),
                status=str(record.get("status") or "unknown"),
                path=str(self.contracts.get(name) or record.get("path") or ""),
                kind="part" if "/parts/" in name else "router",
                purpose=str(record.get("purpose") or ""))))
        # Ties break on the name, so two runs of the same query cannot differ.
        scored.sort(key=lambda row: (-row[0], row[1]))
        return [hit for _, _, hit in scored[:max(1, int(limit))]]

    # -- contracts --

    def contract_path(self, name: str) -> Path:
        """Where one contract lives, or a refusal naming everywhere it was looked for."""
        key = str(name).strip()
        record = self._by_name.get(key)
        if record is None:
            raise CatalogError(f"no such skill in the catalog: {key}")
        found = self.contracts.get(key)
        if found is not None and found.is_file():
            return found
        raw = str(record.get("path") or "")
        looked: list[str] = []
        for root in [row.path for row in self.roots if row.exists]:
            for candidate in ([root / raw] if raw else []) + [root / key / SKILL_FILE]:
                looked.append(str(candidate))
                if candidate.is_file():
                    return candidate
        if not looked:
            raise CatalogError(
                f"the catalog points at a missing file for {key}: there is no skill folder "
                f"to read it from. Install skills in {default_root()} or name folders in "
                f"skills.paths")
        raise CatalogError(f"the catalog points at a missing file for {key}; looked in "
                           f"{', '.join(looked)}")

    def contract(self, name: str, chars: int = CONTRACT_CHARS) -> str:
        """The contract itself, bounded, with an honest note when it is cut."""
        path = self.contract_path(name)
        text = path.read_text(encoding="utf-8", errors="replace")
        limit = max(500, int(chars or CONTRACT_CHARS))
        note = ""
        if len(text) > limit:
            note = (f"\n... [{len(text) - limit} characters of this contract "
                    f"were not shown; call read_skill again with a larger chars "
                    f"value if the part you need is below]")
            text = text[:limit]
        return f"{name} ({path})\n\n{text}{note}"

    def describe(self) -> dict[str, Any]:
        """What the surface shows: where the catalog came from and what is readable."""
        return {"catalog": str(self.path), "catalog_source": self.origin,
                "skills": self.size, "routes": len(self.records), "parts": self.parts,
                "on_disk": self.scanned, "contracts_in_hand": len(self.contracts),
                "truncated": self.truncated,
                "roots": [root.to_dict() for root in self.roots],
                "problems": [root.problem for root in self.roots if root.problem]}


# ---------- where the catalog and the contracts come from ----------


def _declared_catalog() -> tuple[Path, str]:
    """The catalog file to read, and where that choice came from."""
    chosen = str(config.value("skills.catalog") or "").strip()
    if chosen:
        return Path(chosen).expanduser(), "your own file (skills.catalog)"
    return ASSET, SHIPPED


def default_root() -> Path:
    """The product's own skills folder: where a skill is installed to be found."""
    return Path(config.data_root()) / "skills"


def declared_roots() -> list[Root]:
    """The folders skills are looked for in, in the order they are searched.

    The product's own folder comes first, then every ``skills.paths`` entry. An entry
    that is a parent folder keeping its skills under ``.agents/skills`` is recognised as
    such, and both are searched — a person should not have to know which spelling this
    build wants.
    """
    named: list[tuple[Path, str]] = [(default_root(), "the product's own folder")]
    entries = config.value("skills.paths") or []
    if isinstance(entries, list):
        for entry in entries:
            base = Path(str(entry)).expanduser()
            named.append((base, "skills.paths"))
            for nested in NESTED:
                if (base / nested).is_dir():
                    named.append((base / nested, f"skills.paths (its {nested.as_posix()})"))
    unique: list[tuple[Path, str]] = []
    for path, named_by in named:
        if all(path != seen for seen, _ in unique):
            unique.append((path, named_by))
    return [_probe(path, named_by) for path, named_by in unique[:MAX_ROOTS]]


def _probe(path: Path, named_by: str) -> Root:
    """What a root is, without reading it: there, or not there."""
    try:
        return Root(path, named_by, path.is_dir())
    except OSError as exc:                    # an unreadable parent, an odd network path
        return Root(path, named_by, False,
                    f"{path} ({named_by}) cannot be read: {exc.strerror or exc}")


def _head_of(path: Path, chars: int = 4000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:chars]
    except OSError:
        return ""


def _front_matter(text: str) -> dict[str, str]:
    """The ``name``/``description`` a skill file declares about itself, if it does."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not match:
        return {}
    found: dict[str, str] = {}
    for line in match.group(1).splitlines():
        name, _, value = line.partition(":")
        if value.strip():
            found[name.strip().lower()] = value.strip().strip('"').strip("'")
    return found


def _entry_from_disk(name: str, relative: Path, path: Path) -> dict[str, Any]:
    """A searchable entry for a skill the reviewed catalog does not know.

    Nothing is invented for it: the description it declares about itself stands in for the
    review it never had, and ``status`` says out loud that it was not reviewed.
    """
    text = _head_of(path)
    purpose = _front_matter(text).get("description", "").strip()
    if not purpose:
        heading = re.search(r"^#\s+(.+)$", text, re.M)
        purpose = heading.group(1).strip() if heading else ""
    return {"name": name, "path": relative.as_posix(), "purpose": purpose, "status": ON_DISK,
            "semantic": {"use_cases": [], "keywords": [],
                         "trigger_phrases": [purpose] if purpose else [],
                         "review": {"confidence": "n/a"}},
            "parts": []}


def _scan(roots: list[Root]) -> tuple[dict[str, Path], list[dict[str, Any]], int, bool]:
    """Walk the skill folders: by name, the disk entries, how many, and whether it stopped.

    The walk is shallow on purpose — ``<skill>/SKILL.md`` and
    ``<skill>/parts/<part>/SKILL.md`` is the shape a catalog addresses — and bounded, so a
    mistyped path cannot cost a turn the whole disk. A folder that cannot be listed is
    recorded as its own problem rather than skipped in silence.
    """
    contracts: dict[str, Path] = {}
    entries: list[dict[str, Any]] = []
    seen = 0
    truncated = False
    for root in roots:
        if not root.exists:
            continue
        try:
            folders = sorted(item for item in root.path.iterdir() if item.is_dir())
        except OSError as exc:
            root.problem = f"{root.path} could not be listed: {exc.strerror or exc}"
            continue
        for folder in folders:
            candidates = [(folder.name, folder)]
            parts = folder / "parts"
            if parts.is_dir():
                try:
                    candidates += [(f"{folder.name}/parts/{part.name}", part)
                                   for part in sorted(parts.iterdir()) if part.is_dir()]
                except OSError:
                    pass                       # the router is still usable on its own
            for name, where in candidates:
                contract = where / SKILL_FILE
                try:
                    if not contract.is_file():
                        continue
                except OSError:
                    continue
                seen += 1
                if seen > MAX_SCANNED:
                    return contracts, entries, seen - 1, True
                contracts[name] = contract
                entries.append(_entry_from_disk(name, contract.relative_to(root.path),
                                                contract))
    return contracts, entries, seen, truncated


def _read_records(path: Path) -> list[dict[str, Any]]:
    """The records in a catalog file, or a refusal saying what is wrong with it."""
    if not path.exists():
        raise CatalogError(f"the skill catalog is not there: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CatalogError(f"the skill catalog is not valid JSON: {path} ({exc})") from None
    except OSError as exc:
        raise CatalogError(f"the skill catalog could not be read: {path} "
                           f"({exc.strerror or exc})") from None
    records = raw.get("skills") if isinstance(raw, dict) else raw
    if not isinstance(records, list) or not records:
        raise CatalogError(f"the skill catalog has no records: {path}")
    return [record for record in records if isinstance(record, dict)]


_CACHE: dict[str, Any] = {"key": None, "catalog": None}


def _stamp(path: Path) -> tuple[int, int] | None:
    try:
        found = path.stat()
    except OSError:
        return None
    return (found.st_mtime_ns, found.st_size)


def load(*, catalog_path: Path | None = None, roots: list[Root] | None = None,
         cached: bool = True) -> Catalog:
    """Read the catalog and index the skill folders beside it.

    Raises :class:`CatalogError` with the reason when the catalog is not there, is not
    valid JSON or has no records. The result is cached until the catalog file or the set
    of folders changes, because the shipped asset is a few hundred kilobytes and a turn
    must not re-read it to ask one question.
    """
    if catalog_path is None:
        path, origin = _declared_catalog()
    else:
        path, origin = Path(catalog_path), "the catalog given to load()"
    chosen = declared_roots() if roots is None else list(roots)
    key = (str(path), _stamp(path), tuple((str(row.path), row.exists) for row in chosen))
    if cached and _CACHE["key"] == key:
        return _CACHE["catalog"]
    records = _read_records(path)
    contracts, entries, scanned, truncated = _scan(chosen)
    catalog = Catalog(records, path, origin, chosen, contracts, scanned, truncated)
    catalog.absorb(entries)
    if cached:
        _CACHE["key"] = key
        _CACHE["catalog"] = catalog
    return catalog


# ---------- what the surface shows ----------


def describe() -> dict[str, Any]:
    """The catalog, where it came from, the folders, and any named problem."""
    path, origin = _declared_catalog()
    try:
        return {**load().describe(), "error": ""}
    except CatalogError as exc:
        return {"error": str(exc), "catalog": str(path), "catalog_source": origin,
                "skills": 0, "routes": 0, "parts": 0, "on_disk": 0,
                "contracts_in_hand": 0, "truncated": False,
                "roots": [root.to_dict() for root in declared_roots()], "problems": []}


def search(query: str, limit: int = 4) -> dict[str, Any]:
    """Ranked candidates for a description, with a truthful note when there are none."""
    limit = max(1, int(limit or 4))
    catalog = load()
    hits = catalog.search(str(query), limit)
    return {"query": str(query), "limit": limit, "count": len(hits),
            "addressable": catalog.size, "skills": [hit.to_dict() for hit in hits],
            "note": ("" if hits else f"no catalog match for {query!r} in {catalog.size} "
                                     f"contracts; nothing ready-made covers this, so "
                                     f"solve it directly")}


def show(name: str, chars: int = CONTRACT_CHARS) -> dict[str, Any]:
    """One contract as text, or :class:`CatalogError` naming why there is none."""
    catalog = load()
    text = catalog.contract(str(name), int(chars or CONTRACT_CHARS))
    return {"name": str(name), "path": str(catalog.contract_path(str(name))),
            "text": text, "catalog": str(catalog.path)}


# ---------- the tools the agent is offered ----------


def render_search(catalog: Catalog, query: str, limit: int = 4) -> str:
    """What the model reads after `find_skills`, in the migrated wording."""
    hits = catalog.search(query, limit)
    if not hits:
        return (f"No catalog match for {query!r} in {catalog.size} contracts. "
                f"Nothing ready-made covers this; solve it directly.")
    header = f"{len(hits)} of {catalog.size} contracts, best first:"
    return header + "\n\n" + "\n\n".join(hit.line() for hit in hits)


def tool_definitions(catalog: Catalog) -> dict[str, Tool]:
    """The two skills tools, bound to one loaded catalog."""

    def find_skills(ctx: dict, args: dict) -> dict:
        limit = int(args.get("limit") or 4)
        return {"query": str(args["query"]), "limit": limit,
                "text": render_search(catalog, str(args["query"]), limit)}

    def read_skill(ctx: dict, args: dict) -> dict:
        try:
            text = catalog.contract(str(args["name"]), int(args.get("chars") or CONTRACT_CHARS))
        except CatalogError as exc:
            # A named refusal, recorded as a failed call: a skill that cannot be resolved
            # must never come back as an empty success the model can build on.
            raise ToolError(str(exc)) from None
        return {"name": str(args["name"]), "text": text}

    return {
        "find_skills": Tool(
            "find_skills",
            "Search the skill catalog for a ready-made procedure for this task (a "
            "contract that already says how to do it, what to avoid, and when not to use "
            "it). Returns ranked candidates with their review confidence. Use it before "
            "inventing an approach from scratch.",
            {"query": {"type": "string", "description": "what you need to do"},
             "limit": {"type": "integer",
                       "description": "how many candidates to show (default 4)"}},
            ("query",), ROLES, "read", find_skills),
        "read_skill": Tool(
            "read_skill",
            "Read the full contract of one catalog entry by the exact name find_skills "
            "returned (a router, or 'router/parts/part').",
            {"name": {"type": "string"},
             "chars": {"type": "integer",
                       "description": "how much of it to read (default 8000)"}},
            ("name",), ROLES, "read", read_skill),
    }


def registry() -> dict[str, Tool]:
    """The skills tools for this runtime, or none when the catalog cannot be read.

    A capability that cannot run is not offered — the rule ``tools.py`` states for every
    tool here — and the reason it is absent is named on this module's own surface
    (:func:`describe`) rather than hidden from the owner.
    """
    try:
        catalog = load()
    except CatalogError:
        return {}
    return tool_definitions(catalog)


def evidence(actions: list[dict[str, Any]], catalog: Catalog | None) -> dict[str, Any]:
    """What the catalog gave an episode, and what it cost to ask.

    Kept from the migrated module, because the question it answers — was looking in the
    catalog worth its own tokens? — is the one thing about skills that can be measured.
    """
    lookups = [row for row in actions if row.get("tool") == "find_skills"]
    reads = [row for row in actions if row.get("tool") == "read_skill"]
    chars = sum(len(str(row.get("observation") or "")) for row in lookups + reads)
    return {
        "available": catalog is not None,
        "contracts": catalog.size if catalog is not None else 0,
        "lookups": len(lookups),
        "contracts_read": len(reads),
        "observation_chars": chars,
        "queries": [str((row.get("args") or {}).get("query") or "")[:120] for row in lookups],
        "read": [str((row.get("args") or {}).get("name") or "")[:120] for row in reads],
    }


# ---------- the HTTP surface ----------


def add_routes(app: FastAPI) -> None:
    """The skills routes, added to the application by `web.create_app`.

    Read-only: searching a catalog and reading a contract change nothing, so no route here
    writes and none of them needs the runtime.
    """

    @app.get("/api/skills")
    async def skills_overview() -> JSONResponse:
        payload = describe()
        return JSONResponse(payload, status_code=503 if payload["error"] else 200)

    # Declared before the catch-all below, so "search" is an action and not a skill name.
    @app.get("/api/skills/search")
    async def skills_search(q: str = "", limit: int = 4) -> JSONResponse:
        if not q.strip():
            return JSONResponse({"error": "q must be a non-empty search description"},
                                status_code=400)
        try:
            return JSONResponse(search(q, min(max(limit, 1), 20)))
        except CatalogError as exc:
            return JSONResponse({"error": str(exc)}, status_code=503)

    @app.get("/api/skills/{name:path}")
    async def skills_show(name: str, chars: int = CONTRACT_CHARS) -> JSONResponse:
        if not name.strip():
            return JSONResponse({"error": "a skill name is required"}, status_code=400)
        try:
            return JSONResponse(show(name, chars))
        except CatalogError as exc:
            return JSONResponse({"error": str(exc), "name": name}, status_code=404)


# ---------- the command line ----------


def _say(line: str = "") -> None:
    print(line, flush=True)


def skills_command(argv: list[str]) -> int:
    """`oneiro skills` — what is in the catalog, a search, and one contract."""
    parser = argparse.ArgumentParser(prog="oneiro skills",
                                     description="Skills: list, search, show")
    parser.add_argument("action", nargs="?", default="list",
                        choices=("list", "search", "show"))
    parser.add_argument("value", nargs="?", default="",
                        help="the description to search for, or the skill's exact name")
    parser.add_argument("--limit", type=int, default=4, help="search: how many candidates")
    parser.add_argument("--chars", type=int, default=CONTRACT_CHARS,
                        help="show: how much of the contract to read")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if args.action == "list":
        payload = describe()
        if args.json:
            _say(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        else:
            _print_overview(payload)
        return 1 if payload["error"] else 0
    if args.action == "search":
        if not args.value.strip():
            _say("error: a description is required, e.g. "
                 "oneiro skills search \"take a screenshot of a page\"")
            return 2
        return _print_search(args)
    if not args.value.strip():
        _say("error: a skill name is required, e.g. oneiro skills show find-skills")
        return 2
    return _print_contract(args)


def _print_overview(payload: dict[str, Any]) -> None:
    if payload["error"]:
        _say(f"error: {payload['error']}")
    else:
        _say(f"catalog: {payload['catalog']} ({payload['catalog_source']})")
        _say(f"contracts: {payload['skills']} addressable "
             f"({payload['routes']} in the catalog, {payload['parts']} parts, "
             f"{payload['on_disk']} found in the folders)")
        if payload["truncated"]:
            _say("note: the folders hold more contracts than this build walks; the first "
                 "ones are indexed")
    for root in payload["roots"]:
        state = "there" if root["exists"] else "not there"
        _say(f"  folder: {root['path']}  [{root['named_by']}, {state}]")
        if root["problem"]:
            _say(f"    problem: {root['problem']}")


def _print_search(args: argparse.Namespace) -> int:
    try:
        payload = search(args.value, args.limit)
    except CatalogError as exc:
        _say(f"error: {exc}")
        return 1
    if args.json:
        _say(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0
    if not payload["skills"]:
        _say(payload["note"])
        return 0
    _say(f"{payload['count']} of {payload['addressable']} contracts, best first:")
    for row in payload["skills"]:
        _say(f"  {row['name']}  (match {row['score']}, review {row['confidence']}, "
             f"{row['status']})")
    return 0


def _print_contract(args: argparse.Namespace) -> int:
    try:
        payload = show(args.value, args.chars)
    except CatalogError as exc:
        _say(f"error: {exc}")
        return 2
    if args.json:
        _say(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0
    _say(payload["text"])
    return 0


def main(argv: list[str] | None = None) -> int:
    """Used by the tests and by `python -m oneiro.skills`."""
    try:
        return skills_command(list(argv if argv is not None else sys.argv[1:]))
    except BrokenPipeError:                 # a closed pipe is not an error worth a traceback
        return 0
