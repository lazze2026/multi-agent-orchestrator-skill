# Multi-Agent Orchestrator Loop v1.0 Design

**Status**: Draft for review  
**Scope**: Workspace-level timed Loop running inside Codex automation / heartbeat  
**Applies to**: Single-tool logical multi-agent orchestration only  
**Default cadence**: Every 5 minutes  
**Automation level**: Low-risk auto-advance with strict guardrails

---

## 1. Goal

Turn `multi-agent-orchestrator` from a one-shot coordination Skill into a **workspace-level timed Loop system** that can:

- wake up on a fixed schedule
- read orchestrator state from the workspace
- detect stale, blocked, partially completed, and ready-to-advance tasks
- update dashboard snapshots and loop checkpoints
- generate dispatch actions automatically
- auto-advance only tasks that are explicitly allowed and low risk

This Loop is **not** a background daemon in v1. It is a periodic automation run attached to the workspace and executed by Codex heartbeat / automation.

---

## 2. Non-Goals

Loop v1 does **not** aim to:

- autonomously modify business deliverables
- bypass Task Spec authorization
- auto-fix failed verification
- preempt locks
- coordinate work across multiple AI tools
- replace the event log as the source of truth

Loop v1 is intentionally constrained to **observe, derive, checkpoint, and cautiously advance low-risk tasks**.

---

## 3. Runtime Model

### 3.1 Trigger model

Loop runs through a Codex heartbeat / automation job every 5 minutes.

Each run performs one bounded cycle:

1. load workspace state
2. evaluate guardrails
3. append loop events
4. derive new actions
5. auto-advance eligible low-risk tasks
6. rebuild queue snapshot from events
7. write dashboard snapshot
8. write loop checkpoint
9. schedule the next run

### 3.2 Single-cycle rule

Each automation wake-up performs **one cycle only**.  
It must not self-loop indefinitely inside a single run.

Reason:

- keeps each run auditable
- avoids runaway retries
- makes pause/resume predictable
- keeps resource usage bounded

---

## 4. Core Principles

### 4.1 Event-first architecture

Loop never treats `queue/tasks.jsonl` as the only truth source.

Instead:

- **events are authoritative**
- queue is a derived operational view
- dashboard is a derived read-only view
- loop state is runtime metadata

### 4.2 Double-gate auto-advance

A task may be auto-advanced only if both are true:

1. its current status is in the auto-advance status allowlist
2. its Task Spec explicitly allows loop execution

Recommended Task Spec fields:

```yaml
loop_autorun: true
risk: low
loop_safe_actions:
  - read_only_checks
  - status_update_to_verifying
  - report_generation
```

### 4.3 Low-risk only

Loop v1 may auto-advance only tasks with:

- `risk: low` or `minimal`
- no pending authorization issue
- no unresolved dependency
- no lock conflict
- no write action against business deliverables
- only safe actions declared in `loop_safe_actions`

### 4.4 Read-heavy, write-light

Most Loop behavior should remain read-heavy:

- read state
- classify state
- write metadata
- append events

Direct state mutation is minimized and routed through:

- loop events
- queue rebuild
- loop checkpoints

---

## 5. Workspace Layout

Recommended workspace structure:

```text
workspace/
|-- orchestrator.json
|-- queue/
|   |-- tasks.jsonl
|   `-- tasks.snapshot.json
|-- events/
|   |-- task_*.jsonl
|   `-- loop-events.jsonl
|-- checkpoints/
|   `-- ...
|-- reports/
|   `-- ...
|-- locks/
|   `-- ...
|-- dashboard/
|   |-- state.json
|   `-- index.html
`-- loop/
    |-- loop_config.json
    |-- loop_state.json
    |-- checkpoints/
    |   `-- loop_ckpt_*.json
    `-- rebuild/
        |-- queue.snapshot.state.json
        `-- queue-rebuild-report.json
```

---

## 6. New Files

### 6.1 `loop/loop_config.json`

Defines runtime policy for the Loop.

Example:

```json
{
  "version": "1.0.0",
  "enabled": true,
  "mode": "codex-heartbeat",
  "interval_seconds": 300,
  "auto_advance": {
    "enabled": true,
    "allowed_risks": ["low", "minimal"],
    "allowed_statuses": [
      "queued",
      "verifying_ready",
      "stale_review",
      "checkpoint_resume_ready"
    ],
    "allowed_safe_actions": [
      "read_only_checks",
      "status_update_to_verifying",
      "status_update_to_running",
      "report_generation",
      "verifier_trigger"
    ],
    "require_task_spec_opt_in": true
  },
  "stale_detection": {
    "after_minutes": 30,
    "criteria": "no_event_or_heartbeat",
    "heartbeat_event_names": ["worker.heartbeat", "worker.progress", "worker.reported"],
    "exclude_statuses": ["blocked", "needs_human_decision", "cancelled", "done", "failed"],
    "allow_task_spec_override": true
  },
  "lock_policy": {
    "detect_conflicts": true,
    "allow_request_release": true,
    "mark_expired_after_stale_multiplier": 2,
    "auto_release_expired_locks": false,
    "require_human_decision_for_release": true
  },
  "guardrails": {
    "max_consecutive_failures": 3,
    "pause_on_lock_conflict_burst": true,
    "pause_on_repeated_verification_failure": true,
    "max_auto_advances_per_cycle": 3
  },
  "queue_rebuild": {
    "mode": "incremental",
    "allow_full_rebuild_fallback": true,
    "full_rebuild_check_every_n_cycles": 12,
    "snapshot_path": "loop/rebuild/queue.snapshot.state.json"
  },
  "writes": {
    "allow_queue_rebuild": true,
    "allow_dashboard_refresh": true,
    "allow_loop_checkpoints": true,
    "allow_business_deliverable_writes": false
  }
}
```

### 6.2 `loop/loop_state.json`

Stores current runtime status for the most recent Loop cycle.

Example:

```json
{
  "loop_status": "running",
  "last_run_at": "2026-06-13T10:05:00+08:00",
  "next_run_at": "2026-06-13T10:10:00+08:00",
  "iteration": 42,
  "consecutive_failures": 0,
  "last_result": "ok",
  "paused_reason": "",
  "last_checkpoint": "loop/checkpoints/loop_ckpt_20260613_1005.json",
  "last_rebuild_event_time": "2026-06-13T10:05:02+08:00"
}
```

### 6.3 `events/loop-events.jsonl`

Append-only event stream for Loop runtime decisions.

Example:

```json
{
  "event_id": "loop_evt_20260613_0042",
  "time": "2026-06-13T10:05:03+08:00",
  "loop_iteration": 42,
  "agent": "Loop",
  "event": "loop.auto_advance.applied",
  "task_id": "task_20260613_001_sub_002",
  "summary": "Auto-advanced queued task to running after double-gate check passed.",
  "caused_by": "eligible_low_risk_task",
  "next": "queue.rebuild"
}
```

---

## 7. Loop Cycle

### 7.1 Detailed cycle

Each heartbeat run should execute the following steps in order:

1. **Load config**
   - read `orchestrator.json`
   - read `loop/loop_config.json`

2. **Load state**
   - read task queue
   - read task events
   - read checkpoints
   - read locks
   - read reports

3. **Evaluate health**
   - stale task detection
   - blocked task detection
   - dependency readiness
   - lock conflict inspection
   - repeated failure detection

4. **Append observation events**
   - `loop.cycle.started`
   - `loop.state.observed`
   - `loop.blocker.detected`
   - `loop.stale.detected`
   - `loop.lock_conflict.detected`

5. **Generate derived actions**
   - dispatch suggestions
   - verifier suggestions
   - resume candidates
   - escalation candidates

6. **Auto-advance eligible tasks**
   - run double-gate check
   - validate `loop_safe_actions`
   - append task transition events
   - do not directly mutate queue as the primary operation

7. **Rebuild queue**
   - derive current task states from task events
   - prefer incremental rebuild from the previous snapshot
   - write `queue/tasks.jsonl`
   - write `queue/tasks.snapshot.json`
   - write rebuild report

8. **Refresh dashboard**
   - generate `dashboard/state.json`

9. **Write loop checkpoint**
   - write loop summary
   - record next run guidance

10. **Update loop state**
    - update `loop/loop_state.json`
    - append `loop.cycle.completed`

### 7.2 Stale detection

`stale` means the task has no useful progress signal within the configured window.

The default v1 criterion is `no_event_or_heartbeat`:

- no task event newer than `stale_detection.after_minutes`
- no heartbeat/progress/report event newer than `stale_detection.after_minutes`
- task status is not in `stale_detection.exclude_statuses`

A long-running task is **not stale** if it continues to emit heartbeat or progress events, even if the status remains `running`.

Task Spec may override the default threshold when the work naturally runs longer than the workspace default:

```yaml
stale_override:
  after_minutes: 90
  reason: "Long-running export task emits progress every batch."
```

Override rules:

- override must be declared in Task Spec
- override applies only to the target task or subtask
- override cannot exclude terminal or manual-decision statuses from `exclude_statuses`
- override must not disable heartbeat/progress evidence requirements

### 7.3 Lock conflict handling

Loop inspects lock conflicts in this order:

1. identify conflicting lock type and holders
2. check whether the holder is stale by `stale_detection`
3. if holder stale duration exceeds `after_minutes * mark_expired_after_stale_multiplier`, mark the lock as expired
4. append `loop.lock_expired.detected`
5. mark affected tasks as blocked or `needs_human_decision`

Loop may actively request lock release without releasing it:

```json
{
  "lock_request_release": {
    "enabled": true,
    "lock_id": "lock_backend_config_write",
    "reason": "Holder is stale and dependent high-priority task is blocked.",
    "requested_by": "Loop",
    "requires_decision": true
  }
}
```

Request behavior:

- append `lock.release.requested`
- notify Monitor / user-facing dashboard
- keep the original lock active until a human decision or explicit policy authorizes release
- never treat request creation as release approval

Loop v1 must **not** release expired locks by default. Automatic release is allowed only when all are true:

- `lock_policy.auto_release_expired_locks: true`
- the target lock resource is explicitly allowlisted by future policy
- release does not imply business deliverable writes
- a `lock.release.authorized` event or equivalent approval exists

---

## 8. Auto-Advance Rules

### 8.1 Required conditions

Task auto-advance is allowed only when all conditions pass:

- `status` is allowlisted
- Task Spec contains `loop_autorun: true`
- `risk` is `low` or `minimal`
- all dependencies are satisfied
- no conflicting read/write/exclusive lock
- no unresolved `needs_human_decision`
- no pending business write step
- every pending action is included in `loop_safe_actions`

### 8.2 Safe actions

`loop_safe_actions` is explicit. Loop v1 must not infer safety from task wording alone.

Recommended allowed safe actions:

```yaml
loop_safe_actions:
  - read_only_checks
  - status_update_to_verifying
  - status_update_to_running
  - report_generation
  - verifier_trigger
```

Safe action boundaries:

| Safe action | Allowed only when |
|-------------|-------------------|
| `status_update_to_verifying` | Deliverables exist, Worker has reported completion or partial completion, and Verifier input requirements are satisfied. |
| `status_update_to_running` | Task is queued or checkpoint-resume-ready, dependencies are satisfied, locks are available, authorization is valid, and no human decision is pending. |
| `verifier_trigger` | Verification plan exists, required artifacts exist, verifier scope is read-only or explicitly authorized, and the same task is not already under verification. |

Forbidden by default:

```yaml
loop_safe_actions_forbidden_by_default:
  - file_write
  - database_write
  - external_api_write
  - business_deliverable_write
  - lock_release
  - permission_change
```

### 8.3 Recommended initial allowlist

```text
queued
verifying_ready
stale_review
checkpoint_resume_ready
```

### 8.4 Forbidden transitions

Loop v1 must not auto-advance:

- `blocked -> running` when the block reason is unresolved
- `failed -> running` without human decision
- `needs_human_decision -> any-active-state`
- any transition that implies business write scope expansion

---

## 9. Queue Rebuild Strategy

### 9.1 Chosen strategy

The chosen strategy is:

**append events, then rebuild queue from an incremental snapshot**

This means:

- task events are authoritative
- queue is a derived view
- Loop writes transition events first
- rebuild transforms events into operational queue state
- incremental rebuild is the default for performance
- full rebuild remains available for validation or recovery

### 9.2 Why this strategy

Compared with direct row mutation:

- easier auditability
- safer recovery
- deterministic replay
- less risk of partial corruption
- better performance than full replay on every cycle

### 9.3 Incremental rebuild algorithm

Default rebuild flow:

1. load `loop/rebuild/queue.snapshot.state.json`
2. read `last_rebuild_event_time`
3. load only task and loop events after that timestamp
4. apply valid state transitions to the snapshot state
5. reject invalid or out-of-order transitions into rebuild warnings
6. derive current status, owner, next step, blocker, timestamps
7. write rebuilt records into queue outputs
8. update snapshot metadata and rebuild report

Snapshot validity checks:

- snapshot schema version matches the current compatible range
- snapshot `workspace_id` or canonical workspace path matches the active workspace
- snapshot `last_rebuild_event_time` is not later than the newest event timestamp
- snapshot event cursor exists in the event stream
- task count and known task IDs do not contradict current Task Spec inputs
- previous rebuild report did not end with unrecovered hard errors

If any validity check fails, Loop must run full rebuild fallback before writing a new queue snapshot.

Full rebuild fallback:

1. load all task events in time order
2. start from initial task states
3. replay valid state transitions
4. compare with incremental snapshot if available
5. write mismatch warnings and pause Loop if consistency is not recoverable

Scheduled full validation:

- run a full rebuild check every `queue_rebuild.full_rebuild_check_every_n_cycles`
- recommended default is `12`, which equals about 1 hour at the 5-minute cadence
- compare full rebuild output with incremental snapshot
- write drift warnings to `loop/rebuild/queue-rebuild-report.json`
- pause Loop if drift affects authorization, locks, dependencies, or terminal task status

Rebuild outputs:

- `queue/tasks.jsonl`
- `queue/tasks.snapshot.json`
- `loop/rebuild/queue.snapshot.state.json`
- `loop/rebuild/queue-rebuild-report.json`

### 9.4 Rebuild warnings

Examples:

- unknown status transition
- missing dependency artifact
- lock conflict unresolved
- duplicated completion event
- resume event without checkpoint evidence
- incremental snapshot timestamp gap

These do not silently disappear. They must be written into the rebuild report and surfaced in dashboard risks.

---

## 10. Guardrails

### 10.1 Pause conditions

Loop should automatically pause when:

- consecutive failures exceed threshold
- the same lock conflict repeats beyond threshold
- repeated verifier failures occur on the same task
- queue rebuild becomes inconsistent
- heartbeat configuration becomes invalid

### 10.2 Pause behavior

When paused:

- write `loop_status: paused`
- record `paused_reason`
- append `loop.paused`
- continue allowing dashboard refresh
- stop auto-advance until resumed

### 10.3 Resume behavior

Resume should require:

- clearing or acknowledging the pause reason
- writing `loop.resumed`
- preserving prior loop history

---

## 11. Dashboard Extensions for Loop

Dashboard should add a Loop section with:

- loop status
- last run time
- next run time
- iteration count
- consecutive failures
- paused reason
- auto-advance count in the last cycle
- last queue rebuild result
- last cycle summary
- Loop health
- recent Loop events

Recommended new dashboard fields:

```json
{
  "loop": {
    "status": "running",
    "last_run_at": "2026-06-13T10:05:00+08:00",
    "next_run_at": "2026-06-13T10:10:00+08:00",
    "iteration": 42,
    "paused_reason": "",
    "last_rebuild_status": "ok",
    "auto_advances_last_cycle": 2,
    "last_cycle_summary": {
      "stale_detected": 2,
      "blocked_detected": 1,
      "auto_advanced": 2,
      "rebuild_warnings": 0,
      "duration_ms": 1234
    },
    "health": {
      "consecutive_failures": 0,
      "last_failure_reason": "",
      "queue_rebuild_ok": true,
      "events_processed": 156
    },
    "recent_loop_events": [
      {
        "event_id": "loop_evt_20260613_0042",
        "time": "2026-06-13T10:05:03+08:00",
        "event": "loop.auto_advance.applied",
        "summary": "Auto-advanced task_20260613_001_sub_002 after safe-action validation."
      }
    ]
  }
}
```

The dashboard should show recent Loop events as a separate event stream so users can distinguish agent work events from scheduler decisions.

---

## 12. Codex Heartbeat Integration

### 12.1 Automation shape

The Codex automation should:

- target the workspace
- run every 5 minutes
- invoke a Loop runner entrypoint
- produce no side effects outside configured workspace paths

### 12.2 Runner entrypoint

Loop runner should be independently testable:

```bash
python scripts/loop_runner.py ./workspace --dry-run
python scripts/loop_runner.py ./workspace --once
python scripts/loop_runner.py ./workspace
```

Mode semantics:

- `--dry-run`: read state and print planned actions; do not write queue, dashboard, checkpoints, or events
- `--once`: execute one bounded cycle and exit
- no mode flag: run in automation-compatible mode, still executing only one cycle per invocation unless a future daemon mode is explicitly added

### 12.3 Recommended prompt shape

The heartbeat automation prompt should instruct the runner to:

- read `loop/loop_config.json`
- execute one loop cycle only
- respect low-risk auto-advance rules
- validate `loop_safe_actions`
- append loop events
- rebuild queue incrementally from events
- refresh dashboard state
- pause instead of guessing when policy is violated

### 12.4 Why heartbeat over daemon

Heartbeat is preferred in v1 because:

- easier to inspect
- easier to pause
- lower operational complexity
- no need for persistent custom process management

---

## 13. Failure Handling

### 13.1 Soft failure

Examples:

- temporary file read error
- missing optional report
- stale dashboard snapshot

Action:

- append warning event
- continue cycle if safe

### 13.2 Hard failure

Examples:

- queue rebuild inconsistency
- invalid config
- duplicate conflicting state transitions
- unauthorized write attempt

Action:

- append failure event
- increment consecutive failure count
- possibly pause loop

---

## 14. Security Boundaries

Loop v1 may automatically:

- read orchestration files
- append loop events
- rebuild queue
- write loop metadata
- refresh dashboard state
- trigger low-risk verifier paths

Loop v1 may not automatically:

- change business deliverable content
- repair failed outputs
- expand allowed paths
- override locks
- infer write authorization from absence of errors
- release locks unless an explicit future policy and authorization event allow it

---

## 15. Testing and Simulation

### 15.1 Runner test modes

Implementation must support:

- dry-run mode for policy review
- one-cycle mode for deterministic tests
- automation mode for heartbeat integration

The same guardrail logic must run in all modes. Dry-run may skip writes, but it must still report the events and mutations it would have produced.

### 15.2 Loop simulator

Recommended support tool:

```bash
python scripts/simulate_loop.py ./workspace --cycles 10 --output simulation.json
```

Simulator purpose:

- test Loop configuration before enabling automation
- predict auto-advance behavior
- debug guardrail logic
- show likely queue and dashboard changes across future cycles

The simulator is recommended for v1 implementation, but it can be delivered after the core runner if needed.

---

## 16. Rollout Plan

### Phase 1: Runtime skeleton

- add `loop_config.json`
- add `loop_state.json`
- add `loop-events.jsonl`
- implement one-cycle runner
- implement `--dry-run` and `--once`

### Phase 2: Queue rebuild

- implement incremental rebuild from snapshot
- implement full rebuild fallback
- implement scheduled full rebuild validation every 12 cycles by default
- implement snapshot validity checks
- derive queue snapshot
- add rebuild report

### Phase 3: Auto-advance

- implement double-gate checks
- implement `loop_safe_actions` validation
- implement precise status update actions
- implement verifier trigger preconditions
- implement low-risk verifier triggers
- implement pause/resume guards

### Phase 4: Dashboard integration

- add loop section to `dashboard/state.json`
- add health and last-cycle summary fields
- add recent Loop events stream
- extend static dashboard page

### Phase 5: Simulation support

- add Loop simulator
- add example simulation output
- document validation workflow

---

## 17. Minimum Acceptance Criteria

Loop v1 is acceptable only if it can:

1. run one bounded cycle from a Codex heartbeat
2. read orchestrator state without mutating business deliverables
3. append loop events for every cycle
4. detect stale, blocked, and partially completed tasks
5. define stale as `no_event_or_heartbeat` with excluded terminal/manual states
6. support Task Spec-level `stale_override` without disabling heartbeat/progress evidence
7. detect expired locks without releasing them by default
8. actively request lock release when policy allows, without treating the request as approval
9. generate dispatch actions
10. auto-advance only double-gated low-risk tasks with explicit `loop_safe_actions`
11. distinguish `status_update_to_verifying` from `status_update_to_running`
12. trigger verifier only when artifacts, plan, scope, and concurrency preconditions pass
13. rebuild queue incrementally from events, with snapshot validity checks and full rebuild fallback
14. run scheduled full rebuild validation every 12 cycles by default
15. pause on repeated hard failures
16. refresh dashboard state after each cycle
17. surface last-cycle summary, health, and recent Loop events in the dashboard
18. support dry-run and one-cycle runner modes
19. preserve auditability and resumability

---

## 18. Recommended Next Step

After this design is approved, implementation should begin with:

1. loop config schema
2. loop state schema
3. loop event schema
4. one-cycle runner script with `--dry-run` and `--once`
5. incremental queue rebuild script
6. scheduled full rebuild validation
7. precise auto-advance safe-action checks
8. dashboard loop panel fields
9. Loop simulator

This should be implemented as **Loop v1 runtime support**, not as a fully autonomous agent system.
