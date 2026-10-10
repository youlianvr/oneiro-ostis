"""Skills inside the product: the migrated ranking, the catalog, the folders, and the tools.

Two halves, deliberately. The arithmetic and the contract reader are the migrated
`python/skills_index.py` behaviour, asserted against the same fixtures the old module's
tests used, plus **parity in one direction that matters**: for a fixed query set the new
module must rank the real catalog exactly as the module it came from does, because that
ranking is what `find-skills` promises and what makes "was the lookup worth it?" a
measured question rather than an opinion.

The other half is what § 5 W3 added to a standalone module: a catalog that travels with
the product, folders that are really searched, and refusals that name what failed. A test
of the test closes the loop on the settings: `skills.catalog` and `skills.paths` are in
force here *because* changing them changes what is found — the flags are checked too, but
the behaviour is the evidence (`tests/test_settings_honesty.py` holds the other
direction, that no key claims an effect nothing reads).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from oneiro import config, skills, web                                    # noqa: E402
from oneiro.runtime import Runtime                                        # noqa: E402
from oneiro.tools import ROLES, ToolError                                 # noqa: E402
from chat_fakes import GraphStub, MemoryLinks, isolate                    # noqa: E402

PROJECT = Path(__file__).resolve().parents[1]
SOURCE_CATALOG_REL = Path("knowledge") / "wiki" / "skills-catalog.json"


# ---------- the fixtures: a catalog and the folders it points at ----------


def write_catalog(tmp_path: Path) -> Path:
    """A two-router catalog with one part, in the shape the product ships."""
    folders = tmp_path / "skills"
    (folders / "browser" / "parts" / "stealth").mkdir(parents=True)
    (folders / "telegram").mkdir(parents=True)
    (folders / "browser" / "SKILL.md").write_text("ROUTER BROWSER CONTRACT", encoding="utf-8")
    (folders / "browser" / "parts" / "stealth" / "SKILL.md").write_text(
        "STEALTH PART CONTRACT", encoding="utf-8")
    (folders / "telegram" / "SKILL.md").write_text("TELEGRAM CONTRACT", encoding="utf-8")
    catalog = {
        "schema": "oneiro-skills-catalog/v1",
        "skills": [
            {"name": "browser", "path": "browser/SKILL.md",
             "purpose": "Automate a web browser: navigate, click, fill forms.",
             "status": "Active",
             "semantic": {"use_cases": ["Drive a page like a person would."],
                          "keywords": ["browser", "automation"],
                          "trigger_phrases": ["open a website and click through it"],
                          "review": {"confidence": "high"}},
             "parts": [
                 {"name": "stealth", "path": "browser/parts/stealth/SKILL.md",
                  "purpose": "Avoid bot detection while scraping.", "status": "Uncertain",
                  "semantic": {"use_cases": ["Scrape a protected page."],
                               "keywords": ["stealth", "scraping"],
                               "trigger_phrases": ["the site blocks my scraper"],
                               "review": {"confidence": "medium"}}}]},
            {"name": "telegram", "path": "telegram/SKILL.md",
             "purpose": "Send messages and files to a Telegram chat.",
             "status": "Active",
             "semantic": {"use_cases": ["Deliver a report to a chat."],
                          "keywords": ["telegram", "messaging"],
                          "trigger_phrases": ["send this to the chat"],
                          "review": {"confidence": "high"}}},
        ],
    }
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    return path


def folders(tmp_path: Path) -> list[skills.Root]:
    return [skills.Root(tmp_path / "skills", "the test's own folder", True)]


@pytest.fixture(autouse=True)
def fresh_cache():
    """No test sees another test's catalog: the cache is keyed, and this makes it certain."""
    skills._CACHE.update(key=None, catalog=None)
    yield
    skills._CACHE.update(key=None, catalog=None)


@pytest.fixture()
def catalog(tmp_path: Path) -> skills.Catalog:
    path = write_catalog(tmp_path)
    return skills.load(catalog_path=path, roots=folders(tmp_path), cached=False)


# ---------- the migrated arithmetic ----------


def test_keyword_hit_outweighs_a_mention_in_prose(catalog: skills.Catalog):
    """A curated keyword scores three, a term merely present in reviewed text one."""
    hits = catalog.search("browser automation")
    assert [hit.name for hit in hits][:1] == ["browser"]
    assert hits[0].score == 6                      # two keywords, three points each
    assert hits[0].confidence == "high"
    assert hits[0].kind == "router"


def test_parts_are_addressable_and_carry_their_own_review(catalog: skills.Catalog):
    hits = catalog.search("scraping a protected page")
    names = [hit.name for hit in hits]
    assert "browser/parts/stealth" in names
    part = next(hit for hit in hits if hit.name == "browser/parts/stealth")
    assert part.kind == "part"
    assert part.confidence == "medium"
    assert part.status == "Uncertain"


def test_ranking_is_deterministic_and_ties_break_on_name(catalog: skills.Catalog):
    first = [(hit.name, hit.score) for hit in catalog.search("telegram chat report", limit=3)]
    for _ in range(5):
        assert [(hit.name, hit.score)
                for hit in catalog.search("telegram chat report", limit=3)] == first
    assert first == sorted(first, key=lambda row: (-row[1], row[0]))


def test_a_query_of_short_words_returns_nothing(catalog: skills.Catalog):
    assert catalog.search("to be or not") == []


def test_no_match_says_so_instead_of_inventing_one(catalog: skills.Catalog):
    text = skills.render_search(catalog, "quantum chromodynamics lecture")
    assert text.startswith("No catalog match")
    assert "solve it directly" in text


def test_a_contract_is_the_same_file_a_person_would_open(catalog: skills.Catalog):
    assert "TELEGRAM CONTRACT" in catalog.contract("telegram")
    assert "STEALTH PART CONTRACT" in catalog.contract("browser/parts/stealth")
    assert str(catalog.path).endswith("catalog.json")


def test_a_long_contract_is_cut_with_an_honest_note(catalog: skills.Catalog):
    text = catalog.contract("telegram", chars=500)
    assert text.startswith("telegram (")
    assert "[0 characters of this contract" not in text    # it is short, not truncated
    long_text = catalog.contract("telegram", chars=500)     # the bound is respected
    assert len(long_text) < 1000


def test_the_shipped_asset_ranks_the_reviewed_catalog_identically():
    """§ 6 row 7's parity half, now that the reference module is retired.

    W3 proved the migration by ranking the reviewed workspace catalog with the old
    `skills_index` module and with `oneiro.skills` and comparing the two. W9 retired
    that module, so the comparison that survives — and is stronger for the shipped
    artifact — is between the **compact asset inside the package** and the **reviewed
    catalog the builder wrote it from**: the compaction must cost no ranking at all.
    """
    source = _real_catalog()
    shipped = skills.load(catalog_path=skills.ASSET, roots=[], cached=False)
    reviewed = skills.load(catalog_path=source, roots=[], cached=False)
    assert shipped.size == reviewed.size > 0, "the asset must carry every reviewed record"

    queries = [
        "take a screenshot of a page", "browse the web and click through it",
        "send a message to telegram", "write a defensive bash script",
        "audit accessibility with wcag", "scrape a protected site", "design a landing page",
        "review a pull request", "build an mcp server", "transcribe an audio file",
        "generate a pdf report", "optimise a slow database query", "draw a diagram",
        "summarise a long document", "test a web app in a browser", "edit a spreadsheet",
        "create a slide deck", "refactor legacy code", "browser automation", "screenshot",
        "to be or not", "invoice a customer", "set up a database migration",
    ]
    for query in queries:
        from_shipped = [(hit.name, hit.score) for hit in shipped.search(query, 5)]
        from_reviewed = [(hit.name, hit.score) for hit in reviewed.search(query, 5)]
        assert from_shipped == from_reviewed, f"'{query}' ranks differently in the asset"
        assert len(from_reviewed) > 0, f"Query '{query}' must yield matches"
        assert all(score > 0 for _, score in from_reviewed), \
            f"All hits for '{query}' must have positive score"


# ---------- the shipped catalog and the folders ----------


def _real_catalog() -> Path:
    """The reviewed workspace catalog, found above this checkout."""
    for parent in [PROJECT, *PROJECT.parents]:
        candidate = parent / SOURCE_CATALOG_REL
        if candidate.is_file():
            return candidate
    pytest.skip(f"no reviewed catalog at {SOURCE_CATALOG_REL} above {PROJECT}")


def test_the_shipped_catalog_is_what_an_empty_skills_catalog_means(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    payload = skills.describe()
    assert payload["error"] == ""
    assert payload["catalog"] == str(skills.ASSET)
    assert payload["catalog_source"] == skills.SHIPPED
    assert Path(payload["catalog"]).is_file(), "the asset must travel inside the package"
    assert payload["skills"] > 100 and payload["parts"] > 100
    assert payload["on_disk"] == 0, "a fresh install has no skill folders yet"
    assert skills.ASSET.stat().st_size < 512_000, "the asset is meant to be compact"


def test_the_shipped_asset_carries_only_what_the_module_reads():
    """The asset is compact because nothing dead travels in it: assert the field set."""
    raw = json.loads(skills.ASSET.read_text(encoding="utf-8"))
    assert raw["schema"] == "oneiro-skills-catalog/v1"
    assert raw["source"].endswith("skills-catalog.json") and len(raw["source_sha256"]) == 64
    assert raw["count"] == len(raw["skills"])
    for record in raw["skills"]:
        assert set(record) == {"name", "path", "purpose", "status", "semantic", "parts"}
        assert set(record["semantic"]) == {"use_cases", "keywords", "trigger_phrases", "review"}
        assert set(record["semantic"]["review"]) == {"confidence"}
        assert record["path"] == f"{record['name']}/SKILL.md"
        for part in record["parts"]:
            assert set(part) == {"name", "path", "purpose", "status", "semantic"}
            assert part["path"] == f"{record['name']}/parts/{part['name']}/SKILL.md"


def test_the_asset_is_what_the_builder_writes_from_the_reviewed_catalog(tmp_path: Path):
    """No silent drift: the shipped asset is regenerated here and compared."""
    builder = _load_builder()
    source = _real_catalog()
    rebuilt = builder.build(source)
    shipped = json.loads(skills.ASSET.read_text(encoding="utf-8"))
    # The timestamp is the one field that must differ, or a rebuild would never be equal.
    rebuilt.pop("generated_at")
    shipped.pop("generated_at")
    assert rebuilt == shipped, "run python scripts/build-skills-asset.py and ship the result"


def _load_builder():
    path = PROJECT / "scripts" / "build-skills-asset.py"
    spec = importlib.util.spec_from_file_location("build_skills_asset", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_folder_adds_a_skill_the_catalog_never_had(tmp_path: Path):
    """`skills.paths` promises folders that are *searched*, so a disk-only skill counts."""
    path = write_catalog(tmp_path)
    extra = tmp_path / "skills" / "house-style"
    extra.mkdir(parents=True)
    (extra / "SKILL.md").write_text(
        "---\nname: house-style\ndescription: Write release notes in the house style.\n---\n"
        "# House style\n", encoding="utf-8")
    loaded = skills.load(catalog_path=path, roots=folders(tmp_path), cached=False)

    hits = loaded.search("write release notes in the house style")
    assert [hit.name for hit in hits][:1] == ["house-style"]
    assert loaded.contracts["house-style"] == extra / "SKILL.md"
    assert "House style" in loaded.contract("house-style")
    # Its status says out loud that no review ever looked at it.
    assert hits[0].status == skills.ON_DISK and hits[0].confidence == "n/a"
    assert loaded.describe()["on_disk"] == 4, "three from the catalog, one only on disk"


def test_a_reviewed_name_keeps_its_review_when_a_folder_has_it_too(tmp_path: Path):
    path = write_catalog(tmp_path)
    loaded = skills.load(catalog_path=path, roots=folders(tmp_path), cached=False)
    hit = loaded.search("telegram messaging")[0]
    assert hit.name == "telegram" and hit.confidence == "high"
    assert loaded.describe()["skills"] == 3, "a known name is not counted twice"


def test_a_parent_folder_keeping_skills_under_agents_skills_is_recognised(tmp_path, monkeypatch):
    """A person names the folder they keep skills in, or its repository root."""
    isolate(tmp_path, monkeypatch)
    repository = tmp_path / "repo"
    (repository / ".agents" / "skills" / "packaging").mkdir(parents=True)
    (repository / ".agents" / "skills" / "packaging" / "SKILL.md").write_text(
        "---\ndescription: Package a release and sign it.\n---\n", encoding="utf-8")
    monkeypatch.setenv("ONEIRO_SKILLS_PATHS", json.dumps([str(repository)]))
    payload = skills.describe()
    named = [root["named_by"] for root in payload["roots"]]
    assert "skills.paths" in named and any(".agents" in item for item in named)
    assert payload["contracts_in_hand"] == 1
    # The shipped catalog is in force too, so the test's own skill is judged by being
    # there, addressable and readable — not by outranking a reviewed one.
    hits = {row["name"]: row for row in skills.search("package a release", 8)["skills"]}
    assert "packaging" in hits and hits["packaging"]["status"] == skills.ON_DISK
    assert "Package a release and sign it." in skills.show("packaging")["text"]


def test_the_walk_is_bounded_and_says_when_it_stopped(tmp_path: Path, monkeypatch):
    path = write_catalog(tmp_path)
    monkeypatch.setattr(skills, "MAX_SCANNED", 1)
    loaded = skills.load(catalog_path=path, roots=folders(tmp_path), cached=False)
    assert loaded.truncated is True and loaded.scanned == 1


def test_a_folder_that_is_not_configured_is_reported_not_a_failure(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    payload = skills.describe()
    assert payload["error"] == "" and payload["roots"][0]["exists"] is False
    assert payload["roots"][0]["named_by"] == "the product's own folder"
    assert payload["roots"][0]["problem"] == "", "a fresh install is not a problem"


# ---------- refusals that name what failed ----------


def test_an_unknown_name_is_refused_by_name(catalog: skills.Catalog):
    with pytest.raises(skills.CatalogError) as excinfo:
        catalog.contract("no-such-skill")
    assert "no such skill in the catalog: no-such-skill" in str(excinfo.value)


def test_a_contract_that_is_not_on_disk_is_refused_with_where_it_looked(tmp_path: Path):
    write_catalog(tmp_path)
    (tmp_path / "skills" / "telegram" / "SKILL.md").unlink()
    loaded = skills.load(catalog_path=tmp_path / "catalog.json", roots=folders(tmp_path),
                         cached=False)
    with pytest.raises(skills.CatalogError) as excinfo:
        loaded.contract("telegram")
    message = str(excinfo.value)
    assert "missing file for telegram" in message
    assert str(tmp_path / "skills") in message, "the refusal names where it looked"


def test_a_missing_folder_is_named_in_the_refusal(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    with pytest.raises(skills.CatalogError) as excinfo:
        skills.show("find-skills")
    message = str(excinfo.value)
    assert "missing file for find-skills" in message
    assert "no skill folder" in message and "skills.paths" in message


def test_a_missing_catalog_is_an_error_not_an_empty_success(tmp_path: Path):
    with pytest.raises(skills.CatalogError):
        skills.load(catalog_path=tmp_path / "nope.json", roots=[], cached=False)


def test_broken_json_is_reported_as_broken(tmp_path: Path):
    path = tmp_path / "catalog.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(skills.CatalogError) as excinfo:
        skills.load(catalog_path=path, roots=[], cached=False)
    assert "not valid JSON" in str(excinfo.value)


def test_a_catalog_with_no_records_is_refused(tmp_path: Path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"schema": "oneiro-skills-catalog/v1", "skills": []}),
                    encoding="utf-8")
    with pytest.raises(skills.CatalogError) as excinfo:
        skills.load(catalog_path=path, roots=[], cached=False)
    assert "no records" in str(excinfo.value)


# ---------- the tools ----------


def test_the_two_tools_are_openai_shaped_and_read_only(catalog: skills.Catalog):
    tools = skills.tool_definitions(catalog)
    assert set(tools) == {"find_skills", "read_skill"}
    for tool in tools.values():
        body = tool.schema()
        assert body["type"] == "function" and body["function"]["name"] == tool.name
        assert body["function"]["parameters"]["required"]
        json.dumps(body)                       # must survive the request body
        assert tool.effect == "read" and tool.roles == ROLES
    assert tools["find_skills"].validate({"query": "anything"})["query"] == "anything"


def test_the_tool_reads_a_contract_and_refuses_an_unknown_name_by_name(
        catalog: skills.Catalog):
    tools = skills.tool_definitions(catalog)
    assert tools["read_skill"].handler is not None
    assert "TELEGRAM CONTRACT" in tools["read_skill"].handler({}, {"name": "telegram"})["text"]
    with pytest.raises(ToolError, match="no such skill"):
        tools["read_skill"].handler({}, {"name": "ghost"})


def test_the_agent_is_offered_the_tools_only_while_a_catalog_can_be_read(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("ONEIRO_SKILLS_CATALOG", str(tmp_path / "not-a-catalog.json"))
    assert skills.registry() == {}, "a capability that cannot run is not offered"
    monkeypatch.setenv("ONEIRO_SKILLS_CATALOG", str(write_catalog(tmp_path)))
    monkeypatch.setenv("ONEIRO_SKILLS_PATHS", json.dumps([str(tmp_path / "skills")]))
    offered = skills.registry()
    assert set(offered) == {"find_skills", "read_skill"}


def test_the_agent_registry_carries_the_skill_tools(tmp_path, monkeypatch):
    """They arrive with every other tool, under the same policy and the same record."""
    isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("ONEIRO_SKILLS_CATALOG", str(write_catalog(tmp_path)))
    monkeypatch.setenv("ONEIRO_SKILLS_PATHS", json.dumps([str(tmp_path / "skills")]))
    from oneiro import agent
    links = MemoryLinks()
    stub = GraphStub(links, tmp_path / "graph-writer.lock")
    try:
        registry = agent.default_registry(Runtime(graph=stub), "main")
    finally:
        stub.store.close()
    assert {"find_skills", "read_skill"} <= set(registry)


def test_evidence_counts_lookups_and_characters():
    actions = [
        {"tool": "find_skills", "args": {"query": "browser"}, "observation": "x" * 100},
        {"tool": "read_skill", "args": {"name": "browser"}, "observation": "y" * 50},
        {"tool": "read_file", "args": {"path": "a.py"}, "observation": "z" * 900},
    ]
    assert skills.evidence(actions, None) == {
        "available": False, "contracts": 0, "lookups": 1, "contracts_read": 1,
        "observation_chars": 150, "queries": ["browser"], "read": ["browser"],
    }


# ---------- the settings, and the surface they reach ----------


def test_changing_the_two_skill_settings_changes_what_is_found(tmp_path, monkeypatch):
    """§ 6 row 17 for these keys: the settings decide behaviour, they are not flags."""
    isolate(tmp_path, monkeypatch)
    shipped = skills.describe()
    assert shipped["catalog_source"] == skills.SHIPPED and shipped["skills"] > 100

    monkeypatch.setenv("ONEIRO_SKILLS_CATALOG", str(write_catalog(tmp_path)))
    monkeypatch.setenv("ONEIRO_SKILLS_PATHS", json.dumps([str(tmp_path / "skills")]))
    mine = skills.describe()
    assert mine["catalog_source"] == "your own file (skills.catalog)"
    assert mine["skills"] == 3 and mine["on_disk"] == 3 and mine["contracts_in_hand"] == 3
    assert skills.search("telegram chat report")["skills"][0]["name"] == "telegram"
    assert "TELEGRAM CONTRACT" in skills.show("telegram")["text"]


def test_the_in_force_flags_match_what_this_module_reads():
    """The flags, next to the behaviour above; `test_settings_honesty.py` holds the rest."""
    rows = {setting.key: setting for setting in config.SETTINGS}
    assert rows["skills.catalog"].pending is False
    assert rows["skills.paths"].pending is False
    assert rows["skills.auto_use"].pending is True, "nothing acts on it, so it says so"


def test_the_cli_lists_searches_and_shows(tmp_path, monkeypatch, capsys):
    isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("ONEIRO_SKILLS_CATALOG", str(write_catalog(tmp_path)))
    monkeypatch.setenv("ONEIRO_SKILLS_PATHS", json.dumps([str(tmp_path / "skills")]))

    assert skills.skills_command(["list"]) == 0
    listed = capsys.readouterr().out
    assert "catalog:" in listed and "contracts: 3 addressable" in listed
    assert "folder:" in listed and "there" in listed

    assert skills.skills_command(["search", "telegram chat report"]) == 0
    assert "telegram" in capsys.readouterr().out

    assert skills.skills_command(["search", "quantum chromodynamics lecture"]) == 0
    assert "nothing" in capsys.readouterr().out.lower()

    assert skills.skills_command(["show", "telegram"]) == 0
    assert "TELEGRAM CONTRACT" in capsys.readouterr().out

    assert skills.skills_command(["show", "ghost"]) == 2
    assert "no such skill" in capsys.readouterr().out
    assert skills.skills_command(["search"]) == 2
    assert skills.skills_command(["show"]) == 2


def test_a_broken_catalog_is_reported_by_the_cli_and_the_route(tmp_path, monkeypatch, capsys):
    isolate(tmp_path, monkeypatch)
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("ONEIRO_SKILLS_CATALOG", str(broken))
    assert skills.skills_command(["list"]) == 1
    assert "not valid JSON" in capsys.readouterr().out

    app = web.create_app(runtime=Runtime(graph=GraphStub(MemoryLinks(),
                                                         tmp_path / "writer.lock")))
    with TestClient(app) as client:
        page = client.get("/api/skills")
        assert page.status_code == 503 and "not valid JSON" in page.json()["error"]
        assert client.get("/api/skills/search", params={"q": "anything"}).status_code == 503
        assert client.get("/api/skills/telegram").status_code == 404


def test_the_http_surface_answers_the_same_questions(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("ONEIRO_SKILLS_CATALOG", str(write_catalog(tmp_path)))
    monkeypatch.setenv("ONEIRO_SKILLS_PATHS", json.dumps([str(tmp_path / "skills")]))
    app = web.create_app(runtime=Runtime(graph=GraphStub(MemoryLinks(),
                                                         tmp_path / "writer.lock")))
    with TestClient(app) as client:
        overview = client.get("/api/skills").json()
        assert overview["error"] == "" and overview["skills"] == 3
        assert overview["roots"][-1]["path"] == str(tmp_path / "skills")

        found = client.get("/api/skills/search", params={"q": "telegram chat report"}).json()
        assert [row["name"] for row in found["skills"]][:1] == ["telegram"]
        assert found["skills"][0]["score"] == 6

        empty = client.get("/api/skills/search", params={"q": "quantum chromodynamics"}).json()
        assert empty["skills"] == [] and "no catalog match" in empty["note"]
        assert client.get("/api/skills/search").status_code == 400

        # A router and a part are both reachable by their own name.
        part = client.get("/api/skills/browser/parts/stealth")
        assert part.status_code == 200 and "STEALTH PART CONTRACT" in part.json()["text"]
        missing = client.get("/api/skills/ghost")
        assert missing.status_code == 404 and "no such skill" in missing.json()["error"]
