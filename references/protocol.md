# Multi-Agent Orchestrator Skill Design

**版本**: v1.2.0  
**用途**: 单个 AI 工具内的逻辑多 Agent 协同调度协议  
**适用工具**: Codex、ClaudeCode、OpenClaw 等具备文件读写、命令执行、长上下文推理能力的单一 AI 工具  
**状态**: Design Revised  
**Created**: 2026-06-08  
**Last Updated**: 2026-06-08

---

## 1. 核心定义

本 Skill 中的 Agent 指同一 AI 工具实例内的**逻辑角色**，不是独立进程、独立上下文窗口、独立权限主体，也不代表跨工具协作。

换句话说，Coordinator、Worker、Verifier、Monitor、Dashboard 都运行在同一个 AI 工具会话中。它们通过任务卡、状态机、事件日志、检查点和明确的上下文隔离规则协作，避免一段长对话里角色混杂、判断污染、状态丢失。

跨 AI 工具协作，例如 Codex + ClaudeCode + 远程服务器 Agent，将在后续单独设计，不纳入本 Skill 的 v1 范围。

---

## 2. 设计目标

1. 将复杂任务拆成可追踪、可暂停、可恢复的子任务。
2. 在单工具内模拟多个专业角色，但保持一个统一调度入口。
3. 用任务队列和事件日志替代口头进度记忆。
4. 用上下文隔离降低 Worker 之间的结论污染。
5. 用 Verifier 角色对交付物做独立复核。
6. 用 Checkpoint 支持长任务、上下文压缩和断点续跑。
7. 防止自动修复、自动批准、过度并发绕过用户授权。

---

## 3. 典型场景速览

### 3.1 批量数据回填

```text
目标: 导出 2024-2026 年钉钉群聊记录
拆分: 按年份或季度生成 Worker Brief
模式: 并行规划，串行执行
关键控制: API 限流、输出目录锁、部分完成记录、抽样或全量验证
```

### 3.2 多模块代码整理

```text
目标: 同一代码库内整理多个独立模块
拆分: 每个模块一个 Worker Brief
模式: 并行规划，串行执行
关键控制: 写锁、依赖关系、Verifier 独立复核、取消级联
```

### 3.3 长任务断点续跑

```text
目标: 任务跨多轮对话继续执行
拆分: 每个阶段有 Task Spec、事件日志、checkpoint
模式: checkpoint -> 幂等验证 -> resume
关键控制: 已完成交付物复查、last event 检查、避免重复执行
```

---

## 4. 适用与不适用场景

### 4.1 适合场景

1. **大型批量任务**
   - 数据迁移、批量转换、历史数据回填。
   - 多文件、多模块、多步骤处理。
   - 可以按时间、目录、模块、数据分片拆分。

2. **需要质量保证的任务**
   - 需要独立校验交付物。
   - 需要持续记录进度、失败项、风险项。
   - 需要明确验收标准。

3. **长时间运行任务**
   - 预计超过 1 小时。
   - 可能被中断、压缩上下文或分多轮继续。
   - 需要阶段性报告和恢复点。

4. **并行规划、串行执行任务**
   - 多个子任务可以独立分析。
   - 写操作存在资源冲突风险，需要逐个落地。

### 4.2 不适合场景

1. 简单单步任务，预计 10 分钟内完成。
2. 高度交互式任务，需要用户连续判断。
3. 需要实时流式反馈的任务。
4. 无法明确拆分输入、输出、验收标准的任务。
5. 写入范围不清楚或授权边界不清楚的任务。

---

## 5. 逻辑角色模型

### 5.1 Coordinator

主协调角色，始终由当前 AI 工具主线程承担。

职责：
- 理解用户目标。
- 创建或检查 Task Spec。
- 拆解任务、识别依赖、分配 Worker。
- 维护任务队列、事件日志和 checkpoint。
- 检查授权、资源锁和禁止项。
- 汇总 Worker 与 Verifier 的结果。
- 决定下一步是继续、暂停、重试、升级给用户。

禁止：
- 在没有授权的情况下启动写操作。
- 把 Worker 的自我结论直接当成最终结论。
- 跳过 Verifier 直接宣称完成。

### 5.2 Worker

执行角色。Worker 可以有多个，但在单 AI 工具内默认是轮流激活，不是假设真实并发。

职责：
- 按任务卡执行指定子任务。
- 只读取本任务允许的输入。
- 只产出本任务要求的交付物。
- 报告完成、失败、阻塞和风险。

禁止：
- 修改不在 allowed paths 内的文件。
- 自行扩大任务范围。
- 把其他 Worker 的任务接过来做。
- 在未授权时修复额外发现的问题。

### 5.3 Verifier

独立校验角色。Verifier 不继承 Worker 的判断，只基于交付物、验收标准、日志和可重复命令做验证。

职责：
- 检查交付物是否存在。
- 检查输出是否符合任务卡。
- 执行或建议验证命令。
- 识别缺失测试、未覆盖风险和验收差距。
- 产出 `verification.passed`、`verification.failed` 或 `needs.human.decision`。

禁止：
- 为了让验证通过而直接修改交付物。
- 在没有新授权时自动修复代码、数据或配置。

### 5.4 Monitor

状态汇总角色。Monitor 在单工具内表现为定期或按需生成状态报告，不代表后台真实进程。

职责：
- 汇总任务队列状态。
- 识别超时、阻塞、资源冲突和失败率异常。
- 识别异常模式，例如失败率突增、执行耗时异常、重复锁冲突。
- 预测资源瓶颈，例如队列积压、同一资源长期等待、checkpoint 过旧。
- 建议调度优化，例如暂停低优先级任务、拆小超时任务、降低活跃 Worker 数。
- 在满足授权边界时建议触发降级策略；不满足授权时生成 `needs.human.decision`。
- 输出短分诊。
- 提醒 Coordinator 生成 checkpoint。

禁止：
- 自主修复问题。
- 自主改变任务状态为 done。
- 自主抢占资源锁。
- 自主切换到会扩大写入范围的降级方案。

---
### 5.5 Dashboard

只读看板角色。Dashboard 负责把任务队列、事件日志、checkpoint、验证报告和 Agent 状态整理成可刷新视图，不代表后台执行进程。

职责：
- 读取 `queue/tasks.jsonl`、`events/*.jsonl`、`checkpoints/latest.md`、`reports/*.md`。
- 生成 `dashboard/state.json` 作为看板快照。
- 生成或更新 `dashboard/index.html` 静态页面。
- 默认每 3 分钟刷新一次状态快照或页面读取。
- 展示 Agent 状态、任务执行情况、最近事件、阻塞风险、部分完成和恢复点。

禁止：
- 修改任务队列、事件日志、锁、报告、checkpoint 或任务状态。
- 自动重试、取消、调度、修复或抢锁。
- 把 stale 数据伪装成实时状态；必须显示 `generated_at` 和 `refresh_interval_seconds`。
---

## 6. 默认执行模式

### 6.1 推荐默认模式

默认采用：

```text
并行规划，串行执行，独立验证
```

含义：
- Coordinator 可以一次性拆出多个 Worker 任务。
- Worker 默认逐个执行，避免同一工具内上下文混乱。
- 只有资源完全隔离时，才允许交替推进多个 Worker。
- 每个 Worker 完成后都写事件，再由 Verifier 验证。

### 6.2 支持模式

| 模式 | 说明 | 适用场景 | 风险 |
|------|------|----------|------|
| sequential-roleplay | Worker 逐个执行 | 默认模式、代码修改、风险较高任务 | 最慢但最稳 |
| interleaved-execution | 多个 Worker 交替推进 | 长任务、I/O 等待、批量导出 | 需要严格任务卡和 checkpoint |
| parallel-planning-serial-execution | 同时拆解多个方案，串行落地 | 多模块分析、重构计划、验证计划 | 需要防止重复工作 |

### 6.3 不支持的假设

单工具模式下不要假设：
- 多个 Agent 真正在后台同时运行。
- Worker 有独立上下文窗口。
- Monitor 会在工具关闭后继续执行。
- `auto-approve` 等同于用户授权写操作。

---

## 7. 快速开始

### 7.1 初始化

```bash
/multi-agent-orchestrator init \
  --project-name "我的项目" \
  --workspace "./workspace"
```

生成内容：
- `orchestrator.json`
- `tasks/`
- `queue/tasks.jsonl`
- `events/`
- `locks/`
- `reports/`
- `checkpoints/`

### 7.2 启动协调器

```bash
/multi-agent-orchestrator start
```

启动流程：
1. 收集需求。
2. 判断是否适合多 Agent。
3. 创建或检查 Task Spec。
4. 拆解 Worker 任务。
5. 检查授权、资源锁、允许路径、禁止项。
6. 选择执行模式。
7. 请求用户确认调度方案。
8. 执行 Worker。
9. Verifier 验证。
10. 输出最终报告和 checkpoint。

### 7.3 状态查询

```bash
/multi-agent-orchestrator status \
  --detail summary \
  --format markdown
```

### 7.4 暂停与恢复

```bash
/multi-agent-orchestrator checkpoint
/multi-agent-orchestrator resume --from checkpoints/latest.md
```

### 7.5 停止

```bash
/multi-agent-orchestrator stop \
  --archive-results true
```

停止时必须：
- 写入最终事件。
- 释放本次持有的逻辑锁。
- 生成 checkpoint。
- 标记未完成任务为 `blocked` 或 `queued`，不得直接丢弃。

---

## 8. Task Spec 最小字段

任何需要写代码、写数据、改配置、批量生成文件的任务，必须先有 Task Spec。

```markdown
# 任务标题

## task_id
task_YYYYMMDD_001

## objective
要完成什么，以及为什么要做。

## owner
Coordinator / Worker-1 / Worker-2 / Verifier / Monitor

## risk
high / medium / low / minimal

## priority
critical / high / normal / low

## priority_rules
- critical 任务可以优先进入队列，但不能绕过授权、资源锁或验证。
- 同优先级按 FIFO。
- blocked 任务默认降为 low，除非用户明确提升优先级。
- 运行中的写操作不可被强制抢占；只能在安全检查点后暂停。

## authorization
- approved: yes / no
- approver:
- approved_at:
- approval_source:
- approval_snapshot:

## allowed_paths
- path/to/file_or_dir

## forbidden_actions
- 不得删除数据
- 不得修改生产配置
- 不得扩大范围

## prerequisites
- 需要的文件、服务、凭据、锁、验证资产

## dependencies
- depends_on: []
- requires_artifacts: []
- wait_for_status: []

## steps
1. ...

## deliverables
| path | description |
|------|-------------|

## acceptance_criteria
- ...

## completion_event
worker.completed / worker.partially_completed / worker.blocked / verification.passed / needs.human.decision
```

---

## 9. Worker 任务卡

每个 Worker 必须拿到独立任务卡。任务卡越短越好，但必须完整。

```markdown
# Worker Brief

## agent_id
Worker-1

## task_id
task_YYYYMMDD_001_sub_001

## scope
只处理 2024-01 至 2024-04 的数据导出。

## allowed_inputs
- source: ...
- config: ...

## allowed_outputs
- reports/worker-1-result.md
- output/2024-Q1/

## dependencies
- depends_on: [task_YYYYMMDD_001_sub_000]
- requires_artifacts: [output/2024-Q0/summary.json]
- wait_for_status: [done]

## forbidden_actions
- 不处理 2024-05 之后的数据
- 不修改全局配置
- 不删除源数据

## execution_steps
1. ...

## expected_result
- ...

## report_format
- status:
- progress: `completed_count/total_count`，也可以附加百分比，例如 `2000/5000 (40%)`
- completed_count:
- total_count:
- completed_items:
- failed_items:
- partial_outputs:
- changed_files:
- open_risks:
- next_event:
```

Worker 完成后只报告事实、产物和风险，不给出全局完成结论。

当 Worker 只完成部分范围时，必须报告 `worker.partially_completed`，并列出已完成数量、失败数量、可复用交付物和恢复入口。部分完成不是失败，也不是最终完成。

---

## 10. 状态机

任务状态只允许使用以下值：

```text
draft -> planned -> approved -> queued -> running -> verifying -> done
draft -> blocked
planned -> blocked
queued -> cancelled
queued -> running
running -> blocked
running -> failed
running -> partially_completed
partially_completed -> verifying
partially_completed -> blocked
partially_completed -> needs_human_decision
failed -> queued
verifying -> failed
verifying -> done
verifying -> needs_human_decision
```

规则：
- 禁止跳状态。
- 写操作必须先到 `approved`。
- Worker 完成后进入 `verifying`，不能直接进入 `done`。
- Worker 部分完成时进入 `partially_completed`，并保留已完成交付物清单。
- `partially_completed` 可以进入 `verifying`，用于验证已完成部分是否可采信。
- Verifier 失败后进入 `failed` 或 `needs_human_decision`。
- 用户要求停止时进入 `cancelled` 或 `blocked`，不能伪装成 `done`。

---

## 11. 事件日志

事件日志必须追加写入，优先使用 JSONL，避免覆盖历史。

推荐路径：

```text
events/<task_id>.jsonl
```

事件格式：

```json
{
  "event_id": "evt_20260608_0001",
  "time": "2026-06-08 11:00:00",
  "task_id": "task_20260608_001",
  "agent": "Worker-1",
  "event": "worker.started",
  "from_status": "queued",
  "to_status": "running",
  "caused_by": "dispatch",
  "trigger_event_id": "evt_20260608_0000",
  "blocked_by": null,
  "conflicting_resource": null,
  "summary": "开始处理 2024-Q1 数据导出",
  "next": "Worker-1"
}
```

标准事件：

```text
task.created
task.planned
task.approved
task.queued
worker.started
worker.completed
worker.partially_completed
worker.blocked
worker.failed
verification.started
verification.passed
verification.failed
checkpoint.created
needs.human.decision
task.cancelled
task.done
```

因果链规则：
- 每条事件必须有 `event_id`。
- 状态迁移事件必须记录 `from_status` 和 `to_status`。
- 被其他事件触发时，必须记录 `trigger_event_id`。
- 阻塞事件必须尽量记录 `caused_by`、`blocked_by` 和 `conflicting_resource`。
- 事件日志只追加，不覆盖；错误事件也不得删除。

---

## 12. 配置文件

### 12.1 orchestrator.json

```json
{
  "version": "1.2.0",
  "min_compatible_version": "1.0.0",
  "schema_hash": "sha256:<computed-from-schema>",
  "mode": "single-tool-logical-agents",
  "project_name": "钉钉历史回填",
  "workspace": "./workspace",
  "execution": {
    "default_mode": "parallel-planning-serial-execution",
    "allow_interleaved_execution": false,
    "max_active_workers": 1,
    "checkpoint_interval_minutes": 30,
    "priority_policy": "priority-then-fifo"
  },
  "authorization": {
    "require_task_spec_for_write": true,
    "auto_dispatch": false,
    "auto_approve_write": false,
    "auto_fix": false
  },
  "agents": {
    "coordinator": {
      "enabled": true
    },
    "workers": {
      "count": 3,
      "max_retries_readonly": 3,
      "max_retries_write": 0
    },
    "verifier": {
      "enabled": true,
      "verify_all": false,
      "strategy": "risk-based",
      "sampling": {
        "high": 1.0,
        "medium": 0.5,
        "low": 0.2,
        "minimal": 0.05
      }
    },
    "monitor": {
      "enabled": true,
      "report_interval_minutes": 30,
      "active_warning": true
    },
    "dashboard": {
      "enabled": true,
      "type": "static-html",
      "refresh_interval_seconds": 180,
      "state_path": "dashboard/state.json",
      "html_path": "dashboard/index.html",
      "read_only": true
    }
  },
  "state_store": {
    "tasks": "queue/tasks.jsonl",
    "events_dir": "events",
    "reports_dir": "reports",
    "checkpoints_dir": "checkpoints",
    "locks_dir": "locks"
  },
  "safety": {
    "allowed_paths": [],
    "forbidden_actions": [
      "delete-source-data-without-approval",
      "modify-production-config-without-approval",
      "auto-fix-write-failures-without-approval"
    ]
  }
}
```

`priority_policy` 定义任务队列排序策略：

| policy | 说明 | 状态 |
|--------|------|------|
| priority-then-fifo | 先按 `critical > high > normal > low` 排序，同优先级按提交顺序执行 | 默认 |
| strict-fifo | 忽略优先级，严格按提交顺序执行 | 支持 |
| deadline-aware | 综合优先级、截止时间和阻塞成本排序 | 未来扩展 |

无论使用哪种策略，都不能绕过授权、资源锁、依赖关系和 Verifier 复核。

### 12.2 参数命名建议

避免使用容易误解的参数：

| 不推荐 | 推荐 | 原因 |
|--------|------|------|
| auto-approve | auto-dispatch / auto-plan | approve 容易被误解为授权写入 |
| auto-fix | suggest-fix | 单工具内也不能默认自动修复 |
| parallel true | execution-mode | 单工具内的 parallel 多数只是调度策略 |

---

## 13. 资源锁

单工具内仍然需要逻辑锁，防止多个 Worker 修改同一资源。锁是调度协议，不是操作系统级锁。

必须加锁的资源：
- 同一代码文件。
- 同一配置文件。
- 同一数据库表或导入批次。
- 同一输出目录。
- 同一验证报告路径。

锁文件建议：

```text
locks/<resource_hash>.lock
```

锁内容：

```json
{
  "resource": "backend/app/services/sync.py",
  "lock_type": "read | write | exclusive",
  "owner": "Worker-1",
  "holders": ["Worker-1"],
  "max_readers": 5,
  "task_id": "task_20260608_001",
  "created_at": "2026-06-08 11:00:00",
  "expires_at": "2026-06-08 13:00:00",
  "reason": "修改同步逻辑"
}
```

锁规则：
- Coordinator 创建和释放锁。
- Worker 不能自行抢锁。
- 锁过期后不能自动覆盖，必须由 Coordinator 复核。
- 检测到锁冲突时进入 `blocked`。
- `read` 锁允许多个 holder，但不能和 `write` 或 `exclusive` 锁并存。
- `write` 锁用于单资源写入，同一资源只能有一个 holder。
- `exclusive` 锁用于数据库迁移、删除、批量覆盖等高风险操作，必须独占相关资源集合。
- 任务优先级不能绕过锁；critical 任务只能优先排队，不能强制中断运行中的写操作。

---

## 14. Checkpoint

Checkpoint 用于长任务恢复、上下文压缩后继续、人工交接。

推荐路径：

```text
checkpoints/<task_id>_<YYYYMMDD_HHMM>.md
checkpoints/latest.md
```

模板：

```markdown
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
- ...

## key_decisions
- ...

## changed_files
- ...

## open_risks
- ...

## required_verification
- ...

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
```

触发条件：
- 每完成一个 Worker。
- 每次 Verifier 完成。
- 每 30 分钟。
- 用户要求暂停。
- 即将压缩上下文或结束会话。
- 出现阻塞、失败、需要人工决策。

---

## 15. 验证规则

Verifier 必须回答四个问题：

1. 交付物是否存在？
2. 交付物是否只覆盖任务允许范围？
3. 验收标准是否满足？
4. 是否有未验证风险或需要人工判断？

风险等级决定默认验证强度：

| risk | 默认验证策略 |
|------|--------------|
| high | 100% 验证，或必须说明无法全量验证的原因 |
| medium | 至少 50% 采样，并覆盖关键边界 |
| low | 至少 20% 采样 |
| minimal | 至少 5% 采样，且允许只读检查 |

如果任务包含写数据库、删除、覆盖、生产配置或批量通知，即使 Task Spec 标为低风险，Verifier 也必须升级验证策略。

验证报告模板：

```markdown
# Verification Report

## task_id

## verifier

## result
passed / failed / needs_human_decision

## checked_deliverables
| path | status | note |
|------|--------|------|

## commands_run
| command | result | note |
|---------|--------|------|

## acceptance_check
| criterion | status | evidence |
|-----------|--------|----------|

## open_risks
- ...

## next_event
verification.passed / verification.failed / needs.human.decision
```

单工具内可以由同一个 AI 会话切换到 Verifier 角色，但必须先重新读取任务卡和交付物，不能只依赖 Worker 的总结。

---

## 16. 异常处理

### 16.1 异常分类

| 异常类型 | 可自动处理 | 处理方式 |
|----------|------------|----------|
| 只读命令超时 | 是 | 指数退避重试 |
| API 限流 | 是 | 降速、重试、减少活跃 Worker |
| 输出格式错误 | 有条件 | 重新生成报告，不改业务数据 |
| Worker 任务失败 | 有条件 | 只读任务可重试，写任务暂停 |
| 验证失败 | 否 | 进入 `verification.failed` |
| 数据损坏 | 否 | 进入 `needs.human.decision` |
| 授权缺失 | 否 | 进入 `blocked` |
| 资源锁冲突 | 否 | 进入 `blocked` |

### 16.2 重试原则

```text
只读任务: 最多自动重试 3 次
写操作任务: 默认不自动重试
验证失败: 不自动修复
授权缺失: 不自动补授权
资源冲突: 不自动抢锁
```

### 16.3 失败后输出

失败时必须输出：
- 失败任务。
- 失败阶段。
- 已完成产物。
- 可能受影响范围。
- 是否需要人工决策。
- 建议下一步。

### 16.4 降级策略

降级策略只能改变调度方式或提出替代方案，不能绕过授权、扩大写入范围或自动修复业务逻辑。

| 异常类型 | 主策略 | 降级策略 | 授权要求 |
|----------|--------|----------|----------|
| API 限流 | 降速重试 | 切换批量导出 API 或缩小批次 | 若调用范围不变，可继续；范围变化需确认 |
| 数据源不可用 | 等待恢复 | 切换备份数据源 | 必须确认数据源可信和读取范围 |
| Worker 超时 | 延长超时 | 拆分为更小子任务 | 可由 Coordinator 调整任务卡 |
| 锁冲突频繁 | 等待释放 | 调整队列顺序或降低活跃 Worker | 不得抢锁 |
| 验证失败率高 | 暂停后分析 | 提高采样率或全量验证 | 不得自动修复 |

### 16.5 取消级联规则

取消任务必须写入 `task.cancelled` 事件，并说明取消来源。取消不是失败，也不是完成。

| 被取消任务状态 | Worker 处理 | 交付物处理 | 依赖任务处理 |
|---------------|-------------|-------------|--------------|
| draft / planned | 直接标记 `cancelled` | 无交付物 | 依赖任务标记 `cancelled` |
| queued | 直接标记 `cancelled` | 无交付物 | 依赖任务标记 `cancelled` |
| running | 等待当前安全步骤完成后停止 | 保留已产出，标记未验证 | 依赖任务标记 `blocked` |
| partially_completed | 保留已完成部分 | 进入幂等验证清单 | 依赖任务标记 `blocked` |
| verifying | 停止验证或完成当前只读检查 | 保留交付物和验证证据 | 依赖任务标记 `needs_human_decision` |
| done | 不回滚，除非 Task Spec 明确要求 | 保留交付物 | 依赖任务按实际状态继续或重评 |

回滚不是取消的默认动作。任何删除、覆盖、数据库回滚都必须作为新的写操作重新授权。

---

## 17. 用户可见状态报告

状态报告优先短分诊，再展开细节。

```markdown
# Orchestrator Status

## Summary
- changed files:
- open risks:
- next owner:
- required verification:
- suggested action:

## Task Progress
| status | count |
|--------|------:|

## Active Items
| task_id | owner | status | priority | next |
|---------|-------|--------|----------|------|

## Recent Events
- ...

## Partial Progress
| task_id | completed | total | reusable_outputs | risk |
|---------|----------:|------:|------------------|------|
```

---


## 18. Dashboard 看板

Dashboard 是只读状态视图，用于定期查看每个逻辑 Agent 的工作状态和任务执行情况。默认使用静态 HTML：`dashboard/index.html` 读取 `dashboard/state.json`，页面或快照刷新间隔为 180 秒。

### 18.1 state.json 最小结构

```json
{
  "generated_at": "2026-06-10T10:00:00+08:00",
  "refresh_interval_seconds": 180,
  "read_only": true,
  "summary": {
    "total_tasks": 4,
    "running": 1,
    "partially_completed": 1,
    "blocked": 1,
    "done": 1,
    "open_risks": 2
  },
  "agents": [
    {
      "agent_id": "Worker-1",
      "role": "Worker",
      "status": "partially_completed",
      "task_id": "task_20260610_001_sub_001",
      "progress": "2000/5000 (40%)",
      "last_event_id": "evt_20260610_0005",
      "last_seen": "2026-06-10T09:57:00+08:00",
      "next": "Verifier"
    }
  ],
  "tasks": [
    {
      "task_id": "task_20260610_001_sub_001",
      "owner": "Worker-1",
      "priority": "normal",
      "status": "partially_completed",
      "progress": "2000/5000 (40%)",
      "next": "Verifier",
      "open_risks": ["API rate limit"]
    }
  ],
  "recent_events": [],
  "risks": [],
  "checkpoints": []
}
```

### 18.2 看板规则

- 看板只读，不得写队列、事件、锁、checkpoint、报告或任务状态。
- 页面必须显示 `generated_at`、刷新间隔和 stale 状态。
- 刷新间隔默认 180 秒，低于 30 秒需要用户明确要求。
- 看板状态来自快照文件，不得把快照等同真实后台进程。
- 如果输入文件缺失，看板显示 `unknown` 或 `stale`，不能自动补写任务状态。
---


### 18.3 state.json 生成方式

Dashboard 页面不得直接扫描运行目录。必须由只读 Collector 先汇总为单一快照文件，再由页面读取。

推荐命令：

```bash
python scripts/generate_dashboard_state.py <orchestrator-workspace> --output dashboard/state.json --refresh-interval 180
```

等价协议命令：

```bash
/multi-agent-orchestrator dashboard generate
```

Collector 输入来源：

| 看板字段 | 推荐来源 |
|----------|----------|
| `task_groups` | `queue/tasks.jsonl` 或 `queue/tasks.json` |
| `agents` | `agents/*.json` 或 `agents.json` |
| `blockers` | `blockers/*.json`、锁冲突事件、`needs_human_decision` 状态 |
| `dispatch_actions` | Monitor 输出、`dispatch/*.json`、风险规则 |
| `recent_events` | `events/*.jsonl` 最近 10 条 |
| `checkpoints` | `checkpoints/*.json` 或 checkpoint metadata |
| `flow_timeline` | 任务阶段映射，必要时由 Collector 推断 |

Collector 只读读取输入目录，只允许写 `dashboard/state.json`。不得修改队列、事件、锁、报告、checkpoint 或任务状态。

### 18.4 看板交互要求

静态页面至少提供：

- 手动刷新按钮。
- 自动刷新，默认 `refresh_interval_seconds = 180`。
- 刷新失败重试，建议 5 秒起步、最多 30 秒退避。
- 数据新鲜度提示，展示 `freshness.age`、`generated_at` 和 stale/current 状态。
- 最近 10 个事件滚动区域。
- Checkpoint 摘要区域，展示是否可恢复和恢复证据。
- 横向流程泳道或甘特风格视图，展示规划、执行、验证、监控、调度的流转关系。

页面只能读取 `state.json`，不能发起调度、取消、重试、抢锁或自动修复。

## 19. 实际应用示例


## 19.1 钉钉历史数据回填

需求：导出 2024-2026 年的钉钉群聊记录。

拆解：

```text
主任务: 钉钉历史回填
子任务:
- Worker-1: 2026 年回填，5 个月
- Worker-2: 2025 年回填，12 个月
- Worker-3: 2024 年回填，12 个月

执行模式:
parallel-planning-serial-execution

原因:
各年份可独立规划，但实际 API 调用和输出目录需要限流与锁控制。
```

状态报告示例：

```markdown
# Orchestrator Status

## Summary
- changed files: output/2026/, reports/worker-1-result.md
- open risks: 2024 年数据量较大，API 限流风险仍在
- next owner: Worker-2
- required verification: 抽样校验导出文件数量和时间范围
- suggested action: 继续执行 Worker-2，保持单 Worker 活跃

## Progress
- completed: 1/3 workers
- partially_completed: 0
- running: 0
- queued: 2
- blocked: 0
```


## 19.2 批量图片转换

需求：将 10000 张 PNG 图片转换为 WebP。

拆解：

```text
Worker-1: 第 1-2500 张
Worker-2: 第 2501-5000 张
Worker-3: 第 5001-7500 张
Worker-4: 第 7501-10000 张
```

允许交替执行的条件：
- 每个 Worker 输出目录不同。
- 源文件只读。
- 转换命令可重复。
- Verifier 能按分片抽查输出数量、格式和失败清单。


## 19.3 API 限流导致部分完成

需求：导出 5000 条记录，API 每小时限额 2000 条。

Worker 报告：

```markdown
## report_format
- status: partially_completed
- progress: 2000/5000 (40%)
- completed_count: 2000
- total_count: 5000
- reusable_outputs:
  - output/batch_001.json
- next_step: 等待限流窗口后从第 2001 条继续
```

Checkpoint 恢复：

```text
1. 验证 output/batch_001.json 存在。
2. 验证 batch_001.json 包含 2000 条记录。
3. 验证最后一条记录 ID 为 2000。
4. 生成新 Worker Brief，范围为 2001-5000。
5. 继承原授权、允许路径和验证策略。
```

---

## 20. 安全边界

### 20.1 永远不能自动做的事

- 未授权写代码。
- 未授权写数据库。
- 未授权修改配置。
- 未授权删除源数据。
- 验证失败后自动修复业务逻辑。
- 绕过 Task Spec 直接执行复杂任务。
- 把选项预览当成用户批准。
- 把 Worker 的完成报告当成最终验收。

### 20.2 可以自动做的事

- 拆解任务草案。
- 生成 Worker Brief。
- 读取允许范围内文件。
- 运行只读检查。
- 生成状态报告。
- 生成只读看板快照和静态页面。
- 生成 checkpoint。
- 对只读失败做有限重试。
- 给出修复建议。
- 记录部分完成进度。
- 建议降级策略。
- 生成取消级联计划。

---

## 21. 设计与后续演进

本版本只解决同一个 AI 工具内的逻辑多 Agent 协作。它的核心不是制造“多个真实 Agent”，而是用协议让单工具内的多角色协作可追踪、可恢复、可验证。

后续跨工具版本可以复用以下协议层：
- Task Spec。
- Worker Brief。
- 状态机。
- 事件日志。
- 资源锁。
- Checkpoint。
- Verification Report。
- 取消级联规则。
- 风险等级验证策略。

跨工具版本需要另外补充：
- 工具间消息通道。
- 文件同步策略。
- 权限隔离。
- 远程执行确认。
- 多端冲突处理。
- 跨工具身份与责任追踪。

同工具版本后续可以继续增强：
- 更严格的 schema migration 工具。
- 自动生成 `schema_hash`。
- Monitor 异常模式统计。
- 长任务的优先级调度模拟器。

### 21.1 schema_hash 计算规则

`schema_hash` 用于检测不兼容的配置结构变更。

计算规则：
- 只包含 `orchestrator.json` 的必需字段。
- 必需字段按字典序排序后序列化。
- 忽略注释、空白字符和可选字段。
- 对规范化后的 schema 字符串计算 SHA256。
- 当必需字段增删、字段类型变化或枚举值不兼容时，必须更新 `schema_hash`。

---

## 22. 最小可用标准

一个实现只有同时满足以下条件，才算真正支持本 Skill：

1. 能生成 Task Spec。
2. 能生成独立 Worker Brief。
3. 能维护任务状态机。
4. 能追加事件日志。
5. 能生成 checkpoint。
6. 能执行 Verifier 复核。
7. 能在授权缺失、资源冲突、验证失败时暂停。
8. 能输出短分诊状态报告。
9. 不把单工具逻辑 Agent 误描述成真实并发进程。
10. 能记录 `partially_completed` 并恢复未完成部分。
11. 能在 resume 时执行幂等性验证。
12. 能处理任务取消和依赖级联。
13. 能生成只读 Dashboard state.json 和静态 index.html，并默认 180 秒刷新。

