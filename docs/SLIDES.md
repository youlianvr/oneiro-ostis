# Oneiro-OSTIS — slides (outline with real numbers)

1. **Title** — Oneiro-OSTIS: an agent that dreams over its own recordings in
   an OSTIS knowledge graph.
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
   *(screenshot slot: sc-web at localhost:8000)*
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
9. **Demo** — one command; 21 candidates / 3 episodes / 120 steps / 76
   transitions in 9.1 s; day 2 +114.9 (+84 %); 0 conflicts.
10. **Honesty** — truncation conservatism; float32; LLM adapter unwired in
    these numbers; single-world comparison.
11. **Related work** — Dreamer-style "learning by dreaming" (executes a
    learned model); graph-memory agents (logs, not replay-optimizers); OSTIS
    ecosystem (semantic technology). Bounded search 2026-09-19 found no prior
    OSTIS + exact-replay self-improvement combination.
12. **Reproduce** — `docker compose up -d --build`; `pytest tests/ -q`;
    `PYTHONPATH=python python -m metrics.build_table > docs/results.md`;
    `PYTHONPATH=python ONEIRO_ROUNDS=5 python -m loop > docs/rounds.md`;
    `python demo/run_demo.py`.
