#!/usr/bin/env python3
"""Static analyzer (SPEC §5.3) that flags two closure violations:

  (a) `define_machine(states=...)` calls whose `states` argument is a
      literal collection or string instead of a closed enumeration (an
      `Enum` subclass reference or a `Literal[...]` annotation), and
  (b) `transition()` calls whose second positional argument is a literal
      string rather than a member of the bound Enum.

Reads each target .py file via Python's `ast` module without executing it.
Exits 0 if no violations are found, 1 if any violation is detected, 2 on
usage errors.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


class TransitionLiteralChecker(ast.NodeVisitor):
    """Walks `ast.Call` nodes targeting a function named `transition` and
    records calls whose second positional argument is an `ast.Constant`."""

    def __init__(self) -> None:
        self.violations: list[tuple[int, object]] = []

    def visit_Call(self, node: ast.Call) -> None:
        if self._is_transition_call(node.func) and len(node.args) >= 2:
            to_arg = node.args[1]
            if isinstance(to_arg, ast.Constant):
                self.violations.append((node.lineno, to_arg.value))
        self.generic_visit(node)

    @staticmethod
    def _is_transition_call(func: ast.expr) -> bool:
        if isinstance(func, ast.Name):
            return func.id == "transition"
        if isinstance(func, ast.Attribute):
            return func.attr == "transition"
        return False


class DefineMachineStatesChecker(ast.NodeVisitor):
    """Walks `ast.Call` nodes targeting `define_machine` and records calls
    whose `states` argument is a literal collection or string rather than
    a class reference or `Literal[...]` subscript."""

    _LITERAL_NODES = (ast.List, ast.Tuple, ast.Set, ast.Dict)

    def __init__(self) -> None:
        self.violations: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        if self._is_define_machine_call(node.func):
            states_arg = self._extract_states_arg(node)
            if states_arg is not None and not self._is_closed_enumeration(states_arg):
                self.violations.append(
                    (states_arg.lineno, type(states_arg).__name__)
                )
        self.generic_visit(node)

    @staticmethod
    def _is_define_machine_call(func: ast.expr) -> bool:
        if isinstance(func, ast.Name):
            return func.id == "define_machine"
        if isinstance(func, ast.Attribute):
            return func.attr == "define_machine"
        return False

    @staticmethod
    def _extract_states_arg(node: ast.Call) -> ast.expr | None:
        for kw in node.keywords:
            if kw.arg == "states":
                return kw.value
        if node.args:
            return node.args[0]
        return None

    @classmethod
    def _is_closed_enumeration(cls, arg: ast.expr) -> bool:
        if isinstance(arg, cls._LITERAL_NODES):
            return False
        if isinstance(arg, ast.Constant):
            return False
        return True


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: checker.py <path-to-python-file> [<path-to-python-file> ...]",
            file=sys.stderr,
        )
        return 2

    any_violations = False
    for target_str in argv[1:]:
        target = Path(target_str)
        source = target.read_text(encoding="utf-8")
        lines = source.splitlines()
        tree = ast.parse(source, filename=str(target))

        transition_checker = TransitionLiteralChecker()
        transition_checker.visit(tree)
        for lineno, literal in transition_checker.violations:
            line_text = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
            if "# noqa: closure" in line_text:
                continue
            print(
                f"{target}:{lineno}: transition() called with literal target "
                f"{literal!r} — use a member of the bound Enum instead."
            )
            any_violations = True

        states_checker = DefineMachineStatesChecker()
        states_checker.visit(tree)
        for lineno, node_kind in states_checker.violations:
            line_text = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
            if "# noqa: closure" in line_text:
                continue
            print(
                f"{target}:{lineno}: define_machine(states=...) received a "
                f"{node_kind} literal — pass an Enum subclass or Literal type instead."
            )
            any_violations = True

    return 1 if any_violations else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
