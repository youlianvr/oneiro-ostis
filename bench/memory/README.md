# bench/memory — the persistent-memory stand

LongMemEval, asked of four kinds of memory that hold the same content. The point
is not the model's score: it is which way of remembering pays off, with the
model held constant and every number traceable to a record in the graph.

## Data

Outside the repository, so a clone stays small. `ONEIRO_LME_DIR` or
`~/.openclaw/datasets/longmemeval`:

| file | size | what it is |
|---|---|---|
| `longmemeval_oracle.json` | 15 MB | 500 questions with only the sessions that hold the answer |
| `longmemeval_s_cleaned.json` | 277 MB | the same questions with the full haystacks (about 500 sessions each) |

Both come from `xiaowu0162/longmemeval-cleaned` on Hugging Face. The cleaned
repository is the one to use: the authors removed sessions that made the
ground-truth answers wrong. The `s` file is read question by question, so it is
never materialised whole in memory, and a run that stops can be re-run from the
file it already has.

Download with curl, not with a browser tab, and check the size afterwards
against the listing above: a truncated `s` file fails only in the middle of a
long run.

## Stages and arms

| stage | haystack | arms | what it answers |
|---|---|---|---|
| `oracle` | evidence sessions only | `full` (everything in context), `none` (no memory) | the benchmark's own setting, so our floor and ceiling sit next to published numbers |
| `s` | full haystack, capped at `--cap` sessions with every evidence session kept | `graph`, `flat`, `none` | the question under test: does the typed graph beat a flat text journal when the needle is among hundreds of sessions |

`full` against `none` measures the task and the model. `graph` against `flat`
measures the store: both arms see byte-identical session text, produced by the
same renderer, and both rank with the same BM25 scorer. The only difference is
how the sessions are kept and what the ranking is allowed to use. The graph
carries the session date as a numeric relation, so a question naming a time
window is filtered inside that window first and similarity only breaks ties;
the journal has the date as text inside a blob.

## Running

```bash
cd projects/ostis/oneiro-ostis
export $(grep -E '^OMNIROUTE_API_KEY=' ../../.env | head -1)

# smoke: three questions, both stores, live graph
python bench/memory/run.py --stage s --limit 3 --arms graph,flat,none --run-tag smoke-s-1

# the comparison
python bench/memory/run.py --stage s --questions 50 --cap 100 --k 5 --run-tag s-50-1

# the published setting (evidence only)
python bench/memory/run.py --stage oracle --questions 50 --run-tag oracle-50-1
```

A run writes three things:

- `~/.openclaw/bench-memory/runs/<tag>.json`, rewritten after every question, so
  an interrupted run still holds its cells;
- `~/.openclaw/bench-memory/runs/<tag>-report.md`, the same numbers as a table;
- one record per question, arm and repetition into OSTIS, through the bridge.

The dashboard reads the graph and shows the runs at `http://localhost:8130`
(section "Память: бенчмарк"). Every row there can be walked back to the record
that produced it.

## What a record holds

`memory_bench_result_<tag>_<question>_<arm>_r<n>` in the graph carries the
question type, the arm, whether the judge passed, which model answered and which
judged, the retrieved session ids, the evidence ids, recall@k, and the token
cost. Recall exists only for the retrieval arms: `full` and `none` read fixed
context and cannot have one.

## Honesty rules this stand is built on

- No number without a run: every figure in a report comes from records in the
  graph, and the report names the run tag that produced it.
- One row, one model: the answer and judge chains record the model that actually
  served each call, and provider failures are recorded as failures rather than
  quietly retried into a different number.
- The floor is measured, not assumed: `none` is a real arm, so "memory helps"
  is a difference between two measured columns.
- The comparison is only as clean as its content: if the two stores ever hold
  different text, the run is invalid. `tests/test_memory_bench.py` guards the
  renderer and both ranking paths offline.
