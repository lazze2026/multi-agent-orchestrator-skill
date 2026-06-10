# Checkpoint

## task_id

## current_status

## completed_tasks
| task_id | deliverables | verified | note |
|---------|--------------|----------|------|

## running_tasks
| task_id | owner | last_event_id | last_event_time | progress |
|---------|-------|---------------|-----------------|----------|

## partially_completed_tasks
| task_id | completed_count | total_count | reusable_outputs | next_step |
|---------|----------------:|------------:|------------------|-----------|

## blocked_tasks
- 

## key_decisions
- 

## changed_files
- 

## open_risks
- 

## required_verification
- 

## next_owner

## resume_steps
1. Read this checkpoint.
2. Verify completed_tasks deliverables exist.
3. Verify completed_tasks acceptance evidence still matches the task.
4. Verify running_tasks last event timestamp and decide whether they are stale.
5. Read queue/tasks.jsonl.
6. Read events/<task_id>.jsonl.
7. Reconstruct state from append-only events.
8. Continue from the first queued, blocked, or partially_completed task that passes idempotency checks.
