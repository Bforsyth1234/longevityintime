"""Fixture for T20: a `transition()` call using a string literal target.

This file deliberately violates SPEC Rule S3 — the second positional argument
is `ast.Constant` instead of `ast.Attribute`. The static checker (checker.py)
must flag it and exit 1. This file is never executed; it is parsed only via
`ast` for inspection.
"""

transition(inst, "DRAFT", "intentionally violating the closed-enumeration rule")
