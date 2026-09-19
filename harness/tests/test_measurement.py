"""Provider outages must not be scored as capability.

The free tier of the provider admits paid accounts first, so a refused request
is routine. If such a run were counted as a lost task, every policy would look
worse than it is and the comparison would silently drift with the provider's
load. Unmeasured stays unmeasured: `solved` is None, and it is excluded from
every rate and every token total.
"""

import rsi


def run(task, solved):
    return {"task": task, "solved": solved, "steps": 1, "tool_calls": 1,
            "prompt_tokens": 100, "total_tokens": 120, "wall_seconds": 1.0,
            "stop_reason": "finished", "scratch": ""}


def test_a_refused_run_is_unmeasured_not_failed():
    results = [run("t01-start-total", True), run("t02-clamp-bounds", None)]
    summary = rsi.summarise(results)

    assert summary["tasks"] == 2
    assert summary["measured"] == 1
    assert summary["unmeasured"] == 1
    assert summary["solved"] == 1, "the refusal must not count as a lost task"
    assert summary["prompt_tokens"] == 100, "a refused run has no tokens to add"


def test_an_unmeasured_task_is_excluded_from_the_comparison():
    incumbent = [run("t01-start-total", True), run("t02-clamp-bounds", True)]
    candidate = [run("t01-start-total", True), run("t02-clamp-bounds", None)]

    comparison = rsi.compare(incumbent, candidate)

    assert comparison["unmeasured_tasks"] == ["t02-clamp-bounds"]
    assert comparison["tasks"] == 1, "only measured tasks are compared"
    assert comparison["tasks_lost"] == 0
    assert comparison["solved_after"] == 1


def test_measure_records_a_provider_refusal_as_unmeasured(monkeypatch):
    """A refusal during the online run is recorded, not raised, so the round survives."""
    import agent
    from policy import get_policy

    def refuse(*args, **kwargs):
        raise RuntimeError("provider failed after 4 attempts: HTTPError 429")

    monkeypatch.setattr(agent, "run_task", refuse)
    results = rsi.measure(get_policy("baseline"), ["t01-start-total"], "some-model", "test")

    assert results[0]["solved"] is None
    assert results[0]["stop_reason"] == "provider_refused"
    assert "429" in results[0]["error"]
