"""The workspace's written rules for shell scripts, checked mechanically.

None of these rules is stated in this repository. They are the content of one
contract in the workspace skill catalog (``dev/parts/bash-defensive-patterns``):
strict mode, a guard on a required argument, error text on stderr, and quoted
expansions. A policy that looks the contract up can follow them; a policy that
guesses style cannot, which is what makes this task measure the lookup.
"""

from __future__ import annotations

import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "summarize.sh"
TEXT = SCRIPT.read_text(encoding="utf-8", errors="replace")
LINES = TEXT.splitlines()


def _strict_flags() -> set[str]:
    """Letters and words the script enables through `set`."""
    found: set[str] = set()
    for line in LINES:
        stripped = line.strip()
        if not stripped.startswith("set "):
            continue
        for token in stripped.split()[1:]:
            if token.startswith("--"):
                continue
            if token.startswith("-"):
                found |= set(token.lstrip("-"))
            else:
                found.add(token)
    return found


def test_the_script_exists_and_starts_with_a_shebang():
    assert SCRIPT.exists()
    assert LINES and LINES[0].startswith("#!")


def test_strict_mode_is_on():
    """Rule 1: exit on error, on an unset variable, and on a failed pipe."""
    flags = _strict_flags()
    missing = {"e", "u", "pipefail"} - flags
    assert not missing, f"strict mode is missing {sorted(missing)}: {sorted(flags)}"


def test_the_required_argument_is_guarded_before_it_is_used():
    """Rule 2: fail with a message instead of expanding an argument blindly.

    The contract names one idiom, ``: "${REQUIRED_VAR:?message}"``, and it is
    the one meant here. A written argument-count test that exits non-zero is
    accepted too: it guards the same use the same way, and this check exists to
    catch an unguarded argument, not to enforce a spelling. Whether the refusal
    actually happens is checked by running the script, in the visible tests.
    """
    documented = re.search(r"\$\{[A-Za-z0-9_@*#?!]+:\?", TEXT)
    explicit = re.search(r"\$\#", TEXT)
    assert documented or explicit, (
        "guard the argument as ${VAR:?message} or by an explicit $# check")


def test_the_refusal_is_written_to_stderr():
    """Rule 3: the error goes to stderr, so stdout stays parseable."""
    assert ">&2" in TEXT, "the refusal must be written to stderr (>&2)"


def test_every_variable_expansion_is_quoted():
    """Rule 4: unquoted expansions split and glob; every one must be quoted."""
    for number, line in enumerate(LINES, 1):
        bare = line.strip()
        if bare.startswith("#"):
            continue
        scrubbed = re.sub(r"\$\(\(.*?\)\)", "", line)     # arithmetic
        scrubbed = re.sub(r"\$\(.*?\)", "", scrubbed)     # command substitution
        scrubbed = re.sub(r'"[^"]*"', "", scrubbed)       # double-quoted text
        scrubbed = re.sub(r"'[^']*'", "", scrubbed)       # single-quoted text
        unquoted = re.findall(r"\$[A-Za-z_@]", scrubbed)
        assert not unquoted, f"unquoted expansion on line {number}: {bare}"
