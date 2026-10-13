# bench/memory — the persistent-memory stand

LongMemEval, asked of four kinds of memory that hold the same content. The point
is not the model's score: it is which way of remembering pays off, with the
model held constant and every number traceable to a record in the graph.

The stand runs on the code the product runs: model calls go through
`oneiro.chat.chat_call` (see `model_chain.py`), sessions and cells through a graph lane of
the benchmark's own (`oneiro.graph_worker` → `oneiro.sc_graph`). The retired `python/llm.py`
and `python/bridge.py` were removed by the v1 rewrite; this stand was re-hosted on their
replacements on 2026-10-13 and the runs made before that (marked below) do not describe the
current code.

## Data

Outside the repository, so a clone stays small. `ONEIRO_LME_DIR` or
`~/.openclaw/datasets/longmemeval`:

| file | size | what it is |
|---|---|---|
| `longmemeval_oracle.json` | 15 MB | 500 questions with only the sessions that hold the answer |
| `longmemeval_s_cleaned.json` | 277 MB | the same questions with their full haystacks |

Both come from `xiaowu0162/longmemeval-cleaned` on Hugging Face. The cleaned
repository is the one to use: the authors removed sessions that made the
ground-truth answers wrong. The `s` file is read question by question, so it is
never materialised whole in memory, and a run that stops can be re-run from the
file it already has.

A haystack's size is a property of the file, not a constant to quote from memory:
measured on the fifty-question sample this stand uses (seed `20260921`, arithmetics in
`dataset.DEFAULT_SAMPLE`), the `s` haystacks are 41 to 53 sessions, 2396 sessions over the
whole sample. `--cap 100` therefore cuts nothing out of this file — it is a bound for a
larger haystack, and evidence sessions are kept whatever it is set to.

Download with curl, not with a browser tab, and check the size afterwards
against the listing above: a truncated `s` file fails only in the middle of a
long run.

## Stages and arms

| stage | haystack | arms | what it answers |
|---|---|---|---|
| `oracle` | evidence sessions only | `full` (everything in context), `none` (no memory) | the benchmark's own setting, so our floor and ceiling sit next to published numbers |
| `s` | full haystack, capped at `--cap` sessions with every evidence session kept | `graph`, `flat`, `none` | the question under test: does the typed graph beat a flat text journal when the needle is among dozens of sessions |

`full` against `none` measures the task and the model. `graph` against `flat`
measures the store: both arms see byte-identical session text, produced by the
same renderer, and both rank with the same BM25 scorer. The only difference is
how the sessions are kept and what the ranking is allowed to use:

- the **graph** arm publishes one typed record per session into a stream of that
  corpus's own and reads the corpus back out of the graph before ranking it. The record's
  labels carry the session's own date as a machine-readable field (`date-epoch=<seconds>`),
  which is what lets a question naming a time window be filtered inside that window first,
  with similarity only breaking ties;
- the **flat** arm writes one text file per corpus, and the session date is words inside
  that text. Its ranking is word search and nothing else, because a journal has no field to
  filter on. Its reads carry `date_epoch = 0` for exactly that reason.

Under the retired bridge the date was a numeric graph *relation* and the body a JSON payload;
the rewrite replaced that vocabulary with typed records, so the date now travels as a field
of the record. What is under test — structure the search can use, against text — is unchanged.

## Running

The graph arm needs a live sc-server. Start one of the stand's own (its own container, its
own volume, its own port) and keep it: stopping it is not deleting it.

```bash
cd projects/ostis/oneiro-ostis
python _tmp/bench-graph.py start --name oneiro-bench-1 --port 50661
python _tmp/bench-graph.py wait  --name oneiro-bench-1 --port 50661

# smoke: one question, both stores, live graph
python bench/memory/run.py --stage s --limit 1 --arms graph,flat,none \
    --run-tag smoke-s-3 --ostis-port 50661

# the comparison, on a named provider with one pinned model per role
python bench/memory/run.py --stage s --questions 50 --cap 100 --k 5 \
    --arms graph,flat,none --ostis-port 50661 \
    --base-url https://justbash-api.annenkov.me/v1 --key-env JUSTBASH_API_KEY \
    --answer-models kimi-k2.5 --judge-models deepseek-v4-pro \
    --run-tag s-50-7

# the published setting (evidence only, no graph)
python bench/memory/run.py --stage oracle --questions 50 --run-tag oracle-50-1 --no-ostis
```

The provider key is read from the environment, then from the repository's `.env`
(`load_key` walks up to eight parents, so the workspace `.env` is found from here). Export
it if you want it in the environment for other tools:

```bash
export $(grep -E '^JUSTBASH_API_KEY=' ../../../.env | head -1)
```

**Which provider, and why it is named** (measured 2026-10-13). The stand used to call
OmniRoute routing names (`main`, `auto/coding`). Both failed for a day: `main` answered HTTP
401 with the upstream's credits exhausted, and `auto/coding` answered 503 often enough that a
finished fifty-question run (`s-50-6`, exit 0) still met 57 refusals in 150 cells. Worse for a
measurement than the refusals was the routing itself: the report's own "models that served the
cells" line showed a dozen different models behind two routing names (MiniMax-M3,
Top-Tools-Ai, gemini-3.1-pro, ministral, voxtral, …), so a row of numbers no longer belonged
to one model. The stand therefore names the provider and pins one model per role, and the
report keeps the served-model line as the check that the pin held.

`justbash-api.annenkov.me` sits behind an edge that answers **403 `error code: 1010`** to
`urllib`'s library user-agent string, before any model is reached. The stand sends a name of
its own (`model_chain.USER_AGENT`); without it every cell of a run is refused, which is how it
was found (`smoke-s-5`: three arms, three 403s, on a gateway that answers a direct call in a
second).

`--arms graph --no-ostis` is refused by name: a graph arm without a graph used to be given
an empty context and written down as a graph result (measured 2026-10-13, `trap-check-s-1`).

A run writes four things:

- `~/.openclaw/bench-memory/runs/<tag>.json`, rewritten after every question, so
  an interrupted run still holds its cells;
- `~/.openclaw/bench-memory/runs/<tag>-report.md`, the same numbers as a table
  with the storage section it was measured on;
- one record per session per corpus in the graph, under the stream
  `lme-<tag>-<question>`, and one record per cell under `lme-cells-<tag>`;
- the run's own stdout, kept as the log of the exit code it finished with.

Each corpus is a stream of its own so a read walks only that corpus's sessions; the
benchmark keeps its writer leases under `~/.openclaw/bench-memory/lanes/`, never in the
owner's data root. At the end of the run the graph is asked once for its **native Save**
(`action_oneiro_save_memory`) and the report carries that answer verbatim: `saved: true`
means the graph ran its own save and it was observed to finish. It does *not* mean durable —
no snapshot is verified and the effect gate is untouched — and the report says so.

The streams can be read back independently of the run's own report, which is how the
records are checked rather than trusted:

```bash
python _tmp/bench-readback.py --port 50661 --stream lme-s-50-6-<question>
python _tmp/bench-readback.py --port 50661 --stream lme-cells-s-50-6
```

## What a record holds

Sessions: a `Note` per session — `topic` = `LongMemEval session <id>`, `body` = the rendered
session text, `sources` = the corpus, `provenance = observation`, and the labels
`lme-session`, `corpus=`, `session=`, `date=`, `date-epoch=`.

Cells: a `Note` per cell under the name the retired stand used,
`memory_bench_result_<tag>_<question>_<arm>_r<n>`, with the whole cell as JSON in `body` and
its key fields as labels (`run=`, `question=`, `arm=`, `status=`, `judge=`, `passed=`,
`recall=`, `answer-model=`, `judge-model=`), so a reader can select cells in the graph
without parsing the body.

The panel does not show these runs yet. `dashboard/server.py` still reads the retired
bridge, and it is a named, separate debt (see
`docs/forumit-2026/PLAN-P4-FRESH-MEASURE-2026-10-13.md`); nothing in this folder claims the
dashboard works.

## Runs kept on this machine

| tag | when | what it is |
|---|---|---|
| `s-50-1`, `s-50-2` | 2026-09-22 | the retired stand, over the bridge; the numbers a talk may still quote with that date attached |
| `s-50-3-no-llm` | 2026-10-13 | the attempt that measured nothing: every cell `provider_error`, `accuracy=None`, exit 0 |
| `smoke-s-3` | 2026-10-13 | the current stand: records in the graph, cells in the graph, one observed Save |
| `s-50-4` | 2026-10-13 | the same stand cut short by the provider: 25 of 50 questions, 8 of 75 cells without a verdict, exit 1 — kept as the evidence of that outage, not as a number |
| `s-50-5` | 2026-10-13 | killed with its supervisor when the agent's turn was interrupted: 1 of 50 questions, no exit code, and its first corpus already in the graph — a fragment, not a number |
| `smoke-s-5` | 2026-10-13 | the first attempt on the restored gateway: every cell refused with HTTP 403 (`error code: 1010`), which is how the user-agent requirement was found |
| `s-50-6` | 2026-10-13 | finished, exit 0, and still not a number: 57 of 150 cells refused by the provider, and the routing names answered from a dozen different models |
| `smoke-s-6` | 2026-10-13 | the gateway with the stand's own user-agent: 2 questions, 6 cells, every one answered and judged, recall@5 1.0 on both retrieval arms |
| `s-50-7` | 2026-10-13 | the current stand on a named provider with pinned models (`kimi-k2.5` answers, `deepseek-v4-pro` judges), detached from the agent's process tree: the run a talk may quote |

## Price and duration

Measured 2026-10-13 on this machine, one question of stage `s` with all three arms and a
41–53-session haystack: 175 s, of which the graph arm wrote and read 51 records.A fifty-question run is therefore a multi-hour job and belongs in the background with its log
kept, not in a foreground shell. Measured the hard way on 2026-10-13: a run started as a child
of the agent's own shell died with it when that turn was interrupted (that is `s-50-5`), and a
dead run cannot produce a number. Use `_tmp/bench-s-50-6.sh` as the pattern — a supervisor
launched through `Start-Process`, outside the agent's process tree, writing the runner's exit
code to a file of its own.

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
  renderer, both ranking paths, the record round trip and the client's failure
  behaviour offline — no graph, no provider, no dataset needed.
