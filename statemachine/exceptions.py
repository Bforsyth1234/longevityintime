"""Custom exceptions for the closed-enumeration state machine library."""


class ClosedEnumerationError(Exception):
    """Raised when attempting to dynamically inject or add a new state
    to the machine definition or instance at runtime."""


class UndeclaredStateError(Exception):
    """Raised when attempting to transition to a target state that is
    not a declared member of the machine's bound Enum."""


class IllegalTransitionError(Exception):
    """Raised when attempting to transition between two declared states
    where no explicit transition edge was mapped in `allowed_transitions`."""
