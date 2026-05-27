# statemachine

A closed-enumeration state machine library with mathematical guarantees of
closure, an immutable append-only audit history, and a static analyzer to
enforce Enum usage at call sites.

See `SPEC.md` for the full technical specification, `example.py` for a runnable
Clinical Trial lifecycle, and `REPORT.md` for an annotated transcript of one
successful and one blocked path.

## Quick start

```python
from enum import Enum
from statemachine import define_machine, create_instance, transition, current

class TrialState(Enum):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"

machine = define_machine(
    states=TrialState,
    transitions=[
        (TrialState.DRAFT, TrialState.REVIEW),
        (TrialState.REVIEW, TrialState.APPROVED),
    ],
    initial=TrialState.DRAFT,
)

instance = create_instance(machine)
transition(instance, TrialState.REVIEW, "submitted for review")
assert current(instance) is TrialState.REVIEW
```

## Closure Model

The library enforces **closure** — the set of possible states and the set of
legal transitions are both fixed at machine-definition time and cannot be
extended at runtime. Closure is enforced at four layers:

1. **Type-level (`define_machine`).** The `states` argument must be a subclass
   of `enum.Enum`. Lists, tuples, dicts, and arbitrary classes are rejected by
   Pydantic validation. The Enum's membership is the universe of legal states
   for the lifetime of every instance bound to that machine.

2. **Structural (Pydantic).** `StateMachine` is declared with
   `model_config = ConfigDict(frozen=True, extra="forbid")` and
   `MachineInstance` with `extra="forbid"`. Any attempt to assign a new
   attribute (`instance.new_attr = "..."`) raises `ClosedEnumerationError`
   via the overridden `__setattr__`.

3. **Runtime (`transition`).** Every call validates the `to` argument against
   the bound Enum *before* the transition table is consulted. A raw string, an
   `int`, or a member of a different Enum is rejected. The library never
   coerces string-to-Enum.

4. **Static (`checker.py`).** An AST-based linter catches `transition()` calls
   that use a string literal as the second positional argument *before* the
   code is ever executed. Wire it into pre-commit so violations never reach
   `main`. See "Static analyzer" below.

The first three layers each emit a permanent audit record (`SUCCESS`,
`BLOCKED_ILLEGAL`, or `BLOCKED_UNDECLARED`) on every `transition()` call,
including ones that raise — see SPEC §5.2.

## Transition Table Format

Transitions are declared as a `list[tuple[Enum, Enum]]` of
`(from_state, to_state)` pairs:

```python
transitions = [
    (TrialState.DRAFT,    TrialState.REVIEW),
    (TrialState.REVIEW,   TrialState.APPROVED),
    (TrialState.REVIEW,   TrialState.REJECTED),
    (TrialState.REVIEW,   TrialState.DRAFT),     # resubmission loop
    (TrialState.APPROVED, TrialState.COMPLETED),
    (TrialState.REJECTED, TrialState.COMPLETED),
]
```

Rules:

- **Order is insignificant.** The list is internally converted to a
  `frozenset` for O(1) edge lookup.
- **Duplicates are deduplicated** by the frozenset cast — declaring the same
  edge twice is a no-op.
- **Self-loops require explicit declaration.** `(A, A)` must appear in the
  list for `transition(inst, A, "...")` to succeed when `current(inst) is A`.
  There is no implicit "stay" edge.
- **Terminal states** are states with zero outbound edges. Any `transition()`
  call out of them raises `IllegalTransitionError`.
- **Both endpoints must be members of `states`.** A mismatched pair like
  `(TrialState.DRAFT, OtherEnum.X)` is rejected at definition time.

`check_reachability(machine)` returns the set of states unreachable from
`machine.initial` via BFS over the table, which lets you statically detect
orphan states like a `COMPLETED` with no inbound edges.

## API

| Function | Returns | Purpose |
|---|---|---|
| `define_machine(states, transitions, initial)` | `StateMachine` | Frozen machine definition |
| `create_instance(machine, *, clock=None)` | `MachineInstance` | New runtime container |
| `transition(instance, to, reason)` | `TransitionResult` | Apply or block a move; always records to history |
| `current(instance)` | `Enum` | Current state |
| `history(instance)` | `tuple[TransitionRecord, ...]` | Immutable snapshot of audit history |
| `check_reachability(machine)` | `set[Enum]` | States unreachable from `initial` |

The `clock=` keyword on `create_instance` injects a `Callable[[], float]`
used to timestamp history records. Default is `time.time`. Tests and
reproducible demos pass a fixed value or a counter — see
`tests/test_clock_seam.py`.

### Note on `history()`'s return type

The original brief specifies `history(instance) -> list[TransitionRecord]`.
This library deliberately tightens that signature to
`tuple[TransitionRecord, ...]`. The audit-log requirement — *"the history
is never mutated; there is no edit or delete primitive"* — is a load-bearing
guarantee of the closure model, and a `tuple` enforces it at the type level
rather than relying on the caller not to call `.append()` or `.pop()` on a
returned list. `test_history_is_immutable` pins the behavior by asserting
that `.pop()` and `.clear()` on the snapshot raise `AttributeError`. Callers
that need a `list` can write `list(history(instance))`; the cost is one
shallow copy and the loss of the structural guarantee.

## Static analyzer (`checker.py`)

```bash
python checker.py path/to/your_module.py [more_files.py ...]
```

Parses each target via `ast` (no execution). Two rules are enforced:

1. **States closure (rule A).** A `define_machine(states=...)` call must pass
   a class reference (e.g. an `Enum` subclass) or a `Literal[...]` subscript.
   A literal `list`, `tuple`, `set`, `dict`, or bare string is rejected.
2. **Transition closure (rule B).** A `transition()` call must not use a
   string (or other) literal as its second positional argument; pass a
   member of the bound Enum instead.

Exit codes:

- `0` — no violations.
- `1` — at least one violation; line numbers and offending values printed.
- `2` — usage error.

A line ending with `# noqa: closure` is exempt from the check. This is
reserved for tests and worked examples that *intentionally* demonstrate the
runtime guard rejecting a string — see the three call sites in
`tests/test_statemachine.py` and `example.py`. Production code should never
use it.

A `.pre-commit-config.yaml` ships with the repo that wires the checker into
the standard pre-commit framework:

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

The hook excludes `tests/fixtures/` because `planted_violation.py` is
deliberately invalid.

## Testing

```bash
.venv/bin/python -m pytest
```

The suite contains the 20 SPEC-mandated tests plus
`tests/test_clock_seam.py`, which documents and verifies the clock
dependency-injection seam used by `example.py` and by downstream SLA tests.
