"""Public API stubs for the closed-enumeration state machine library.

Function bodies are intentionally left unimplemented; this module defines
the type-safe boundaries against which the SDD test suite is written first.
"""

from collections import deque
from collections.abc import Callable
from enum import Enum
from typing import Any

from .exceptions import (
    ClosedEnumerationError,
    IllegalTransitionError,
    UndeclaredStateError,
)
from .models import (
    MachineInstance,
    StateMachine,
    TransitionDef,
    TransitionRecord,
    TransitionResult,
)

__all__ = [
    "ClosedEnumerationError",
    "IllegalTransitionError",
    "UndeclaredStateError",
    "MachineInstance",
    "StateMachine",
    "TransitionDef",
    "TransitionRecord",
    "TransitionResult",
    "check_reachability",
    "create_instance",
    "current",
    "define_machine",
    "history",
    "transition",
]


def define_machine(
    states: type[Enum],
    transitions: list[TransitionDef],
    initial: Enum,
) -> StateMachine:
    """Construct a frozen `StateMachine` definition.

    Validates that `states` is an `Enum` subclass, that `initial` is a member
    of `states`, and that every `(from_state, to_state)` pair in `transitions`
    is composed of members of `states`. Converts `transitions` into a
    `frozenset` for O(1) edge lookup and returns the frozen `StateMachine`.
    """
    machine = StateMachine(
        states=states,
        allowed_transitions=frozenset(transitions),
        initial=initial,
    )
    if not isinstance(machine.initial, machine.states):
        raise ValueError(
            f"initial state {machine.initial!r} is not a member of "
            f"{machine.states.__name__}"
        )
    for from_state, to_state in machine.allowed_transitions:
        if not isinstance(from_state, machine.states):
            raise ValueError(
                f"transition from-state {from_state!r} is not a member of "
                f"{machine.states.__name__}"
            )
        if not isinstance(to_state, machine.states):
            raise ValueError(
                f"transition to-state {to_state!r} is not a member of "
                f"{machine.states.__name__}"
            )
    return machine


def create_instance(
    machine: StateMachine,
    *,
    clock: Callable[[], float] | None = None,
) -> MachineInstance:
    """Instantiate a runtime container bound to `machine`.

    Sets the private `_current_state` to `machine.initial` and initializes
    the private `_history` to an empty list. The optional `clock` keyword
    overrides the default `time.time` source used to timestamp transitions —
    pass a fixed-value lambda from tests to control time deterministically.
    """
    instance = MachineInstance(machine=machine)
    instance._current_state = machine.initial
    instance._history = []
    if clock is not None:
        instance._clock = clock
    return instance


def transition(
    instance: MachineInstance,
    to: Any,
    reason: str,
) -> TransitionResult:
    """Evaluate and apply a requested state transition.

    Behavior:
    - If `to` is not a member of the bound Enum, append a
      `"BLOCKED_UNDECLARED"` record to history, then raise
      `UndeclaredStateError`.
    - If `(current_state, to)` is not in `machine.allowed_transitions`,
      append a `"BLOCKED_ILLEGAL"` record to history, then raise
      `IllegalTransitionError`.
    - Otherwise, mutate `_current_state`, append a `"SUCCESS"` record,
      and return a successful `TransitionResult`.
    """
    machine = instance.machine
    current_state = instance._current_state
    now = instance._clock

    if not isinstance(to, machine.states):
        instance._history.append(
            TransitionRecord(
                timestamp=now(),
                from_state=current_state,
                to_state=to,
                reason=reason,
                status="BLOCKED_UNDECLARED",
            )
        )
        raise UndeclaredStateError(
            f"{to!r} is not a declared member of {machine.states.__name__}"
        )

    if (current_state, to) not in machine.allowed_transitions:
        instance._history.append(
            TransitionRecord(
                timestamp=now(),
                from_state=current_state,
                to_state=to,
                reason=reason,
                status="BLOCKED_ILLEGAL",
            )
        )
        raise IllegalTransitionError(
            f"no transition declared from {current_state.name} to {to.name}"
        )

    instance._history.append(
        TransitionRecord(
            timestamp=now(),
            from_state=current_state,
            to_state=to,
            reason=reason,
            status="SUCCESS",
        )
    )
    instance._current_state = to
    return TransitionResult(success=True, current_state=to)


def current(instance: MachineInstance) -> Enum:
    """Return the current state of `instance`."""
    return instance._current_state


def history(instance: MachineInstance) -> tuple[TransitionRecord, ...]:
    """Return a mathematically decoupled snapshot of the audit history.

    External mutation of the returned object must not alter the
    instance's internal `_history`.
    """
    return tuple(instance._history)


def check_reachability(machine: StateMachine) -> set[Enum]:
    """Return the set of states unreachable from `machine.initial`.

    Performs a BFS over `allowed_transitions` starting at `machine.initial`
    and returns `set(machine.states) - reachable`.
    """
    adjacency: dict[Enum, list[Enum]] = {}
    for from_state, to_state in machine.allowed_transitions:
        adjacency.setdefault(from_state, []).append(to_state)

    reachable: set[Enum] = {machine.initial}
    queue: deque[Enum] = deque([machine.initial])
    while queue:
        node = queue.popleft()
        for neighbor in adjacency.get(node, ()):
            if neighbor not in reachable:
                reachable.add(neighbor)
                queue.append(neighbor)

    return set(machine.states) - reachable
