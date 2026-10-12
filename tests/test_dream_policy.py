"""The candidate descriptor: it round-trips, refuses what it does not know, and sits
over the knobs the settings actually declare.

The last test is the honesty check that matters: if a shipped default drifts away from
the setting it names, `BASE` would stop being the policy the product runs, and every
judgement built on it would be against the wrong floor.
"""
from __future__ import annotations

import pytest

from chat_fakes import isolate
from oneiro import agent, config
from oneiro.dream.policy import (BASE, FIELDS, KNOBS, VARIANTS, PolicyError, TurnPolicy,
                                 get_policy)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    isolate(tmp_path, monkeypatch)


def test_the_descriptor_round_trips_through_its_stored_form():
    policy = get_policy("windowed")

    again = TurnPolicy.from_descriptor(policy.descriptor())

    assert again == policy
    assert set(policy.descriptor()) == set(FIELDS)


def test_a_field_the_descriptor_does_not_know_is_refused_by_name():
    with pytest.raises(PolicyError) as refused:
        TurnPolicy.from_descriptor({"history_messages": 4, "temperature": 0.2})

    message = str(refused.value)
    assert "temperature" in message
    assert "temperature" not in KNOBS


def test_a_partial_descriptor_keeps_the_defaults_for_what_it_omits():
    policy = TurnPolicy.from_descriptor({"include_facts": False})

    assert policy.include_facts is False
    assert policy.history_messages == BASE.history_messages


def test_a_value_of_the_wrong_shape_is_refused():
    for bad in ({"max_turns": -1}, {"context_chars": 1.5}, {"include_facts": 1},
                {"name": "  "}):
        with pytest.raises(PolicyError):
            TurnPolicy.from_descriptor(bad)
    with pytest.raises(PolicyError):
        TurnPolicy(history_messages=True)      # bool is not an integer count


def test_the_recorded_policy_is_the_settings_the_product_declares():
    assert BASE.history_messages == int(config.value("chat.history_messages"))
    assert BASE.context_chars == int(config.value("chat.context_chars"))
    assert BASE.max_turns == int(config.value("agent.max_turns"))
    assert BASE.observation_chars == agent.MAX_RESULT


def test_changed_fields_names_the_knobs_and_never_the_label():
    policy = get_policy("blind")
    renamed = TurnPolicy.from_descriptor({**policy.descriptor(), "name": "blind-again"})

    assert policy.changed_fields(BASE) == ("include_facts",)
    assert renamed.changed_fields(policy) == ()
    assert renamed != policy, "the label is still part of the record"


def test_every_hand_written_variant_is_valid_and_named_after_its_key():
    assert set(VARIANTS) == {"recorded", "blind", "windowed", "no_history", "tight_context",
                             "long_turn", "terse_observations"}
    for key, policy in VARIANTS.items():
        assert policy.name == key
        policy.check()
    assert get_policy("recorded") is BASE


def test_an_unknown_variant_is_refused_by_name():
    with pytest.raises(PolicyError) as refused:
        get_policy("cautious")

    assert "cautious" in str(refused.value)
