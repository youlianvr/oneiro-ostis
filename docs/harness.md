# RSI harness: searching the harness itself, judged by replay

The island experiments search *strategies inside a deterministic world*. This
harness searches the thing that surrounds a real coding agent: what it is shown,
what it keeps, when it stops. The subject is our own agent loop (`harness/agent.py`),
and the judge is the same idea as the island's dream cycle: decide from the
recording, not by running the world.

Three papers set the frame. Dream-RSI (arXiv 2609.14858) makes history the
simulator. SoL-Pi freezes the acceptance rules before the search and keeps a
held-out set out of it. Meta-Harness shows that a proposer given full
trajectories beats one given summaries. All three are implemented here, and the
places where they break are recorded rather than hidden.

## What is searched

A policy is a program (`harness/policy.py`) with eleven fields: whether the file
list and the initial test output are shown, how much history is kept
(`context_mode`, `window_steps`), how long tool output may be
(`observation_chars`), how many lines a read returns (`read_lines`), the step
budget (`max_steps`), whether failing tests send the agent back in
(`verify_before_finish`, `max_verify_nudges`), and `temperature`. The proposer
may only vary these; a descriptor with any other field is rejected.

## The corpus

Six small Python tasks, each a repository with visible tests and a hidden test
file the agent never sees (`harness/tasks/`). Four are the search set
(`t01-start-total`, `t02-clamp-bounds`, `t03-parse-duration`, `t05-retry-backoff`);
two are held out (`t04-dedupe-order`, `t06-csv-column-total`) and a policy that
influenced the search never touched them.

The agent is ours: a tool loop over `list_files`, `read_file`, `write_file`,
`edit_file`, `run_tests`, `run_command`, on a scratch copy of the task. The
model is `deepseek-ai/DeepSeek-V4-Flash-0731` through the provider at
`inference.dahl.global`. Every episode is recorded as `record.json`: the exact
messages sent, the tool calls, the observations returned, the tokens billed, and
the history length at each step. **That recording is what the judge replays.**

## The judge: what replay can decide, and what it cannot

`harness/replay.py` rebuilds, from a recording alone, the messages a candidate
policy *would have sent*, and computes what it would have cost. No agent run, no
provider call, no tokens: the tests assert this.

Measured on the seven replayable episodes:

| quantity | value |
|---|---|
| recorded episodes replayed | 7 |
| prompt sizes rebuilt character for character | **7/7** |
| token model, cross-validated (fit on other tasks, predict this one) | mean relative error **6.5%**, max 18.6% |
| a candidate identical to the recorded policy | decisions replayed **1.00**, cost ratio 1.00 |

The incomplete half is the important half. A candidate diverges from the
recording the moment it changes what the model sees, and from that step on the
recording says nothing about what the model would do. The judge therefore splits
every candidate into:

- **exact** steps: the prompt is rebuilt as recorded, the cost is a measurement;
- **abstained** steps: the prompt differs, the cost is an extrapolation.

`decision_replayable` is the share of exact steps. It is a first-class number,
not a footnote: the loop is not allowed to treat an abstention as evidence.

## The loop

`harness/rsi.py` runs five steps, in this order, because the order is the method:

1. **Freeze** the acceptance rules to disk before any search (`lab/rsi/criteria.json`).
2. **Propose**: the model reads full trajectories (not summaries), every earlier
   candidate's estimate and online result, and the judge's own briefing about
   what it could not judge.
3. **Judge** every candidate from the recordings. No runs, no tokens.
4. **Gate**: a candidate is deployable only on evidence. Efficiency comes from
   the judge; capability is never claimed by the judge, only settled online.
5. **Deploy and measure**: online on the search set, then on the held-out tasks.
   Held-out numbers are the only ones quoted as results.

## The acceptance rules, and why they have versions

Two revisions happened during the search. Neither moved a threshold; both
repaired a way the gate could have said more than it knew. The rules that applied
to a round are stored *in that round*, so a later revision never relabels an
earlier result.

| version | change | evidence that forced it |
|---|---|---|
| v1 | `min_predicted_saving` 0.15, at most 1 task lost online, coverage field named but read by no code | — |
| v2 | coverage floor 0.5 wired into the gate; verdict split into `passed_efficiency`, `passed_evidence`, `passed_gate` | rounds 2 and 3 deployed candidates with `decision_replayable` **0.0**: the saving was an extrapolation with no replayed step behind it |
| v3 | the online path: a candidate the judge abstains on is measured online inside the round budget instead of being silently banned; the proposer is handed the list of families the judge cannot judge | round 4 proposed three candidates at +22..27% predicted saving, all with 0% replayed decisions, and the round measured nothing at all |

`python harness/rsi.py --recheck` re-applies the frozen rules to what the rounds
recorded. Under v2, **3 of 8 recorded verdicts would be refused, and both
deployments are among them**:

| round | policy | predicted saving | decisions replayed | passed then | passed now | deployed then |
|---|---|---|---|---|---|---|
| 1 | window_trim | +11.3% | 65% | no | no | no |
| 1 | clip_warnings_obs | +5.6% | 31% | no | no | no |
| 1 | no_repeat_tests | +0.0% | 100% | no | no | no |
| 2 | no_initial_tests | +22.5% | 0% | yes | no | yes |
| 2 | window6_obs1500 | +3.6% | 88% | no | no | no |
| 2 | clip_to_800 | +0.0% | 100% | no | no | no |
| 3 | no_initial_tests_window | +26.1% | 0% | yes | no | yes |
| 3 | no_initial_tests_short_obs | +22.5% | 0% | yes | no | no |

## Results so far

Incumbent (baseline policy, the recordings the loop started from):

| set | tasks | solved | prompt tokens |
|---|---|---|---|
| search | 4 | 4/4 | 57,977 |
| held out | 2 | 1/2 | 9,995 |

Rounds:

| round | candidates | judged | deployed | evidence | held-out solved | transferred |
|---|---|---|---|---|---|---|
| 1 | 3 | 0 | – | none | – | – |
| 2 | 3 | 1 | `no_initial_tests` | none | 1/2 | – |
| 3 | 2 | 2 | `no_initial_tests_window` | none | 1/2 | **no** |
| 4 | 3 | 0 | – | none | – | – |
| 5 | 3 | 0 | – | none | – | – |

Round 5 was proposed by `deepseek-ai/DeepSeek-V4-Flash-0731` after the preferred
proposer `zai-org/GLM-5.3-Flash` was refused by the provider; the round records
which model answered.

### What the loop actually established

- **A real saving family exists, and the loop could not prove it.** Removing the
  initial test output from the first prompt is predicted to save 22–27% of prompt
  tokens, and it is *unjudgeable by replay*: the very first message differs from
  the recording, so nothing aligns and coverage is 0%. Under v1 that was
  deployed on the strength of an extrapolation; under v2 it is refused; under v3
  it is measured online instead.
- **The measured deployments did not transfer.** Both deployed policies solved
  1/2 held-out tasks against the incumbent's 1/2, and cost *more* prompt tokens
  on held-out tasks (+25.4% and +24.3%) than on the search set, where they were
  predicted to save. The saving was a property of the search tasks, not of the
  policy. This is the honest headline result, and it is negative.
- **The judge refuses cheaply.** 11 of 14 proposed candidates were refused on
  recordings alone, with no online run and no token spent on them.

### What it saved against judging online

| quantity | value |
|---|---|
| candidates proposed | 14 |
| refused on recordings alone | 11 |
| deployed | 2 |
| deployed without replayed evidence | 2 |
| online runs spent | 12 |
| online runs if every candidate were measured | 56 |
| runs saved | 44 (**4.7x**) |

The counterfactual is the plain one: one online run per candidate per search
task. It is a comparison against the same decision made without recordings, not
against the papers' numbers, which run on different tasks and models.

## Honest limitations

- **Six tasks, two held out.** The held-out set is too small to support any
  generalisation claim; it is enough to falsify one (and did).
- **One model, one provider.** The provider's free tier admits paid accounts
  first, so runs were occasionally refused; those are recorded as unmeasured,
  never as failures.
- **Replay judges prompts, not decisions.** Everything replay can say is about
  what the agent *saw* and what that would have cost. Whether the agent then
  solves the task is settled only by running it.
- **The online path has not fired yet.** It exists since v3; rounds 4 and 5 had
  no candidate that both cleared the efficiency threshold and failed the
  evidence floor, so no round has taken it. Until one does, the path is
  implemented and untested in production, which this document says rather than
  implies.

## Reproducing

```bash
python harness/run.py --task t01-start-total            # one recorded episode
python harness/report.py                                # table from the recordings
python harness/rsi.py --init                            # freeze the criteria (once)
python harness/rsi.py --round 6                         # propose, judge, gate, measure
python harness/rsi.py --show --recheck --ledger          # what the rounds established
python harness/publish.py                               # the search tree into the OSTIS graph
python -m pytest harness/tests -q                       # the judge and the gate, offline
```
