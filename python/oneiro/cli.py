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
import socket
import threading
from typing import Any, Callable, Coroutine

from oneiro import (config, mcp as mcp_module, mcp_surface, research as research_module,
                    schedule as schedule_module, skills as skills_module, tasks, window)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Oneiro standalone rewrite")
    parser.add_argument("command", nargs="?", default="serve",
                        choices=("doctor", "serve", "verify-model", "settings", "tasks",
                                 "schedules", "mcp", "skills", "research"))
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
