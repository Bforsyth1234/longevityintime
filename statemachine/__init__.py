"""Closed-enumeration state machine library."""

from .core import (
    check_reachability,
    create_instance,
    current,
    define_machine,
    history,
    transition,
    verify_history,
)
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
)

__all__ = [
    "ClosedEnumerationError",
    "IllegalTransitionError",
    "MachineInstance",
    "StateMachine",
    "TransitionDef",
    "TransitionRecord",
    "TransitionResult",
    "UndeclaredStateError",
    "UnknownInstanceError",
    "check_reachability",
    "create_instance",
    "current",
    "define_machine",
    "history",
    "transition",
    "verify_history",
]
