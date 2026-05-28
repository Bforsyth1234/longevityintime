"""Tamper-resistance tests for the closure and audit-history guarantees.

These tests sit outside SPEC §6. They formalize a three-layer contract
that the README's headline guarantees ("closure", "the history is never
mutated") actually have to defend:

  Layer 1 — Public API closure. Honest callers cannot reach a primitive
            that mutates state or rewrites history.
  Layer 2 — Conventional reach-around blocked. Dereferencing leading-
            underscore attributes on the instance (Python's "private by
            convention") yields AttributeError, not mutable state.
  Layer 3 — Deliberate module-internal trespass detected. A caller who
            imports `statemachine.core._STATE` and mutates the audit
            log cannot do so silently; `verify_history()` returns False.

Tail truncation from inside _STATE is explicitly out of scope — no
single-process Python library can detect "the log used to be longer."
That limit is documented in the README.
"""

from __future__ import annotations

from enum import Enum

import pytest

from statemachine import (
    ClosedEnumerationError,
    MachineInstance,
    UnknownInstanceError,
    create_instance,
    current,
    define_machine,
    history,
    transition,
    verify_history,
)


class _S(Enum):
    A = "a"
    B = "b"
    C = "c"


def _machine():
    return define_machine(
        states=_S,
        transitions=[(_S.A, _S.B), (_S.B, _S.C)],
        initial=_S.A,
    )


# ---------------------------------------------------------------------------
# Layer 2: instance has no reachable state attributes
# ---------------------------------------------------------------------------


def test_instance_exposes_no_current_state_attribute() -> None:
    instance = create_instance(_machine())
    assert not hasattr(instance, "_current_state")


def test_instance_exposes_no_history_attribute() -> None:
    instance = create_instance(_machine())
    assert not hasattr(instance, "_history")


def test_instance_exposes_no_clock_attribute() -> None:
    instance = create_instance(_machine())
    assert not hasattr(instance, "_clock")


def test_instance_rejects_underscore_attribute_assignment() -> None:
    """Assigning to a leading-underscore name does not silently succeed."""
    instance = create_instance(_machine())
    with pytest.raises(ClosedEnumerationError):
        instance._current_state = _S.C  # type: ignore[attr-defined]


def test_instance_rejects_public_attribute_assignment() -> None:
    instance = create_instance(_machine())
    with pytest.raises(ClosedEnumerationError):
        instance.injected = "x"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Layer 1: TransitionRecord is frozen at the field level
# ---------------------------------------------------------------------------


def test_record_field_assignment_raises() -> None:
    """`record.status = ...` raises — records are frozen."""
    instance = create_instance(_machine())
    transition(instance, _S.B, "submit")
    record = history(instance)[0]
    with pytest.raises((TypeError, ValueError)):
        record.status = "BLOCKED_ILLEGAL"  # type: ignore[misc]


def test_record_reason_assignment_raises() -> None:
    instance = create_instance(_machine())
    transition(instance, _S.B, "submit")
    record = history(instance)[0]
    with pytest.raises((TypeError, ValueError)):
        record.reason = "fabricated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Layer 3: hash-chain verification detects deliberate trespass
# ---------------------------------------------------------------------------


def test_verify_history_passes_on_untouched_log() -> None:
    instance = create_instance(_machine())
    transition(instance, _S.B, "first")
    transition(instance, _S.C, "second")
    assert verify_history(instance) is True


def test_verify_history_passes_on_empty_log() -> None:
    """A freshly created instance with no transitions verifies clean."""
    instance = create_instance(_machine())
    assert verify_history(instance) is True


def test_verify_history_detects_record_content_tamper() -> None:
    """Bypassing frozen=True via object.__setattr__ is caught by the chain."""
    from statemachine.core import _STATE

    instance = create_instance(_machine())
    transition(instance, _S.B, "legit")
    log = _STATE[instance].history
    # object.__setattr__ bypasses pydantic's frozen guard.
    object.__setattr__(log[0], "reason", "rewritten after the fact")
    assert verify_history(instance) is False


def test_verify_history_detects_record_insertion() -> None:
    """Splicing a forged record into the middle of the log is caught."""
    from statemachine.core import _STATE

    instance = create_instance(_machine())
    transition(instance, _S.B, "first")
    transition(instance, _S.C, "second")
    log = _STATE[instance].history
    forged = log[0].model_copy(update={"reason": "smuggled in"})
    log.insert(1, forged)
    assert verify_history(instance) is False


def test_verify_history_detects_reordering() -> None:
    from statemachine.core import _STATE

    instance = create_instance(_machine())
    transition(instance, _S.B, "first")
    transition(instance, _S.C, "second")
    log = _STATE[instance].history
    log[0], log[1] = log[1], log[0]
    assert verify_history(instance) is False


def test_chain_hash_links_records() -> None:
    """Each record's prev_chain_hash equals the previous record's chain_hash."""
    instance = create_instance(_machine())
    transition(instance, _S.B, "first")
    transition(instance, _S.C, "second")
    log = history(instance)
    assert log[0].prev_chain_hash == "0" * 64
    assert log[1].prev_chain_hash == log[0].chain_hash


# ---------------------------------------------------------------------------
# Unregistered instances raise a domain-specific error, not a raw KeyError
# ---------------------------------------------------------------------------


def test_transition_on_directly_constructed_instance_raises() -> None:
    """Bypassing `create_instance` does not surface as a raw KeyError."""
    rogue = MachineInstance(machine=_machine())
    with pytest.raises(UnknownInstanceError):
        transition(rogue, _S.B, "submit")


def test_current_on_directly_constructed_instance_raises() -> None:
    rogue = MachineInstance(machine=_machine())
    with pytest.raises(UnknownInstanceError):
        current(rogue)


def test_history_on_directly_constructed_instance_raises() -> None:
    rogue = MachineInstance(machine=_machine())
    with pytest.raises(UnknownInstanceError):
        history(rogue)


def test_verify_history_on_directly_constructed_instance_raises() -> None:
    rogue = MachineInstance(machine=_machine())
    with pytest.raises(UnknownInstanceError):
        verify_history(rogue)


def test_model_copy_produces_unregistered_instance() -> None:
    """`model_copy()` returns a new instance that was never registered."""
    instance = create_instance(_machine())
    copy = instance.model_copy()
    with pytest.raises(UnknownInstanceError):
        transition(copy, _S.B, "submit")
