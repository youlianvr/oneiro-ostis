# Oneiro-OSTIS — slides (outline with real numbers)

1. **Title** — Oneiro-OSTIS: an agent that dreams over its own recordings in
   an OSTIS knowledge graph.
   *(shot: `shots/01-hero.png` as the opening background — dark dashboard,
   glowing ascent line)*
2. **The claim** — Experience recorded natively in the sc-graph; a dream that
   replays recordings (exactly, no execution); a deployed winner measured
   online: 137.5 → 252.4 (+84 %).
3. **The world** — deterministic island expedition: 9 locations, 8 dig sites,
   40 steps, travel −0.1, delivery ×1.0/1.2/1.5; same seed → identical day
   (sha256 values; process-stable — regression test).
4. **The graph** — attempts as `concept_attempt` nodes (C++ agents), chronology
   `nrel_prev_attempt`, provenance `nrel_source`, trajectory: `nrel_episode`,
   `nrel_step_index`, `nrel_state`, `nrel_legal`, `nrel_strategy`, `nrel_note`;
   strategies = `concept_strategy` with descriptor + replay + online scores.
   *(shot: `shots/02-constellation.png` — the dream constellation read back
   from the live graph; can also open sc-web at localhost:8000 live)*
5. **Memory results (stage 3)** — table: context-only 0.12 recall; flat 1.00
   recall / 0.00 provenance; **OSTIS 1.00 / 1.00 / 1.00, 0 contradictions**;
   temporal ablation → order 0.58; provenance ablation → 0.00.
6. **The dream cycle** — day → explore → dream → deploy diagram; judge =
   exact replay; signature (location, carried artefact, dug-at-site) + action;
   uncovered → truncate; coverage reported.
7. **No execution, exactly** — test patch: `ExpeditionWorld.step` raises,
   replay numbers unchanged (identical estimates). Float32 note for equality.
8. **Recursive loop** — rounds table: 137.5 → 252.4 (converged; equals the
   best candidate of the offline sweep); replay estimates grow with the tree
   (3 → 15 episodes).
9. **It generalizes** — second domain (workshop crafting economy), 8/8 seeds
   improved after one dream; island mean +77.8 (1.58×), workshop mean +49.3
   (6.97×); judge bias honestly calibrated: +56.9 island, +11.3 workshop;
   0 recording conflicts across all dream trees (`docs/series.md`).
10. **Demo** — one command; 21 candidates / 3 episodes / 120 steps / 76
    transitions in 9.1 s; day 2 +114.9 (+84 %); 0 conflicts.
    *(shot: `shots/03-dream-table.png` — every dream verdict with bars;
    `shots/04-episodes.png` — the recorded experience the judge replays)*
11. **The same cycle over a real coding agent** — our own loop, six tasks with
    hidden tests (4 search / 2 held out), `DeepSeek-V4-Flash-0731`; judge over
    ten rounds: 6/6 episodes rebuilt exactly, token model 5.9% error, **19 of 28
    candidates refused with no run spent**, 22 runs spent against 112 for a
    sweep; **all three deployments refuted** (+22.5→+27.0%, +26.1→+21.1% and a
    task lost, -3.4% single-run → +4.0% repeated); the `window3` control:
    +7.6% predicted, +12.4% measured, +81.8% held out. Five rule revisions.
    *(shot: the dashboard's harness panel — the round table and the verdict
    badges, `lab/rsi/round-*.json` behind it)*
12. **Honesty** — truncation conservatism; float32; single-world family
    comparison (two domains, eight seeds); judge overestimates replay relative
    to measured online; the harness is six tasks, one model, one provider, with
    run-to-run spread up to 90.8% of the baseline, and **no measured saving
    survives**; the loop's value so far is its refusals, not its deploys.
13. **Related work** — Dreamer-style "learning by dreaming" (executes a
    learned model); graph-memory agents (logs, not replay-optimizers); OSTIS
    ecosystem (semantic technology; NIKA as in-ecosystem prior art). Three
    contemporary works frame the harness: Dream-RSI (arXiv 2609.14858,
    recorded history as the simulator), Meta-Harness (arXiv 2603.28052, the
    harness is the object worth searching; full traces beat summaries),
    SoL-Pi (arXiv 2609.20519, criteria frozen before the search, held-out kept
    out of it), GAVEL (arXiv 2609.19315, symbolic model repairs what it can
    itself: 1 LLM query beats 3.4). Bounded search 2026-09-19 found no prior
    OSTIS + exact-replay self-improvement combination.
14. **Reproduce** — `docker compose up -d --build`; `pytest tests/ -q`;
    `PYTHONPATH=python python -m metrics.build_table > docs/results.md`;
    `PYTHONPATH=python ONEIRO_ROUNDS=5 python -m loop > docs/rounds.md`;
    `python demo/run_demo.py`; then
    `PYTHONPATH=python python python/viz.py <subject> --out docs/dream-tree.html`
    and show the page live — hover any node, click any episode.
    Harness: `python harness/run.py --task t01-start-total --policy baseline`;
    `python harness/rsi.py --round 11` (one search round, deploys under the
    frozen criteria); `python harness/rsi.py --show --ledger` (the ten recorded
    rounds and the run ledger); `python harness/publish.py` writes the tree into
    the graph.

## Screenshots (generated, in `docs/shots/`)

- `01-hero.png` — opening view: stats row + constellation + ascent.
- `02-constellation.png` — the strategy graph: node size = replay verdict,
  green glow = deployed winner, arrows = derived-from.
- `03-dream-table.png` — all 21 strategies with verdict bars.
- `04-episodes.png` — episode explorer: full step-by-step recorded experience.
- `05-fullpage.png` — the whole page in one scroll.

Regenerate everything with one command:

```bash
PYTHONPATH=python python python/viz.py demo_1789780697 \
  --out docs/dream-tree.html \
  --title "Oneiro-OSTIS — live demo (island, seed oneiro-0)"
python scripts/take_shots.py   # playwright screenshots into docs/shots/
```
