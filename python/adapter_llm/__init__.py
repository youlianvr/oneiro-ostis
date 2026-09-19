"""Strategy candidate generation: LLM adapter + deterministic offline sweep.

The LLM adapter is OpenAI-compatible (base_url + api_key + model from the
environment; no provider is hard-coded). It is strictly optional:

  - if ONEIRO_LLM_BASE_URL / ONEIRO_LLM_API_KEY / ONEIRO_LLM_MODEL are set,
    make_generator() returns the LLM generator;
  - otherwise the offline deterministic sweep runs;
  - any LLM failure (network, bad JSON, schema violations) falls back to the
    offline sweep, so the dream cycle never depends on a network.

Every descriptor is validated against the strategy schema before it becomes a
candidate; invalid proposals are dropped, never repaired silently.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from strategy import Strategy, default_candidates, validate_descriptor

DEFAULT_TIMEOUT = 45.0

STRATEGY_SCHEMA_HINT = {
    "name": "string (unique, short)",
    "site_priority": "list of dig site names, first = visit first",
    "dig_limit": "integer 1..6, max artefacts taken from one site per episode",
    "deliver_order": "delivery points best-first, subset of [cove, beach, camp]",
}


class OfflineStrategyGenerator:
    """Deterministic sweep over orders x dig limits x delivery preferences."""

    name = "offline"

    def __init__(self, limit: int = 24):
        self.limit = limit

    def generate(self, context: dict, n: int) -> list[Strategy]:
        incumbent = None
        inc_desc = (context or {}).get("incumbent")
        if isinstance(inc_desc, dict):
            try:
                incumbent = Strategy.from_descriptor(inc_desc)
            except ValueError:
                incumbent = None
        return default_candidates(incumbent, limit=min(n or self.limit, self.limit))


@dataclass
class LLMStrategyGenerator:
    """OpenAI-compatible chat-completions client producing strategy JSON.

    Reads ONEIRO_LLM_BASE_URL, ONEIRO_LLM_API_KEY, ONEIRO_LLM_MODEL.
    Falls back to the offline sweep on any failure (and says so via `notes`).
    """

    name = "llm"
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    timeout: float = DEFAULT_TIMEOUT
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.base_url = (self.base_url or os.environ.get("ONEIRO_LLM_BASE_URL") or "").rstrip("/")
        self.api_key = self.api_key or os.environ.get("ONEIRO_LLM_API_KEY") or ""
        self.model = self.model or os.environ.get("ONEIRO_LLM_MODEL") or ""

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def generate(self, context: dict, n: int) -> list[Strategy]:
        if not self.configured:
            self.notes.append("llm not configured; using offline sweep")
            return OfflineStrategyGenerator().generate(context, n)
        try:
            proposals = self._ask_model(context, n)
        except Exception as exc:  # network, HTTP, JSON — never fatal
            self.notes.append(f"llm failed ({exc.__class__.__name__}: {exc}); using offline sweep")
            return OfflineStrategyGenerator().generate(context, n)

        candidates: list[Strategy] = []
        for proposal in proposals:
            errors = validate_descriptor(proposal) if isinstance(proposal, dict) else ["not an object"]
            if errors:
                self.notes.append(f"dropped invalid proposal: {errors}")
                continue
            strategy = Strategy.from_descriptor(proposal)
            if all(c.name != strategy.name for c in candidates):
                candidates.append(strategy)
        if not candidates:
            self.notes.append("llm proposed nothing valid; using offline sweep")
            return OfflineStrategyGenerator().generate(context, n)
        return candidates

    # ---------- transport ----------

    def _ask_model(self, context: dict, n: int) -> list[dict]:
        system = (
            "You propose expedition strategies for a deterministic mini-world. "
            "Reply with ONLY a JSON array of strategy objects; each object uses this schema: "
            + json.dumps(STRATEGY_SCHEMA_HINT)
            + ". No prose, no markdown fences."
        )
        user = (
            f"Propose exactly {n} strategies. Context about the agent's recorded experience "
            f"and the current strategy follows as JSON:\n{json.dumps(context, sort_keys=True)}"
        )
        payload = {
            "model": self.model,
            "temperature": 0.7,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = body["choices"][0]["message"]["content"].strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            raise ValueError("model did not return a JSON array")
        return parsed


def make_generator():
    """LLM adapter when configured, otherwise the deterministic offline sweep."""
    llm = LLMStrategyGenerator()
    return llm if llm.configured else OfflineStrategyGenerator()
