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
| payload `manifest.json` (43 entries) | 4,383 | `7d24f8e9d239059f1bd20ce7f448c220568b81bc20b1e8507fc0f46ff6c354c3` |
| `console/vendor/cowagent-2.1.9.zip` (named by `NOTICE`) | 4,394,330 | `cc92ae3e8dbffdc52154e3b5199e44543a20eca10220edcaf0d38c5fac534f73` |

The payload hash is of the manifest `scripts/build_installer_payload.py` writes at the end of
a build, so it covers all 43 files by name and SHA-256 — including `NOTICE` and `LICENSE`,
which the builder refuses to build without (`FileNotFoundError`, not a warning) and which
`tests/test_installer_payload.py` fails on if they are absent from either the payload or the
manifest. The W8 note in `docs/PROGRESS.md` records 41 entries; the two added since are
`NOTICE` and `LICENSE`. The manifest hash changed with the language fix and again in each
later pass, as it must: it covers every shipped file, and the last two passes edited
`python/oneiro/graph_worker.py`, `memory.py`, `web.py`, `runtime.py` and `i18n.py` among them.

## 2. Acceptance screenshots (`docs/shots/oneiro-v1/`)

Twenty-two frames, written by `python tests/live_w9_shots.py` against the web console on a
free loopback port (never the owner's preview on 9899), with the document's `lang` and
`data-theme` asserted before the shutter.

The hashes below are the last run of 2026-10-11 recorded with this file — the re-shoot taken
after the read budget moved onto the graph lane, so the frames show the console this report
describes. **They are not stable between runs**, and the file does not pretend
otherwise: runs over identical code produce different hashes each time (`ru-settings.png`
901,253 bytes before the first of these passes, 900,150 in it, 898,836 in the second,
899,728 in the third, 901,464 in the run recorded below) because Chromium's rasterizer is not
bit-reproducible. What *is* stable is the set's structure: 22 files, 20
distinct hashes, because `theme-night-*` always equals its `*-conversation.png` counterpart
*within the same run* (checked: identical hash, not just identical size) — `night` is the
default theme, so re-theming to it redraws the same pixels. So the hashes are manifest
evidence for the frames that were actually committed, and a caller re-running the check
must expect its own hashes, not these.

| Frame | Bytes | SHA-256 |
| --- | --- | --- |
| `ru-conversation.png` | 83,051 | `aecdb78a86bf8817fc643dc666b6f9b2aa25332147b76c240e11d2cd5bd5708d` |
| `ru-tasks.png` | 78,654 | `e65a3d7fed1c75ca01c3f794ae1c92a4f7cfffc835a480727af51f8a2f7f2a3f` |
| `ru-tools.png` | 70,575 | `2e5d189e524d465de40014244d7043860dc59ee8d93b7d9a585d628eb503d845` |
| `ru-settings.png` | 901,464 | `a2ca9f1f486e60e44d19a9e48c6a1cc5cdce6eb932746da77f780a5d9da9cd83` |
| `ru-memory.png` | 78,576 | `20df991987f06bc528e986d7bded064359e864baa4ee1a13e3ac619ce373008e` |
| `en-conversation.png` | 82,130 | `3711515331b51ea8a3af93af264922465d8c6ee02258cc2a0d64e8b99f2300f5` |
| `en-tasks.png` | 78,953 | `0f2c96abdf91546ec91eddb149e1c64753f23534a98636589e2ad901e0929ed4` |
| `en-tools.png` | 70,845 | `def0d1b204cc2d354e196f0e9ab9f56edc1a354005f13b718cd84e556eb761b5` |
| `en-settings.png` | 793,484 | `5dcad9eaee8a6ec7db049e1916b47a06531fa7fe98110448db52a7312ee66f69` |
| `en-memory.png` | 78,739 | `4585dff71fc6833439775a2d4de6591ac77424822539af9ee5bc926507693c27` |
| `theme-night-ru.png` | 83,051 | `aecdb78a86bf8817fc643dc666b6f9b2aa25332147b76c240e11d2cd5bd5708d` |
| `theme-night-en.png` | 82,130 | `3711515331b51ea8a3af93af264922465d8c6ee02258cc2a0d64e8b99f2300f5` |
| `theme-paper-ru.png` | 83,385 | `98454626459f1845845de84ebf340b008a14f3e87ce77b7666ebd89e0612c814` |
| `theme-paper-en.png` | 82,540 | `86b3235ae4786a238f43f6ab92a481a87d61a487e9ead2c06e461deb5807b2e5` |
| `theme-editorial-ru.png` | 73,248 | `ca9361bfd3fb8a0a5d624996ef90e3f943fb56bbc2018e883b985f3b8ccf1aef` |
| `theme-editorial-en.png` | 70,733 | `078eef84fe486f3b14f6b8f82a0a4e222b856c1775804d2d3c3ec4ce4299fb22` |
| `theme-cosmic-ru.png` | 80,764 | `50c4a932025d794231cb0b430e50ff0d09671e2013e9fbd4330e907d697d87d8` |
| `theme-cosmic-en.png` | 80,865 | `ee2d82abdc88f2ed53791bb9f837d09e2f1ed75b42061f4efb02d9147ee33c58` |
| `theme-agentic-ru.png` | 85,795 | `3f0257937a5140d5805052faf9a2bdd60f3cd35819c13febbc5b79a88b3a932a` |
| `theme-agentic-en.png` | 84,435 | `26d3b6f2546a8294de873eebf1065481ccf92e628f5ffc1a3a72bfe0b1684f44` |
| `installed-conversation-ru.png` | 83,248 | `6ccb10b090ae9685b383285daf9c3caf317ce411f962f430592996bb62f28ec9` |
| `installed-conversation-en.png` | 82,459 | `1eeb9035c4aab6135a8e44ee5f741b1765780753290c6f1d62a33bdf56c9076f` |

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
| conversation | 9 | 922 | **0** | **0** |
| tasks | 11 | 927 | **0** | **0** |
| tools | 9 | 841 | **0** | **0** |
| settings | 82 | 15,352 | **0** | **0** |
| memory | 10 | 987 | **0** | **0** |

The panel is included because it used to be *removed* before that comparison, and the removal
is what hid the defect a first pass fixed: `/api/status` served `run \`oneiro verify-model\` to
check the configured model with a real call` plus three English blocked reasons, and a Russian
page printed all four inside Russian sentences — four of the panel's lines carried English,
and neither rule could see it. The payload now carries codes with their data, and both the
panel and the graph page render them from the catalog.

A second pass found the panel *contradicting* the page it links to: `Runtime._inspect` answered
from a TCP connect and hardcoded `verified: False`, so in the owner's environment — a live
`sc-server`, `probe` reading an arc back, `/oneiro/` reporting a readable graph — the panel
said memory answered but nothing could be read back. The verdict is the probe's own now, and
the three states read like this (Russian panel, measured through `/api/status` for each state):

```
# a live graph, the read verified
Память (OSTIS) проверена чтением графа.
...
  - типовой адаптер OSTIS не подключён: память читается через sc_client напрямую
  - настроенная модель не проверена

# nothing listening
Память (OSTIS) недоступна. Она обязательна и не имеет заменителей.
...
  - сервер OSTIS недоступен по адресу 127.0.0.1:8090

# a port that accepts TCP and never answers
Память (OSTIS) отвечает, но чтение графа не подтверждено — причина ниже.
...
  - граф памяти не отдал чтение, поэтому содержимое не подтверждено — причину называют
    страница «Граф» и журнал
```

That is the agreement row 14 asks for: the panel says readable exactly when the page shows a
read, and when it does not, it names a memory reason instead of describing the same moment
differently. The dependency's own sentence stays where it belongs — on the graph page's
`blocked.probe_failed` line; the panel reports `blocked.graph_unreadable`, whose data is the
machine facts only, so the one English clause cannot appear on all five screens.

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
| `python tests/live_w6_check.py` | five screens in EN, no JSON on screen, the three memory states, a page view that restarts no worker and closes no gate, owner files unchanged | 0 |
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
| `python -m pytest -q` | 595 passed, 2 warnings, 0 failed (exit 0) |

595 tests passed across 36 `tests/test_*.py` files. The translation rule lives in
`tests/test_i18n_themes.py` (parametrised over the five canonical screens, `/setup` and the
legacy graph route, plus a mirror of the readiness panel and a test of the measurement
itself) and in the live check above; the agreement between the panel and the graph page in
all three memory states lives in `tests/test_graph_states.py`, which also pins that the
panel's payload carries no interpolated exception sentence. The W9 note in `docs/PROGRESS.md`
said "35/35 test suites"; 35 was the `tests/test_*.py` count at W9 (36 now, after
`tests/test_graph_states.py`), and this report uses the measured test count.

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
7. **The readiness panel and the graph page contradicted each other.** With the owner's live
   graph (`probe` reading an arc back, `/oneiro/` showing `Readable. 1 anchor arc(s)`), the
   panel printed `Память (OSTIS) отвечает, но из графа ничего не удалось прочитать обратно`,
   because `Runtime._inspect` measured a TCP connect and hardcoded `verified: False`. Two
   surfaces describing one moment differently is exactly what "no panel lies" forbids, and it
   was found on the live DOM with the owner's real settings, not by a test: the panel's line
   came from a connect, so no check that compared it with a probe could see the disagreement.
   Repaired by making the panel's verdict the probe's own (`memory.probe_within`, machine data
   in the payload) and by rewording the standing `blocked.adapter_absent` line, which said
   "so memory is not verified" and would have contradicted the line above it once the verdict
   became honest. `tests/test_graph_states.py` asserts the agreement in all three states, and
   it is the repository's only *readable*-graph exercise: no `sc-server` exists here to make
   a live one on demand, so this row's live evidence is the owner's environment, which is
   where it was measured, while `tests/live_w6_check.py` drives the closed and silent states
   through real sockets and the real routes.
8. **A port that accepted TCP and never answered turned the graph route into a 500.** The read
   inside `sc_client` has no deadline, so `serve()`'s outer `wait_for(memory.probe,
   PROBE_TIMEOUT + 2)` raised `TimeoutError` out of the handler: `GET /oneiro/?lang=ru` and
   `GET /api/graph` answered `500 text/plain "Internal Server Error"` — 21 bytes of English on
   a Russian screen whose § 6 promised none, and a path § 6 did not name. `/tasks?lang=ru`
   also failed to settle, because each read behind it held the graph lane's own 10 s deadline
   (measured: `/api/tasks` 10.04 s, `/api/schedules` 9.11 s, `/api/conversations` 8.98 s).
   Repaired by bounding the read itself: `memory.probe_within` returns facts (a
   `blocked.probe_timeout` code, or the reachability it measured) within `PROBE_BUDGET`
   instead of raising, at most one silent worker may linger per target so a silent graph
   cannot spawn one thread per page view, and page-facing reads run on the lane under a 3 s
   `PAGE_READ_BUDGET`. Measured after, by `python tests/live_w6_check.py`, whose own output is
   these lines: in the silent state `/oneiro/` answers 200 in 0.15 s and `/api/graph` answers
   200 with `blocked.probe_failed` in 0.13 s, and with the graph down `/api/tasks` and
   `/api/schedules` settle in about 3.0 s each (3.02 s and 3.02 s in the run recorded here,
   within 0.1 s of that across five runs of this pass - the pair swaps between runs, the bound
   does not) instead of holding the graph lane's 10 s deadline. The audit run that found this defect measured the same state at 6.07 s for the
   first `/oneiro/` on the live DOM in the owner's environment; that figure belongs to that
   run, and this one to the live check.
9. **A page read killed the worker and closed the durability gate.** The budget was enforced
   by `asyncio.wait_for` around the lane call, so it arrived as a `CancelledError` inside the
   call that held the graph lane — and that path stops the owned worker. Measured with a graph
   that accepted TCP and never answered: each `/api/tasks` view started a new worker (pid
   20500, then 1764) and recorded `graph_worker_restarted`, closing `external_effects_allowed`
   until the next checkpoint because somebody looked at a page. Repaired by moving the budget
   onto the lane itself (`graph_worker.page_budget`, a context deadline the lane's own
   deadline is clamped to): a read that runs out of its budget is *abandoned*, not cancelled —
   the worker stays, the failure path counts one answer owed, and the next call drains it
   before sending, so no later request can read an abandoned answer as its own. A worker that
   never came up wrote nothing, so `_stop(uncertain=False)` leaves the durability gate as it
   was, and a target that did not come up is remembered for 5 s, so a page view costs one
   spawn per window instead of one per view. `tests/test_graph_worker.py` pins both: the kept
   worker whose abandoned answer is drained, and the single attempt with an unchanged gate.
10. **A verdict outlived the target it was about.** The lingering silent worker was one
    process-wide slot, so after a read of a silent-but-accepting port a probe for a merely
    *closed* port answered `blocked.probe_timeout` instead of `blocked.graph_unreachable`, and
    the panel rendered an address-less "unreadable" verdict for a port that was not
    listening. Measured on the live DOM. Repaired by keying it to the host and port the read
    was about, so a verdict always names the target it was derived from: the closed-port row
    of `live_w6_check.py` measures it *after* a silent read of another port
    (`['blocked.adapter_absent', 'blocked.graph_unreachable', 'blocked.model_unverified']`,
    ports `[None, 55642, None]`), and `tests/test_graph_states.py` asserts the same through
    `panel_reasons`.
11. **The panel and the page measured one fact with different tools.** `Runtime.status`
    cached the whole reading — the memory verdict included — for 5 s, and the panel asked for
    its TCP check with 0.5 s while the page asked with 4.0 s (`STATUS_TIMEOUT`), so the two
    surfaces could describe the same moment differently for as long as five seconds. The
    memory verdict is now a fresh reading on every status call and both surfaces ask with
    `PROBE_TIMEOUT`: one fact, one reading, and no cached verdict to age. That gap was found by
    reading the code, not by a run — said plainly because § 6 promises the difference between
    the two.

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
- **Exception prose is interpolated, not translated, and it belongs to the graph page.** A
  probe that fails carries `blocked.probe_failed` with the library's own text as data
  (`ConnectionAbortedError: ...`), so the Russian *graph page* can contain an English clause.
  That is a deliberate boundary — the alternative is swallowing the exception's message. It is
  not on the readiness panel and cannot be: the panel never probes the graph itself, it reports
  the probe's verdict, and `memory.panel_reasons` maps a failed or timed-out read to
  `blocked.graph_unreadable`, whose sentence interpolates machine data only. A previous version
  of this file said the panel was where that text could appear; it was wrong (found 2026-10-11
  by reading the two surfaces against each other), and `tests/test_graph_states.py` now asserts
  the panel payload carries no such sentence.
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
