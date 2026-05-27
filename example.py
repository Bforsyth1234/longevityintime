"""Worked example: a Clinical Trial lifecycle modeled with `statemachine`.

Demonstrates SPEC §7 deliverable — a realistic ≥5-state machine that
exercises the full public API: define, instantiate, transition (success
and blocked), inspect current state, dump history, and run reachability.

Run with: `python example.py`
"""

from __future__ import annotations

from enum import Enum

from statemachine import (
    IllegalTransitionError,
    UndeclaredStateError,
    check_reachability,
    create_instance,
    current,
    define_machine,
    history,
    transition,
)


class TrialState(Enum):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


# Fixed timestamp source so the printed history is deterministic across runs.
_TICKS = iter(range(1_700_000_000, 1_700_000_100))


def _clock() -> float:
    return float(next(_TICKS))


def _print_header(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def _print_history(instance) -> None:
    for i, rec in enumerate(history(instance), start=1):
        from_name = rec.from_state.name if hasattr(rec.from_state, "name") else rec.from_state
        to_name = rec.to_state.name if hasattr(rec.to_state, "name") else repr(rec.to_state)
        print(
            f"  {i:>2}. t={rec.timestamp:.0f}  "
            f"{from_name:>9} -> {to_name:<9}  "
            f"[{rec.status:<18}]  reason={rec.reason!r}"
        )


def main() -> None:
    # ------------------------------------------------------------------
    # 1. Define the machine (DRAFT -> REVIEW -> APPROVED/REJECTED -> COMPLETED)
    # ------------------------------------------------------------------
    machine = define_machine(
        states=TrialState,
        transitions=[
            (TrialState.DRAFT, TrialState.REVIEW),
            (TrialState.REVIEW, TrialState.APPROVED),
            (TrialState.REVIEW, TrialState.REJECTED),
            (TrialState.REVIEW, TrialState.DRAFT),  # resubmission loop
            (TrialState.APPROVED, TrialState.COMPLETED),
            (TrialState.REJECTED, TrialState.COMPLETED),
        ],
        initial=TrialState.DRAFT,
    )

    _print_header("Reachability check")
    orphans = check_reachability(machine)
    print(f"  unreachable states: {orphans or '(none)'}")

    # ------------------------------------------------------------------
    # 2. Successful path: DRAFT -> REVIEW -> APPROVED -> COMPLETED
    # ------------------------------------------------------------------
    _print_header("Successful path: DRAFT -> REVIEW -> APPROVED -> COMPLETED")
    instance = create_instance(machine, clock=_clock)
    print(f"  initial state: {current(instance).name}")

    transition(instance, TrialState.REVIEW, "submitted for IRB review")
    transition(instance, TrialState.APPROVED, "approved by IRB chair")
    transition(instance, TrialState.COMPLETED, "enrollment closed, results filed")

    print(f"  final state:   {current(instance).name}")
    print("  history:")
    _print_history(instance)

    # ------------------------------------------------------------------
    # 3. Blocked path: an illegal jump and an undeclared string target
    # ------------------------------------------------------------------
    _print_header("Blocked path: illegal jump + undeclared string target")
    instance = create_instance(machine, clock=_clock)
    print(f"  initial state: {current(instance).name}")

    # T2: declared states but no edge from DRAFT to APPROVED.
    try:
        transition(instance, TrialState.APPROVED, "rubber-stamp attempt")
    except IllegalTransitionError as exc:
        print(f"  IllegalTransitionError raised: {exc}")

    # T1: a raw string is not a member of the bound Enum.
    try:
        transition(instance, "APPROVED", "string literal bypass attempt")  # noqa: closure
    except UndeclaredStateError as exc:
        print(f"  UndeclaredStateError raised:   {exc}")

    print(f"  state after blocks: {current(instance).name}  (unchanged)")
    print("  history (note both blocked attempts were recorded):")
    _print_history(instance)


if __name__ == "__main__":
    main()
