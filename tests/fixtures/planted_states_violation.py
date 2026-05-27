"""Fixture for the states-closure rule: a `define_machine()` call whose
`states` argument is a literal list of strings instead of an Enum subclass.

The static checker (checker.py) must flag this file and exit 1. This file
is never executed; it is parsed only via `ast` for inspection.
"""

define_machine(
    states=["DRAFT", "REVIEW", "APPROVED"],
    transitions=[],
    initial="DRAFT",
)
