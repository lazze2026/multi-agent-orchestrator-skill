# Worker Brief

## agent_id
Worker-1

## task_id
task_20260608_001_sub_001

## scope
Export synthetic records 1-5000 until the simulated API hourly limit of 2000 records is reached.

## allowed_inputs
- tasks/task_20260608_001.md
- synthetic record generator

## allowed_outputs
- output/batch_001.json
- reports/worker-1-result.md

## dependencies
- depends_on: []
- requires_artifacts: []
- wait_for_status: []

## forbidden_actions
- Do not call real APIs.
- Do not write outside the test workspace.
- Do not mark the parent task done.

## execution_steps
1. Generate records 1-2000.
2. Write output/batch_001.json.
3. Stop at simulated API limit.
4. Report partially_completed and next range 2001-5000.

## expected_result
- output/batch_001.json contains 2000 records.
- Worker status is partially_completed.
- Reusable output is preserved for resume.

## report_format
- status:
- progress: `completed_count/total_count`, optionally with percentage
- completed_count:
- total_count:
- completed_items:
- failed_items:
- partial_outputs:
- changed_files:
- open_risks:
- next_event:
