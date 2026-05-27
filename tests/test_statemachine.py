"""Test suite for the closed-enumeration state machine library.

Implements the 20 target tests defined in SPEC.md §6. All tests are
currently stubs — each calls `pytest.fail()` so the suite starts in a
fully RED state, per SDD discipline. Implement them one at a time.
"""

import subprocess
import sys
from enum import Enum
from pathlib import Path

import pytest
from pydantic import ValidationError

from statemachine import (
    ClosedEnumerationError,
    IllegalTransitionError,
    StateMachine,
    UndeclaredStateError,
    check_reachability,
    create_instance,
    current,
    define_machine,
    history,
    transition,
)


class TrialState(Enum):
    """Canonical Clinical Trial lifecycle Enum used across tests (SPEC §7)."""

    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"


# ---------------------------------------------------------------------------
# Category 1: Structural Closure Guards
# ---------------------------------------------------------------------------


def test_define_machine_valid_enum() -> None:
    """Can successfully define a machine with an Enum."""
    transitions = [
        (TrialState.DRAFT, TrialState.REVIEW),
        (TrialState.REVIEW, TrialState.APPROVED),
        (TrialState.REVIEW, TrialState.REJECTED),
        (TrialState.APPROVED, TrialState.COMPLETED),
    ]
    machine = define_machine(
        states=TrialState,
        transitions=transitions,  # type: ignore[arg-type]
        initial=TrialState.DRAFT,
    )

    assert isinstance(machine, StateMachine)
    assert machine.states is TrialState
    assert machine.initial is TrialState.DRAFT
    assert isinstance(machine.allowed_transitions, frozenset)
    assert machine.allowed_transitions == frozenset(transitions)


def test_define_machine_rejects_non_enum() -> None:
    """Passing a list of strings to `states` raises a validation error."""
    with pytest.raises(ValidationError):
        define_machine(
            states=["DRAFT", "REVIEW"],  # type: ignore[arg-type]  # noqa: closure
            transitions=[],
            initial="DRAFT",  # type: ignore[arg-type]
        )


def test_runtime_extension_rejection_instance() -> None:
    """Adding an attribute to MachineInstance raises ClosedEnumerationError."""
    machine = define_machine(
        states=TrialState,
        transitions=[(TrialState.DRAFT, TrialState.REVIEW)],
        initial=TrialState.DRAFT,
    )
    instance = create_instance(machine)
    with pytest.raises(ClosedEnumerationError):
        instance.injected_attr = "malicious"  # type: ignore[attr-defined]


def test_undeclared_state_rejection() -> None:
    """Passing a raw string to transition() raises UndeclaredStateError."""
    machine = define_machine(
        states=TrialState,
        transitions=[(TrialState.DRAFT, TrialState.REVIEW)],
        initial=TrialState.DRAFT,
    )
    instance = create_instance(machine)
    with pytest.raises(UndeclaredStateError):
        transition(instance, "COMPLETED", "raw string target")  # noqa: closure


def test_foreign_enum_rejection() -> None:
    """Passing a member of a different Enum raises UndeclaredStateError."""

    class OtherState(Enum):
        ALPHA = "ALPHA"
        BETA = "BETA"

    machine = define_machine(
        states=TrialState,
        transitions=[(TrialState.DRAFT, TrialState.REVIEW)],
        initial=TrialState.DRAFT,
    )
    instance = create_instance(machine)
    with pytest.raises(UndeclaredStateError):
        transition(instance, OtherState.ALPHA, "foreign enum target")


# ---------------------------------------------------------------------------
# Category 2: Execution Mechanics
# ---------------------------------------------------------------------------


def test_legal_transition_updates_state() -> None:
    """A -> B works and current() returns B."""
    machine = define_machine(
        states=TrialState,
        transitions=[(TrialState.DRAFT, TrialState.REVIEW)],
        initial=TrialState.DRAFT,
    )
    instance = create_instance(machine)
    assert current(instance) is TrialState.DRAFT
    result = transition(instance, TrialState.REVIEW, "submitted for review")
    assert result.success is True
    assert result.current_state is TrialState.REVIEW
    assert current(instance) is TrialState.REVIEW


def test_multiple_legal_transitions() -> None:
    """A chain of 3 consecutive legal transitions updates state accurately."""
    machine = define_machine(
        states=TrialState,
        transitions=[
            (TrialState.DRAFT, TrialState.REVIEW),
            (TrialState.REVIEW, TrialState.APPROVED),
            (TrialState.APPROVED, TrialState.COMPLETED),
        ],
        initial=TrialState.DRAFT,
    )
    instance = create_instance(machine)
    transition(instance, TrialState.REVIEW, "submit")
    transition(instance, TrialState.APPROVED, "approve")
    transition(instance, TrialState.COMPLETED, "complete")
    assert current(instance) is TrialState.COMPLETED


def test_illegal_transition_rejection() -> None:
    """A -> C (skipping B) raises IllegalTransitionError."""
    machine = define_machine(
        states=TrialState,
        transitions=[
            (TrialState.DRAFT, TrialState.REVIEW),
            (TrialState.REVIEW, TrialState.APPROVED),
        ],
        initial=TrialState.DRAFT,
    )
    instance = create_instance(machine)
    with pytest.raises(IllegalTransitionError):
        transition(instance, TrialState.APPROVED, "skip review")


def test_illegal_transition_state_unchanged() -> None:
    """After IllegalTransitionError is caught, current() remains at A."""
    machine = define_machine(
        states=TrialState,
        transitions=[
            (TrialState.DRAFT, TrialState.REVIEW),
            (TrialState.REVIEW, TrialState.APPROVED),
        ],
        initial=TrialState.DRAFT,
    )
    instance = create_instance(machine)
    with pytest.raises(IllegalTransitionError):
        transition(instance, TrialState.APPROVED, "skip review")
    assert current(instance) is TrialState.DRAFT


def test_explicit_self_transition() -> None:
    """A -> A succeeds when explicitly declared."""
    machine = define_machine(
        states=TrialState,
        transitions=[(TrialState.DRAFT, TrialState.DRAFT)],
        initial=TrialState.DRAFT,
    )
    instance = create_instance(machine)
    result = transition(instance, TrialState.DRAFT, "re-saved")
    assert result.success is True
    assert current(instance) is TrialState.DRAFT


def test_implicit_self_transition_fails() -> None:
    """A -> A fails when not declared in allowed_transitions."""
    machine = define_machine(
        states=TrialState,
        transitions=[(TrialState.DRAFT, TrialState.REVIEW)],
        initial=TrialState.DRAFT,
    )
    instance = create_instance(machine)
    with pytest.raises(IllegalTransitionError):
        transition(instance, TrialState.DRAFT, "implicit self-loop")


def test_terminal_state_blocks_all() -> None:
    """A state with 0 outbound edges rejects all subsequent transitions."""
    machine = define_machine(
        states=TrialState,
        transitions=[(TrialState.DRAFT, TrialState.COMPLETED)],
        initial=TrialState.DRAFT,
    )
    instance = create_instance(machine)
    transition(instance, TrialState.COMPLETED, "fast finish")
    assert current(instance) is TrialState.COMPLETED
    for target in TrialState:
        with pytest.raises(IllegalTransitionError):
            transition(instance, target, f"attempt {target.name}")
    assert current(instance) is TrialState.COMPLETED


# ---------------------------------------------------------------------------
# Category 3: Append-Only History Integrity
# ---------------------------------------------------------------------------


def test_history_records_success() -> None:
    """A valid transition appends exactly one SUCCESS record."""
    machine = define_machine(
        states=TrialState,
        transitions=[(TrialState.DRAFT, TrialState.REVIEW)],
        initial=TrialState.DRAFT,
    )
    # Inject a deterministic clock so we can assert an exact timestamp
    # rather than `isinstance(..., float)`. This also documents the DI seam.
    instance = create_instance(machine, clock=lambda: 1_700_000_000.0)
    transition(instance, TrialState.REVIEW, "submitted")
    h = history(instance)
    assert len(h) == 1
    assert h[0].status == "SUCCESS"
    assert h[0].from_state is TrialState.DRAFT
    assert h[0].to_state is TrialState.REVIEW
    assert h[0].reason == "submitted"
    assert h[0].timestamp == 1_700_000_000.0


def test_history_records_blocked_illegal() -> None:
    """IllegalTransitionError appends exactly one BLOCKED_ILLEGAL record."""
    machine = define_machine(
        states=TrialState,
        transitions=[(TrialState.DRAFT, TrialState.REVIEW)],
        initial=TrialState.DRAFT,
    )
    instance = create_instance(machine)
    with pytest.raises(IllegalTransitionError):
        transition(instance, TrialState.APPROVED, "illegal jump")
    h = history(instance)
    assert len(h) == 1
    assert h[0].status == "BLOCKED_ILLEGAL"
    assert h[0].from_state is TrialState.DRAFT
    assert h[0].to_state is TrialState.APPROVED
    assert h[0].reason == "illegal jump"


def test_history_records_blocked_undeclared() -> None:
    """UndeclaredStateError appends exactly one BLOCKED_UNDECLARED record."""
    machine = define_machine(
        states=TrialState,
        transitions=[(TrialState.DRAFT, TrialState.REVIEW)],
        initial=TrialState.DRAFT,
    )
    instance = create_instance(machine)
    with pytest.raises(UndeclaredStateError):
        transition(instance, "COMPLETED", "raw string")  # noqa: closure
    h = history(instance)
    assert len(h) == 1
    assert h[0].status == "BLOCKED_UNDECLARED"
    assert h[0].from_state is TrialState.DRAFT
    assert h[0].to_state == "COMPLETED"
    assert h[0].reason == "raw string"


def test_history_is_immutable() -> None:
    """Mutating the output of history() does not erase the internal trail."""
    machine = define_machine(
        states=TrialState,
        transitions=[(TrialState.DRAFT, TrialState.REVIEW)],
        initial=TrialState.DRAFT,
    )
    instance = create_instance(machine)
    transition(instance, TrialState.REVIEW, "submitted")

    snapshot = history(instance)
    assert isinstance(snapshot, tuple)
    assert len(snapshot) == 1

    with pytest.raises(AttributeError):
        snapshot.pop()  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        snapshot.clear()  # type: ignore[attr-defined]

    assert len(history(instance)) == 1
    assert history(instance)[0].status == "SUCCESS"


# ---------------------------------------------------------------------------
# Category 4: Graph Reachability
# ---------------------------------------------------------------------------


def test_reachability_all_reachable() -> None:
    """check_reachability returns an empty set when all states are reachable."""
    machine = define_machine(
        states=TrialState,
        transitions=[
            (TrialState.DRAFT, TrialState.REVIEW),
            (TrialState.REVIEW, TrialState.APPROVED),
            (TrialState.REVIEW, TrialState.REJECTED),
            (TrialState.APPROVED, TrialState.COMPLETED),
            (TrialState.REJECTED, TrialState.COMPLETED),
        ],
        initial=TrialState.DRAFT,
    )
    assert check_reachability(machine) == set()


def test_reachability_flags_unreachable() -> None:
    """check_reachability returns the set of orphan states."""
    # COMPLETED is an orphan — no edge ever points into it.
    machine = define_machine(
        states=TrialState,
        transitions=[
            (TrialState.DRAFT, TrialState.REVIEW),
            (TrialState.REVIEW, TrialState.APPROVED),
            (TrialState.REVIEW, TrialState.REJECTED),
        ],
        initial=TrialState.DRAFT,
    )
    assert check_reachability(machine) == {TrialState.COMPLETED}


# ---------------------------------------------------------------------------
# Category 5: Static Analysis Checker
# ---------------------------------------------------------------------------


def _run_checker(fixture_name: str) -> subprocess.CompletedProcess[str]:
    """Invoke checker.py against a fixture file and return the completed process."""
    fixture = Path(__file__).parent / "fixtures" / fixture_name
    checker = Path(__file__).parent.parent / "checker.py"
    return subprocess.run(
        [sys.executable, str(checker), str(fixture)],
        capture_output=True,
        text=True,
    )


def test_static_checker_passes_valid_code() -> None:
    """checker.py on a valid fixture exits 0."""
    result = _run_checker("valid_usage.py")
    assert result.returncode == 0, (
        f"checker.py unexpectedly flagged a valid fixture\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_static_checker_flags_planted_violation() -> None:
    """checker.py on a fixture with a string literal `to` arg exits 1."""
    result = _run_checker("planted_violation.py")
    assert result.returncode == 1, (
        f"checker.py failed to flag the planted violation\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "transition" in result.stdout
    assert "DRAFT" in result.stdout


def test_static_checker_flags_planted_states_violation() -> None:
    """checker.py on a fixture passing a list literal to `states=` exits 1."""
    result = _run_checker("planted_states_violation.py")
    assert result.returncode == 1, (
        f"checker.py failed to flag the planted states violation\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "define_machine" in result.stdout
    assert "List" in result.stdout
