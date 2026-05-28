"""Public API for the closed-enumeration state machine library.

Runtime state — current node, audit history, and the injected clock — is
deliberately not stored as attributes on `MachineInstance`. It lives in a
module-private `WeakKeyDictionary` (`_STATE`) keyed by instance identity,
so `instance._history` and the like raise `AttributeError` rather than
exposing mutable internals. Deliberate trespass against `_STATE` is
detected by `verify_history()` via a per-record hash chain.
"""

import hashlib
import time
import weakref
from collections import deque
from collections.abc import Callable
from enum import Enum
from typing import Any

from .exceptions import (
    ClosedEnumerationError,
    IllegalTransitionError,
    UndeclaredStateError,
    UnknownInstanceError,
)
from .models import (
    MachineInstance,
    StateMachine,
    TransitionDef,
    TransitionRecord,
    TransitionResult,
    TransitionStatus,
)

__all__ = [
    "ClosedEnumerationError",
    "IllegalTransitionError",
    "UndeclaredStateError",
    "UnknownInstanceError",
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
    "verify_history",
]


GENESIS_HASH = "0" * 64


class _InstanceState:
    """Backing store for a single `MachineInstance`.

    Held only in the module-private `_STATE` map; never exposed as an
    attribute of `MachineInstance`.
    """

    __slots__ = ("current_state", "history", "clock")

    def __init__(self, current_state: Enum, clock: Callable[[], float]) -> None:
        self.current_state: Enum = current_state
        self.history: list[TransitionRecord] = []
        self.clock: Callable[[], float] = clock


_STATE: "weakref.WeakKeyDictionary[MachineInstance, _InstanceState]" = (
    weakref.WeakKeyDictionary()
)


def _get_state(instance: MachineInstance) -> _InstanceState:
    """Look up `instance` in `_STATE`, raising a domain-specific error on miss.

    A `MachineInstance` constructed directly or produced via `model_copy()`
    is never registered in `_STATE`; surfacing the resulting `KeyError`
    would leak an internal data structure, so the miss is translated into
    `UnknownInstanceError`.
    """
    try:
        return _STATE[instance]
    except KeyError as exc:
        raise UnknownInstanceError(
            "MachineInstance was not produced by create_instance(); "
            "direct construction and model_copy() are unsupported"
        ) from exc


def _safe_repr(value: Any) -> str:
    """Canonical string representation used inside the chain hash.

    Enums are serialized as `module:QualName.MEMBER` so the hash commitment
    is unambiguous across distinct Enum types that happen to share a class
    name and member name, and is stable across Python sessions independent
    of `id()` or memory layout.
    """
    if isinstance(value, Enum):
        cls = type(value)
        return f"{cls.__module__}:{cls.__qualname__}.{value.name}"
    return repr(value)


def _compute_chain_hash(
    timestamp: float,
    from_state: Any,
    to_state: Any,
    reason: str,
    status: str,
    prev_chain_hash: str,
) -> str:
    payload = "\x1f".join(
        [
            repr(timestamp),
            _safe_repr(from_state),
            _safe_repr(to_state),
            reason,
            status,
            prev_chain_hash,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _append_record(
    state: _InstanceState,
    from_state: Any,
    to_state: Any,
    reason: str,
    status: TransitionStatus,
) -> None:
    """Build a hash-chained `TransitionRecord` and append it to `state.history`."""
    prev_hash = state.history[-1].chain_hash if state.history else GENESIS_HASH
    timestamp = state.clock()
    chain_hash = _compute_chain_hash(
        timestamp, from_state, to_state, reason, status, prev_hash
    )
    state.history.append(
        TransitionRecord(
            timestamp=timestamp,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            status=status,
            prev_chain_hash=prev_hash,
            chain_hash=chain_hash,
        )
    )


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

    The instance itself is frozen and stateless; current state, audit
    history, and the optional `clock` injection are stored in the module-
    private `_STATE` map. The default clock is `time.time`.
    """
    instance = MachineInstance(machine=machine)
    _STATE[instance] = _InstanceState(
        current_state=machine.initial,
        clock=clock if clock is not None else time.time,
    )
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
    - Otherwise, advance the current state, append a `"SUCCESS"` record,
      and return a successful `TransitionResult`.

    Every appended record is hash-chained to its predecessor so that
    `verify_history()` can detect after-the-fact content tampering,
    insertion, or reordering of records inside `_STATE`.
    """
    state = _get_state(instance)
    machine = instance.machine
    current_state = state.current_state

    if not isinstance(to, machine.states):
        _append_record(state, current_state, to, reason, "BLOCKED_UNDECLARED")
        raise UndeclaredStateError(
            f"{to!r} is not a declared member of {machine.states.__name__}"
        )

    if (current_state, to) not in machine.allowed_transitions:
        _append_record(state, current_state, to, reason, "BLOCKED_ILLEGAL")
        raise IllegalTransitionError(
            f"no transition declared from {current_state.name} to {to.name}"
        )

    _append_record(state, current_state, to, reason, "SUCCESS")
    state.current_state = to
    return TransitionResult(success=True, current_state=to)


def current(instance: MachineInstance) -> Enum:
    """Return the current state of `instance`."""
    return _get_state(instance).current_state


def history(instance: MachineInstance) -> tuple[TransitionRecord, ...]:
    """Return an immutable snapshot of the audit history.

    The returned tuple is a shallow copy of the live log; the records
    themselves are frozen pydantic models, so callers cannot rewrite a
    record's fields. Module-internal tampering against `_STATE` is
    detected by `verify_history()`, not prevented here.
    """
    return tuple(_get_state(instance).history)


def verify_history(instance: MachineInstance) -> bool:
    """Recompute the per-record hash chain and confirm it is intact.

    Returns `True` iff every record's `prev_chain_hash` matches the prior
    record's `chain_hash` and every record's `chain_hash` matches the
    SHA-256 of its own content. This detects content mutation, insertion,
    and reordering of records inside `_STATE`. It cannot detect tail
    truncation — see the README's "Tamper Resistance" section for the
    threat model and the documented limit.
    """
    prev_hash = GENESIS_HASH
    for record in _get_state(instance).history:
        if record.prev_chain_hash != prev_hash:
            return False
        expected = _compute_chain_hash(
            record.timestamp,
            record.from_state,
            record.to_state,
            record.reason,
            record.status,
            prev_hash,
        )
        if record.chain_hash != expected:
            return False
        prev_hash = record.chain_hash
    return True


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
