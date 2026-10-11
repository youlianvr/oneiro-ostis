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

The hashes below are the run of 2026-10-11 recorded with this file. **They are not stable
between runs**, and the file does not pretend otherwise: an earlier run over identical code
produced 22 different hashes (`ru-settings.png` 900,562 bytes then, 901,253 now) because
Chromium's rasterizer is not bit-reproducible. What *is* stable is the set's structure: 22
files, 20 distinct hashes, because `theme-night-*` always equals its `*-conversation.png`
counterpart *within the same run* (checked: identical hash, not just identical size) —
`night` is the default theme, so re-theming to it redraws the same pixels. So the hashes are
manifest evidence for the frames that were actually committed, and a caller re-running the
check must expect its own hashes, not these.

| Frame | Bytes | SHA-256 |
| --- | --- | --- |
| `ru-conversation.png` | 82,900 | `eda5a2284baa95861ce00c9461b5dbb2d25881726872c65220143cc6163bac9f` |
| `ru-tasks.png` | 78,503 | `b1e3a6982b7d2c30721679dab1a3f70e7a5daa7c6fc9cb3ab99dd541f1fb84ca` |
| `ru-tools.png` | 70,413 | `be8677fd35980fd2a48ae071fa90b791c1545591ed74ac879af8e3ca4c0d06f7` |
| `ru-settings.png` | 901,253 | `9499d15ba9d86439e1bd91d801f96f41a75336998ddd0b57bb457aa758f3c9e4` |
| `ru-memory.png` | 78,447 | `496dfba42210a69bef8b6af00402bebcfc1e5ec2f70d3f9172cfc5818eb29497` |
| `en-conversation.png` | 81,023 | `f4839d40b8bebc57adc59541fd2e3b961b7552326d7c748ea58ddaef0d6e93a9` |
| `en-tasks.png` | 77,772 | `bca8e49571cdcf0979f67ec7c92e17287fdc86fb72bf1790434d567282055fe0` |
| `en-tools.png` | 69,654 | `89bc2c959ffc399727b88a9763706907e043e724e244d4b2c6454b9c21e86241` |
| `en-settings.png` | 791,957 | `ecaed178911cae576c8ea37b786f03079b844cf2bb5f83f50bf0a2dfa317334d` |
| `en-memory.png` | 77,608 | `f37dbba786be3b712d4b624c6a9e2f6c13c7343e30d6e844bbbe467a4ce24b66` |
| `theme-night-ru.png` | 82,900 | `eda5a2284baa95861ce00c9461b5dbb2d25881726872c65220143cc6163bac9f` |
| `theme-night-en.png` | 81,023 | `f4839d40b8bebc57adc59541fd2e3b961b7552326d7c748ea58ddaef0d6e93a9` |
| `theme-paper-ru.png` | 83,173 | `df5c9902be118e1c4965e63e15d68b1b3c0fde024a6cb83d00e7685b38509c35` |
| `theme-paper-en.png` | 81,338 | `8f46cf8e9002ec57158213c0c7f1f5318d7c89113f92bd216ea612c50860950f` |
| `theme-editorial-ru.png` | 73,339 | `50cc3c91f508dc5382bb44839b6fde5fe261003451b7e2f3fbf089a9daf9c871` |
| `theme-editorial-en.png` | 69,781 | `e587f9bcba4b0c70d2e7375e93613529582cf8e6443ebfc39762ebb505ca2c4f` |
| `theme-cosmic-ru.png` | 80,522 | `26d8df92da738c3122a773dfa06685b775e2066cf100156e262f9318ee324c9e` |
| `theme-cosmic-en.png` | 79,632 | `003af1d3a98dd0e59f0bc1aeafe6ca4e684e0c1fc8c879e2b5786dca7f55dea0` |
| `theme-agentic-ru.png` | 85,538 | `ddc47ff91071334acc5ae41e79552c9ce6c6e94b0bf9b97885c34dc0e1592fa8` |
| `theme-agentic-en.png` | 83,237 | `c21b80fec22be7e574088027fd4344456d1f0961af35d83b83b8d5caf4bd37f7` |
| `installed-conversation-ru.png` | 83,145 | `47724d89fdf3bfdf96b23b0bdc48dc175054ef87b0b7c74352ff05cdab7f628d` |
| `installed-conversation-en.png` | 81,393 | `e25666f28fbe2112c9e7d91cf5132ca90840de73eef187a26e39823782b5dfc0` |

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

The measurement is the point of this section, because the previous version of this file
asserted row 14 from evidence that could not support it. Two measurements, on two different
objects, both kept because they disagree and the difference matters:

**Rendered DOM, five screens** — `tests/live_w9_shots.py`, after the five screens are shot,
reads `document.body.innerText` in each language and asserts RU and EN share no English
sentence. English sentences on the EN side / Russian-side characters: conversation 4 / 562,
tasks 6 / 567, tools 4 / 481, settings 77 / 14,992, memory 5 / 627; **shared: 0 on all five**.
The settings screen is where the defect lived: before the repair its Russian rendering carried
48 English sentences, all of them the registry's English `label`/`help` strings that the
English page also shows, so every one was shared.

**Served HTML, `/settings`** — the same rule applied to what the server sends, measured
with `tests/test_i18n_themes.py`'s extractor on this run:

| `/settings` served HTML, 2026-10-11 | RU | EN |
| --- | --- | --- |
| visible text lines | 212 | 212 |
| lines containing Cyrillic | 168 | 0 |
| Latin-only lines | 44 | 212 |
| lines that read as English prose (≥ 4 ASCII words, no Cyrillic) | **0** | 80 |

English prose shared between the two: **0** (the EN column's 80 sentences all have their
Russian counterpart, or none at all, on the RU page).

The 44 Latin-only lines on the Russian page are paths and machine values a settings form has
to show as-is — `C:\Users\pc\.oneiro\settings.json`, `"base_url": "http://127.0.0.1:20128/v1",`,
`"discover_models": true`, `MCP`, `JSON_LINES` — not product prose. That is the whole
remaining gap between "a Latin-only line" and "an English sentence", and the prose column is
the one that measures the interface.

This is also why the table above counts 212 lines where an earlier draft of this file claimed
308: the DOM measurement counts rendered nodes, the HTML one counts text lines in the markup,
and quoting one as the other was part of the same mistake. `tests/test_i18n_themes.py` adds a
test of the measurement itself (`test_the_measurement_can_see_a_shared_sentence`) so the rule
cannot pass by finding nothing.

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
| `python -m pytest -q` | 580 passed, 2 warnings, 0 failed (exit 0) |

580 tests across 35 `tests/test_*.py` files. The translation rule lives in
`tests/test_i18n_themes.py` (21 tests, parametrised over the five canonical screens, `/setup`
and the legacy graph route) and in the live check above. The W9 note in `docs/PROGRESS.md`
said "35/35 test suites"; 35 is the file count, and this report uses the measured test count.

## 5. Defects found while writing this evidence, and their repair

Writing the evidence out is what surfaced all three; none was visible from the W9 notes,
which claimed the matrix was fully verified.

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
- **Backend diagnostics are still English.** The readiness panel's `blocked` lines and the
  legacy graph page's reason list come from `memory.probe`/`Runtime.status`, and one branch
  embeds raw exception prose (`ConnectionAbortedError: ...`). A reason is data about a
  machine, not a sentence about the product, so it is not in the catalog: turning those
  reasons into codes with data is a separate change. They are the one place a Russian screen
  still shows English text, they are excluded from the measurement in § 2 by subtracting the
  probe's own strings, and `tests/test_i18n_themes.py` fails if the diagnosis ever moves into
  a template.
- **The settings save path is JSON-only, and dies without JavaScript.** The form posts to
  `/api/settings`, which parses JSON only (`python/oneiro/web.py`) and requires the
  `X-Oneiro-CSRF` header, so a native submit returns a raw-JSON error page — a reachable
  violation of the "no JSON on screen" rule for a browser without JavaScript. The "an empty
  field leaves the current key unchanged" promise is kept by the client script skipping an
  empty key field; the server's `empty_means_unset` would otherwise clear it.
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
python tests/live_w1_check.py          # … w2 … w8, then:
python tests/live_w9_shots.py          # rewrites docs/shots/oneiro-v1/ (22 frames)
python ../../../_scripts/validate_doc_routes.py   # workspace-root validator; three levels up from here
```

`live_w9_shots.py` needs Playwright with Chromium. Without it the script says so and exits 1
instead of writing placeholder pictures; the § 6 screenshot rows would then have to be marked
"manual shot required".
