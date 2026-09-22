# CowAgent against our approach: where it conflicts, and what it already paid for

Read on 2026-09-22 from `github.com/zhayujie/CowAgent` (branch `master`, MIT, Python,
about 16 MB of source, 47k stars) and its documentation (`docs/memory/`,
`docs/knowledge/`, `docs/skills/`, `docs/tools/memory.mdx`). Everything below is
quoted from their documents, not from a summary of the README.

The question was not "is it good". The question was: where do their choices
contradict ours, and which of their choices are the result of real operation that
we would be foolish to learn the hard way.

## 1. Memory: their shape

- **Files are the store.** `~/cow/MEMORY.md` (core, long term), `~/cow/memory/YYYY-MM-DD.md`
  (daily, by date), `~/cow/memory/dreams/YYYY-MM-DD.md` (dream diary), `memory/evolution/YYYY-MM-DD.md`
  (evolution records). "Long-term memory is stored in workspace files, persisting across sessions."
- **Writing is automatic and asynchronous.** On context trimming (the oldest half is
  summarized into the daily file), on a daily schedule at 23:55, on an API context
  overflow error. "All memory writes run asynchronously in a background thread, never
  blocking normal conversation replies."
- **Retrieval is hybrid, not one method.** FTS5 full-text with BM25 plus embeddings,
  "rank-normalizing the vector and keyword scores onto a common scale and taking a
  weighted average (default: 0.7 vector weight + 0.3 keyword weight)". Because the top
  hit normalizes to 1.0, `min_score` is a rank cutoff, not a relevance floor. Daily
  memory **decays** with a 30-day half-life; core memory does not.
- **Consolidation is bounded.** Deep Dream reads `MEMORY.md` plus today's daily memory,
  deduplicates, merges, prunes, lets newer information win conflicts, and overwrites
  `MEMORY.md`, which is injected into the system prompt of every conversation and is
  therefore capped at roughly 30 entries. Each run writes a dream diary. Guards:
  skipped when there is no content, skipped when the input has not changed, sequential
  guarantee that the daily flush finishes before distillation, and an explicit prompt
  constraint "no fabrication", consolidation of existing materials only.
- **Embeddings are a rebuildable index**, not the truth: `embedding/rebuild.py`,
  `rebuild_index.py`, `embedding/state.py`.

## 2. Memory: our shape

- **The OSTIS sc-graph is the store.** Episodes, worlds, strategies, organization
  records and memory sessions are nodes with an ontology; every answer is traceable to
  the episodes it came from.
- **One measured claim, and it is a negative one.** On the same 50 questions the flat
  journal scores 72.7% and the graph 72.1%; the graph wins only on time questions (40%
  against 16.7%). The graph's real advantage that we measured is provenance (1.00
  against 0.00) and chronology, not recall.
- **No decay, no distillation, no trimming.** Everything that was ever recorded stays at
  full weight, and there is no bounded "core" that is always in the prompt.

## 3. Where that conflicts

| Area | Their choice | Ours | Conflict | Verdict |
|---|---|---|---|---|
| Retrieval | Hybrid BM25 + vector, weighted, rank-normalized | Graph traversal only | Both claim to answer the same questions from the same episodes; ours loses to a flat journal | **Adopt theirs on top of ours** |
| Truth of record | Markdown files are truth, the graph is a view (`desktop/.../KnowledgeGraph.tsx`) | The graph is truth, there is no file view | Direct architectural contradiction | Keep the graph as truth (our contribution), add exported file views |
| Weight over time | Daily memory decays, core does not | Nothing decays | Old episodes can outrank fresh ones in our scoring | **Adopt** |
| Bounded core | `MEMORY.md`, ~30 entries, injected into every prompt | Nothing bounded, nothing always present | Without it, "what the agent always knows" is undefined | **Adopt** |
| Consolidation | Deep Dream: dedupe, merge, prune, newer wins, no fabrication | None | Our graph grows monotonically; no deduplication of episodes | **Adopt**, with the journal as the diary |
| Context trimming | Oldest half summarized into memory on overflow | None; our loop has no trimming | A long autonomous run would simply end | **Adopt** |
| Index as state | Embedding index is rebuildable, with a state file | Graph indices are implicit | Ours cannot be rebuilt after a schema change | **Adopt the discipline** |
| Where knowledge lives | Topic wiki in `knowledge/` with `index.md` and `log.md`, memory by timeline | One ontology for both | Their split (timeline vs topic) is a real distinction we collapsed | **Adopt the distinction**, keep one store |
| Self-improvement trigger | Idle (10 min) **and** enough turns (6) | We planned idle only | Without the second condition there is nothing to review | **Adopt both conditions** |
| Applying changes | Edit the skill file directly, backup before, undo on request | Judge by replay first, deploy only if it passes, 19 of 29 candidates rejected | They edit prose and revert on complaint; we refuse to deploy on measurement | **Keep ours, take their backup** |
| Noise discipline | "No work, no notification": file snapshots decide whether anything changed | We planned to report every review | Their rule is strictly better for a human | **Adopt** |
| Reviewer's reach | Restricted toolset: read context, edit memory and skill files only; built-in skills protected | "Curator touches only its own artifacts" (owner's decision) | Same intent, theirs is an explicit allow-list | **Adopt the allow-list** |
| Human-readable trail | Dated markdown logs plus console tabs for memory, dreams, evolution | Graph records plus a dashboard | A human cannot diff a graph node | **Adopt** |
| Skills | Install from Hub, GitHub and ClawHub; create from conversation; frontmatter, loader, manager | Our own catalog of 101, looked up by `find_skills` | Same idea, our shelf is two orders of magnitude smaller | **Adopt the shelf** (ClawHub, 5,400+ in the community list) |
| Channels | Web, WeChat, Feishu, DingTalk, QQ, Telegram, Slack, desktop app, console on 9899 | Dashboard plus MCP tools | Not a conflict, a gap | Decide with the host question |
| Execution model | Everything long runs in background threads | Our loop is synchronous per cycle | Theirs survives a slow model without freezing | **Adopt** |
| Evidence | No published measurement of memory recall | 50 questions, judge, oracle ceiling, honest noise | This is our ground | **Keep** |

## 4. What they paid for that we would pay again

1. **Hybrid retrieval, not one blessed method.** They reached BM25 + vectors after
   shipping pure semantic search; our own numbers say the same thing from the other
   side, where a plain journal beats our graph on recall. Two independent results
   pointing at hybrid is the strongest data in this document.
2. **Decay.** Daily memory fades, core does not. Without it, "recent" is a guess.
3. **A bounded core that is always in the prompt.** The agent needs a small, stable
   statement of what it knows, separate from the searchable pile.
4. **Consolidation with conflict rules and a written diary.** "Newer information
   takes precedence" is a decision we have never made in writing.
5. **Backups before editing yourself, and an undo.** Our never-destroy rule protects
   against deletion; it does not protect against a bad edit.
6. **Quiet by default.** If a review changed nothing, nobody hears about it.
7. **Human-readable logs next to machine records.** Graph nodes for questions, dated
   markdown for the human who wants to see what changed and when.
8. **An explicit allow-list for the self-editing process**, with built-in skills
   protected from it.

## 5. What we have and they do not

- **A judge that prices an idea before it is deployed.** Eleven rounds, 29 candidates,
  4 deployments, 19 refusals, judge error measured at 5.9%, and the over-estimation of
  the judge reported instead of hidden. Their self-evolution edits and asks you to
  complain if you disagree; ours refuses to ship what did not survive a replay.
- **Provenance as a measured property** (1.00 against 0.00 for a flat journal): every
  answer names the episodes it came from. Their memory files have no query layer.
- **Durability evidence**: an interrupted run is resumed, not restarted, and a restart
  reads its records back from the graph.
- **A publishable negative result.** "The graph does not beat a flat journal on recall,
  only on provenance and chronology" is a finding; a product README cannot contain it.
- **PR packets without merge or push**, with a human decision path that a bot cannot
  forge (the approval channel sends two buttons and only the owner's press counts).

## 6. The three decisions this leaves

1. **Retrieval**: adopt hybrid over the graph (keyword + vector, rank-normalized,
   decayed) and re-measure the 50 questions. Until that measurement exists, the memory
   claim stays negative.
2. **Host**: keep reading their mechanisms and port them into our own host, or take
   CowAgent itself as the host and put our graph and our judge inside it. Their
   mechanisms are the valuable part; the host is a delivery decision.
3. **Self-edits**: their way (apply, backup, undo on request) or ours (judge first,
   deploy on pass), with their backup discipline added to ours either way.
