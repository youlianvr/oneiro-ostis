#!/usr/bin/env python
"""The memory benchmark run: LongMemEval against four memory policies.

    python bench/memory/run.py --stage oracle --questions 50
    python bench/memory/run.py --stage s --questions 20 --cap 100 --k 5

Stage ``oracle`` answers from the evidence sessions only: full context (the
benchmark's own setting, so the number sits next to published ones) and no
memory (the floor). Stage ``s`` puts the evidence back among hundreds of
distractor sessions and runs the two policies under test: the typed graph
store (time window first, similarity second) and the flat journal (word search
over one text file). Model calls go through the local OmniRoute proxy; every
cell writes a record to OSTIS, and the run writes a JSON log plus a markdown
summary under ``~/.openclaw/bench-memory``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
for extra in (PROJECT / "python", PROJECT / "bench" / "memory"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from llm import ChatClient, ProviderError  # noqa: E402

import arms as arms_module  # noqa: E402
import dataset as dataset_module  # noqa: E402
import judge as judge_module  # noqa: E402
from stores import FlatJournal, GraphStore, search_flat  # noqa: E402

DEFAULT_BASE_URL = "http://127.0.0.1:20128/v1"
# Two live OmniRoute routing names, deliberately in opposite order: the answer
# chain prefers the strong general model, the judge chain prefers the fast one,
# so a cell's answer and its verdict come from different models. Routing names
# survive provider churn; the record keeps the id that actually served the call.
DEFAULT_ANSWER_MODELS = ("main", "auto/coding")
DEFAULT_JUDGE_MODELS = ("auto/coding", "main")
DEFAULT_BENCH_DIR = Path(os.environ.get("ONEIRO_BENCH_DIR") or (Path.home() / ".openclaw" / "bench-memory"))


def load_key(name: str) -> str:
    """The provider key: environment first, then the workspace .env."""
    value = os.environ.get(name)
    if value:
        return value.strip()
    for parent in [PROJECT, *PROJECT.parents][:8]:
        env_file = parent / ".env"
        if not env_file.is_file():
            continue
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith(name + "="):
                found = line.split("=", 1)[1].strip().strip('"').strip("'")
                if found:
                    return found
    raise SystemExit(f"no {name} in the environment or in a .env above {PROJECT}")


def scaled_sample(total: int) -> dict:
    """DEFAULT_SAMPLE scaled to `total` questions, at least one per type."""
    if total >= 50:
        return dict(dataset_module.DEFAULT_SAMPLE)
    base = dataset_module.DEFAULT_SAMPLE
    scale = total / sum(base.values())
    return {kind: max(1, int(round(count * scale))) for kind, count in base.items()}


class ModelChain:
    """One logical model backed by an ordered chain of provider model ids.

    The benchmark's rule is that a row of results belongs to one model; this
    chain keeps that promise by recording which model actually served the
    call, and by never silently mixing a different model into the same cell.
    """

    def __init__(self, models, base_url: str, key: str, temperature: float = 0.0) -> None:
        self.models = list(models)
        self.base_url = base_url
        self.key = key
        self.temperature = temperature
        self.model = self.models[0]
        self.failures: list[str] = []

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             max_tokens: int | None = None):
        problems = []
        for model in self.models:
            client = ChatClient(model=model, api_key=self.key, base_url=self.base_url,
                                temperature=self.temperature)
            try:
                message, usage = client.chat(messages, tools=tools, max_tokens=max_tokens)
            except ProviderError as exc:
                problems.append(f"{model}: {exc}")
                self.failures.append(f"{model}: {exc}"[:300])
                continue
            self.model = model
            return message, usage
        raise ProviderError("model chain exhausted: " + "; ".join(problems))


def run_question(question, args, graph: GraphStore | None, flat: FlatJournal,
                 run_tag: str) -> list[dict]:
    """All arms for one question; returns this question's records."""
    corpus = f"lme_{run_tag}_{question.question_id}"
    retrieved: dict[str, list[dict]] = {}
    if "graph" in args.arms and graph is not None:
        graph.write(corpus, question.haystack)
        retrieved["graph"] = graph.search(corpus, question.question, args.k, question.question_epoch)
    if "flat" in args.arms:
        flat.write(corpus, question.haystack)
        retrieved["flat"] = search_flat(flat, corpus, question.question, args.k)

    records = []
    for arm in args.arms:
        for run_index in range(1, args.repeat + 1):
            prompt = arms_module.build_prompt(arm, question, retrieved.get(arm))
            answer = {"text": "", "model": "", "prompt_tokens": 0, "completion_tokens": 0}
            verdict = {"passed": False, "raw": "", "model": "", "prompt_tokens": 0, "completion_tokens": 0}
            status = "ok"
            try:
                answer = arms_module.answer(args.answer_chain, prompt, max_tokens=args.max_tokens)
                verdict = judge_module.verdict(
                    args.judge_chain, question.question_type, question.question,
                    question.answer, answer["text"], abstention=question.is_abstention,
                    max_tokens=args.judge_max_tokens,
                )
            except ProviderError as exc:
                status = "provider_error"
                verdict["raw"] = f"provider failure: {exc}"[:200]
                print(f"    ! provider failure on {arm}: {str(exc)[:160]}", flush=True)
            hit_ids = [session["session_id"] for session in retrieved.get(arm, [])]
            evidence_hits = sorted(set(hit_ids) & set(question.answer_session_ids))
            # Only the retrieval arms have a recall; fixed-context arms have none.
            retrieval_arm = arm in ("graph", "flat")
            record = {
                "run_tag": run_tag,
                "stage": args.stage,
                "question_id": question.question_id,
                "question_type": question.question_type,
                "question": question.question[:500],
                "gold": question.answer[:500],
                "abstention": question.is_abstention,
                "arm": arm,
                "run": run_index,
                "k": args.k,
                "status": status,
                "prompt_chars": len(prompt),
                "haystack_size": len(question.haystack),
                "retrieved_ids": hit_ids,
                "evidence_ids": list(question.answer_session_ids),
                "evidence_hits": evidence_hits,
                "recall_at_k": (len(evidence_hits) / len(question.answer_session_ids)
                                if retrieval_arm and question.answer_session_ids else None),
                "answer": answer["text"][:2000],
                "answer_model": answer["model"],
                "judge_passed": bool(verdict["passed"]),
                "judge_label": str(verdict.get("label") or ""),
                "judge_raw": str(verdict["raw"])[:600],
                "judge_chars": len(str(verdict["raw"])),
                "judge_model": verdict["model"],
                "prompt_tokens": answer["prompt_tokens"] + verdict["prompt_tokens"],
                "completion_tokens": answer["completion_tokens"] + verdict["completion_tokens"],
                "ts": int(time.time()),
            }
            records.append(record)
            if args.bridge is not None:
                args.bridge.save_memory_bench_result(
                    f"memory_bench_result_{run_tag}_{question.question_id}_{arm}_r{run_index}",
                    record,
                )
    return records


def summarize(records: list[dict]) -> dict:
    arms = sorted({record["arm"] for record in records})
    summary: dict = {"per_arm": {}, "per_type": {}, "totals": {"cells": len(records)}}
    for arm in arms:
        cells = [r for r in records if r["arm"] == arm]
        ok = [r for r in cells if r["status"] == "ok"]
        # A cell without a verdict is not a wrong answer, it is an unjudged one;
        # folding it into the denominator would invent a failure.
        judged = [r for r in ok if r.get("judge_label")]
        passed = sum(1 for r in judged if r["judge_passed"])
        recalls = [r["recall_at_k"] for r in ok if r["recall_at_k"] is not None]
        summary["per_arm"][arm] = {
            "cells": len(cells),
            "ok": len(ok),
            "judged": len(judged),
            "unjudged": len(ok) - len(judged),
            "passed": passed,
            "accuracy": round(passed / len(judged), 4) if judged else None,
            "mean_recall_at_k": round(sum(recalls) / len(recalls), 4) if recalls else None,
            "tokens": sum(r["prompt_tokens"] + r["completion_tokens"] for r in cells),
        }
    for question_type in sorted({r["question_type"] for r in records}):
        row: dict = {}
        for arm in arms:
            judged = [r for r in records
                      if r["arm"] == arm and r["question_type"] == question_type
                      and r["status"] == "ok" and r.get("judge_label")]
            row[arm] = round(sum(1 for r in judged if r["judge_passed"]) / len(judged), 4) if judged else None
        summary["per_type"][question_type] = row
    return summary


def render_report(payload: dict) -> str:
    lines = [f"# Memory benchmark run {payload['run_tag']}", ""]
    lines.append(f"stage: {payload['stage']} | questions: {payload['questions']} | "
                 f"k: {payload['k']} | cap: {payload['cap']} | seed: {payload['seed']}")
    lines.append(f"answer models: {', '.join(payload['answer_models'])}")
    lines.append(f"judge models: {', '.join(payload['judge_models'])}")
    lines.append("")
    lines.append("## Per arm")
    lines.append("")
    lines.append("accuracy is passed / judged: a cell whose judge gave no verdict at all "
                 "is counted in `unjudged`, never as a wrong answer.")
    lines.append("")
    lines.append("| arm | cells | judged | unjudged | passed | accuracy | mean recall@k | tokens |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for arm, row in payload["summary"]["per_arm"].items():
        lines.append(f"| {arm} | {row['cells']} | {row['judged']} | {row['unjudged']} | "
                     f"{row['passed']} | {row['accuracy']} | {row['mean_recall_at_k']} | {row['tokens']} |")
    lines.append("")
    lines.append("## Per question type (judge pass rate)")
    lines.append("")
    arms = list(payload["summary"]["per_arm"].keys())
    lines.append("| type | " + " | ".join(arms) + " |")
    lines.append("|---" * (len(arms) + 1) + "|")
    for question_type, row in payload["summary"]["per_type"].items():
        lines.append(f"| {question_type} | " + " | ".join(str(row.get(arm)) for arm in arms) + " |")
    lines.append("")
    return "\n".join(lines)


def build_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LongMemEval memory benchmark")
    parser.add_argument("--stage", choices=["oracle", "s"], default="oracle")
    parser.add_argument("--questions", type=int, default=50)
    parser.add_argument("--cap", type=int, default=100,
                        help="haystack cap for stage s: evidence is always kept")
    parser.add_argument("--k", type=int, default=5, help="sessions retrieved per arm")
    parser.add_argument("--arms", default="", help="comma list; defaults per stage")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260921)
    parser.add_argument("--max-tokens", type=int, default=500)
    parser.add_argument("--judge-max-tokens", type=int, default=judge_module.JUDGE_MAX_TOKENS,
                        help="completion budget for the judge; a reasoning judge needs room "
                             "for the thought before its verdict")
    parser.add_argument("--data", default="", help="LongMemEval data dir")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--key-env", default="OMNIROUTE_API_KEY")
    parser.add_argument("--answer-models", default=",".join(DEFAULT_ANSWER_MODELS))
    parser.add_argument("--judge-models", default=",".join(DEFAULT_JUDGE_MODELS))
    parser.add_argument("--run-tag", default="")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--ostis-port", type=int, default=8090)
    parser.add_argument("--no-ostis", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="smoke runs: keep only N questions")
    parser.add_argument("--dry", action="store_true", help="print the sample and exit")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = build_args(argv)
    if not args.arms:
        args.arms = ["full", "none"] if args.stage == "oracle" else ["graph", "flat", "none"]
    else:
        args.arms = [arm.strip() for arm in args.arms.split(",") if arm.strip()]
    run_tag = args.run_tag or f"{args.stage}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    questions = dataset_module.load_questions(
        args.stage,
        data_dir=Path(args.data) if args.data else None,
        per_type=scaled_sample(args.questions),
        seed=args.seed,
        cap=args.cap if args.stage == "s" else None,
        limit=args.limit or None,
    )
    if not questions:
        print("no questions selected; check the data dir", flush=True)
        return 1
    print(f"run {run_tag}: {len(questions)} questions, stage {args.stage}, "
          f"arms {args.arms}, k {args.k}", flush=True)
    if args.dry:
        for question in questions:
            print(f"  {question.question_id} [{question.question_type}] "
                  f"haystack={len(question.haystack)} evidence={len(question.answer_session_ids)}"
                  f"{' ABS' if question.is_abstention else ''} {question.question[:70]}")
        return 0

    key = load_key(args.key_env)
    args.answer_chain = ModelChain(args.answer_models.split(","), args.base_url, key)
    args.judge_chain = ModelChain(args.judge_models.split(","), args.base_url, key)
    args.bridge = None
    if not args.no_ostis:
        from bridge import OneiroBridge  # imported late so --dry works without the stack
        args.bridge = OneiroBridge("localhost", args.ostis_port)
        args.bridge.connect()
        print(f"OSTIS connected on :{args.ostis_port}", flush=True)

    out_root = Path(args.out_dir or DEFAULT_BENCH_DIR)
    runs_dir = out_root / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    json_path = runs_dir / f"{run_tag}.json"
    flat = FlatJournal(out_root / "journals")
    graph = GraphStore(args.bridge) if args.bridge is not None else None

    records: list[dict] = []
    started = time.time()
    for index, question in enumerate(questions, 1):
        try:
            cell_records = run_question(question, args, graph, flat, run_tag)
        except (ProviderError, RuntimeError, OSError, TimeoutError) as exc:
            print(f"  ! question {question.question_id} aborted: {str(exc)[:200]}", flush=True)
            traceback.print_exc()
            continue
        records.extend(cell_records)
        summary_line = " ".join(
            f"{record['arm']}={'P' if record['judge_passed'] else 'F'}"
            for record in cell_records if record["run"] == 1
        )
        print(f"  {index}/{len(questions)} {question.question_id} [{question.question_type}] "
              f"{summary_line}", flush=True)
        snapshot = {
            "run_tag": run_tag, "stage": args.stage, "seed": args.seed, "k": args.k,
            "cap": args.cap if args.stage == "s" else None,
            "questions": len(questions), "arms": args.arms,
            "answer_models": args.answer_models.split(","),
            "judge_models": args.judge_models.split(","),
            "records": records,
            "summary": summarize(records),
        }
        json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    payload["seconds"] = round(time.time() - started, 1)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    report_path = runs_dir / f"{run_tag}-report.md"
    report_path.write_text(render_report(payload), encoding="utf-8")

    summary = payload["summary"]
    print("\n=== summary ===", flush=True)
    for arm, row in summary["per_arm"].items():
        print(f"  {arm:6s} n={row['ok']:3d} accuracy={row['accuracy']} "
              f"recall@k={row['mean_recall_at_k']} tokens={row['tokens']}", flush=True)
    print(f"json: {json_path}", flush=True)
    print(f"report: {report_path}", flush=True)
    if args.bridge is not None:
        args.bridge.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
