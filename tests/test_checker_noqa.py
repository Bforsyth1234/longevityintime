"""Tests covering the `# noqa: closure` escape hatch in `checker.py`.

These tests are NOT part of the 20 SPEC-mandated tests in `SPEC.md` §6.
They pin the behavior of the suppression marker so a future refactor of
`checker.py` cannot silently re-enable violations in `example.py` and the
deliberate-string-target tests (T4, T15).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CHECKER = Path(__file__).parent.parent / "checker.py"


def _run(*paths: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), *(str(p) for p in paths)],
        capture_output=True,
        text=True,
    )


def _write(tmp_path: Path, name: str, source: str) -> Path:
    target = tmp_path / name
    target.write_text(source, encoding="utf-8")
    return target


def test_noqa_marker_suppresses_violation(tmp_path: Path) -> None:
    """A line ending with `# noqa: closure` must exit 0 with no output."""
    target = _write(
        tmp_path,
        "ok.py",
        'transition(inst, "DRAFT", "deliberate demo")  # noqa: closure\n',
    )
    result = _run(target)
    assert result.returncode == 0
    assert result.stdout == ""


def test_noqa_only_suppresses_its_own_line(tmp_path: Path) -> None:
    """The marker is line-scoped: a sibling violation must still fire."""
    target = _write(
        tmp_path,
        "mixed.py",
        'transition(inst, "DRAFT", "ok")  # noqa: closure\n'
        'transition(inst, "REVIEW", "bad")\n',
    )
    result = _run(target)
    assert result.returncode == 1
    assert "REVIEW" in result.stdout
    assert "DRAFT" not in result.stdout
    assert ":2:" in result.stdout  # the bad line is line 2


def test_unrelated_noqa_does_not_suppress(tmp_path: Path) -> None:
    """A bare `# noqa` or unrelated rule code must NOT silence the checker.

    The marker is namespaced (`# noqa: closure`) precisely so suppressions
    of other tools (mypy, ruff, etc.) on the same line do not accidentally
    disable the closure rule.
    """
    target = _write(
        tmp_path,
        "unrelated.py",
        'transition(inst, "DRAFT", "x")  # noqa: E501\n',
    )
    result = _run(target)
    assert result.returncode == 1
    assert "DRAFT" in result.stdout


def test_noqa_marker_stacks_with_other_suppressions(tmp_path: Path) -> None:
    """`# type: ignore` and `# noqa: closure` on the same line both work."""
    target = _write(
        tmp_path,
        "stacked.py",
        'transition(inst, "DRAFT", "x")  # type: ignore[arg-type]  # noqa: closure\n',
    )
    result = _run(target)
    assert result.returncode == 0
    assert result.stdout == ""


def test_multi_file_invocation_isolates_violations(tmp_path: Path) -> None:
    """Pre-commit batches files into one call; only dirty files must fail it."""
    clean = _write(
        tmp_path,
        "clean.py",
        'transition(inst, "DRAFT", "x")  # noqa: closure\n',
    )
    dirty = _write(
        tmp_path,
        "dirty.py",
        'transition(inst, "DRAFT", "x")\n',
    )
    result = _run(clean, dirty)
    assert result.returncode == 1
    assert str(dirty) in result.stdout
    assert str(clean) not in result.stdout
