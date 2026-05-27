"""Pydantic domain models and type aliases for the state machine library."""

import time
from collections.abc import Callable
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, PrivateAttr

from .exceptions import ClosedEnumerationError

TransitionStatus = Literal["SUCCESS", "BLOCKED_ILLEGAL", "BLOCKED_UNDECLARED"]

TransitionDef = tuple[Enum, Enum]


class TransitionRecord(BaseModel):
    """An immutable audit record of a single transition attempt."""

    timestamp: float
    from_state: Any
    to_state: Any
    reason: str
    status: TransitionStatus


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
    """The runtime container holding current state and audit history."""

    machine: StateMachine
    _current_state: Enum = PrivateAttr()
    _history: list[TransitionRecord] = PrivateAttr()
    _clock: Callable[[], float] = PrivateAttr(default=time.time)

    model_config = ConfigDict(extra="forbid")

    def __setattr__(self, name: str, value: Any) -> None:
        """Translate Pydantic's rejection of unknown attributes into
        `ClosedEnumerationError` to enforce SPEC Rule C2."""
        try:
            super().__setattr__(name, value)
        except ValueError as exc:
            raise ClosedEnumerationError(
                f"cannot assign new attribute {name!r} to MachineInstance: "
                "the state machine is closed to runtime extension"
            ) from exc
