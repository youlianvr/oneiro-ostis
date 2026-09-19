# Multi-seed series — does the dream improve reliably, and how honest is the judge?

Generated 2026-09-19 against the live stack, 3 rounds per seed:

```bash
PYTHONPATH=python ONEIRO_SEEDS=5 ONEIRO_ROUNDS=3 python -m series island
PYTHONPATH=python ONEIRO_SEEDS=3 ONEIRO_ROUNDS=3 python -m series workshop
```

### island — 5 seeds

| seed | day 1 | final | delta | ratio | winners (by round) | replay est. per ep → measured next day | judge error |
|---|---|---|---|---|---|---|---|
| `oneiro-0` | 137.5 | 252.4 | **+114.9** | 1.84x | cand_alpha_d4 → cand_alpha_d4 → cand_alpha_d4 | 311.1 → 252.4; 296.4 → 252.4 | +58.7, +44.0 |
| `oneiro-1` | 122.5 | 137.2 | **+14.7** | 1.12x | cand_alpha_d1 → cand_farthest_d1 → cand_coastal_d1 | 218.4 → 137.3; 219.4 → 137.2 | +81.1, +82.3 |
| `oneiro-2` | 148.9 | 236.9 | **+88.0** | 1.59x | cand_alpha_d4 → cand_alpha_d4 → cand_alpha_d4 | 300.8 → 236.9; 284.8 → 236.9 | +63.9, +48.0 |
| `oneiro-3` | 117.3 | 184.6 | **+67.3** | 1.57x | cand_alpha_d4 → cand_alpha_d4 → cand_alpha_d4 | 228.2 → 184.6; 217.3 → 184.6 | +43.5, +32.6 |
| `oneiro-4` | 133.8 | 237.8 | **+104.0** | 1.78x | cand_alpha_d4 → cand_alpha_d4 → cand_alpha_d4 | 303.7 → 237.8; 287.2 → 237.8 | +65.9, +49.4 |

- improved seeds: **5/5**; delta mean +77.8, median +88.0, min +14.7, max +114.9; ratio mean 1.58x
- judge calibration (10 deployed winners): bias +56.9 (replay − measured), MAE 56.9, mean relative error 29.7%

- recording conflicts across all dream trees: 0

### workshop — 3 seeds

| seed | day 1 | final | delta | ratio | winners (by round) | replay est. per ep → measured next day | judge error |
|---|---|---|---|---|---|---|---|
| `workshop-0` | 16.6 | 79.2 | **+62.6** | 4.77x | ws_cart_wof → ws_cart_wof → ws_cart_wof | 79.2 → 79.2; 79.2 → 79.2 | -0.0, -0.0 |
| `workshop-1` | 10.4 | 53.1 | **+42.6** | 5.08x | ws_cart_wof → ws_cart_wof → ws_cart_wof | 70.5 → 53.1; 66.1 → 53.1 | +17.4, +13.1 |
| `workshop-2` | 4.3 | 47.1 | **+42.8** | 11.07x | ws_cart_wof → ws_cart_wof → ws_cart_wof | 68.5 → 47.1; 63.1 → 47.1 | +21.4, +16.1 |

- improved seeds: **3/3**; delta mean +49.3, median +42.8, min +42.6, max +62.6; ratio mean 6.97x
- judge calibration (6 deployed winners): bias +11.3 (replay − measured), MAE 11.3, mean relative error 22.9%

- recording conflicts across all dream trees: 0
## Reading the numbers

- **8/8 seeds improved after a single dream** (5 island + 3 workshop): island mean +77.8 (1.58x), workshop mean +49.3 (6.97x).
- The workshops' larger ratios come from a deliberately uninformed day-1 policy (planks instead of the combo cart); the island's day-1 policy was closer to reasonable, so its deltas are smaller — except seed oneiro-1, where one dream gained only +14.7: the honest lower bound of the method on this world.
- **The judge is not an oracle.** Replay scores carry a positive bias (island +56.9, ~29.7% relative; workshop +11.3, ~22.9% relative): the replay walk follows recorded transitions that can score better than the episode it started from, and it credits them. Ranking survived the bias in all 8 runs — every deployed winner beat the incumbent — but the absolute estimate must not be quoted as a prediction.
- **0 recording conflicts** across all dream trees: the deterministic worlds never produced two different outcomes for the same (signature, action), which is exactly what the tree's consistency check is for.
- Limitation that remains: seeds differ by world instance, not by task family; the two domains are the only ones implemented so far.
