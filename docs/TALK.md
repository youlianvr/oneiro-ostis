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

## 4:00–5:00 — Results

- Recursive loop (`docs/rounds.md`): round 1 weak_wander 137.5 →
  dream → cand_alpha_d4 → rounds 2–5 stable at 252.4 — the value of the best
  strategy found by exhaustively running the whole sweep in the world offline.
- Demo (`docs/demo-log.md`): 21 candidates, 3 episodes / 120 steps / 76
  transitions judged in 9.1 s; day 2 measured **+114.9 points (+84 %)**;
  0 recording conflicts.

## 5:00–5:40 — Honesty corner

- Judge is conservative: under-covered candidates get truncated, so the dream
  prefers paths it has seen — coverage column is in every table.
- Scores are float32 in the KB; exactness tests use a 1e-4 tolerance.
- LLM adapter implemented but not exercised without a provider.
- Improvement is a controlled single-world comparison, not a statistical
  claim.

## 5:40–6:40 — Live demo (if time and stack allow)

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
