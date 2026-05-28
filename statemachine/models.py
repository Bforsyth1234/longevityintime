"""Pydantic domain models and type aliases for the state machine library."""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from .exceptions import ClosedEnumerationError

TransitionStatus = Literal["SUCCESS", "BLOCKED_ILLEGAL", "BLOCKED_UNDECLARED"]

TransitionDef = tuple[Enum, Enum]


class TransitionRecord(BaseModel):
    """An immutable, hash-chained audit record of a single transition attempt.

    `prev_chain_hash` and `chain_hash` form a tamper-evident chain over the
    audit log; see `statemachine.core.verify_history` for the verifier and
    the README's "Tamper Resistance" section for the threat model.
    """

    timestamp: float
    from_state: Any
    to_state: Any
    reason: str
    status: TransitionStatus
    prev_chain_hash: str
    chain_hash: str

    model_config = ConfigDict(frozen=True)


class TransitionResult(BaseModel):
    """The outcome of a `transition()` call."""

    success: bool
    current_state: Enum
    error: str | None = None


class StateMachine(BaseModel):
    """The frozen, immutable machine definition."""

    states: type[Enum]
    allowed_transitions: frozenset[tuple[Enum, Enum]]
    initial: Enum

    model_config = ConfigDict(frozen=True, extra="forbid")


class MachineInstance(BaseModel):
    """An opaque handle to a running state machine.

    The instance deliberately carries no state attributes — the current
    state, audit history, and injected clock all live in a module-private
    `WeakKeyDictionary` in `statemachine.core`. This blocks the "private by
    convention" reach-around (`instance._history.append(...)`) at the
    attribute layer; module-internal trespass against the backing dict is
    detected by `verify_history()` rather than prevented.
    """

    machine: StateMachine

    model_config = ConfigDict(extra="forbid", frozen=True)

    def __setattr__(self, name: str, value: Any) -> None:
        """Reject every post-construction attribute write.

        Pydantic v2 routes leading-underscore names that are *not* declared
        as `PrivateAttr` straight into `__dict__`, bypassing both
        `extra="forbid"` and `frozen=True`. An explicit allowlist (declared
        fields only) is required to close that gap. Pydantic itself will
        then reject the declared-field write because the model is frozen,
        which our except-block translates to `ClosedEnumerationError`.
        """
        if name not in type(self).model_fields:
            raise ClosedEnumerationError(
                f"cannot assign attribute {name!r} on MachineInstance: "
                "the state machine is closed to runtime extension"
            )
        try:
            super().__setattr__(name, value)
        except (ValueError, TypeError) as exc:
            raise ClosedEnumerationError(
                f"cannot assign attribute {name!r} on MachineInstance: "
                "the state machine is closed to runtime extension"
            ) from exc

    # Identity-based hashing so a `WeakKeyDictionary` keyed by the instance
    # distinguishes two `create_instance(machine)` calls even when their
    # pydantic field content is structurally equal.
    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, other: object) -> bool:
        return self is other
