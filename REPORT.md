# REPORT — Clinical Trial Lifecycle Walkthrough

Companion to `example.py`. Reproduces SPEC §7's required "one successful
path / one blocked path" demonstration with the exact runtime history-log
output produced by the library.

## Machine under test

Five states, six declared edges (one is a `REVIEW → DRAFT` resubmission
loop). Initial state is `DRAFT`.

| from       | to         | meaning                  |
|------------|------------|--------------------------|
| `DRAFT`    | `REVIEW`   | submit for IRB review    |
| `REVIEW`   | `APPROVED` | reviewer approves        |
| `REVIEW`   | `REJECTED` | reviewer rejects         |
| `REVIEW`   | `DRAFT`    | revise and resubmit      |
| `APPROVED` | `COMPLETED`| trial enrollment closes  |
| `REJECTED` | `COMPLETED`| trial closed unapproved  |

`check_reachability(machine)` returns the empty set — every state can be
reached from `DRAFT`.

Timestamps in the transcripts below come from a deterministic clock
injected via `create_instance(machine, clock=_clock)`; in production
calls would use `time.time()`.

## Successful path

Three legal moves: `DRAFT → REVIEW → APPROVED → COMPLETED`. Each appends
exactly one `SUCCESS` record and advances `_current_state`.

```
  initial state: DRAFT
  final state:   COMPLETED
  history:
   1. t=1700000000      DRAFT -> REVIEW     [SUCCESS           ]  reason='submitted for IRB review'
   2. t=1700000001     REVIEW -> APPROVED   [SUCCESS           ]  reason='approved by IRB chair'
   3. t=1700000002   APPROVED -> COMPLETED  [SUCCESS           ]  reason='enrollment closed, results filed'
```

Things to note:

- **Three records, three transitions** — there is a strict 1:1 mapping
  between successful `transition()` calls and `SUCCESS` rows.
- **`from_state`/`to_state` are Enum members**, not strings. The library
  refuses to coerce; if you read history programmatically you get
  `TrialState.REVIEW`, not the string `"REVIEW"`.
- **`reason` is free-form** and is the auditable "why". It is the only
  field a caller is trusted to populate.

## Blocked path

A fresh instance attempts two illegal operations. Both raise, both are
caught, and **both still appear in `history()`** — the audit log records
the *attempt*, not just the success. After both failures
`current(instance)` is still `DRAFT`.

```
  initial state: DRAFT
  IllegalTransitionError raised: no transition declared from DRAFT to APPROVED
  UndeclaredStateError raised:   'APPROVED' is not a declared member of TrialState
  state after blocks: DRAFT  (unchanged)
  history (note both blocked attempts were recorded):
   1. t=1700000003      DRAFT -> APPROVED   [BLOCKED_ILLEGAL   ]  reason='rubber-stamp attempt'
   2. t=1700000004      DRAFT -> 'APPROVED'  [BLOCKED_UNDECLARED]  reason='string literal bypass attempt'
```

Two distinct failure modes are visible:

1. **`BLOCKED_ILLEGAL` (record 1)** — `TrialState.APPROVED` *is* a
   declared state, but there is no `(DRAFT, APPROVED)` edge in
   `allowed_transitions`. This is the "rubber-stamp prevention" case:
   the reviewer step cannot be skipped.

2. **`BLOCKED_UNDECLARED` (record 2)** — the second argument is the
   string `"APPROVED"`. It looks plausible, but a raw string is not a
   member of the bound `TrialState` Enum, so the library rejects it
   before even consulting the transition table. Note the `to_state` is
   printed with quotes (`'APPROVED'`) precisely *because* it is a string,
   not an Enum member.

The "record-then-raise" ordering is mandated by SPEC §5.2 rules T1 and
T2 and verified by tests T14 and T15. It is what makes the history log
trustworthy as a forensic trail: an attacker who tries to bypass the
allowlist with `transition(inst, "APPROVED", "...")` leaves a permanent
fingerprint behind even though the call raised.

## How to reproduce

```bash
.venv/bin/python example.py
```

The output is byte-stable across runs because `example.py` injects a
counting integer clock; remove the `clock=_clock` argument to see real
UTC timestamps.
