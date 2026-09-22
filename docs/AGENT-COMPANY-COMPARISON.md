# The company of agents: what the field settled on, and the evidence against it

Surveyed 2026-09-22 through the GitHub API and the projects' own documentation. Numbers
are stars and last push at the time of reading; nothing here was run by us.

## 1. What exists

| Project | Stars | License | Language | Last push | What it claims to be |
|---|---|---|---|---|---|
| `FoundationAgents/MetaGPT` | 70.5k | MIT | Python | 2026-01-21 | The first AI software company: one line of requirement in, artifacts and a repository out |
| `microsoft/autogen` | 61.1k | CC-BY-4.0 | Python | 2026-04-15 | A programming framework for agentic AI |
| `crewAIInc/crewAI` | 58.9k | MIT | Python | 2026-09-22 | Orchestrating role-playing autonomous agents |
| `OpenBMB/ChatDev` | 34.4k | Apache-2.0 | Python | 2026-07-24 | ChatDev 2.0: development all through LLM multi-agent collaboration |
| `SWE-agent/SWE-agent` | 20.4k | MIT | Python | 2026-09-21 | One GitHub issue in, a fix out (single agent, for contrast) |
| `camel-ai/camel` | 17.8k | Apache-2.0 | Python | 2026-09-20 | Role-playing societies of agents and their scaling law |
| `SakanaAI/AI-Scientist` | 14.6k | custom | Jupyter | 2025-12-19 | Fully automated open-ended discovery, with an automated reviewer |
| `OpenBMB/AgentVerse` | 5.1k | Apache-2.0 | JS | 2024-09-09 | Deploying multiple LLM agents in societies |
| `uluckyXH/OpenMOSS` | 1.3k | - | Python | recent | Self-organizing multi-agent collaboration on top of OpenClaw |
| `mims-harvard/AutoScientists` | 749 | - | Python | 2026 | Self-organizing agent teams for long-running scientific work |
| `plasma-ai/fractal` | 732 | Apache-2.0 | Python | 2026-09-21 | Hierarchical agent loops with recursive self-organization |
| `GreenSheep01201/claw-empire` | 1.4k | - | TypeScript | recent | Command an agent empire from a CEO desk (the metaphor, made literal) |

## 2. The choices they converged on

1. **A standard operating procedure, not a chat.** MetaGPT's philosophy is written as
   `Code = SOP(Team)`: roles are product manager, architect, project manager, engineer,
   and what passes between them is a **deliverable artifact** (user stories, competitive
   analysis, requirements, data structures, APIs, documents), not conversation. The
   handoff is typed by the procedure.
2. **An explicit reviewer and tester, with a checklist.** ChatDev runs a chat chain
   (CEO, CPO, CTO, programmer, reviewer, tester) and its reviewer role performs what the
   paper calls communicative dehallucination: instead of accepting an answer, it demands
   the specific information it is missing. The gate is a role, not a rubric in a prompt.
3. **Orchestration as infrastructure.** crewAI (crews, processes), AutoGen (group chat
   manager, conversation patterns), CAMEL (role-playing societies) all sell the same
   thing: roles and message routing as a library. They are frameworks, and none of them
   is evidence that the structure helps.
4. **An automated reviewer as a decision gate in research loops.** AI-Scientist runs
   experiments and then reviews its own output before it counts, which is the closest
   published shape to our judge-before-deploy.
5. **Self-organization as the 2026 frontier.** AutoScientists (teams that organize
   themselves for long-running science), fractal (hierarchical loops with recursive self
   organization), OpenMOSS and swarmclaw (self-organizing swarms on OpenClaw), claw-empire
   (a CEO desk over an agent empire). All recent, none with published measurements we
   could find.

## 3. The evidence against the whole idea

This is the part that matters most for us, and it is not from a README.

**"Why Do Multi-Agent LLM Systems Fail?"** (Cemri, Pan, Yang et al., arXiv 2503.13657,
NeurIPS 2025 Datasets and Benchmarks). Their first sentence about the state of the art:
"Despite enthusiasm for Multi-Agent LLM Systems (MAS), their performance gains on popular
benchmarks are often minimal." They built MAST-Data, 1600+ annotated traces across **7
popular MAS frameworks**, and the first Multi-Agent System Failure Taxonomy: **14 failure
modes in 3 categories**, namely system design issues, inter-agent misalignment, and task
verification, validated at an inter-annotator agreement of kappa = 0.88.

Read plainly: the field's own audit says a company of agents often costs more and
delivers no more, and it names where the losses come from. A project that builds an
agent company and does not measure it against a single agent is repeating a mistake
that has already been documented at 1600 traces.

## 4. Against our own design

| Their settled choice | Ours today | Verdict |
|---|---|---|
| Artifacts as the contract between roles | Roles exchange conversation plus PR packets; the packet is typed, the rest is not | **Adopt**: name the artifacts each role must produce and refuse a handoff without one |
| A reviewer role with a checklist | We have a judge for candidates; the researcher's and worker's output has no reviewer | **Adopt**: a reviewer role that must reject or state what is missing |
| SOP as the spine | Our pipeline is a fixed sequence of calls in one bounded heartbeat | Partly adopt: keep the small loop, add the missing artifact checks |
| Orchestration framework as the product | We wrote our own small loop | **Reject**: we already chose CowAgent as the host, a second framework is duplication |
| Automated reviewer decides on evidence | Our judge decides before deployment, with recorded error | **Keep**, and it is our strongest card: 11 rounds, 29 candidates, 4 deployed, 19 refused, judge error 5.9% |
| Failure labels from the literature | We record outcomes without a failure taxonomy | **Adopt**: label refusals and failures with the MAST categories so failures become countable |
| A single agent as the baseline | We have never run the company against a solo agent on the same tasks | **Our own experiment, and nobody else has it**: same tasks, same judge, one agent against the company, both costs reported |

## 5. What this leaves

The company of agents is what we are building, and the honest version of that claim is
measurable: on our own task set, with our own recorded judge, does the organization beat
one agent working alone, and at what cost. We already have the harness, the tasks, the
judge and the graph; no surveyed project publishes that comparison for its own system,
and the field's audit says the answer is often "no". Either answer is a result.

Three decisions follow: whether to run that comparison now, whether to add the reviewer
role with its checklist, and whether to label failures with MAST categories.
