"""Build the compact skill catalog the product ships, from the reviewed workspace one.

The product does not ship `knowledge/wiki/skills-catalog.json` (693 KB, with
review evidence, membership and provenance that no module reads). It ships the
part of it `oneiro/skills.py` reads: where each skill's contract lives, what it
is for, its reviewed keywords, and the review's confidence — so a search and a
refusal can both be answered on a machine that never had the workspace.

Run from anywhere:  python scripts/build-skills-asset.py [SOURCE] [DEST]

Only the fields listed in `RECORD_FIELDS`/`SEMANTIC_FIELDS` travel; the source's
`reason`, evidence, membership and review prose stay in the workspace, where the
document that explains them lives. `skills.py` reads nothing else, and
`tests/test_skills.py` fails if that stops being true.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REL = Path("knowledge") / "wiki" / "skills-catalog.json"
DEFAULT_DEST = ROOT / "python" / "oneiro" / "assets" / "skills-catalog.json"

SCHEMA = "oneiro-skills-catalog/v1"
SKILL_FILE = "SKILL.md"
SEMANTIC_FIELDS = ("use_cases", "keywords", "trigger_phrases")
RECORD_FIELDS = ("name", "path", "purpose", "status")


def default_source() -> Path | None:
    """The reviewed catalog above this checkout, wherever it sits.

    The source is the workspace's own file, not this repository's: the asset is a
    build-time derivation from it, so the path is found rather than compiled in and
    the script says what it looked for when it is not there.
    """
    for parent in [ROOT, *ROOT.parents]:
        if (parent / SOURCE_REL).exists():
            return parent / SOURCE_REL
    return None


def compact_semantic(raw: Any) -> dict[str, Any]:
    """The reviewed semantics, minus the prose nothing reads."""
    semantic = raw if isinstance(raw, dict) else {}
    review = semantic.get("review") if isinstance(semantic.get("review"), dict) else {}
    return {
        **{field: list(semantic.get(field) or []) for field in SEMANTIC_FIELDS},
        "review": {"confidence": str(review.get("confidence") or "n/a")},
    }


def compact_record(raw: dict[str, Any], *, name: str, path: Path) -> dict[str, Any]:
    """One skill, with its contract path made relative to a skill folder."""
    return {"name": name, "path": path.as_posix(), "purpose": str(raw.get("purpose") or ""),
            "status": str(raw.get("status") or "unknown"),
            "semantic": compact_semantic(raw.get("semantic"))}


def build(source: Path) -> dict[str, Any]:
    raw = json.loads(source.read_text(encoding="utf-8"))
    records = raw.get("skills") if isinstance(raw, dict) else raw
    if not isinstance(records, list) or not records:
        raise SystemExit(f"the source catalog has no records: {source}")
    skills: list[dict[str, Any]] = []
    parts = 0
    for record in records:
        name = str(record.get("name") or "").strip()
        if not name:
            continue
        entry = compact_record(record, name=name, path=Path(name) / SKILL_FILE)
        entry["parts"] = []
        for part in record.get("parts") or []:
            part_name = str(part.get("name") or "").strip()
            if not part_name:
                continue
            entry["parts"].append(compact_record(
                part, name=part_name,
                path=Path(name) / "parts" / part_name / SKILL_FILE))
            parts += 1
        skills.append(entry)
    return {
        "schema": SCHEMA,
        "source": SOURCE_REL.as_posix(),
        "source_schema": str(raw.get("schema") or "") if isinstance(raw, dict) else "",
        "source_bytes": source.stat().st_size,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "count": len(skills),
        "parts": parts,
        "note": ("Only what oneiro/skills.py reads: the contract path relative to a skill "
                 "folder, the purpose, the reviewed keywords and the review's confidence. "
                 "The review prose and the evidence graph stay in the workspace catalog "
                 "named above; regenerate with scripts/build-skills-asset.py."),
        "skills": skills,
    }


def main(argv: list[str]) -> int:
    source = Path(argv[0]) if argv else default_source()
    dest = Path(argv[1]) if len(argv) > 1 else DEFAULT_DEST
    if source is None or not source.exists():
        print(f"error: no catalog to read; looked for {SOURCE_REL} above {ROOT}"
              + (f" and at {source}" if source is not None else ""))
        return 2
    payload = build(source)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Compact, because it is a derived machine asset: the script is the readable
    # form of it, and indentation would cost ~100 KB of the payload for nothing.
    dest.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
                    encoding="utf-8")
    print(f"source: {source} ({payload['source_bytes']} bytes, "
          f"schema {payload['source_schema']})")
    print(f"asset:  {dest} ({dest.stat().st_size} bytes, "
          f"{payload['count']} skills + {payload['parts']} parts)")
    print(f"kept fields: {', '.join(sorted(RECORD_FIELDS))} + "
          f"semantic.{'/'.join(SEMANTIC_FIELDS)} + review.confidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
