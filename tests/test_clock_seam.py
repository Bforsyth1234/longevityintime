"""Supplementary tests covering the `clock` dependency-injection seam.

These tests are NOT part of the 20 SPEC-mandated tests in `SPEC.md` §6;
they document and verify the time-source override on `create_instance`
that downstream SLA / deadline tests will build on.
"""

from __future__ import annotations

from enum import Enum

from statemachine import (
    create_instance,
    define_machine,
    history,
    transition,
)


class _S(Enum):
    A = "a"
    B = "b"
    C = "c"


def _make_machine():
    return define_machine(
        states=_S,
        transitions=[(_S.A, _S.B), (_S.B, _S.C)],
        initial=_S.A,
    )


def test_clock_default_is_wall_clock() -> None:
    """When no clock is provided, timestamps are non-zero floats."""
    machine = _make_machine()
    instance = create_instance(machine)
    transition(instance, _S.B, "default clock")
    record = history(instance)[0]
    assert isinstance(record.timestamp, float)
    assert record.timestamp > 1_600_000_000.0  # any time after 2020-09


def test_injected_clock_produces_exact_timestamps() -> None:
    """A fixed-value clock yields deterministic, repeatable timestamps."""
    machine = _make_machine()
    instance = create_instance(machine, clock=lambda: 42.0)
    transition(instance, _S.B, "first")
    transition(instance, _S.C, "second")
    assert [r.timestamp for r in history(instance)] == [42.0, 42.0]


def test_clock_supports_fast_forward_for_sla_checks() -> None:
    """A mutable clock cell allows simulating elapsed time without sleeping.

    This is the canonical pattern for SLA / deadline tests built on top of
    this library — a downstream caller can read `record.timestamp` and
    compare deltas without ever waiting on real wall-clock seconds.
    """
    machine = _make_machine()
    now = [1_700_000_000.0]
    instance = create_instance(machine, clock=lambda: now[0])

    transition(instance, _S.B, "t=0")
    now[0] += 86_400 * 7  # fast-forward seven days
    transition(instance, _S.C, "t=+7d")

    first, second = history(instance)
    assert second.timestamp - first.timestamp == 86_400 * 7
