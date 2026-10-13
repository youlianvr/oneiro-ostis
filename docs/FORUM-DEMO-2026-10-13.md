# Oneiro — local forum delivery, 14 October

## What is ready and what is not

This is a **local demonstration**, not full-product Windows acceptance. The running
model is **Mistral Codestral through the existing OmniRoute gateway**. BashAPI remains
configured but does not generate (503); it is not on the active default/role route.
The existing two fallback entries/provider records were preserved.

The demo proves separate, explicit paths:

1. Signed webhook → queued task → independent graph read.
2. **Test mailbox** → observed mail note → exact draft → human press → one matching
   call; repeat press/refusal cannot send again. The bot is a **test stdio bot**,
   not the owner's Telegram. Real Telegram remains unconfigured; chat identification
   must be explicitly verified before real delivery.
3. Explicit office command → predefined ODF sources → real LibreOffice conversions
   in a network-disabled container → six artifacts → seven actions + experience.

These are **not** an invented automatic webhook→mail→office chain. The demo runner
moves between them explicitly. The office operation is not autonomous GUI use and
its two-slide output is a job artifact, not the talk's presentation.

## Run without the agent

Working directory: `projects/ostis/oneiro-ostis/`.

Prerequisites already present on this demonstration machine:
- Python 3.11–3.14 with the project installed or `PYTHONPATH=python`; FastAPI,
  uvicorn, optional sc-client graph dependencies and Playwright Chromium.
- Docker Desktop running, local images `oneiro-rewrite-machine:checkpoint` and
  `oneiro-office:local`. No image rebuild/download is required here.
- The knowledge-base sources in this checkout. The owner graph on 8096 is only
  fingerprinted/read by the W3 check; the demo creates its own graph/free ports.
- Existing graph/test helpers are used, not a second application.

Full, repeatable usage path:

```bash
python scripts/forum-demo.py
```

The runner creates a unique `_tmp/forum-rehearsal-<timestamp>/` folder with logs,
`receipts.json` and `summary.json`. It runs W3 including the real Chromium click,
restarts **that run's** retained graph, checks W2, converts office files and reads
records, then stops the owned graph. Both outer and child command exit codes are
retained. Nothing is permanently deleted; container/volume evidence stays stopped.

To rehearse webhook/office only using this already-verified W3 run:

```bash
python scripts/forum-demo.py --w3-root _tmp/oneiro-w3-live-i86svxus
```

A nonzero exit means **stop and inspect the named log**, not claim the next package
passed. Ctrl+C interrupts the outer runner; inspect the receipts and stop only the
named `oneiro-w3-<suffix>` graph if necessary (`docker stop <name>`). Do not use mass
kill, remove volumes, restart owner services, change keys or touch 9899. The wrapper
preserves the office container by replacing only the injectable cleanup runner's
`docker rm` with `docker stop`; all real conversion and graph commands are unchanged.

## Stage cues / fallback if live networking or Docker fails

If the live run fails in the room, the recorded run becomes the show. Play
[`forumit-2026/demo-record/oneiro-demo-run.mp4`](forumit-2026/demo-record/oneiro-demo-run.mp4)
— measured **40.96 s, 1280x720, H.264**, the same session as `oneiro-demo-run.webm`
(VP8, 2,525,714 bytes) — and walk the key screens beside it:
[the journal with the webhook's task](forumit-2026/demo-record/key-07-tasks-webhook.png),
[before the press](forumit-2026/demo-record/key-02-drafts-before.png),
[after it](forumit-2026/demo-record/key-03-drafts-after.png),
[the memory section](forumit-2026/demo-record/key-04-memory.png),
[the graph page](forumit-2026/demo-record/key-05-graph-read.png),
[page one of this run's produced PDF](forumit-2026/demo-record/key-08-office-document.png),
[the office listing](forumit-2026/demo-record/key-06-office-listing.png) and
[the console](forumit-2026/demo-record/key-01-console.png). It was produced by
`python tests/live_demo_record.py --marker p6-20261013i` — **exit 0, 30/30 checks** — on an
isolated data root and a graph container of that run's own; the mail in it is the **test**
transport (one press, one call in the fake mailbox's log) and no owner file is in any frame.
It carries the whole talked chain, not only the browser part: the **signed webhook**
delivered into that console (accepted with **202**; no signature, a stranger's key and this key
over other bytes each refused with **401** and their own code, with the journal holding exactly
the one task the signed call made), its task read back out of the graph by id and shot in the
journal; the **office job** by the product's own command in the
shipped container (six artifacts, sizes on disk equal to the sizes reported, pages 1/1/2, the
container stopped not removed, 8/8 records read back by id); and the **independent graph read**
by the product's own reader, whose exit code is kept. The video was also asked about its own
contents: sampled once per second, each of the eight key screens is found in it, at the second
`record.json` names beside each screen's route, window and measured size.
Three differences from the live screen are named rather than hidden: the readiness block in the
recording belongs to that isolated root, which never calls the owner's provider (a check does
not), so where the presenting machine says «Настроенная модель ответила на реальный запрос» the
recording says the model was not verified; the office listing is the durable page below, not a
re-shoot; and four moments have no screen at all — the signed POST itself, the refusals, the
conversion inside the container and the reader's printed page — so they are covered by their
results (the task in the journal, the status codes with no task behind them, the files on disk,
the reader's exit code) and never shown as a log standing in for the interface.

1. Open [current Russian speech](TALK-RU-2026-10-13.md). Eight static screen cues are
   provided, and the recording above carries the journal with the webhook's task, the press,
   the memory section, the graph page and page one of that run's own office document — each of
   them found in the video by sampling it — so nothing has to be improvised if the panel will
   not start.
2. Show the before/after drafts screenshots: [before](shots/w3-drafts/ru-drafts-tab.png),
   [after](shots/w3-drafts/ru-drafts-tab-sent.png). Say **test transport** aloud.
3. Open generated office documents/PDFs from the run folder named in `summary.json`.
   The current measured output is retained below; all files were opened/parsed.
4. Show the transport count and graph states in the W3 log. JSON logs are engineering
   evidence, not user-interface screens; don't present a log as the product UI.
5. For self-improvement show only the [saved W4 report](O8-2026-10-12.md): repeated
   measurement and **rejected candidate**. No new measurements or speedup claims.

## Evidence / checkpoints

- Working primary: `_tmp/forum-mistral-primary.json` reports exact `ONEIRO_READY`
  and `oneiro_probe(text=ready)` from `codestral-2508`, ledger provider `omniroute`.
- W3 final: `_tmp/forum-final-w3.log`, outer exit **0**, **67/67**; CLI list/show/revise/
  send/new exits **0**, dry-run refusal **2**. Console/deny-console exit **0**;
  three test mail sends + one bot notice, six total MCP calls. All read back by ID.
  Owner data 15 files unchanged; product graph stream unchanged. No retries reported.
- W2/office final-tree rehearsal: `_tmp/forum-rehearsal-20261013-014311/receipts.json`:
  all six command exits **0**, W2 **22/22**, office **30.53 s**, graph stop **0**.
  This is scripted usage timing, **not human oral rehearsal**.
- Office: six readable archives/PDFs, PDF page counts **1/1/2**, exact label
  `Презентация` verified after a narrow column-width repair. Seven action records plus
  one experience, independently read back. Sources are predefined by the demo.
- The earlier full suite exposed stale skills-asset content: **765 passed, 1 failed**.
  Owner explicitly authorized regeneration; only the `sessions` entry changed.
  Skill regressions **32 passed**, office regressions **11 passed**, mypy **45 files**.
  Frozen final full-suite result and all-in-one rehearsal: recorded below when complete.

## Speech time — estimated, not falsely measured

The speech has **1,487 spoken words**, across seven sections. At **145–160 words/min**
plus **90 seconds** of explicit stage transitions, the estimate is **10.79–11.76 min**.
At 150 words/min it is **11.41 min**. Read only marked speech blocks, not headings,
evidence references or answers to anticipated questions. A slower delivery may exceed
12 minutes: reduce the architecture section or transitions, do not speed-read the ending.

Human speaking/transition cadence cannot be measured by a scripted command. The owner
still needs one actual oral rehearsal with a stopwatch; that is not a hidden completed
check. The automation verifies command timing and artifacts, not someone's speech rate.

## Final freeze

- Frozen final full suite: **767 passed**, exit **0**, 182.46 s; three existing
  dependency deprecation warnings. Log `_tmp/forum-frozen-pytest.log` and explicit
  exit `_tmp/forum-frozen-pytest.exit`. Full mypy: **45 files, exit 0**.
- Actual no-argument usage `python scripts/forum-demo.py`: outer **exit 0**,
  seven child receipts all **0**, wall **80.15 s**; W3 **67/67**, W2 **22/22**.
  `_tmp/forum-rehearsal-20261013-014632/summary.json` includes graph-stop receipt.
- Durable [evidence viewer](demo-artifacts/2026-10-13/index.html), [document](demo-artifacts/2026-10-13/note.odt),
  [spreadsheet](demo-artifacts/2026-10-13/table.xlsx), [presentation](demo-artifacts/2026-10-13/slides.pptx),
  [PDF document](demo-artifacts/2026-10-13/note.pdf), [PDF spreadsheet](demo-artifacts/2026-10-13/table.pdf),
  [PDF slides](demo-artifacts/2026-10-13/slides.pdf) and [artifact evidence](demo-artifacts/2026-10-13/evidence.json).
- Task graph containers stopped/retained, owner graph untouched. The static evidence
  viewer remains on its own loopback port for review, not a running Oneiro application.
- Safe owned checkpoint: pending final diff review. Ambiguous pre-existing W3/client
  edits remain uncommitted; no broad staging. Full-product readiness, real account
  integration or successful self-improvement is not implied. Actual oral timing
  remains a human acceptance step, not a missing automation claim.
