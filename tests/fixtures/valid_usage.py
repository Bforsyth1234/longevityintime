"""Fixture for T19: a `transition()` call using an Enum attribute target.

The static checker (checker.py) must accept this file with exit code 0.
This file is never executed; it is parsed only via `ast` for inspection.
"""

transition(inst, TrialState.APPROVED, "approved by reviewer")
