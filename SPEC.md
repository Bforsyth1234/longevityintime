# Technical Specification: Task Q — Closed-Enumeration State Machine

## 1. Objective

Build a Python state-machine library (`statemachine`) that provides mathematical guarantees of closure. The library must physically prevent runtime state injection, mathematically restrict transitions to an explicit allowlist, maintain an immutable append-only history of both successful and blocked transitions, and provide tools for static verification and reachability analysis.

---

## 2. Domain Models

All models must utilize `pydantic.BaseModel` with strict configurations to physically prevent runtime monkey-patching.

### 2.1 Types and Enums

* **`ClosedStateSet`**: Must strictly be implemented as a subclass of Python's built-in `enum.Enum`.
* **`TransitionDef`**: A simple structure mapping an allowed move: `tuple[Enum, Enum]` representing `(from_state, to_state)`.
* **`TransitionStatus`**: A literal with values `"SUCCESS"`, `"BLOCKED_ILLEGAL"`, and `"BLOCKED_UNDECLARED"`.

### 2.2 Pydantic Data Models

* **`TransitionRecord`**:
* `timestamp: float` (UTC epoch timestamp)
* `from_state: Any` (Can be None for initial state)
* `to_state: Any` (Typed as `Any` to capture undeclared string attempts)
* `reason: str`
* `status: TransitionStatus`


* **`TransitionResult`**:
* `success: bool`
* `current_state: Enum`
* `error: str | None`


* **`StateMachine` (The Definition)**:
* `states: type[Enum]`
* `allowed_transitions: frozenset[tuple[Enum, Enum]]`
* `initial: Enum`
* *Constraint:* `model_config = ConfigDict(frozen=True, extra="forbid")`


* **`MachineInstance` (The Runtime Container)**:
* `machine: StateMachine`
* `_current_state: Enum` (Private variable)
* `_history: list[TransitionRecord]` (Private variable)
* *Constraint:* `model_config = ConfigDict(extra="forbid")`



---

## 3. Exceptions

All custom errors must inherit from Python's base `Exception`.

* **`ClosedEnumerationError`**: Raised when attempting to dynamically inject or add a new state to the machine definition or instance at runtime.
* **`UndeclaredStateError`**: Raised when attempting to transition to a target state that is not a declared member of the machine's `ClosedStateSet`.
* **`IllegalTransitionError`**: Raised when attempting to transition between two declared states where no explicit transition edge was mapped.

---

## 4. Public Interfaces (API)

### `define_machine`

* **Signature:** `define_machine(states: type[Enum], transitions: list[TransitionDef], initial: Enum) -> StateMachine`
* **Behavior:** Validates that `initial` and all items in `transitions` belong to the `states` Enum. Converts `transitions` into a `frozenset` for $O(1)$ lookup. Returns the frozen `StateMachine`.

### `create_instance`

*(Note: standard instantiation wrapper)*

* **Signature:** `create_instance(machine: StateMachine) -> MachineInstance`
* **Behavior:** Instantiates the runtime container. Sets `_current_state` to `machine.initial` and initializes an empty `_history` list.

### `transition`

* **Signature:** `transition(instance: MachineInstance, to: Any, reason: str) -> TransitionResult`
* **Behavior:** Evaluates the requested move. Records to history, mutates state if legal, or raises an error if blocked. *(See Section 5.2 for explicit rules).*

### `current`

* **Signature:** `current(instance: MachineInstance) -> Enum`
* **Behavior:** Returns the current state of the machine instance.

### `history`

* **Signature:** `history(instance: MachineInstance) -> tuple[TransitionRecord, ...]`
* **Behavior:** Returns a mathematically decoupled (e.g., a `tuple` cast or deep copy) list of history events.

### `check_reachability`

* **Signature:** `check_reachability(machine: StateMachine) -> set[Enum]`
* **Behavior:** Executes a Breadth-First Search (BFS) starting at `machine.initial`. Returns a set of Enums that are completely unreachable.

---

## 5. Functional Requirements (The Rules)

### 5.1 Closure & Non-Extensibility

* **Rule C1:** `define_machine` must reject `states` arguments that are lists, strings, or arbitrary classes. It must strictly be an `Enum` class.
* **Rule C2:** Any attempt to assign `instance.states.NEW_STATE = ...` or `instance.NEW_ATTR = ...` must trigger a `ClosedEnumerationError` (handled via Pydantic's `extra="forbid"` and frozen configs).

### 5.2 Transitions & Audit Log

* **Rule T1 (Undeclared):** If `to` is not a member of the bound Enum, `transition()` must append a `"BLOCKED_UNDECLARED"` record to `_history`, and *then* raise `UndeclaredStateError`.
* **Rule T2 (Illegal):** If `(current_state, to)` is not in `allowed_transitions`, `transition()` must append a `"BLOCKED_ILLEGAL"` record to `_history`, and *then* raise `IllegalTransitionError`.
* **Rule T3 (Success):** If the edge exists, update `_current_state`, append a `"SUCCESS"` record to `_history`, and return a successful `TransitionResult`.
* **Rule T4 (Immutability):** External mutation of the object returned by `history()` must NOT alter the `MachineInstance`'s private `_history`.

### 5.3 Static Analyzer (`checker.py`)

* **Rule S1:** A standalone CLI script that reads a target `.py` file via Python's `ast` module without executing it.
* **Rule S2:** Subclasses `ast.NodeVisitor` to find all `ast.Call` nodes targeting the `transition` function.
* **Rule S3:** If the `to` argument (the second positional arg) is an `ast.Constant` (e.g., a literal string like `"APPROVED"`) instead of an `ast.Attribute` (e.g., `TrialState.APPROVED`), the analyzer prints the line number and exits with system code `1`.

---

## 6. Test Specification (The 20 Target Tests)

Your `pytest` suite must implement exactly the following tests to satisfy the Definition of Done.

### Category 1: Structural Closure Guards

1. **`test_define_machine_valid_enum`**: Can successfully define a machine with an Enum.
2. **`test_define_machine_rejects_non_enum`**: Passing a list of strings to `states` raises a validation error.
3. **`test_runtime_extension_rejection_instance`**: Attempting to dynamically add an attribute to `MachineInstance` raises `ClosedEnumerationError`.
4. **`test_undeclared_state_rejection`**: Passing a raw string (e.g., `"COMPLETED"`) to `transition()` raises `UndeclaredStateError`.
5. **`test_foreign_enum_rejection`**: Passing a valid Enum from a *different* class to `transition()` raises `UndeclaredStateError`.

### Category 2: Execution Mechanics

6. **`test_legal_transition_updates_state`**: State A $\rightarrow$ State B works and `current()` returns B.
7. **`test_multiple_legal_transitions`**: A chain of 3 consecutive legal transitions updates state accurately.
8. **`test_illegal_transition_rejection`**: State A $\rightarrow$ State C (an implicit jump skipping B) raises `IllegalTransitionError`.
9. **`test_illegal_transition_state_unchanged`**: After `IllegalTransitionError` is caught, `current()` remains at State A.
10. **`test_explicit_self_transition`**: If A $\rightarrow$ A is explicitly defined in the allowed list, `transition(A)` succeeds.
11. **`test_implicit_self_transition_fails`**: If A $\rightarrow$ A is NOT defined in the list, `transition(A)` fails.
12. **`test_terminal_state_blocks_all`**: A state defined with 0 outbound edges safely rejects all subsequent transition attempts.

### Category 3: Append-Only History Integrity

13. **`test_history_records_success`**: A valid transition appends exactly one `"SUCCESS"` record.
14. **`test_history_records_blocked_illegal`**: An `IllegalTransitionError` appends exactly one `"BLOCKED_ILLEGAL"` record *before* raising.
15. **`test_history_records_blocked_undeclared`**: An `UndeclaredStateError` appends exactly one `"BLOCKED_UNDECLARED"` record *before* raising.
16. **`test_history_is_immutable`**: Calling `.pop()` or `.clear()` on the output of `history(instance)` does not erase the internal audit trail.

### Category 4: Graph Reachability

17. **`test_reachability_all_reachable`**: `check_reachability` returns an empty set when all states are accessible from the initial state.
18. **`test_reachability_flags_unreachable`**: Define a graph with an isolated "orphan" state; assert `check_reachability()` correctly catches and returns it.

### Category 5: Static Analysis Checker

*(Note: Requires using Python's `subprocess` to run `checker.py` against dummy `.py` files in a `tests/fixtures/` directory)*
19. **`test_static_checker_passes_valid_code`**: Run `checker.py` on a fixture using valid Enum attributes. Assert exit code `0`.
20. **`test_static_checker_flags_planted_violation`**: Run `checker.py` against a fixture containing `transition(inst, "DRAFT", "reason")`. Assert it outputs a compilation warning and exits `1`.

---

## 7. Deliverable Checklist

* [x] **`statemachine/`** (Python Package) containing your Pydantic models, core logic, and exceptions.
* [x] **`checker.py`** (Executable Script) handling the AST validation.
* [x] **`example.py`** (Worked Example) instantiating a realistic $\ge$ 5 state machine (e.g., a Clinical Trial lifecycle: `DRAFT`, `REVIEW`, `APPROVED`, `REJECTED`, `COMPLETED`).
* [x] **`tests/`** (Pytest Suite) containing the 20 tests detailed in Section 6.
* [x] **`README.md`** Documenting the closure model and transition table format.
* [x] **`REPORT.md`** A short text walkthrough of one successful path and one blocked path from `example.py`, showcasing what the history log output looks like.