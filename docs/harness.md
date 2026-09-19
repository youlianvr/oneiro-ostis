# RSI harness: searching the harness itself, judged by replay

The island experiments search *strategies inside a deterministic world*. This
harness searches the thing that surrounds a real coding agent: what it is shown,
what it keeps, when it stops. The subject is our own agent loop
(`harness/agent.py`), the judge is the same idea as the island's dream cycle
(decide from the recording, not by running the world), and the proposer is a
language model that reads full trajectories.

Three papers set the frame. Dream-RSI (arXiv 2609.14858) makes history the
simulator. SoL-Pi freezes the acceptance rules before the search and keeps a
held-out set out of it. Meta-Harness shows that a proposer given full
trajectories beats one given summaries. All three are implemented here, and this
document is mostly about where they break: two criteria revisions and one
measured refutation of the judge's own estimate came out of running it.

## What is searched

A policy is a program (`harness/policy.py`) with eleven fields: whether the file
list and the initial test output are shown, how much history is kept
(`context_mode`, `window_steps`), how long tool output may be
(`observation_chars`), how many lines a read returns, the step budget, whether
failing tests send the agent back in, and `temperature`. The proposer may vary
only these; a descriptor with any other field is rejected.

## The corpus, and one rule about recordings

Six small Python tasks, each a repository with visible tests and a hidden test
file the agent never sees (`harness/tasks/`). Four are the search set
(`t01-start-total`, `t02-clamp-bounds`, `t03-parse-duration`, `t05-retry-backoff`);
two are held out (`t04-dedupe-order`, `t06-csv-column-total`) and a policy that
influenced the search never touched them.

Only runs that terminated normally (`finished`, `max_steps`, `stopped`) are
evidence. A run that ended in a timeout, a provider refusal or an error says
nothing about the policy that produced it and its token count is partial, so it
neither calibrates the judge nor sets the baseline. This rule was added after it
turned out to matter, see *Corrections* below.

The agent is ours: a tool loop over `list_files`, `read_file`, `write_file`,
`edit_file`, `run_tests`, `run_command`, on a scratch copy of the task. The model
is `deepseek-ai/DeepSeek-V4-Flash-0731` through the provider at
`inference.dahl.global`. Every episode is recorded as `record.json`: the exact
messages sent, the tool calls, the observations returned, the tokens billed, and
the history length at each step. **That recording is what the judge replays.**

## The judge: what replay can decide, and what it cannot

`harness/replay.py` rebuilds, from a recording alone, the messages a candidate
policy *would have sent*, and computes what they would have cost. No agent run,
no provider call, no tokens: a test asserts this.

Measured on the six normal recordings:

| quantity | value |
|---|---|
| episodes the judge replays | 6 (33 steps) |
| prompt sizes rebuilt character for character | **6/6** |
| token model, cross-validated (fit on other tasks, predict this one) | mean relative error **5.9%**, worst 17.3% |
| a candidate identical to the recorded policy | decisions replayed **1.00**, cost ratio 1.00 |

The incomplete half is the important half. A candidate diverges from the
recording the moment it changes what the model sees, and from that step on the
recording says nothing about what the model would do. The judge therefore splits
every candidate into:

- **exact** steps: the prompt is rebuilt as recorded, the cost is a measurement;
- **abstained** steps: the prompt differs, the cost is an extrapolation.

`decision_replayable` is the share of exact steps. It is a first-class number,
not a footnote.

What it still cannot do, and the measurement that proved it: **coverage counts
aligned prompts, not the steps the agent will then take.** A policy that trims
history keeps most prompts alignable while changing how the agent behaves. See
the control experiment below.

## The loop

`harness/rsi.py` runs five steps, in this order, because the order is the method:

1. **Freeze** the acceptance rules to disk before any search (`lab/rsi/criteria.json`).
2. **Propose**: the model reads full trajectories (not summaries), every earlier
   candidate's estimate and online result, what the online runs actually
   measured, the measured control policies, and the judge's briefing about what
   it could not judge.
3. **Judge** every candidate from the recordings. No runs, no tokens.
4. **Gate**: a candidate is deployable only on evidence, and which evidence
   depends on what it changes.
5. **Deploy and measure**: online on the search set first, then on the held-out
   tasks. Held-out numbers are the only ones quoted as results.

## The acceptance rules, and why they have four versions

Three revisions happened during the search. None of them moved a numeric
threshold. Each one repaired a way the gate could have claimed more than it knew,
and each was forced by a measurement. The rules that applied to a round are
stored *in that round*, so a later revision never relabels an earlier result.

| version | change | evidence that forced it |
|---|---|---|
| v1 | saving threshold 0.15, at most one task lost online, a coverage field named but read by no code | none, it was the starting point |
| v2 | coverage floor 0.5 wired into the gate; the verdict split into `passed_efficiency`, `passed_evidence`, `passed_gate` | rounds 2 and 3 deployed candidates with `decision_replayable` **0.0**: the saving was an extrapolation with no replayed step behind it |
| v3 | the online path: a candidate the judge cannot replay is measured online inside the round budget instead of being silently banned, and the proposer is told which families the judge cannot judge | round 4 proposed three candidates at +22..27% predicted saving, all with 0% replayed decisions, and the round measured nothing at all |
| v4 | a policy that changes what the agent is shown or how long it may run is measured online before it may be deployed, whatever its replay coverage | the control measurement of the hand-written `window3`: predicted to save 7.5% at 73% coverage, measured **20.4% more** prompt tokens, because with less history the agent took more steps on five of six tasks (t02: 6 to 9, t06: 6 to 10) |

`python harness/rsi.py --recheck` re-applies the frozen rules to what the rounds
recorded. Under v2, **3 of the 8 verdicts recorded before it would be refused, and
both deployments are among them.**

## Results so far

Incumbent (the recorded baseline, averaged over normal runs, solved runs preferred):

| set | tasks | solved | prompt tokens |
|---|---|---|---|
| search | 4 | 4/4 | 38,685 |
| held out | 2 | 1/2 | 16,967 |

Eight rounds, 22 candidates, two deployments, and the deployments are the
problem:

| round | criteria | candidates | deployed | measured online | transferred |
|---|---|---|---|---|---|
| 1 | v1 | 3 | none | — | — |
| 2 | v1 | 3 | `no_initial_tests` | search **+27.0%** tokens, 4/4 solved | no |
| 3 | v1 | 2 | `no_initial_tests_window` | search **+21.1%** tokens, 4/4 solved | no |
| 4 | v2 | 3 | none (refused on evidence) | — | — |
| 5 | v3 | 3 | none (nothing cleared the saving threshold) | — | — |
| 6 | v3 | 3 | none (nothing cleared the saving threshold) | — | — |
| 7 | v3 | 2 | none (nothing cleared the saving threshold) | — | — |
| 8 | v4 | 3 | none (measured and refused) | predicted +32.0%, measured **+1.5%**, 4/4 solved | — |

The two deployments are the honest headline: **both cost more than the baseline,
not less.** They were deployed when the gate had no evidence requirement and the
baseline was contaminated (see *Corrections*), and their savings were prediction
artifacts of exactly the kind the later criteria were written to catch.

Round 8 is what the loop looks like once it works: the proposer offered three
variants of the family the judge cannot replay, the judge abstained, the gate sent
them down the online path, the measurement contradicted the prediction (+1.5%
instead of +32.0%), and the round recorded the refusal and never touched the
held-out tasks.

### The control experiment

Hand-written policies, judged offline (free), then measured online. `window3` is
the clearest result of the whole harness:

| policy | judge: predicted saving | decisions replayed | measured: search | measured: held-out | held-out solved |
|---|---|---|---|---|---|
| `window3` | +7.5% | 73% | **+20.4%** | **+71.7%** | 1/2 (unchanged) |

Trimming the agent's history is not a saving. The agent, with less context,
re-reads and re-checks: tool calls rise from 4 to 7 on `t02-clamp-bounds` and
from 4 to 8 on `t06-csv-column-total`, and the extra steps cost more than the
trimmed prompt saves. The judge could not see this, because it replays a fixed
set of recorded steps while the policy changes how many steps happen. That is
the boundary this work is about, and it is now an acceptance rule (v4) rather
than a footnote.

### What it saved against judging online

| quantity | value |
|---|---|
| candidates proposed | 22 |
| refused on recordings alone | 16 |
| decided online | 3 |
| deployed | 2 |
| deployed without replayed evidence | 2 |
| online runs spent | 16 |
| online runs if every candidate were measured | 88 |
| runs saved | 72 (**5.5x**) |

The counterfactual is the plain one: one online run per candidate per search
task. It compares against the same decision made without recordings, not against
the papers' numbers, which run on different tasks, models and budgets. The
control experiment above is outside this ledger: 6 runs, spent on purpose.

## Corrections

The first baseline this loop used picked, per task, the cheapest recording, which
on `t04-dedupe-order` was a one-step run that ended in an error. Against a bar
like that every real attempt looks wasteful, and the held-out deltas came out at
+25% and +24%. Recomputed against runs that terminated normally, and comparing
tokens only on tasks both sides solved, the same runs read +27.0% and +21.1% on
the search set (see the table). The originals are still in the round files:
`python harness/rsi.py --recompare` wrote the corrected numbers beside them as
`comparison_corrected` and recorded the reason. A correction that erases what it
corrects is not a correction.

## Honest limitations

- **Six tasks, two held out.** Enough to falsify a claim, not enough to support
  one. The held-out set is where the two deployments failed to transfer.
- **One model, one provider.** The provider's free tier admits paid accounts
  first, so runs were sometimes refused. Refusals are recorded as unmeasured, not
  as failures; a round that hit one says so.
- **Replay judges prompts, not decisions.** Everything replay can say is about
  what the agent *saw* and what that would have cost. Whether the agent then
  solves the task, and how many steps it takes, is settled only by running it.
- **The proposer never found the efficient region.** Everything that cleared the
  gate was hand-written, not proposed. The proposer's candidates were either
  below the saving threshold or in the family the judge cannot replay. That is a
  real result about proposer quality on a small corpus, and it is not flattering.

## Reproducing

```bash
python harness/run.py --task t01-start-total            # one recorded episode
python harness/report.py                                # raw table from the recordings
python harness/rsi.py --init                            # freeze the criteria (once)
python harness/rsi.py --round 9                         # propose, judge, gate, measure
python harness/rsi.py --show --recheck --ledger          # what the rounds established
python harness/rsi.py --reference                        # judge the hand-written policies
python harness/rsi.py --measure-reference window3        # measure one online, as a control
python harness/rsi.py --state                            # the whole loop as JSON (the dashboard reads this)
python harness/publish.py                               # the search tree into the OSTIS graph
python -m pytest harness/tests -q                       # judge, gate and accounting, offline
```
