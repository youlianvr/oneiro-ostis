"""The skill catalog as a tool: same arithmetic as the skill, same contract file.

The catalog on this machine is real (101 routers plus 219 parts), so the tests
that read it are marked to fail loudly if it moves shape under us. Everything
else runs on a catalog written into tmp_path, so a broken workspace cannot make
the ranking arithmetic untested.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "python"))

import skills_index  # noqa: E402


def make_catalog(tmp_path: Path) -> Path:
    """A two-router catalog with one part, shaped like oper-skills-catalog/v2."""
    skills = tmp_path / ".agents" / "skills"
    (skills / "browser" / "parts" / "stealth").mkdir(parents=True)
    (skills / "telegram").mkdir(parents=True)
    (skills / "browser" / "SKILL.md").write_text("ROUTER BROWSER CONTRACT",
                                                 encoding="utf-8")
    (skills / "browser" / "parts" / "stealth" / "SKILL.md").write_text(
        "STEALTH PART CONTRACT", encoding="utf-8")
    (skills / "telegram" / "SKILL.md").write_text("TELEGRAM CONTRACT",
                                                  encoding="utf-8")
    catalog = {
        "schema": "oper-skills-catalog/v2",
        "skills": [
            {
                "name": "browser",
                "path": ".agents/skills/browser/SKILL.md",
                "purpose": "Automate a web browser: navigate, click, fill forms.",
                "status": "Active",
                "semantic": {
                    "use_cases": ["Drive a page like a person would."],
                    "keywords": ["browser", "automation"],
                    "trigger_phrases": ["open a website and click through it"],
                    "review": {"confidence": "high"},
                },
                "parts": [
                    {
                        "name": "stealth",
                        "path": ".agents/skills/browser/parts/stealth/SKILL.md",
                        "purpose": "Avoid bot detection while scraping.",
                        "status": "Uncertain",
                        "semantic": {
                            "use_cases": ["Scrape a protected page."],
                            "keywords": ["stealth", "scraping"],
                            "trigger_phrases": ["the site blocks my scraper"],
                            "review": {"confidence": "medium"},
                        },
                    }
                ],
            },
            {
                "name": "telegram",
                "path": ".agents/skills/telegram/SKILL.md",
                "purpose": "Send messages and files to a Telegram chat.",
                "status": "Active",
                "semantic": {
                    "use_cases": ["Deliver a report to a chat."],
                    "keywords": ["telegram", "messaging"],
                    "trigger_phrases": ["send this to the chat"],
                    "review": {"confidence": "high"},
                },
            },
        ],
    }
    path = tmp_path / skills_index.CATALOG_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog), encoding="utf-8")
    return path


@pytest.fixture()
def catalog(tmp_path: Path) -> skills_index.Catalog:
    make_catalog(tmp_path)
    return skills_index.load(workspace=tmp_path)


def test_keyword_hit_outweighs_a_mention_in_prose(catalog: skills_index.Catalog):
    """A curated keyword scores three, a term merely present in reviewed text one."""
    hits = catalog.search("browser automation")
    assert [h.name for h in hits][:1] == ["browser"]
    assert hits[0].score == 6                      # two keywords, three points each
    assert hits[0].confidence == "high"
    assert hits[0].kind == "router"


def test_parts_are_addressable_and_carry_their_own_review(catalog: skills_index.Catalog):
    hits = catalog.search("scraping a protected page")
    names = [h.name for h in hits]
    assert "browser/parts/stealth" in names
    part = next(h for h in hits if h.name == "browser/parts/stealth")
    assert part.kind == "part"
    assert part.confidence == "medium"
    assert part.status == "Uncertain"


def test_ranking_is_deterministic_and_ties_break_on_name(catalog: skills_index.Catalog):
    first = [(h.name, h.score) for h in catalog.search("telegram chat report", limit=3)]
    for _ in range(5):
        assert [(h.name, h.score) for h in catalog.search("telegram chat report",
                                                          limit=3)] == first
    assert first == sorted(first, key=lambda row: (-row[1], row[0]))


def test_a_query_of_short_words_returns_nothing(catalog: skills_index.Catalog):
    assert catalog.search("to be or not") == []


def test_no_match_says_so_instead_of_inventing_one(catalog: skills_index.Catalog):
    text = skills_index.render_search(catalog, "quantum chromodynamics lecture")
    assert text.startswith("No catalog match")
    assert "solve it directly" in text


def test_a_contract_is_the_same_file_a_person_would_open(catalog: skills_index.Catalog):
    assert "TELEGRAM CONTRACT" in catalog.contract("telegram")
    assert "STEALTH PART CONTRACT" in catalog.contract("browser/parts/stealth")
    assert str(catalog.path).endswith("skills-catalog.json")


def test_a_long_contract_is_cut_with_an_honest_note(catalog: skills_index.Catalog):
    text = catalog.contract("telegram", chars=500)
    assert text.startswith("telegram (")
    assert "[0 characters of this contract" not in text    # it is short, not truncated
    long_text = catalog.contract("telegram", chars=500)     # bound is respected
    assert len(long_text) < 1000


def test_an_unknown_name_is_refused_by_name(catalog: skills_index.Catalog):
    with pytest.raises(skills_index.CatalogError):
        catalog.contract("no-such-skill")


def test_a_catalog_that_points_at_a_missing_file_says_that(tmp_path: Path):
    make_catalog(tmp_path)
    (tmp_path / ".agents" / "skills" / "telegram" / "SKILL.md").unlink()
    catalog = skills_index.load(workspace=tmp_path)
    with pytest.raises(skills_index.CatalogError) as excinfo:
        catalog.contract("telegram")
    assert "missing file" in str(excinfo.value)


def test_a_missing_catalog_is_an_error_not_an_empty_success(tmp_path: Path):
    with pytest.raises(skills_index.CatalogError):
        skills_index.load(workspace=tmp_path, catalog_path=tmp_path / "nope.json")


def test_broken_json_is_reported_as_broken(tmp_path: Path):
    path = tmp_path / "catalog.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(skills_index.CatalogError):
        skills_index.load(workspace=tmp_path, catalog_path=path)


def test_evidence_counts_lookups_and_characters():
    actions = [
        {"tool": "find_skills", "args": {"query": "browser"}, "observation": "x" * 100},
        {"tool": "read_skill", "args": {"name": "browser"}, "observation": "y" * 50},
        {"tool": "read_file", "args": {"path": "a.py"}, "observation": "z" * 900},
    ]
    evidence = skills_index.evidence(actions, None)
    assert evidence == {
        "available": False, "contracts": 0, "lookups": 1, "contracts_read": 1,
        "observation_chars": 150, "queries": ["browser"], "read": ["browser"],
    }


def test_the_two_tool_schemas_are_openai_shaped():
    names = {schema["function"]["name"] for schema in skills_index.TOOL_SCHEMAS}
    assert names == {"find_skills", "read_skill"}
    for schema in skills_index.TOOL_SCHEMAS:
        function = schema["function"]
        assert schema["type"] == "function"
        assert schema["type"] == "function" and function["description"]
        assert function["parameters"]["type"] == "object"
        assert function["parameters"]["required"]


# -- against the catalog that is actually on this machine --


def test_the_real_catalog_ranks_the_skill_whose_job_it_is():
    catalog = skills_index.load()
    assert catalog.size > 100
    top = [h.name for h in catalog.search("browse the web and take a screenshot", limit=5)]
    assert any(name.startswith("browser") for name in top)
    top = [h.name for h in catalog.search("send a message to telegram", limit=5)]
    assert any("telegram" in name for name in top)


def test_the_real_catalog_opens_a_real_contract():
    catalog = skills_index.load()
    text = catalog.contract("find-skills", chars=1200)
    assert "Find Skills" in text
