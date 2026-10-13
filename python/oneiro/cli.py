"""Standalone entrypoint: every command the product offers from a terminal.

Commands are thin: they resolve what the settings declare, call one part of the
package and print it. `settings` is here rather than in `oneiro/config.py`
because this module owns the command line, and the settings layer owns the
catalog — `python python/config.py` still works, through the compatibility shim
there, which forwards to this command. `tasks` and `schedules` are the same
shape: they hold a runtime for one command, call `oneiro.tasks` or
`oneiro.schedule`, and print what happened, including why nothing happened.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import socket
import threading
from pathlib import Path
from typing import Any, Callable, Coroutine

from oneiro import (config, drafts, hooks, mcp as mcp_module, mcp_surface, office_env,
                    research as research_module, schedule as schedule_module,
                    skills as skills_module, tasks, window)
from oneiro.ownership import OwnershipError
from oneiro.query import GraphQueryError
from oneiro.runtime import Runtime
from oneiro.schedule import ScheduleError
from oneiro.tasks import TaskError


def settings_command(argv: list[str]) -> int:
    """`oneiro settings` — what every setting is, and which layer answered."""
    parser = argparse.ArgumentParser(prog="oneiro settings",
                                     description="Oneiro settings: read, set, list")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--set", nargs="*", metavar="KEY=VALUE", help="store values")
    parser.add_argument("--reset", nargs="*", metavar="KEY", help="forget stored values")
    args = parser.parse_args(argv)

    try:
        if args.set:
            patch = {}
            for item in args.set:
                if "=" not in item:
                    raise ValueError(f"KEY=VALUE was expected, got {item!r}")
                key, value = item.split("=", 1)
                patch[key.strip()] = value
            config.save(patch)
        if args.reset is not None:
            config.reset(args.reset or None)
    except ValueError as exc:
        # A refusal carries its reasons, which is what makes it fixable.
        print(f"error: {exc}")
        return 2

    description = config.describe()
    if args.json:
        print(json.dumps(description, ensure_ascii=False, indent=2))
        return 0
    print(f"root: {description['data_root']}")
    print(f"file: {description['path']}")
    if description["error"]:
        print(f"error: {description['error']}")
    group = None
    for row in description["settings"]:
        if row["group"] != group:
            group = row["group"]
            print(f"\n{group}")
        print(f"  {row['key']:<20} {str(row['value']):<40} [{row['source']}] {row['help']}")
    return 0


def _one_shot(action: Callable[[Runtime], Coroutine[Any, Any, Any]]) -> Any:
    """Hold the runtime for one command and let it go, whatever the command did."""
    async def runner() -> Any:
        runtime = Runtime()
        await runtime.start()
        try:
            return await action(runtime)
        finally:
            await runtime.close()

    return asyncio.run(runner())


def _show(payload: Any, *, machine: bool) -> None:
    if machine:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _counts(rows: list[dict[str, Any]], scanned: int, skipped: int, complete: bool) -> str:
    """What was read, said honestly: a capped read is never presented as the whole."""
    text = f"{len(rows)} shown, {scanned} stored records read"
    if not complete:
        text += "; the read stopped before the end of the memory"
    if skipped:
        text += f"; {skipped} records could not be read"
    return text


def tasks_command(argv: list[str]) -> int:
    """`oneiro tasks` — the owner's work: what it is, where it stands, run it now."""
    parser = argparse.ArgumentParser(prog="oneiro tasks",
                                     description="Oneiro tasks: list, show, add, run, tick")
    parser.add_argument("action", nargs="?", default="list",
                        choices=("list", "show", "add", "run", "tick"))
    parser.add_argument("task_id", nargs="?", help="the task to run, or to read the history of")
    parser.add_argument("--title", default="", help="what the task is, in your own words")
    parser.add_argument("--detail", default="", help="the longer version, if there is one")
    parser.add_argument("--role", default="executor", choices=tasks.ROLES)
    parser.add_argument("--retry", action="store_true",
                        help="make another attempt after a failure or an unknown outcome")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if args.action == "show":
        if not args.task_id:
            print("error: a task id is required to read its history")
            return 2
        result = _one_shot(lambda owner: tasks.history(owner, args.task_id))
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 0
        print(f"{result['id']}  {result['state']}  {result['title']}")
        print(f"    {result['why']}")
        if result["blocked_by_titles"]:
            print(f"    waits for: {', '.join(result['blocked_by_titles'])}")
        if result["last_result"]:
            print(f"    last result: {result['last_result'][:400]}")
        for attempt in result["runs"]:
            print(f"    attempt {attempt['attempt']} as {attempt['role']}: {attempt['state']}"
                  f"  {attempt['started_at']} -> {attempt['updated_at']}")
            if attempt["notes"]:
                print(f"      {attempt['notes'][:400]}")
        return 0

    if args.action == "add":
        if not args.title.strip():
            print("error: --title is required to add a task")
            return 2
        client = tasks.client_id_for(args.title + "\n" + args.detail, tasks.utcnow())
        result = _one_shot(lambda owner: tasks.create(
            owner, title=args.title, detail=args.detail, role=args.role, client_id=client))
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        task = result["task"]
        print(f"{task['id']}  {task['state']}  {task['title']}"
              + ("  (already there)" if result["duplicate"] else ""))
        print(f"run it with: oneiro tasks run {task['id']}")
        return 0

    if args.action == "run":
        if not args.task_id:
            print("error: a task id is required to run one")
            return 2
        result = _one_shot(lambda owner: tasks.run_now(owner, args.task_id,
                                                       retry=args.retry))
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 0
        if not result.get("started", True):
            print(f"{args.task_id}: not started — {result.get('why') or 'it cannot start'}")
            return 0
        run = result.get("run") or {}
        print(f"attempt {run.get('attempt', 1)} of {args.task_id}: {result['state']}")
        for step in result.get("steps") or ():
            print(f"  {step['index']}. {step['tool']}: {step['decision']} — {step['reason']}")
        if result.get("text"):
            print(f"  {result['text']}")
        return 0 if result["state"] == "completed" else 1

    if args.action == "tick":
        result = _one_shot(tasks.tick)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 0
        worked = result.get("worked")
        print(f"level {result['level']}")
        if result["reconciled"]:
            print(f"attempts that stopped reporting: {', '.join(result['reconciled'])}")
        print(f"worked: {worked['id']} -> {worked['state']}" if worked
              else f"worked: nothing — {result['why']}")
        return 0

    async def listing(owner: Runtime) -> dict[str, Any]:
        found = await tasks.view(owner)
        return {**found.to_dict(), "level": tasks.level(),
                "level_error": tasks.settings_error()}

    payload = _one_shot(listing)
    _show(payload, machine=args.json)
    if args.json:
        return 0
    if not payload["tasks"]:
        print("no tasks yet. Add one with: oneiro tasks add --title \"...\"")
        return 0
    print(f"initiative: {payload['level']}"
          + (f"  ({payload['level_error']})" if payload["level_error"] else ""))
    for row in payload["tasks"]:
        print(f"{row['id']}  {row['state']:<9} {row['title']}")
        print(f"    {row['why']}")
        for attempt in row["runs"]:
            print(f"    attempt {attempt['attempt']} as {attempt['role']}: "
                  f"{attempt['state']}"
                  + (f" — {attempt['notes'][:120]}" if attempt["notes"] else ""))
    print(_counts(payload["tasks"], payload["scanned"], payload["skipped"],
                  payload["complete"]))
    return 0


def schedules_command(argv: list[str]) -> int:
    """`oneiro schedules` — the standing instructions and the clock that runs them."""
    parser = argparse.ArgumentParser(prog="oneiro schedules",
                                     description="Oneiro schedules: list, add, remove, tick")
    parser.add_argument("action", nargs="?", default="list",
                        choices=("list", "add", "remove", "tick"))
    parser.add_argument("schedule_id", nargs="?", help="the schedule to call off")
    parser.add_argument("--title", default="", help="the task this schedule makes")
    parser.add_argument("--cron", default="", help="e.g. '0 9 * * *' for 09:00 every day")
    parser.add_argument("--detail", default="", help="what the task should say, in full")
    parser.add_argument("--role", default="executor", choices=tasks.ROLES)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if args.action == "add":
        if not args.title.strip() or not args.cron.strip():
            print("error: --title and --cron are required to add a schedule")
            return 2
        client = tasks.client_id_for(args.cron + "\n" + args.title, tasks.utcnow())
        result = _one_shot(lambda owner: schedule_module.add(
            owner, title=args.title, cron=args.cron, detail=args.detail, role=args.role,
            client_id=client))
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        record = result["schedule"]
        print(f"{record['id']}  {record['cron']}  {record['task_title']}"
              + ("  (already there)" if result["duplicate"] else ""))
        return 0

    if args.action == "remove":
        if not args.schedule_id:
            print("error: a schedule id is required to call one off")
            return 2
        client = tasks.client_id_for("remove " + args.schedule_id, tasks.utcnow())
        result = _one_shot(lambda owner: schedule_module.remove(
            owner, args.schedule_id, client_id=client))
        print(f"{result['id']}: called off" + (" (it was already off)"
                                               if result["duplicate"] else ""))
        return 0

    if args.action == "tick":
        result = _one_shot(schedule_module.tick)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 0
        print(f"level {result['level']} at {result['at']}")
        for fired in result["fired"]:
            print(f"fired {fired['schedule_id']} -> {fired['task_id']}"
                  + (" (the task was already there)" if fired["duplicate_task"] else ""))
        for held in result["due"]:
            print(f"due but not fired: {held['title']} ({held['cron']})")
        worked = result.get("worked")
        if worked:
            print(f"worked: {worked['id']} -> {worked['state']}" if worked.get("id")
                  else f"worked: nothing — {result['why']}")
        else:
            print(f"worked: nothing — {result['why']}")
        return 0

    async def listing(owner: Runtime) -> dict[str, Any]:
        return await schedule_module.listing(owner)

    payload = _one_shot(listing)
    _show(payload, machine=args.json)
    if args.json:
        return 0
    if not payload["schedules"]:
        print("no schedules yet. Add one with: oneiro schedules add --title \"...\" "
              "--cron \"0 9 * * *\"")
    for row in payload["schedules"]:
        state = "on" if row["enabled"] else "off"
        print(f"{row['id']}  {state}  {row['cron']:<16} {row['title']}")
        print(f"    next: {row['next_at'] or 'never'}"
              + (f" (due now)" if row["due_now"] else "")
              + (f"  {row['problem']}" if row["problem"] else ""))
    print(f"initiative is {payload['level']}: "
          + ("a schedule fires" if payload["fires"]
             else "a schedule is held until you set initiative.level to scheduled"))
    return 0


def _arguments_of(tool: Any, pairs: list[str]) -> dict[str, Any]:
    """The exact call's arguments, typed by the tool's own declared schema.

    The schema is the authority for the type, so `--argument n=5` reaches a tool that
    declares an integer as an integer, and a string that only looks like a number stays
    a string. A name the tool does not declare is left as given: the module refuses it
    with the field named, which is a better sentence than a guess made here.
    """
    values: dict[str, Any] = {}
    for item in pairs:
        if "=" not in item:
            raise ValueError(f"an argument is name=value, got {item!r}")
        name, raw = item.split("=", 1)
        name = name.strip()
        kind = (tool.properties.get(name) or {}).get("type")
        if kind == "integer" and re.fullmatch(r"-?\d+", raw.strip()):
            values[name] = int(raw)
        elif kind == "boolean" and raw.strip().lower() in ("true", "false"):
            values[name] = raw.strip().lower() == "true"
        else:
            values[name] = raw
    return values


def _one_line(arguments: dict[str, Any], limit: int = 400) -> str:
    """The exact call as one readable line, bounded, with the rest counted."""
    text = ", ".join(f"{name}={value!r}" for name, value in sorted(arguments.items()))
    return text if len(text) <= limit else text[:limit] + f" …(+{len(text) - limit})"


def drafts_command(argv: list[str]) -> int:
    """`oneiro drafts` — the replies Oneiro has written and not sent.

    `send` is the owner's press and the only thing here that sends: it decides the
    approval and then releases exactly that call. `send --dry-run` asks the same question
    and sends nothing, and `send` without a press is refused by the module with the reason
    that nothing goes out until the owner presses.
    """
    parser = argparse.ArgumentParser(
        prog="oneiro drafts",
        description="Drafts: list, show, read, new, revise, discard, send, notice")
    parser.add_argument("action", nargs="?", default="list",
                        choices=("list", "show", "read", "new", "revise", "discard",
                                 "send", "notice"))
    parser.add_argument("draft_id", nargs="?", help="the draft to show, edit, send or call off")
    parser.add_argument("--tool", default="",
                        help="the MCP tool key the draft would call, e.g. mailbox.send_message")
    parser.add_argument("--argument", action="append", default=[], metavar="NAME=VALUE",
                        help="one exact argument of the call; repeatable")
    parser.add_argument("--updates-tool", default="",
                        help="the bot tool that reports your own chat, for `notice`")
    parser.add_argument("--source-id", default="", help="the record this draft answers")
    parser.add_argument("--reason", default="", help="why a draft was called off")
    parser.add_argument("--dry-run", action="store_true",
                        help="say whether the press would send, and send nothing")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    def need_tool(value: str) -> Any:
        if "." not in value:
            raise ValueError("error: --tool must be the key of a declared MCP tool")
        return value

    if args.action in ("read", "new"):
        need_tool(args.tool)
    if args.action in ("show", "revise", "discard", "send", "notice") and not args.draft_id:
        print(f"error: a draft id is required to {args.action} a draft")
        return 2
    if args.action == "notice" and ("." not in args.tool or "." not in args.updates_tool):
        print("error: --tool and --updates-tool must both name declared MCP tools")
        return 2

    if args.action == "list":
        payload = _one_shot(lambda owner: drafts.listing(owner))
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
            return 0
        if not payload["drafts"]:
            print("no drafts are waiting.")
        for item in payload["drafts"]:
            print(f"{item['id']}  {item['state']}  {item['why']}  ->  "
                  f"{item['target'] or item['tool']}")
            print(f"    {item['tool']}: {_one_line(item['arguments'])}")
        for item in payload["settled"]:
            print(f"{item['id']}  {item['state']}  {item['why']} "
                  f"({item['effect']['outcome']})")
        print(f"waiting for your press: {payload['waiting']}")
        return 0

    if args.action == "show":
        item = _one_shot(lambda owner: drafts.get(owner, args.draft_id))
        if args.json:
            print(json.dumps(item, ensure_ascii=False, indent=2, default=str))
            return 0
        print(f"{item['id']}  {item['state']}  {item['why']}")
        print(f"    tool: {item['tool']}")
        for name, value in sorted(item["arguments"].items()):
            print(f"    {name}: {str(value)[:2000]}")
        print(f"    effect: {item['effect']['kind']} -> {item['effect']['target'] or '—'} "
              f"({item['effect']['outcome']})")
        if item["result"]:
            print(f"    result: {str(item['result'])[:400]}")
        return 0

    async def with_tool(work: Any) -> Any:
        tool = await drafts.offered(args.tool)
        return await work(tool)

    if args.action in ("read", "new", "notice"):
        # `offered` is read for the schema: what a call may carry is the server's own
        # declaration, and a name it does not declare is refused with the field named.
        if args.action == "read":
            payload = _one_shot(lambda owner: with_tool(
                lambda tool: drafts.read_incoming(owner, tool=args.tool,
                                                  arguments=_arguments_of(tool, args.argument))))
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
                return 0
            if not payload["ok"]:
                print(f"error: the read did not finish: {payload['reason']}")
                return 2
            print(f"read {payload['read']} message(s) through {payload['tool']}")
            for note in payload["notes"]:
                print(f"  {note['id']}  {note['topic']}")
                print(f"    {str(note['body'])[:400]}")
            return 0

        if args.action == "new":
            created = _one_shot(lambda owner: with_tool(
                lambda tool: drafts.create(owner, tool=args.tool,
                                           arguments=_arguments_of(tool, args.argument),
                                           source_id=args.source_id)))
            if args.json:
                print(json.dumps(created, ensure_ascii=False, indent=2, default=str))
                return 0
            print(f"{created['id']}  {created['state']}  {created['why']}")
            print(f"    {created['tool']}: {_one_line(created['arguments'])}")
            print(f"nothing is sent yet. press with: oneiro drafts send {created['id']}")
            return 0

        found = _one_shot(lambda owner: drafts.get(owner, args.draft_id))
        sent = _one_shot(lambda owner: drafts.notify(owner, drafts.notice_for(owner, found),
                                                     tool=args.tool,
                                                     updates_tool=args.updates_tool))
        if args.json:
            print(json.dumps({**sent, "draft_id": found["id"]}, ensure_ascii=False,
                             indent=2, default=str))
            return 0
        print(f"notice to chat {sent['chat_id']}: "
              + ("delivered" if sent["ok"] else f"not delivered ({sent['reason']})"))
        return 0 if sent["ok"] else 2

    if args.action == "revise":
        # The tool comes from the **draft**, not from the command line: a draft is about one
        # exact call, and `--tool` here could only disagree with it. (Measured 2026-10-12: a
        # revise without `--tool` answered `unknown_tool: ''`, because the schema was read
        # from an empty flag instead of from the draft being edited.)
        async def edit(owner: Any) -> Any:
            found = await drafts.get(owner, args.draft_id)
            tool = await drafts.offered(str(found["tool"]))
            return await drafts.revise(owner, args.draft_id,
                                       arguments=_arguments_of(tool, args.argument))

        renamed = _one_shot(edit)
        if args.json:
            print(json.dumps(renamed, ensure_ascii=False, indent=2, default=str))
            return 0
        print(f"{renamed['id']}  {renamed['state']}  {renamed['why']}")
        print(f"    {renamed['tool']}: {_one_line(renamed['arguments'])}")
        print("the edited call has not been pressed: press it again if it is right now.")
        return 0

    if args.action == "discard":
        called_off = _one_shot(lambda owner: drafts.discard(owner, args.draft_id,
                                                           reason=args.reason))
        if args.json:
            print(json.dumps(called_off, ensure_ascii=False, indent=2, default=str))
            return 0
        print(f"{called_off['id']}  {called_off['state']}  {called_off['why']}")
        return 0

    if args.dry_run:
        asked = _one_shot(lambda owner: drafts.send(owner, args.draft_id, actor="owner",
                                                    dry_run=True))
        if args.json:
            print(json.dumps(asked, ensure_ascii=False, indent=2, default=str))
            return 0
        print(f"{asked['draft']['id']}  would send: {asked['why']}")
        return 0

    result = _one_shot(lambda owner: drafts.press(owner, args.draft_id))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"{result['draft']['id']}  {result['draft']['state']}  {result['draft']['why']}"
          + (f"  ->  {result['text'][:200]}" if result["text"] else ""))
    if result["state"] == "uncertain":
        print("the send may or may not have happened; nothing will be retried by itself.")
    return 0 if result["ok"] else 2


def hooks_command(argv: list[str]) -> int:
    """`oneiro hooks` — the webhook secret, and the signature of one body.

    The secret is never printed. `key` names the file it lives in and its fingerprint,
    which is enough to check *which* key an integration is using; `sign` prints the
    signature of a body, which is what a script needs to send. A person who must have
    the value reads the file that was named, and the reports stay clean.
    """
    parser = argparse.ArgumentParser(prog="oneiro hooks",
                                     description="Inbound webhooks: the secret and the signature")
    parser.add_argument("action", nargs="?", default="key", choices=("key", "sign"))
    parser.add_argument("--body-file", default="", help="the exact bytes to sign")
    parser.add_argument("--rotate", action="store_true",
                        help="replace the secret; every integration must be told")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if args.action == "key":
        described = hooks.rotate_secret() if args.rotate else hooks.ensure_secret()
        if args.json:
            print(json.dumps(described, ensure_ascii=False, indent=2))
            return 0
        state = "rotated" if args.rotate else (
            "created" if described["created"] else "already present")
        print(f"secret: {state}  {described['path']}")
        print(f"length: {described['length']} bytes  fingerprint: {described['fingerprint']}")
        print("the value is not printed: the file above is what an integration reads")
        return 0

    if not args.body_file:
        print("error: --body-file is required to sign a body")
        return 2
    body = Path(args.body_file).read_bytes()
    try:
        secret = hooks.load_secret()
    except hooks.HookError as exc:
        print(f"error: {exc.code}: {exc.reason}")
        return 2
    signature = hooks.sign(secret, body)
    if args.json:
        print(json.dumps({"bytes": len(body), "header": hooks.HEADER,
                          "signature": signature}, ensure_ascii=False, indent=2))
        return 0
    print(f"{hooks.HEADER}: {signature}")
    return 0


def office_command(argv: list[str]) -> int:
    """`oneiro office` — office work in the isolated environment.

    The heavy work happens in a container, never on the owner's desktop, and the
    job is recorded: a run whose records the graph refuses is reported as a
    failure, because a job nobody can trace is not a job that happened.
    """
    parser = argparse.ArgumentParser(prog="oneiro office",
                                     description="Office work in the isolated environment: "
                                                 "document, spreadsheet, presentation and PDF")
    parser.add_argument("action", nargs="?", default="run", choices=("run", "image"))
    parser.add_argument("--topic", default="Oneiro: работа в изолированной среде",
                        help="what the document, sheet and slides are about")
    parser.add_argument("--out", default="", help="where the job folder is written")
    parser.add_argument("--stream", default=office_env.DEMO_STREAM,
                        help="the stream the job is recorded in (never the product's)")
    parser.add_argument("--no-record", action="store_true",
                        help="do the work without writing records (not for a demo)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    try:
        if args.action == "image":
            built = office_env.Sandbox().build()
            print(f"image: {built}")
            return 0
        job = office_env.run_job(args.topic, out_dir=Path(args.out) if args.out else None,
                                 stream=args.stream, record=not args.no_record)
    except office_env.OfficeError as exc:
        print(f"error: {exc.code}: {exc.reason}")
        return 2

    if args.json:
        print(json.dumps(office_env.report(job), ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"job: {job.id}  environment: {job.image}  container: {job.container}")
    print(f"topic: {job.topic}")
    print(f"work: {job.workdir}")
    print(f"sources: {', '.join(sorted(job.sources))}")
    print(f"the environment listed {len(job.listing_files)} file(s):")
    for line in job.listing.splitlines():
        print(f"    {line.strip()}")
    for item in job.artifacts:
        pages = f", {item.pages} page(s)" if item.pages is not None else (
            f", pages not measured: {item.pages_reason}" if item.pages_reason else "")
        print(f"  {item.name:<12} {item.bytes:>8} bytes  sha256 {item.sha256[:12]}{pages}")
    print(f"container stopped: {'yes' if job.stopped else 'NO'}")
    print(f"records: {len(job.records)} in stream {args.stream}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Oneiro standalone rewrite")
    parser.add_argument("command", nargs="?", default="serve",
                        choices=("doctor", "serve", "verify-model", "settings", "tasks",
                                 "schedules", "mcp", "skills", "research", "office", "hooks",
                                 "drafts"))
    parser.add_argument("--no-window", action="store_true", help="run server without window")
    # `settings`, `tasks` and `schedules` have options of their own, and a
    # positional with nargs="*" cannot absorb a token that starts with a dash, so
    # each command's own arguments are collected here and handed over whole. Every
    # other command takes none, and a stray word is still an error, not silence.
    args, rest = parser.parse_known_args(argv)
    if args.command == "settings":
        return settings_command(rest)
    if args.command in ("tasks", "schedules"):
        handler = tasks_command if args.command == "tasks" else schedules_command
        try:
            return handler(rest)
        except (TaskError, ScheduleError) as exc:
            print(f"error: {exc}")
            return 2
        except GraphQueryError as exc:
            print(f"error: the memory could not be read ({exc.code}: {exc.reason}). "
                  f"Nothing was changed.")
            return 2
        except OwnershipError:
            print("error: another Oneiro process holds the runtime. Stop it, or point "
                  "ONEIRO_DATA_DIR somewhere else for this command.")
            return 2
    if args.command == "mcp":
        # The MCP surface owns itself; the command line only names it. A store that
        # cannot be written is a refusal, because a call is recorded or not made.
        try:
            return mcp_surface.mcp_command(rest)
        except mcp_module.McpError as exc:
            print(f"error: {exc}")
            return 2
        except GraphQueryError as exc:
            print(f"error: the memory could not be read ({exc.code}: {exc.reason}). "
                  f"Nothing was changed.")
            return 2
        except OwnershipError:
            print("error: another Oneiro process holds the runtime. Stop it, or point "
                  "ONEIRO_DATA_DIR somewhere else for this command.")
            return 2
    if args.command == "skills":
        # The skills surface owns itself too, and it is read-only: a search and a contract
        # read touch no records, so no runtime is held for them.
        return skills_module.skills_command(rest)
    if args.command == "research":
        return research_module.research_command(rest)
    if args.command == "office":
        return office_command(rest)
    if args.command == "hooks":
        return hooks_command(rest)
    if args.command == "drafts":
        # A draft is read and written through the memory, and the tools it names are MCP
        # servers of the owner's: the hub is closed on the way out either way, so a
        # command that started a server does not leave the child behind.
        try:
            return drafts_command(rest)
        except drafts.DraftError as exc:
            print(f"error: {exc.reason}: {exc}")
            return 2
        except ValueError as exc:
            print(f"error: {exc}")
            return 2
        except GraphQueryError as exc:
            print(f"error: the memory could not be read ({exc.code}: {exc.reason}). "
                  f"Nothing was changed.")
            return 2
        except OwnershipError:
            print("error: another Oneiro process holds the runtime. Stop it, or point "
                  "ONEIRO_DATA_DIR somewhere else for this command.")
            return 2
        finally:
            mcp_module.hub().close()
    if rest:
        parser.error(f"unrecognized arguments: {' '.join(rest)}")
    listener: socket.socket | None = None
    try:
        if args.command == "doctor":
            # Read-only: no runtime lease or graph writes.
            result = asyncio.run(Runtime().status())
            print(json.dumps(result, indent=2))
            return 0 if result["ready"] else 1
        if args.command == "verify-model":
            # One real provider call. No runtime lease, no graph write.
            report = asyncio.run(Runtime().verify_model())
            print(json.dumps(report, indent=2))
            return 0 if report["verified"] else 1
        host, port = str(config.value("web.host")), int(config.value("web.port"))
        listener = socket.socket()
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind((host, port))
        listener.listen(128)
        listener.setblocking(False)
        import uvicorn
        from oneiro.web import create_app
        # This process is the product, so it keeps the clock: a schedule fires
        # while the pages are served, and stopping it stops the schedules.
        server = uvicorn.Server(uvicorn.Config(create_app(scheduler=True), host=host,
                                             port=port, access_log=False,
                                             log_level="warning"))
        print(f"Oneiro: http://{host}:{port}", flush=True)

        if not args.no_window and config.value("ui.window") != "none":
            # Launch window in separate thread or fallback
            def _stop():
                server.should_exit = True
            threading.Thread(
                target=window.launch_window,
                args=(port,),
                kwargs={"on_close": _stop},
                daemon=True,
            ).start()

        server.run(sockets=[listener])
        return 0 if server.started else 2
    except (ValueError, OSError, OwnershipError):
        print("Oneiro cannot start: check configuration, runtime ownership and port availability.")
        return 2
    finally:
        if listener is not None:
            listener.close()


if __name__ == "__main__":
    raise SystemExit(main())
