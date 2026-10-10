# Oneiro v1 — acceptance report (W9)

Written 2026-10-11 while closing W9. The plan of record is `docs/MASTER-PLAN.md` (§ 5 W9,
§ 6 matrix); this file is its evidence bundle: what was built, the hash of each artifact,
which live check was run and with what exit status, and — in § 6 — what was **not** verified.
Companions: `docs/DECISIONS-v1.md` § 1.6 for the NOTICE obligation, `docs/PROGRESS.md` for
the per-package log.

The product under test is the checkout at commit `adf76694e Land the Oneiro v1 rewrite and
retire every module it replaced`, which carries packages W0–W9 and the § 6 matrix. Nothing was
verified against a copy in a worktree: every command below ran in this checkout, and every
live check keeps its settings, data root and keys in a temporary folder while fingerprinting
the owner's own files before and after.

## 1. Artifacts and their hashes

| Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| `NOTICE` | 4,618 | `8b348dd92cbd1989428a89c05cc062452fc93c6afee48815420e0dfafa40c6c1` |
| `LICENSE` | 1,061 | `6367df4033615b0c0626662c15a562afba3e061d72b2c2e4d37c230abdd4882c` |
| `python/oneiro/assets/skills-catalog.json` (shipped catalog) | 409,403 | `f5ddd9d025563ab96f9fbf5de6d62a3d71e66cd010f99e57fe9dcd1760ca0245` |
| payload `manifest.json` (43 entries) | — | `ed0ac7c27e08b3f4da1a4e8191623bd59d1bfb7cc0533b729e66790f4540f586` |
| `console/vendor/cowagent-2.1.9.zip` (named by `NOTICE`) | 4,394,330 | `cc92ae3e8dbffdc52154e3b5199e44543a20eca10220edcaf0d38c5fac534f73` |

The payload hash is of the manifest `scripts/build_installer_payload.py` writes at the end of a
build, so it covers all 43 files by name and SHA-256 — including `NOTICE` and `LICENSE`, which
the builder refuses to build without (`FileNotFoundError`, not a warning) and which
`tests/test_installer_payload.py` fails on if they are absent from either the payload or the
manifest. The earlier W8 note in `docs/PROGRESS.md` records 41 entries; the two added since are
`NOTICE` and `LICENSE`.

## 2. Acceptance screenshots (`docs/shots/oneiro-v1/`)

Twenty-two frames, all taken by `python tests/live_w9_shots.py` against the product's own
console on a free loopback port (never the owner's preview on 9899), with the document's
`lang` and `data-theme` asserted before the shutter. Twenty of the 22 are distinct images: the
`theme-night-*` pair is byte-identical to `ru-conversation.png` / `en-conversation.png` because
`night` is the default theme, which is itself the evidence that the capture is deterministic.

| Frame | Bytes | SHA-256 |
| --- | --- | --- |
| `ru-conversation.png` | 81,136 | `83465117c5e314b1f4c73df86bf567d6e77083499debcac132738843957aba94` |
| `ru-tasks.png` | 78,926 | `78f97d0ba8624cd89927df914688733694d4145bff54f6068a627264f8695208` |
| `ru-tools.png` | 70,666 | `32006086e8aef264c674c508c8d372345076e177f3abba3db0cc7dfd92ab4c4c` |
| `ru-settings.png` | 792,810 | `0345a02e7d31917cc1d3a6aec8f27a4846e6adf9889b13447d2d4ed464ff1892` |
| `ru-memory.png` | 77,008 | `552a8a8ba28e95f5aa71ecb52fb1227fea668684114b7745a64596a7e2b9febc` |
| `en-conversation.png` | 80,779 | `2e9bf14de2e9a992b85585c335f12f40f60326c33c5f468674ab79c41ae9459e` |
| `en-tasks.png` | 77,497 | `e0aad238c4493d3c4db6efe1d703101c4ce87187cb150b3fb9e5ebbeffc671a3` |
| `en-tools.png` | 69,373 | `6234a67f74af78d0aa236878f1e1a1b10ca55a78f0d9cce59cefa9f748039932` |
| `en-settings.png` | 789,399 | `d199c3ad4821d635cfb6240d554f506cb209a984548a9dda51582c848a1cf5ac` |
| `en-memory.png` | 77,340 | `a2ca5683ca5be9bef9c3591db752fdf6f26932d2a836dcc2c719f92c96de38af` |
| `theme-night-ru.png` | 81,136 | `83465117c5e314b1f4c73df86bf567d6e77083499debcac132738843957aba94` |
| `theme-night-en.png` | 80,779 | `2e9bf14de2e9a992b85585c335f12f40f60326c33c5f468674ab79c41ae9459e` |
| `theme-paper-ru.png` | 81,225 | `dc7a0e51a83388016f84f351df81ab7f838ad5669fc45c75cfa745eb2814e3ba` |
| `theme-paper-en.png` | 81,185 | `dfdd91f4ed225294610eddeaa304b7d94923dac9c013b58cb3cdb145ec7e5475` |
| `theme-editorial-ru.png` | 70,134 | `f1c07bfa1ffaeefb110fa4a7d9d88ee775dab979d4125e9c1e85510c711bded3` |
| `theme-editorial-en.png` | 69,678 | `6df884e865c74f9c778bbd1b481f82f373670ab6ca7fcfe5ef23d4d3e77fdbce` |
| `theme-cosmic-ru.png` | 79,662 | `8d682d277b6b60a2212773f93e228a629be87bb83a98a87579386997f39f0917` |
| `theme-cosmic-en.png` | 79,474 | `d7fdcc0f436bb22d9f3de77e3600382504c2af9b000cae4d68001694ca1595da` |
| `theme-agentic-ru.png` | 83,088 | `f892cdfb2f23cf93c67c967b4bf8b1bc9939e48187c9ba34dd2d2ecfe3cba1f2` |
| `theme-agentic-en.png` | 83,070 | `a9723a4d77f1de601bae532ab41bf6223640c8e603bbb0c565b87d506b4e5d4c` |
| `installed-conversation-ru.png` | 80,946 | `57f3ea9b1f07aa13d762b5bb1be77e2d9101ba61f99627314690ee5b9859f246` |
| `installed-conversation-en.png` | 80,602 | `2d0832118778259631e2459f5d6ecf69d213ce9a5a91c8cd062ba4bc5ba2cdec` |

The two `installed-*` frames are the console served from an **installed copy outside this
checkout**: the check builds the payload, copies it to a temporary install tree, runs
`python -m oneiro serve --no-window` there with `PYTHONPATH` pointing at that tree only, and
asserts before the shutter that the process resolves `oneiro` to
`<install>/app/python/oneiro/__init__.py`. That is § 6 row 1 shown as a picture rather than
only as a log line.

Language is machine-checked, not eyeballed: every `?lang=ru` page carries 136–208 Cyrillic
characters while the matching `?lang=en` page carries none, and no page equals its other-language
twin.

## 3. Live checks, with exit statuses

Each was run as a plain command in this checkout; the exit status is the process's own.

| Check | What it proves | Exit |
| --- | --- | --- |
| `python tests/live_w1_check.py` | tasks, schedules, approvals, restart | 0 |
| `python tests/live_w2_check.py` | MCP over stdio and HTTP JSON-RPC | 0 |
| `python tests/live_w3_check.py` | skills: shipped catalog, folders, CLI, HTTP, a full turn | 0 |
| `python tests/live_w4_check.py` | conversation with tools, probes, memory writes | 0 |
| `python tests/live_w5_check.py` | research with sources, attachments | 0 |
| `python tests/live_w6_check.py` | five screens, no JSON on screen, owner files unchanged | 0 |
| `python tests/live_w7_check.py` | RU/EN and the five themes, contrast | 0 |
| `python tests/live_w8_check.py` | payload, out-of-tree install, upgrade preserves data | 0 |
| `python tests/live_w9_shots.py` | the 22 acceptance frames above | 0 |

`live_w8_check.py` reports `Installed doctor check -> exit 1, ready=False, phase=agent` and
still exits 0: the installed copy is being asked for a doctor report in a temporary root with
no model key and no graph, and `ready=False` with a named phase is the honest answer there.

## 4. Suite and typecheck

| Command | Result |
| --- | --- |
| `python -m mypy python/oneiro` | Success: no issues found in 33 source files (exit 0) |
| `python -m pytest -q` | 563 passed, 2 warnings (three runs on this revision: 93.6s, 88.4s, 84.1s; exit 0) |

563 tests across 35 `tests/test_*.py` files. The W9 note in `docs/PROGRESS.md` says "35/35 test
suites"; this report replaces that phrasing with the measured count.

## 5. Defects found while writing this report, and their repair

Writing the report against the artifacts is what surfaced both; neither was visible from the
committed W9 evidence, which claimed the live checks were clean.

1. **`tests/live_w3_check.py` could not run at all.** Its parity block still did
   `import skills_index`, a module W9 retired, so the check died with `ModuleNotFoundError` and
   § 6 row 7's named evidence produced no evidence. Repaired by comparing the two catalogs that
   still exist: the compact asset that ships (`python/oneiro/assets/skills-catalog.json`,
   409,403 B) against the reviewed workspace catalog the builder wrote it from. Six queries over
   319 addressable contracts, 0 ranking mismatches; a mismatch now fails the check instead of
   passing quietly. The check exits 0 again.
2. **`tests/test_skills.py` had a test whose name no longer matched its body.**
   `test_the_migrated_module_ranks_the_real_catalog_identically` had been reduced to asserting
   that results were non-empty and scored above zero — no comparison with anything — while still
   claiming parity with the retired module. Renamed to
   `test_the_shipped_asset_ranks_the_reviewed_catalog_identically` and made to assert real
   parity: equal record counts and identical (name, score) top-5 for all 23 queries. 32 passed.

Neither repair weakens a check; both replace a claim with a measurement. The retired-module
parity that W3 originally recorded (`docs/PROGRESS.md`: "oneiro.skills and skills_index.py rank
the same 319 addressable contracts identically") cannot be re-run now that the reference module
is gone, and is not counted here as fresh evidence.

## 6. What was not verified, and why

Named gaps, not silent ones.

- **A real graph server.** No `sc-server` on 8090 was running for this work, so the OSTIS-backed
  paths (graph worker, query surface) are exercised only against the fake and in-memory link
  graphs the live checks and tests build. Their contract tests pass; a live round trip against a
  real `sc-server` did not happen in this session.
- **The real model.** Every live check drives a stub provider on loopback (plus a recorded
  provider transcript where a turn is asserted). No live provider call was made here, so the
  shipped defaults are unproven against a real endpoint with the owner's key; the owner's key
  files were deliberately left untouched (they are fingerprinted by each check).
- **The full PowerShell payload builder.** `installer/build-payload.ps1` embeds Python 3.14.3
  and `docker save`s the graph image, so it needs network and the built
  `oneiro-rewrite-machine:checkpoint` image. It was edited to copy `NOTICE` but was not executed
  in this session; only `scripts/build_installer_payload.py` was built and installed, and that is
  what the hashes in § 1 and the `installed-*` shots come from.
- **A real WebView2 window.** `live_w6_check.py` verifies the launcher in its headless fallback
  (`mode=headless, active=True`); a real window on a desktop session was not opened or
  photographed.
- **Keyboard and contrast behaviour** in the delivered screenshots: the frames show rendering,
  not tab order or focus rings. Those are covered by `tests/test_console_tokens.py` and
  `tests/test_i18n_themes.py`, not by the pictures.
- **`harness/`.** This development-only tree (not shipped, not in the payload) still names the
  retired `mcp_client` and `skills_index` in a guarded import at `harness/agent.py`, and gets
  `None` for both; it imports and runs in that degraded form. `bench/memory/run.py` still relies
  on the `python/config.py` compatibility shim, which is why that shim remains. Neither is part
  of the v1 runtime; both are reported rather than quietly cleaned up or claimed as retired.

## 7. Reproducing this report

```bash
cd projects/ostis/oneiro-ostis
python -m mypy python/oneiro
python -m pytest -q
python tests/live_w1_check.py   # … w2 … w8, then:
python tests/live_w9_shots.py   # rewrites docs/shots/oneiro-v1/ (22 frames)
```

`live_w9_shots.py` needs Playwright with Chromium. Without it the script says so and exits 1
instead of writing placeholder pictures; the § 6 screenshot rows would then have to be marked
"manual shot required".
