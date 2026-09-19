# Oneiro-OSTIS — demo transcript

Stack: sc-machine at `localhost:8090` (C++ agents), sc-web at `http://localhost:8000`.
Subject: `demo_1789780697` · world: deterministic island expedition, seed `oneiro-0`.

## 0. Before

- strategy nodes in the graph: 0
- attempts recorded for this subject: 0

## 1. Day 1 — the agent acts (current strategy)

- strategy: `weak_wander` — {'name': 'weak_wander', 'site_priority': ['swamp', 'peak', 'cliff', 'cave', 'ruins', 'jungle', 'cove', 'beach'], 'dig_limit': 1, 'deliver_order': ['camp', 'beach', 'cove']}
- result: **137.5** (weak_wander: score=137.5 steps=40 digs=8 deliveries=8)

## 2. The experience lives in the graph

- attempts recorded for the subject: **40**
- retrieval from the KB returns them chronologically with provenance

| # | action | object | outcome | score | strategy | episode |
|---|---|---|---|---|---|---|
| 0 | travel | beach | concept_success | -0.10000000149011612 | weak_wander | demo_1789780697-d1 |
| 1 | dig | beach | concept_success | 0.0 | weak_wander | demo_1789780697-d1 |
| 2 | deliver | beach | concept_success | 15.239999771118164 | weak_wander | demo_1789780697-d1 |
| 3 | travel | cove | concept_success | -0.10000000149011612 | weak_wander | demo_1789780697-d1 |
| … | (36 more) | | | | | |

Open `http://localhost:8000` to browse the same graph in sc-web.

## 3. Exploration day (wider experience for the judge)

- `survey`: 170.8 (survey: score=170.8 steps=40 digs=10 deliveries=10)
- `survey_reverse`: 252.4 (survey_reverse: score=252.4 steps=40 digs=11 deliveries=11)

## 4. The dream — proposals judged by exact replay

- the judge replayed **21 candidates** over 3 recorded episodes (120 steps, 76 transitions) in 8.6s — zero world executions
- recordings consistent: 0 conflicts

| candidate | replay score | per episode | episodes | coverage | uncovered steps | truncated episodes |
|---|---|---|---|---|---|---|
| cand_farthest_d4 | 933.2 | 311.1 | 3 | 1.00 | 0 | 0 |
| cand_alpha_d4 | 933.2 | 311.1 | 3 | 1.00 | 0 | 0 | **WINNER**
| cand_reverse_alpha_d4 | 933.2 | 311.1 | 3 | 1.00 | 0 | 0 |
| cand_coastal_d4 | 933.2 | 311.1 | 3 | 1.00 | 0 | 0 |
| cand_coastal_dl_bcc | 933.2 | 311.1 | 3 | 1.00 | 0 | 0 |
| cand_coastal_dl_ccb | 933.2 | 311.1 | 3 | 1.00 | 0 | 0 |
| weak_wander | 419.3 | 139.8 | 3 | 1.00 | 0 | 0 |

- winner: **`cand_alpha_d4`** → {'name': 'cand_alpha_d4', 'site_priority': ['beach', 'cave', 'cliff', 'cove', 'jungle', 'peak', 'ruins', 'swamp'], 'dig_limit': 4, 'deliver_order': ['cove', 'beach', 'camp']}
- saved to the graph as `strategy_cand_alpha_d4` (class concept_strategy, replay score 933.2)

## 5. Day 2 — the deployed winner acts online

- strategy: `cand_alpha_d4`
- result: **252.4** (cand_alpha_d4: score=252.4 steps=40 digs=11 deliveries=11)

## 6. Verdict

| day | strategy | measured score |
|---|---|---|
| 1 | weak_wander | 137.5 |
| 2 | cand_alpha_d4 | 252.4 |

**The dream improved the measured online score by +114.9 (+84%)** — judged only from recordings, proven in the world.

Graph after the demo: 21 strategy nodes, 160 attempts for the subject, online scores attached to the deployed strategies.
