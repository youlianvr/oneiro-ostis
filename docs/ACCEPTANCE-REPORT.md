# Oneiro v1 — acceptance report

The plan of record is `docs/MASTER-PLAN.md` (§ 5 packages, § 6 matrix); this file is its
evidence bundle: what was built, the hash of each artifact, which live check was run and
with what exit status, and — in § 6 — what was **not** verified. Companions:
`docs/DECISIONS-v1.md` § 1.6 for the NOTICE obligation, `docs/PROGRESS.md` for the
per-package log.

First written 2026-10-11 while closing W9. The same day it was corrected: an audit of the
accepted deliverable found that § 6 row 14 (RU/EN) had been asserted from evidence that did
not support it — the settings screen served English on a Russian page. § 5 records that
defect and its repair, and § 2 now carries the measurement rather than a claim.

Nothing here is verified against a copy in a worktree: every command ran in this checkout,
and every live check keeps its settings, data root and keys in a temporary folder while
fingerprinting the owner's own files before and after.

## 1. Artifacts and their hashes

| Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| `NOTICE` | 4,618 | `8b348dd92cbd1989428a89c05cc062452fc93c6afee48815420e0dfafa40c6c1` |
| `LICENSE` | 1,061 | `6367df4033615b0c0626662c15a562afba3e061d72b2c2e4d37c230abdd4882c` |
| `python/oneiro/assets/skills-catalog.json` (shipped catalog) | 409,403 | `f5ddd9d025563ab96f9fbf5de6d62a3d71e66cd010f99e57fe9dcd1760ca0245` |
| payload `manifest.json` (43 entries) | — | `0adb29111eef40564ab92cf4875b56dd41a6c0206df9d5b4f576eb49b901dd61` |
| `console/vendor/cowagent-2.1.9.zip` (named by `NOTICE`) | 4,394,330 | `cc92ae3e8dbffdc52154e3b5199e44543a20eca10220edcaf0d38c5fac534f73` |

The payload hash is of the manifest `scripts/build_installer_payload.py` writes at the end of
a build, so it covers all 43 files by name and SHA-256 — including `NOTICE` and `LICENSE`,
which the builder refuses to build without (`FileNotFoundError`, not a warning) and which
`tests/test_installer_payload.py` fails on if they are absent from either the payload or the
manifest. The W8 note in `docs/PROGRESS.md` records 41 entries; the two added since are
`NOTICE` and `LICENSE`. The manifest hash changed with the language fix, as it must: it
covers every shipped file.

## 2. Acceptance screenshots (`docs/shots/oneiro-v1/`)

Twenty-two frames, written by `python tests/live_w9_shots.py` against the web console on a
free loopback port (never the owner's preview on 9899), with the document's `lang` and
`data-theme` asserted before the shutter.

The hashes below are the run of 2026-10-11 recorded with this file, after the readiness
panel was rewritten. **They are not stable between runs**, and the file does not pretend
otherwise: earlier runs over identical code produced different hashes each time
(`ru-settings.png` 901,253 bytes before this pass, 900,150 in it, 898,836 in the re-run
recorded below) because Chromium's rasterizer is not bit-reproducible. What *is* stable is the set's structure: 22 files, 20
distinct hashes, because `theme-night-*` always equals its `*-conversation.png` counterpart
*within the same run* (checked: identical hash, not just identical size) — `night` is the
default theme, so re-theming to it redraws the same pixels. So the hashes are manifest
evidence for the frames that were actually committed, and a caller re-running the check
must expect its own hashes, not these.

| Frame | Bytes | SHA-256 |
| --- | --- | --- |
| `ru-conversation.png` | 81,808 | `c17b30f41183490eb0d2a3ce998734fdc8366899cc5dbe9fa9c82a52b00d1dfc` |
| `ru-tasks.png` | 77,332 | `30088df0796e70d8fa4105243e7cbf5c2eba0f518bb125b0b99a43b93ea59311` |
| `ru-tools.png` | 69,256 | `b00f8aab7bafacc1275b208b39602010ab20c75eecf2e61df18234b2b433b02b` |
| `ru-settings.png` | 898,836 | `c183d085d591f45ac4569d06e235ff1e26305e82e6aedf33516140909b39e4ae` |
| `ru-memory.png` | 77,339 | `9f43dec1e920438f78f0222522d0377e3dee5faab4a3c5d301782d3aee682d4b` |
| `en-conversation.png` | 81,008 | `36b353bb71e7f1518885e4fa86cc744e1c7a018ef4226594bf417f7a374ba7bb` |
| `en-tasks.png` | 77,725 | `b212fffccd639184a865e6810f58eaab25530ff601e467d2780ab92dfd109a99` |
| `en-tools.png` | 69,613 | `4d2712d70e47962da1e1bb65f23e42104a1ca664ecdd004a50ef991b0f19b455` |
| `en-settings.png` | 791,379 | `cafa89c3ff10ec3a38ecec899cb77b1fa60eb36043d873193122096f6369408b` |
| `en-memory.png` | 77,564 | `8966ccc0ce4c8db5a3318afe8616d8be29c5f12e591955a8210ee6b1aae80f42` |
| `theme-night-ru.png` | 81,808 | `c17b30f41183490eb0d2a3ce998734fdc8366899cc5dbe9fa9c82a52b00d1dfc` |
| `theme-night-en.png` | 81,008 | `36b353bb71e7f1518885e4fa86cc744e1c7a018ef4226594bf417f7a374ba7bb` |
| `theme-paper-ru.png` | 82,201 | `e705c385ac1d21489d2cb8fd00a5903325a0940f8d59d54358ad111f26123fa3` |
| `theme-paper-en.png` | 81,438 | `ce1960f833ac767226b4856e9a69a975df16ebf5bb2174f7819a850296c2100c` |
| `theme-editorial-ru.png` | 72,277 | `7d0ff1cbe32ec0f8fdc74fb7c19163c23db5a5a8608139bdc34417179f9ce6a9` |
| `theme-editorial-en.png` | 69,986 | `5c30f8c8cf7ba25a35485b48cac4b1d3b45ec28d3386e610b198a40c743c4d8e` |
| `theme-cosmic-ru.png` | 79,539 | `860207c0cf69bbc11719dc50d985e9e6903d6dda3da2b6f4f7c770198604488f` |
| `theme-cosmic-en.png` | 79,721 | `034825b828b1bb753b0f9239a34db20bc49d6eee8880845ca52f8e593b30b8a3` |
| `theme-agentic-ru.png` | 84,515 | `718d9e321cf46effce9e13c7a7170ccc80727d7e73a8850bf2e0218ffe28749f` |
| `theme-agentic-en.png` | 83,341 | `766002509094bd0a4fb9ccc8b17e59babe639c2b53d36ce9f6531b6745a26a03` |
| `installed-conversation-ru.png` | 82,062 | `08d8abbe45c25ef3939217346dc464da4936c107d62086b00ce72b27a787074a` |
| `installed-conversation-en.png` | 81,342 | `8f71a129de73b704979c3931d0231c93ecb9d777f563fa95d1da3bd024a2a388` |

Every frame is checked against the catalog **before** the shutter: a `ru` frame must carry
`oneiro.i18n`'s Russian text for that screen as element text or attribute value, and must not
carry the English value of those same keys. A file whose name claims a language its picture
does not show fails the run, so the set cannot go stale silently.

The two `installed-*` frames are the console served from an **installed copy outside this
checkout**: the check builds the payload, copies it to a temporary install tree, runs
`python -m oneiro serve --no-window` there with `PYTHONPATH` pointing at that tree only, and
asserts before the shutter that the process resolves `oneiro` to
`<install>/app/python/oneiro/__init__.py`. That is § 6 row 1 shown as a picture rather than
only as a log line.

### The language, measured

Two measurements on two objects, each one the output of a command in § 7 rather than of a
shell history. The earlier draft of this file quoted numbers from an ad-hoc script with its
own rules; these are reproducible, and the differences between them are stated instead of
averaged away.

**Rendered text, the five screens, the readiness panel included** — `tests/live_w9_shots.py`
reads `document.body.innerText` in both languages on every screen and asserts, per screen,
both that the Russian side holds no English sentence and that the two languages share none:

| screen | EN sentences | RU characters | English prose on ru | shared |
| --- | --- | --- | --- | --- |
| conversation | 9 | 909 | **0** | **0** |
| tasks | 11 | 914 | **0** | **0** |
| tools | 9 | 828 | **0** | **0** |
| settings | 82 | 15,339 | **0** | **0** |
| memory | 10 | 974 | **0** | **0** |

The panel is included because it used to be *removed* before that comparison, and the removal
is what hid the defect this pass fixed: `/api/status` served `run \`oneiro verify-model\` to
check the configured model with a real call` plus three English blocked reasons, and a Russian
page printed all four inside Russian sentences — four of the panel's eight lines carried
English, and neither rule could see it. The payload now carries codes with their data, and
both the panel and the graph page render them from the catalog, so the same facts read as
sentences in either language:

```
Не готов — см. ниже.
Фаза: agent.
Память (OSTIS) недоступна. Она обязательна и не имеет заменителей.
проверьте настроенную модель реальным вызовом: `oneiro verify-model`
Пока заблокировано:
  - типовой адаптер OSTIS не подключён, поэтому память не проверена
  - сервер OSTIS недоступен по адресу 127.0.0.1:8090
  - настроенная модель не проверена
```

That text is the Russian panel from this run, and the English page carries the same eight
lines with `blocked.graph_unreachable` interpolating the same host and port.

**Served markup** — `python tests/i18n_measure.py`, whose own output is this table (unique
visible lines; the script prints the same rows):

| screen | lang | lines | with Cyrillic | Latin-only | English prose |
| --- | --- | --- | --- | --- | --- |
| `/` | ru | 24 | 22 | 2 | **0** |
| `/` | en | 25 | 0 | 25 | 4 |
| `/tasks` | ru | 24 | 22 | 2 | **0** |
| `/tasks` | en | 24 | 0 | 24 | 4 |
| `/tools` | ru | 34 | 27 | 7 | **0** |
| `/tools` | en | 34 | 0 | 34 | 3 |
| `/settings` | ru | 201 | 167 | 34 | **0** |
| `/settings` | en | 201 | 0 | 201 | 80 |
| `/memory` | ru | 22 | 20 | 2 | **0** |
| `/memory` | en | 22 | 0 | 22 | 5 |
| `/setup` | ru | 196 | 162 | 34 | **0** |
| `/setup` | en | 196 | 0 | 196 | 80 |
| every screen | — | — | — | — | **0 shared** |

The method, so a reviewer can disagree with it precisely: a *visible line* is a **distinct**
line of the document once `<script>`, `<style>` and `<textarea>` content is removed, tags
become newlines and entities are unescaped; *English prose* is a visible line of four or more
whitespace-separated words, every character printable ASCII, no Cyrillic in it. A *Latin-only*
line is not prose — the Russian settings page must show 34 of them: two temporary paths and 32
machine values (`night`, `paper`, `editorial`, `cosmic`, `agentic`, `comfortable`, `compact`,
`allow`, `deny`, `ask`, `auto`, `manual`, `true`, `false`, `ru`, `en`, `strict`, `trusted`,
`on_command`, `proactive`, `scheduled`, `off`, `debug`, `info`, `warning`, `error`, `window`,
`browser`, `both`, `workspace`, `MCP`, `Oneiro`). `tests/i18n_measure.py` prints that list and
exits non-zero if a Russian screen shows English prose or if the languages share a sentence.

The rule is deliberately the sterner one. A filter that excused any line containing a colon or
a slash — the one this file's earlier draft used — would have missed 24 of the 80 English lines
on `/settings`, because real help text reads `How much Oneiro writes to its own log: debug,
info, warning or error.` and `Fixed to loopback: Oneiro is not reachable from the network.`
Counting those is what makes the rule worth trusting. `tests/test_i18n_themes.py` also tests
the measurement itself (`test_the_measurement_can_see_a_shared_sentence`) so it cannot pass by
finding nothing.

## 3. Live checks, with exit statuses

Each was run as a plain command in this checkout; the exit status is the process's own.

| Check | What it proves | Exit |
| --- | --- | --- |
| `python tests/live_w1_check.py` | tasks, schedules, approvals, restart | 0 |
| `python tests/live_w2_check.py` | MCP over stdio and HTTP JSON-RPC | 0 |
| `python tests/live_w3_check.py` | skills: shipped catalog, folders, CLI, HTTP, a full turn | 0 |
| `python tests/live_w4_check.py` | conversation with tools, probes, memory writes | 0 |
| `python tests/live_w5_check.py` | research with sources, attachments | 0 |
| `python tests/live_w6_check.py` | five screens in EN, no JSON on screen, owner files unchanged | 0 |
| `python tests/live_w7_check.py` | RU/EN language attributes and the five themes, contrast | 0 |
| `python tests/live_w8_check.py` | payload, out-of-tree install, upgrade preserves data | 0 |
| `python tests/live_w9_shots.py` | the 22 frames above, each checked against the catalog | 0 |

`live_w8_check.py` reports `Installed doctor check -> exit 1, ready=False, phase=agent` and
still exits 0: the installed copy is asked for a doctor report in a temporary root with no
model key and no graph, and `ready=False` with a named phase is the honest answer there.

## 4. Suite and typecheck

| Command | Result |
| --- | --- |
| `python -m mypy python/oneiro` | Success: no issues found in 33 source files (exit 0) |
| `python -m pytest -q` | 582 passed, 2 warnings, 0 failed (exit 0) |

582 tests across 35 `tests/test_*.py` files. The translation rule lives in
`tests/test_i18n_themes.py` (parametrised over the five canonical screens, `/setup` and the
legacy graph route, plus a mirror of the readiness panel and a test of the measurement
itself) and in the live check above. The W9 note in `docs/PROGRESS.md` said "35/35 test
suites"; 35 is the file count, and this report uses the measured test count.

## 5. Defects found while writing this evidence, and their repair

Writing the evidence out surfaced the first three, and auditing what it claimed surfaced the
last three. None was visible from the W9 notes, which said the matrix was fully verified.

1. **`tests/live_w3_check.py` could not run at all.** Its parity block still did
   `import skills_index`, a module W9 retired, so the check died with `ModuleNotFoundError`
   and § 6 row 7's named evidence produced no evidence. Repaired by comparing the two
   catalogs that still exist: the compact asset that ships against the reviewed workspace
   catalog the builder wrote it from. Six queries over 319 addressable contracts, 0 ranking
   mismatches; a mismatch now fails the check.
2. **`tests/test_skills.py` had a test whose name no longer matched its body.**
   `test_the_migrated_module_ranks_the_real_catalog_identically` had been reduced to
   asserting that results were non-empty, while still claiming parity with the retired
   module. Renamed to `test_the_shipped_asset_ranks_the_reviewed_catalog_identically` and
   made to assert real parity over 23 queries.
3. **The interface was not bilingual, and row 14 said it was.** `oneiro/i18n.py` held
   translations that nothing rendered: the composer buttons, the tagline and the readiness
   panel were English literals in `pages.py`, `static/page.html` and `static/app.js`, and the
   settings screen showed the registry's English `label`/`help` for all 62 settings — a
   declared decision (`settings_registry.Setting` said labels are English by design) that the
   owner's "переключить язык" criterion overrules. Repaired by making the catalog the single
   owner of every visible string: 287 keys in both languages, the settings text generated
   from the declarations on the English side and written out in Russian, the client script
   reading its sentences from a JSON block the page embeds, and a Russian page checked to
   share no English sentence with the English one. The Russian settings labels and help were
   written in this pass; the measurement in § 2 is what proves it.

   The registry's promise survived: a setting declared a minute ago renders its own wording
   until the catalog carries a translation (`i18n.setting_text`), so `test_adding_a_setting_needs_no_html_edit`
   still holds, and the parity test is what forces the translation to exist in a shipped build.
4. **The readiness panel and the graph page printed the backend's own English, and no check
   could see it.** `/api/status` served the sentence `run \`oneiro verify-model\` to check the
   configured model with a real call` and three English `blocked` reasons; the panel printed
   them inside Russian sentences, so four of its eight lines were English on every Russian
   screen, and `memory.probe` did the same to the graph page. Both rules were blind by
   construction: the markup rule reads the panel's placeholder because the panel is filled in
   the browser, and the DOM rule *deleted* `#status` before comparing. Repaired by moving the
   prose into the catalog as `REASON_KEYS` and making both surfaces report and render codes
   with their data (`reason.verify_model`, `blocked.adapter_absent`,
   `blocked.graph_unreachable` with `{host}`/`{port}`, `blocked.model_unverified`, and the
   probe's four other branches). Raw exception prose stays data: it is interpolated into the
   catalog's sentence for `blocked.probe_failed`. Three tests hold it now — the panel is
   measured on the real DOM with `#status` included, `test_the_readiness_panel_says_nothing_a_backend_composed`
   mirrors the panel in both languages and fails on a sentence anywhere in the payload, and the
   graph test no longer subtracts the probe's own strings, which was a subtraction that could
   not fail on a translation regression.
5. **Raw JSON could reach a screen without JavaScript, and row 15 did not say so.** Measured
   2026-10-11 in Chromium with scripting disabled: the settings form's own Save button posted
   to `/api/settings` and the tab rendered `{"error": "Cross-origin request refused"}`. The
   gate is the `Origin` check — the browser sent `Origin: null` — and the CSRF branch answers
   with JSON too, so whichever fires the person sees JSON. Repaired in the middleware: a
   request that accepts HTML is refused with `pages.render_error(...)`, the same shell and
   stylesheets in the active language, while a client that asks for `application/json` keeps
   the exact body it parsed before. `test_a_settings_post_without_scripts_gets_a_page_and_not_json`
   asserts both shapes, and all five screens already rendered without scripts.
6. **mypy was green because its cache was stale.** Touching `memory.py` made it re-check and
   report 18 errors in `memory.py` and `query.py`: the graph extra is installed here but ships
   no stubs, so the inline `# type: ignore[import-not-found]` comments were both unused and
   wrong for the firing code. Repaired by scoping the suppression to the two modules that reach
   the graph (`import-untyped` *and* `import-not-found`, so the result does not depend on which
   extras a machine has) and deleting the inline ignores. The earlier "Success: no issues" in
   this very report was that stale cache talking.

## 6. What was not verified, and why

Named gaps, not silent ones.

- **A real graph.** No `sc-server` on 8090 was running for this work, so the OSTIS-backed
  paths are exercised only against the fake and in-memory link graphs the live checks and
  tests build.
- **The real model.** Every live check drives a stub provider on loopback. No live provider
  call was made here, so the shipped defaults are unproven against a real endpoint with the
  owner's key; the owner's key files were deliberately left untouched.
- **The full PowerShell payload.** `installer/build-payload.ps1` embeds Python 3.14.3 and
  `docker save`s the graph image, so it needs network and the built
  `oneiro-rewrite-machine:checkpoint` image. It was edited to copy `NOTICE` but was not
  executed here; only `scripts/build_installer_payload.py` was built and installed, and that
  is what § 1 and the `installed-*` frames come from.
- **A real WebView2 window.** `live_w6_check.py` verifies the launcher in its headless
  fallback; a real window on a desktop session was not opened or photographed.
- **Keyboard and contrast behaviour** in the frames: the pictures show rendering, not tab
  order or focus rings. Those are covered by `tests/test_console_tokens.py` and
  `tests/test_i18n_themes.py`.
- **Exception prose is interpolated, not translated.** A probe that fails carries
  `blocked.probe_failed` with the library's own text as data (`ConnectionAbortedError: ...`),
  so a Russian sentence can contain an English clause. That is a deliberate boundary — the
  alternative is swallowing the exception's message — and it is the only English left in the
  Russian panel, since the reason *sentences* are catalog text now.
- **The settings save path is JSON-only on the wire.** The form posts to `/api/settings`, which
  parses JSON only and requires the `X-Oneiro-CSRF` header. A browser that accepts HTML is now
  refused with a page rather than a JSON body (defect 5 in § 5), but a script-less submit still
  *cannot save* — it can only be refused legibly. The "an empty field leaves the current key
  unchanged" promise is kept by the client script skipping an empty key field; the server's
  `empty_means_unset` would otherwise clear it.
- **The scheduler retries the missing graph without visible backoff.** With no
  `sc-server` the console stays up and reports memory as unreachable, but the scheduler logs
  `a scheduler tick failed (GraphQueryError: server_unreachable …)` once per tick.
- **The frames' hashes are per-run.** They prove the files that were committed, not that a
  re-run gives the same bytes (§ 2). Nobody should diff a fresh run against the table.
- **The installed console is killed, not asked to stop.** `live_w9_shots.py` ends the
  out-of-tree console with `process.terminate()`, which on Windows is `TerminateProcess`, so
  it prints `installed console stopped (exit 1)`. That number is the stop mechanism, not the
  console's health: it had answered `/api/health` and served both frames before it. A
  graceful-shutdown exit code was not verified here.
- **`harness/`.** This development-only tree (not shipped, not in the payload) still names the
  retired `mcp_client` and `skills_index` in a guarded import and gets `None` for both;
  `bench/memory/run.py` still relies on the `python/config.py` compatibility shim. Neither is
  part of the v1 runtime.

## 7. Reproducing this report

```bash
cd projects/ostis/oneiro-ostis
python -m mypy python/oneiro
python -m pytest -q                    # includes the RU/EN measurement
python tests/i18n_measure.py           # the § 2 table, and it fails on English on ru
python tests/live_w1_check.py          # … w2 … w8, then:
python tests/live_w9_shots.py          # rewrites docs/shots/oneiro-v1/ (22 frames)
python ../../../_scripts/validate_doc_routes.py   # workspace-root validator; three levels up from here
```

`live_w9_shots.py` needs Playwright with Chromium. Without it the script says so and exits 1
instead of writing placeholder pictures; the § 6 screenshot rows would then have to be marked
"manual shot required".
