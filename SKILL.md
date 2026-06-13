---
name: multi-agent-orchestrator
description: Use when a complex task should be coordinated inside one AI tool with logical agents, task specs, worker briefs, dependencies, resource locks, event logs, checkpoints, dashboard snapshots, independent verification, partial completion, or resumable long-running execution.
---

# Multi-Agent Orchestrator

## Overview

Use this skill to coordinate logical multi-agent work inside a single AI tool session. The agents are roles in one session, not separate processes or separate permission boundaries.

Default to parallel planning, serial execution, and independent verification.

## When To Use

Use for:
- Long-running or resumable work that needs checkpoints.
- Batch work that can be split by time range, module, file set, or data shard.
- Multi-step work with dependencies, locks, partial completion, or cancellation risk.
- Work where one role should implement and another role should verify.
- Work where a read-only dashboard should periodically show agent and task status.
- Work where a workspace-level timed Loop should periodically observe state, rebuild queue snapshots, refresh the dashboard, and cautiously auto-advance explicit low-risk tasks.

Do not use for:
- Simple one-step tasks under about 10 minutes.
- Highly interactive work that needs continuous user decisions.
- Work with unclear authorization, allowed paths, or acceptance criteria.
- Cross-tool orchestration. This skill is only for logical agents inside one AI tool.

## Required First Decisions

Before executing, decide and record:

| Decision | Required answer |
|----------|-----------------|
| Suitability | Why this needs logical multi-agent coordination |
| Execution mode | `parallel-planning-serial-execution`, `sequential-roleplay`, or `interleaved-execution` |
| Authorization | Whether any write action is approved |
| Scope | Allowed paths, forbidden actions, deliverables |
| Verification | Risk level and verification strategy |
| Recovery | Checkpoint path and resume rule |
| Dashboard | Whether to generate a read-only dashboard snapshot and refresh every 3 minutes |
| Loop | Whether to enable workspace Loop, dry-run first, and which safe actions are allowed |

If these answers are missing, create a draft Task Spec instead of executing.

## Core Workflow

1. Create or check a Task Spec before any complex or write operation.
2. Split work into Worker Briefs with scope, dependencies, allowed inputs, allowed outputs, and acceptance criteria.
3. Build a queue using `priority-then-fifo` unless the user or task spec requires another policy.
4. Acquire logical locks before touching shared resources.
5. Activate Workers one at a time by default.
6. Record every state transition as an append-only event.
7. Treat `partially_completed` as a first-class state; preserve reusable outputs.
8. Run Verifier from the task spec and deliverables, not from the Worker's self-assessment.
9. Write a checkpoint after every Worker, verification result, failure, cancellation, or pause.
10. Generate dashboard state through the read-only Collector when requested; default refresh interval is 3 minutes.
11. If workspace Loop is enabled, run `scripts/loop_runner.py <workspace> --dry-run` before `--once`.
12. Report status with changed files, open risks, next owner, required verification, and suggested action.

For the full protocol, templates, dashboard state schema, Collector rules, state machine, lock rules, event schema, checkpoint schema, cancellation rules, Loop design, and examples, read `references/protocol.md` and `references/loop-v1-design.md`.

## Safety Rules

- `auto-approve` never means write authorization.
- `auto_fix` must default to false.
- Worker completion is not final completion; Verifier must review it.
- Priority cannot bypass authorization, locks, dependencies, or verification.
- Lock expiration cannot be overwritten automatically.
- Cancellation is not rollback. Any deletion, overwrite, or database rollback is a new write operation requiring authorization.
- Monitor may warn, suggest, and request decisions; it must not autonomously repair or mark work done.
- Dashboard is read-only. It may refresh views and snapshots, but must not mutate queue, events, locks, reports, checkpoints, or task status.
- Loop auto-advance requires explicit `loop_autorun`, low/minimal risk, satisfied dependencies, available locks, and precise `loop_safe_actions`.
- Loop may request lock release, but must not treat a release request as approval.

## Minimum Outputs

For coordinated work, produce or update:
- Task Spec.
- Worker Briefs.
- Queue or task status.
- Event log.
- Checkpoint.
- Verification Report.
- User-facing status summary.
- Optional dashboard state, static dashboard page, and Collector-generated `state.json` when dashboard mode is requested.
- Optional Loop state, Loop events, queue rebuild report, and simulation output when workspace Loop mode is requested.

If the user asks to implement the skill itself, deliver a skill folder with `SKILL.md`, `agents/openai.yaml`, and `references/protocol.md`.


