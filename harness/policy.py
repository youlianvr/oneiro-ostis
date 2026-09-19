"""The harness policy: what the agent stores, retrieves and is shown.

This is the search space. Every knob here is a decision the harness makes
before the model ever sees the task, so a policy is a program that can be
rewritten, judged and deployed. The descriptor is what the knowledge graph
stores on a `concept_harness` node.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class HarnessPolicy:
    name: str = "baseline"
    # context: what the model is shown before it starts
    include_file_list: bool = True
    include_initial_tests: bool = True
    # history: what is kept from earlier steps
    context_mode: str = "full"          # full | window
    window_steps: int = 10              # used when context_mode == "window"
    observation_chars: int = 2000       # truncation of tool output shown back
    read_lines: int = 120               # max lines one read_file returns
    # control: when the loop stops and whether it verifies itself
    max_steps: int = 14
    verify_before_finish: bool = True   # failing tests send the agent back in
    max_verify_nudges: int = 1
    temperature: float = 0.2

    def descriptor(self) -> dict:
        return {
            "name": self.name,
            "include_file_list": self.include_file_list,
            "include_initial_tests": self.include_initial_tests,
            "context_mode": self.context_mode,
            "window_steps": self.window_steps,
            "observation_chars": self.observation_chars,
            "read_lines": self.read_lines,
            "max_steps": self.max_steps,
            "verify_before_finish": self.verify_before_finish,
            "max_verify_nudges": self.max_verify_nudges,
            "temperature": self.temperature,
        }

    @classmethod
    def from_descriptor(cls, data: dict) -> "HarnessPolicy":
        """Build a policy from a descriptor, rejecting unknown or bad fields."""
        if not isinstance(data, dict):
            raise ValueError("policy descriptor must be an object")
        known = set(cls().descriptor())
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown policy fields: {sorted(unknown)}")
        policy = cls(**{k: v for k, v in data.items() if k != "name"})
        policy = replace(policy, name=str(data.get("name") or policy.name))
        if policy.context_mode not in ("full", "window"):
            raise ValueError(f"bad context_mode: {policy.context_mode!r}")
        for field_name in ("window_steps", "observation_chars", "read_lines",
                           "max_steps", "max_verify_nudges"):
            if not isinstance(getattr(policy, field_name), int) or getattr(policy, field_name) < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        return policy


BASE = HarnessPolicy()

# Hand-written reference policies. The RSI loop proposes its own; these exist so
# a run always has a sane starting point and an ablation to compare against.
VARIANTS = {
    "baseline": BASE,
    "blind": replace(BASE, name="blind", include_file_list=False,
                     include_initial_tests=False),
    "windowed": replace(BASE, name="windowed", context_mode="window", window_steps=6),
    "terse": replace(BASE, name="terse", observation_chars=600, read_lines=60,
                     include_initial_tests=False),
    "cautious": replace(BASE, name="cautious", max_steps=20, max_verify_nudges=2,
                        context_mode="window", window_steps=8),
}


def get_policy(name: str) -> HarnessPolicy:
    if name not in VARIANTS:
        raise SystemExit(f"unknown policy {name!r}; known: {sorted(VARIANTS)}")
    return VARIANTS[name]
