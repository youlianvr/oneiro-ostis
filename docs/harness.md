# RSI harness: searching the harness itself, judged by replay

The island experiments search *strategies inside a deterministic world*. This
harness searches the thing that surrounds a real coding agent: what it is shown,
what it keeps, when it stops. The subject is our own agent loop
(`harness/agent.py`), the judge is the same idea as the island's dream cycle
(decide from the recording, not by running the world), and the proposer is a
language model that reads full trajectories.

Four papers set the frame. Dream-RSI (arXiv 2609.14858) makes history the
simulator. SoL-Pi freezes the acceptance rules before the search and keeps a
held-out set out of it. Meta-Harness shows that a proposer given full
trajectories beats one given summaries. GAVEL (arXiv 2609.19315) is robotics,
not agent harnesses, but its division of responsibility is ours: an explicit
symbolic model decides everything it can decide for free (it repairs plans whose
corrections follow from action semantics), and the expensive, error-prone path
(asking the LLM again) is reserved for what the model cannot decide. Their
measured result is the same argument ours makes: graph repair alone with one
query beat a feedback loop with 3.4 queries. Here the symbolic model is the
replay judge and the expensive path is online measurement. All four are
implemented here, and this document is mostly about where they break: four
criteria revisions, and every saving this loop has claimed being killed by the
next honest measurement.

## What is searched

A policy is a program (`harness/policy.py`) with eleven fields: whether the file
list and the initial test output are shown, how much history is kept
(`context_mode`, `window_steps`), how long tool output may be
(`observation_chars`), how many lines a read returns, the step budget, whether
failing tests send the agent back in, and `temperature`. The proposer may vary
only these; a descriptor with any other field is rejected.

## The corpus, and two rules about recordings

Six small Python tasks, each a repository with visible tests and a hidden test
file the agent never sees (`harness/tasks/`). Four are the search set
(`t01-start-total`, `t02-clamp-bounds`, `t03-parse-duration`, `t05-retry-backoff`);
two are held out (`t04-dedupe-order`, `t06-csv-column-total`) and a policy that
influenced the search never touched them.

Two rules decide what counts as evidence, both of them added after they turned
out to matter:

1. **Only runs that terminated normally** (`finished`, `max_steps`, `stopped`)
   are evidence. A run that ended in a timeout, a provider refusal or an error
   says nothing about the policy that produced it, and its token count is
   partial, so it neither calibrates the judge nor sets the baseline.
2. **Only runs that solved the task are comparable on cost.** A task neither side
   solved burns steps until the budget ends; counting that as a cost increase
   punishes a policy for failing exactly as much as the baseline.

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

What the judge still cannot do, and the measurements that proved it:
**coverage counts aligned prompts, not the steps the agent will then take**, and
**a predicted saving is not a measured one, however careful the model.** Both are
now acceptance rules rather than footnotes.

### Judge calibration: every hand-written policy, judged and then measured

The full control experiment: all reference policies estimated by the judge from
recordings alone, then measured online with 3 runs per task (17 to 32 runs
each; every label on disk counts). `bias = judge prediction − online measured`.

| policy | judge | replayable | online search | online held-out | bias |
|---|---|---|---|---|---|
| baseline | +0.0% | 100% | +20.6% | +10.4% | −20.6% (the noise floor) |
| windowed | +0.0% | 100% | +1.3% | +9.9% | −1.3% |
| window3 | +7.5% | 73% | +12.4% | +81.8% | −4.8% |
| window2 | +15.1% | 55% | **−10.8%** | +0.0% | +25.9% |
| terse | +32.6% | 0% | +19.7% | +47.3% | +12.9% |
| blind | +33.7% | 0% | +62.9% | +58.1% | −29.3% |
| cautious | +0.0% | 100% | +43.0% | +21.5% | −43.0% |

Readings, in the order they matter:

1. **The noise floor is ±20%.** Rerunning the baseline itself moved its own
   tokens by +20.6% (search) and +10.4% (held-out). Any single-run comparison
   smaller than that is indistinguishable from nothing, which is why three runs
   per task are the minimum before a number is quoted.
2. **The judge can be wrong in both directions.** `terse` was judged a 32.6%
   saving and measured 19.7%; `window2` was judged a 15.1% *cost* and measured
   a 10.8% *saving* — the only policy that actually saved tokens. An
   extrapolation with 55% coverage is not a mild correction of the truth, it is
   a different experiment.
3. **The two candidates with 0% replayable coverage were the two worst
   online.** `blind` (+62.9%) and `terse` (+19.7%, held-out +47.3%): the judge
   said save, the world said spend. A 0%-coverage estimate is noise dressed as
   a number.
4. **Cautious's 43% increase would have passed a capability-only gate.** It
   solves everything and replays perfectly; it is just expensive. The
   efficiency gate is what catches it, and only the online measurement sees
   the size.
5. **window2 saved on the search set and did not transfer** (held-out +0.0%):
   even the one real saving is a search-set phenomenon, exactly the failure
   mode the held-out rule exists to expose.

The calibration set is shown to the proposer as facts about the world, and it
is the reason the loop's later criteria revisions were written before the next
search rather than after the next disappointment.

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
   tasks, at least three runs per task. Held-out numbers are the only ones
   quoted as results.

## The acceptance rules, and why they have five versions

Four revisions happened during the search. None of them moved a numeric
threshold. Each one repaired a way the gate could have claimed more than it knew,
and each was forced by a measurement, not by taste. The rules that applied to a
round are stored *in that round*, so a later revision never relabels an earlier
result.

| version | change | evidence that forced it |
|---|---|---|
| v1 | saving threshold 0.15, at most one task lost online, a coverage field named but read by no code | none, it was the starting point |
| v2 | coverage floor 0.5 wired into the gate; the verdict split into `passed_efficiency`, `passed_evidence`, `passed_gate` | rounds 2 and 3 deployed candidates with `decision_replayable` **0.0**: the saving was an extrapolation with no replayed step behind it |
| v3 | the online path: a candidate the judge cannot replay is measured online inside the round budget instead of being silently banned, and the proposer is told which families the judge cannot judge | round 4 proposed three candidates at +22..27% predicted saving, all with 0% replayed decisions, and the round measured nothing at all |
| v4 | a policy that changes what the agent is shown or how long it may run is measured online before it may be deployed, whatever its replay coverage | the control measurement of the hand-written `window3`: predicted to save 7.5% at 73% coverage, measured **12.4% more** prompt tokens over three runs per task, because with less history the agent took more steps on five of six tasks |
| v5 | at least three runs per task, averaged, before any online number is quoted | round 9 deployed on a single run per task: the search set read **-3.4%**; with three runs per task the same policy reads **+4.0%** overall and no transfer, with per-task spreads of 34% and 91% of the baseline |

`python harness/rsi.py --recheck` re-applies the frozen rules to what the rounds
recorded. Under v2, **3 of the verdicts recorded before it would be refused, and
both deployments are among them.**

## Results so far

Incumbent (the recorded baseline, averaged over normal runs, solved runs preferred):

| set | tasks | solved | prompt tokens |
|---|---|---|---|
| search | 4 | 4/4 | 38,685 |
| held out | 2 | 1/2 | 16,967 |

Eleven rounds, 29 candidates, four deployments, and for ten rounds not one
survived:

| round | criteria | candidates | deployed | measured online | after repeats |
|---|---|---|---|---|---|
| 1 | v1 | 3 | none | — | — |
| 2 | v1 | 3 | `no_initial_tests` | search **+27.0%** tokens, 4/4 solved | not repeated |
| 3 | v1 | 2 | `no_initial_tests_window` | search **+21.1%** tokens, 4/4 solved | not repeated |
| 4 | v2 | 3 | none (refused on evidence) | — | — |
| 5 | v3 | 3 | none (nothing cleared the saving threshold) | — | — |
| 6 | v3 | 3 | none (nothing cleared the saving threshold) | — | — |
| 7 | v3 | 2 | none (nothing cleared the saving threshold) | — | — |
| 8 | v4 | 3 | none (measured and refused) | predicted +32.0%, measured **+1.5%** | — |
| 9 | v4 | 3 | `no_initial_tests_deploy` | predicted +32.0%, measured **-3.4%**, transferred | **+4.0%, no saving** |
| 10 | v5 | 3 | none (nothing cleared the saving threshold) | — | — |
| 11 | v5 | 1 | `no_initial_tests_obs1500` | search **−13.3%**, held-out **−28.5%**, 4/4 + 1/2 solved, **transferred** | this is the measurement |

Round 11 is the first deployment the whole apparatus is built for: the judge
abstained (0% replayed decisions), the online path measured it with three runs
per task, capability held on every comparable task, and the saving appeared on
both the search set and the held-out set the search never saw. The policy is
two fields: no initial test output in the first prompt, and longer tool
observations (1500 instead of 1000 characters). The second field is the
interesting one: round 2 (`no_initial_tests` alone) cost +27%, and the
round-11 pair saves, so the *combination*, not either field, is what works.
That is a fact only an online measurement could have produced, and exactly the
kind the replay judge cannot see.

The headline is no longer purely negative, but its history is: ten rounds
produced nothing defensible, and the first defensible saving arrived only after
four criteria revisions had shut every dishonest path. The negative results are
not the cost of the method, they are the method working.

### Round 9 in detail, because it is the whole argument

The policy is one line: do not put the initial test output in the first prompt.
The judge abstained on it (0% replayed decisions, the first message differs from
every recording), so it went down the online path and was measured:

| task | baseline | three runs | mean | spread |
|---|---|---|---|---|
| search: t01-start-total | 7,489 | 6,095 / 6,098 / 6,097 | **-18.6%** | 0% |
| search: t02-clamp-bounds | 9,072 | 8,315 / 8,389 / 8,243 | -8.3% | 2% |
| search: t03-parse-duration | 8,824 | 12,086 / 12,126 / 15,083 | **+48.4%** | 34% |
| search: t05-retry-backoff | 13,300 | 10,855 / 14,433 / 22,929 | +20.8% | **91%** |
| held out: t06-csv-column-total | 9,115 | 6,158 / 6,151 / 6,142 | -32.5% | 0% |

All comparable tasks: baseline 47,800 tokens, mean 49,733 (**+4.0%**). The
single-run measurement the round made reads -3.4% on the search set and -32.4%
on the held-out task, which is how a policy gets deployed on noise: one sample
per task landed on the good side of a 91% spread. `t04-dedupe-order`, unsolved by
both sides, is excluded: its cost is not comparable work.

### The control experiment

All hand-written policies, judged offline (free), then measured online, three
runs per task. Full table and readings in the calibration section above; the
short form: the judge's bias spans −43% to +26%, the provider's noise floor is
about ±20%, and `window2` (judged +15.1% cost) turned out to save 10.8% —
an extrapolation is not a mild correction of the truth, it is a different
experiment.

### What it saved against judging online

| quantity | value |
|---|---|
| candidates proposed | 29 |
| refused on recordings alone | 19 |
| decided online | 7 |
| deployed | 4 |
| deployed without replayed evidence | 4 |
| online runs spent | 26 |
| online runs if every candidate were measured | 116 |
| runs saved | 90 (**4.5x**) |

The counterfactual is the plain one: one online run per candidate per search
task. It compares against the same decision made without recordings, not against
the papers' numbers, which run on different tasks, models and budgets. The
control and repeat measurements are outside this ledger: they were spent on
purpose, to check claims rather than to make them.

## Corrections

Two corrections, both written down beside what they correct rather than instead
of it.

**The baseline.** The first version picked, per task, the cheapest recording,
which on `t04-dedupe-order` was a one-step run that ended in an error. Against a
bar like that every real attempt looks wasteful, and the held-out deltas came out
at +25% and +24%. Recomputed against normal runs, and comparing tokens only on
tasks both sides solved, the same runs read +27.0% and +21.1% on the search set.
`python harness/rsi.py --recompare` wrote the corrected numbers beside the stored
ones, with the reason.

**The repeats.** Round 9's deployment was made on one run per task. Its repeat
check is stored in the round as `repeat_check`, with the reason, and criteria v5
was written because of it. A correction that erases what it corrects is not a
correction.

## Honest limitations

- **Six tasks, two held out.** Enough to falsify a claim, not enough to support
  one. Every saving this loop produced has been falsified.
- **One model, one provider.** The provider's free tier admits paid accounts
  first, so runs were sometimes refused. Refusals are recorded as unmeasured, not
  as failures; a round that hit one says so.
- **Replay judges prompts, not decisions.** Everything replay can say is about
  what the agent *saw* and what that would have cost. Whether the agent then
  solves the task, and how many steps it takes, is settled only by running it.
- **The proposer never found the efficient region.** Everything that cleared the
  gate was either hand-written or a variation of the one family it kept
  proposing. On a corpus this small, that is a real result about proposer
  quality, and it is not flattering.
- **The saving is real on two tasks and negative overall.** Round 9's policy
  halves the prompt on `t01` (-18.6%, spread 0%) and `t06` (-32.5%), and gives it
  back with interest on `t03` (+48%) and `t05` (+21%). A per-task policy would use
  it; a single harness for all six tasks cannot.

## Reproducing

```bash
python harness/run.py --task t01-start-total            # one recorded episode
python harness/report.py                                # raw table from the recordings
python harness/rsi.py --init                            # freeze the criteria (once)
python harness/rsi.py --round 10                        # propose, judge, gate, measure
python harness/rsi.py --show --recheck --ledger          # what the rounds established
python harness/rsi.py --reference                        # judge the hand-written policies
python harness/rsi.py --measure-reference window3 --times 3   # measure a control, three runs per task
python harness/rsi.py --repeat-round 9 --times 3         # check a claim against the noise floor
python harness/rsi.py --state                            # the whole loop as JSON (the dashboard reads this)
python harness/publish.py                               # the search tree into the OSTIS graph
python -m pytest harness/tests -q                       # judge, gate and accounting, offline
```
