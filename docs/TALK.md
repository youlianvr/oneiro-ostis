# Oneiro-OSTIS — talk script (5–7 minutes)

Everything below is measured; no slide promises anything the repo cannot
reproduce in one command.

## 0:00–0:40 — Hook

"Every agent forgets. Mine doesn't — and not just because it logs things.
Its entire life is a graph: every step it ever took, what the world showed it,
what it chose, and what that cost. And when it sleeps, it *dreams*: it replays
its own recordings, tries twenty-one different futures in nine seconds, and
wakes up better. Today: 137.5 points. Tomorrow, after one dream: 252.4.
Nothing was executed during the night — only recordings were read."

## 0:40–1:40 — The world and the graph

- World: deterministic island expedition — 9 locations, 8 dig sites,
  40 steps, travel costs 0.1, delivery multipliers 1.0/1.2/1.5. Same seed →
  identical day, forever (sha256 values, no clock, no hash randomization).
- The graph (OSTIS / sc-memory): attempts are nodes created by C++ agents
  (`action_record_attempt`), chained chronologically; the bridge adds
  provenance and the trajectory fields — episode, step index, the world state
  *before* the action, the legal actions *before* the action, the strategy,
  the note.
- Strategies and dreams are also graph citizens: `concept_strategy` nodes
  carry the JSON descriptor, the replay verdict and the measured online
  score. Show it in sc-web (`http://localhost:8000`).

## 1:40–2:40 — Stage 3: the graph remembers what matters

Table (`docs/results.md`):

- context-only window: recall 0.12;
- flat list: recall 1.00 but provenance 0.00;
- OSTIS memory: recall 1.00, order 1.00, provenance 1.00, 0 contradictions;
- ablate temporal chaining → order 0.58; ablate provenance → provenance 0.00.

Line: "The ablations are real switches in the C++ agent and the ontology,
not dashboard toggles."

## 2:40–4:00 — The dream (the core)

- Day: strategy acts; every step recorded.
- Exploration: two survey walks widen the recording coverage.
- Night: candidates proposed (deterministic sweep today; an OpenAI-compatible
  LLM adapter is wired with strict validation — offline fallback always).
- Judge: exact replay over the recordings. Signature = (location, carried
  artefact, artefacts taken from the current site) + action. Every outcome
  comes from a recording; an unrecorded decision truncates the episode
  (coverage is reported, never fabricated).
- Proof of "no execution": tests patch `ExpeditionWorld.step` to raise and
  replay still gives identical numbers.

## 4:00–4:50 — Results (the island)

- Recursive loop (`docs/rounds.md`): round 1 weak_wander 137.5 →
  dream → cand_alpha_d4 → rounds 2–5 stable at 252.4 — the value of the best
  strategy found by exhaustively running the whole sweep in the world offline.
- Demo (`docs/demo-log.md`): 21 candidates, 3 episodes / 120 steps / 76
  transitions judged in 9.1 s; day 2 measured **+114.9 points (+84 %)**;
  0 recording conflicts.

## 4:50–5:50 — Why it is not a toy: the same cycle over a real coding agent

- The island is a world we wrote, so it proves the machinery, not the use.
  Take the same loop and point it at a coding agent instead: our own loop
  (`harness/agent.py`), six tasks with hidden tests, four in the search set and
  two held out, model `DeepSeek-V4-Flash-0731` on a host but not a model of ours.
- The judge, ten rounds: 6 of 6 recorded episodes rebuilt character for
  character, token model 5.9% mean error, **19 of 28 candidates refused on
  recordings alone, no run spent**; 22 runs spent against 112 for a sweep.
- Now the honest half, and this is the part I would trust us on: **all three
deployments failed their own promise** (+22.5% predicted → +27.0% measured;
  +26.1% → +21.1% and a task lost; –3.4% on single runs → +4.0% once repeated).
  Every fix to the acceptance rules came from one of those failures: a coverage
  floor, then an online path, then the rule that a policy changing the agent's
  context may never be deployed on a replay estimate (the `window3` control:
  +7.6% predicted, **+12.4% measured**, held-out **+81.8%**), then three runs
  per task before any number is quoted.
- Line: "The judge cannot tell you what the agent will do next, only what it
did. That is a narrow guarantee, and it is exactly as wide as we can defend."
- The tree lives in the same graph as the island's strategies:
  `concept_harness` nodes carry policy, estimate, verdict and the online
  comparison; the dashboard shows all ten rounds and the ledger.

## 5:50–6:30 — Honesty corner

- Judge is conservative: under-covered candidates get truncated, so the dream
  prefers paths it has seen — coverage column is in every table.
- Scores are float32 in the KB; exactness tests use a 1e-4 tolerance.
- Improvement is a controlled single-world comparison, not a statistical
  claim; the harness is six tasks, one model, one provider, and its run-to-run
  spread reaches 90.8% of the baseline on one task.
- **No measured saving survives anywhere.** The harness loop's value so far is
  its refusals, not its deploys, and we report it that way.

## 6:30–7:30 — Live demo (if time and stack allow)

```bash
python demo/run_demo.py
```

Narrate the transcript: day 1 line, the attempts table (provenance visible),
the dream's verdict table with coverage 1.00, day 2 score. Open sc-web on
`localhost:8000` and show a `strategy_cand_alpha_d4` node.

## Anticipated questions

- **"Isn't this just RL?"** No learned value function and no environment
  interaction during the dream: the judge is a lookup over recordings; the
  policy space is a small explicit descriptor.
- **"Why OSTIS and not SQL?"** The point of the entry: experience, strategies
  and dream history as semantic graph entities — one uniform structure that
  sc-web displays and future reasoning agents can query; the C++ agent layer
  is where the recording happens.
- **"What breaks it?"** Stochastic environments (conflicting recordings —
  the tree's consistency checker is the alarm) and large state spaces
  (signature collapse).
- **"Did the harness save anything?"** No, and we measure it instead of
  claiming it: three deployments, three refutations, ten rounds, five rule
  revisions. What is measured is the cost side: 22 agent runs spent where a
  sweep costs 112.
- **"Why trust the estimates at all?"** Because they are labelled as estimates
  and bounded: a saving claim needs at least half the candidate's decisions
  replayed, and any policy that changes the agent's context goes online before
  deployment whatever its coverage.
