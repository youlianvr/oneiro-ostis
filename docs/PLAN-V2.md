# v2 — a manager you can talk to, in one language, without the wood

This branch is the second line of the product. Three things change, and they are
one change: the organization stops speaking through rigid forms, the interface
stops speaking Russian, and the manager becomes a counterpart the owner can
actually talk to.

Branch: `v2` on `youlianvr/oneiro-ostis` (opened 2026-09-28 at `1a9b9a9b`, the
same commit `main` stands on, so `main` stays the stable clone-and-run point).

## Owner decisions (2026-09-28)

1. **English everywhere it matters** — the console and panel interface, the
   agent's logic and what it outputs, code, docs and commits. The spoken chat
   between the owner and the agent stays Russian.
2. **The manager becomes a conversational counterpart**:
   - the owner can exchange free-form messages with the manager, the way one
     talks to a plain assistant, not through a form;
   - the manager may open a conversation on its own initiative;
   - when the manager needs an answer it calls a dedicated tool, and the question
     carries three possible answers: **confirm**, **reject**, and **the owner's
     own next message treated as free text**;
   - if the owner ignores the question and answers in their own words, the tool
     returns **reject plus that text**, together with an instruction that the
     question must be asked again if the message sounded like agreement.
3. The three sources of "wood" named by the owner are all in scope: the rigid
   JSON-only role contracts, the prescribed bureaucratic phrasing, and the
   uniform cycle that always walks the same path.

## Where the agent logic lives today

| File | What it is |
|---|---|
| `python/swarm.py` | the bounded protocol: researcher → manager → worker → PR packet, no model, no git |
| `python/roles.py` | `RESEARCHER_SYSTEM`, `MANAGER_SYSTEM` — prompts plus one strict JSON reply shape each |
| `python/worker.py` | `WORKER_SYSTEM` and the tool loop inside one isolated worktree |
| `python/life_loop.py` | one bounded cycle: dossier, roles, freeze reasons, journal |
| `python/approval.py` | asking the human: a `Proposal`, Russian render, **two** inline buttons, verdicts recorded to disk and graph |
| `python/telegram_entry.py` | the owner's channel: text becomes work, button presses go to the approval channel |
| `console/overlay/**` | 14 recorded files applied onto vendored CowAgent 2.1.9; the console chat's own prompt is not in this repository |

Two properties of the current code matter more than anything else for this
branch:

- `roles.py` says *"Answer with a single JSON object and nothing else"*, and
  `swarm.py`'s docstring says *"Free-form prose never leaks into the organization
  records"*. Anything else is a schema error with exactly one corrective retry
  and then a dead cycle. A living answer physically cannot pass through.
- `approval.py`'s docstring says *"there is no text path, no model path, and no
  second press"*. That was deliberate. v2 adds a text path, and the safety
  property must survive it: **only a button press from the owner's own account is
  ever an approval.** Free text is context, never a verdict. The owner's own
  three-answer rule already has this shape — text returns *reject plus the
  message*, never *confirm* — so the rule is kept, not traded away.

## The design

### The question tool

One tool, called by the manager. It sends a question to the owner and returns
exactly one of:

| Outcome | How it happens | What the manager gets |
|---|---|---|
| `confirmed` | the owner presses the confirm button from their own account | the verdict, and the evidence that it was a press |
| `rejected` | the owner presses the reject button | the verdict |
| `free_text` | the owner answers with words instead | the owner's text, the fact that the question was **not** answered, and the standing instruction to ask again when the message reads as agreement |

Open questions, decided when the first unit lands rather than guessed now:

- whether a free-text answer is also delivered to the manager as an ordinary
  conversation turn (my reading: yes — it is a message to the manager that also
  closes the open question), or only as a question answer;
- whether a question has a deadline and what the manager sees when it expires.

### A conversation, not a form

The manager keeps history across messages instead of being rebuilt each cycle.
The graph already has the places for this — `bridge.record_organization_event`
and the `LifeSession` records — so the conversation is stored where every other
fact about the work is stored, and survives restarts.

The manager's own initiative is the same tool without a question behind it: a
message sent to the owner because the manager has something to say. It must be
rate-limited and it must never be able to merge, push or release — the existing
rule *"Never approve a merge, a push, or a release"* stays untouched.

### English-only

| Surface | What changes |
|---|---|
| `python/roles.py`, `python/worker.py` | drop "write … in Russian"; human-readable fields (`title`, `rationale`, `reason`, summary) become English |
| `python/approval.py` | `render()` and `keyboard()` strings become English |
| `python/telegram_entry.py` | the owner-facing texts become English |
| `console/overlay/common/i18n_ru.py` | removed, together with the Russian call sites it feeds |
| `console/overlay/**` | console and panel strings become English, including the Oneiro settings page |
| tests | 10 test files assert Russian text; they are updated with the code they cover |

Note the reversal this is. On 2026-09-23–26 the console and panel were
deliberately translated **into** Russian ("Read the panel in Russian, under the
Oneiro name", "Say the console lines in Russian too"). v2 undoes that on
purpose: one language for the product, Russian only in the owner's own chat.
Whoever reads this later should know it was a decision, not drift.

### Less wood

Three named causes, three treatments:

1. **Rigid JSON contracts.** Roles keep a machine-readable record — the
   organization still needs records it can test — but the record stops being the
   *only* thing a role may say. Prose is allowed in the human-facing fields, and
   a malformed record is no longer a dead cycle.
2. **Prescribed phrasing.** The worker's summary rule ("no file names, no English
   words, no tool names, one or two sentences") is replaced by a plain
   requirement to be honest and specific; nothing prescribes the register.
3. **A uniform cycle.** Open the dossier and the route: the researcher may
   propose fewer than two options, the manager may answer a question instead of
   deciding, and a cycle may spend its budget on a conversation rather than on a
   worktree.

## Units, in order

1. **The three-outcome question model** (`approval.py`): a third verdict carrying
   the owner's text, a rule that free text never approves, and tests.
   *Exit:* existing approval and telegram tests pass, new tests cover each of the
   three outcomes and the "text never approves" rule.
2. **Routing** (`telegram_entry.py`): a text message while a question is open
   becomes that question's free-text answer, and the question closes as
   `free_text` rather than staying silently open.
   *Exit:* the gateway test drives both paths — a press and a written answer.
3. **The conversational manager**: history, a session that survives restarts, and
   the question tool wired to it.
   *Exit:* two consecutive owner messages reach the same manager session, and the
   graph shows both turns.
4. **Manager initiative**: an unprompted message, rate-limited, with the existing
   no-merge/no-push rule enforced.
   *Exit:* a test where the manager speaks first and cannot sign anything.
5. **English conversion**, surface by surface, each with the tests it touches.
6. **Loosen the contracts** in `roles.py` / `worker.py` / `swarm.py` and drop the
   prescribed register.

Units 5 and 6 touch every surface and are done last, on top of a working
behavior — not as a rename pass that hides whether the behavior changed.

## State

- Branch `v2` exists on the remote, at `1a9b9a9b`.
- **Unit 1 done**: `approval.py` carries the third outcome (`free_text`), the
  rule that only a press approves, and `Answer.for_manager()`, which is the exact
  shape the question tool will hand back. `tests/test_approval.py` went from 21
  to 29 passing tests; the full local suite is 277 passed with the same 10
  sc-server connection errors it has without a running graph stack.
- Units 2 to 6 are not started.
- Nothing on this branch is published beyond its creation: the commits below sit
  in the workspace until the owner asks for a publish.
