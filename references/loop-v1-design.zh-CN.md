# Multi-Agent Orchestrator Loop v1.0 设计稿

**状态**：待评审草稿  
**范围**：运行在 Codex automation / heartbeat 中的工作区级定时 Loop  
**适用边界**：仅适用于单个 AI 工具内的逻辑多 Agent 编排  
**默认周期**：每 5 分钟一次  
**自动化级别**：低风险自动推进，带严格护栏

---

## 1. 目标

把 `multi-agent-orchestrator` 从一次性协同 Skill，升级为一个**工作区级定时 Loop 系统**，使其能够：

- 按固定周期唤醒
- 从工作区读取编排状态
- 识别 stale、blocked、partially completed、ready-to-advance 等任务
- 更新 dashboard 快照和 loop checkpoint
- 自动生成调度动作
- 只对明确允许且低风险的任务做自动推进

Loop v1 **不是**长期常驻的后台守护进程。它是挂在工作区上的周期性 automation run，由 Codex heartbeat / automation 调度执行。

---

## 2. 非目标

Loop v1 **不**解决以下问题：

- 自动修改业务交付物
- 绕过 Task Spec 授权机制
- 自动修复验证失败结果
- 抢占锁
- 跨多个 AI 工具协同
- 取代事件日志成为唯一真实来源

Loop v1 的设计边界是：**观察、推导、checkpoint、谨慎推进低风险任务**。

---

## 3. 运行模型

### 3.1 触发模型

Loop 通过 Codex heartbeat / automation 以每 5 分钟一次的节奏运行。

每次唤醒只执行一个有边界的 cycle：

1. 加载工作区状态
2. 检查 guardrails
3. 追加 loop 事件
4. 推导新的调度动作
5. 自动推进符合条件的低风险任务
6. 根据事件重建队列快照
7. 写入 dashboard 快照
8. 写入 loop checkpoint
9. 计算下一次运行信息

### 3.2 单轮执行规则

每次 automation 唤醒只允许执行**一轮 cycle**。  
禁止在单次运行里自我无限循环。

原因：

- 保持每轮执行可审计
- 避免失控重试
- 让 pause / resume 行为可预测
- 控制资源消耗

---

## 4. 核心原则

### 4.1 事件优先架构

Loop 不能把 `queue/tasks.jsonl` 当成唯一真实来源。

正确关系应当是：

- **events 是权威来源**
- queue 是派生出的运行视图
- dashboard 是派生出的只读视图
- loop state 是运行时元数据

### 4.2 双重门禁自动推进

任务只有在同时满足以下两个条件时，才允许被自动推进：

1. 当前状态属于 auto-advance status allowlist
2. Task Spec 明确声明允许 Loop 执行

推荐的 Task Spec 字段：

```yaml
loop_autorun: true
risk: low
loop_safe_actions:
  - read_only_checks
  - status_update_to_verifying
  - report_generation
```

### 4.3 仅限低风险

Loop v1 仅允许自动推进满足以下条件的任务：

- `risk: low` 或 `minimal`
- 没有待解决的授权问题
- 没有未完成依赖
- 没有 lock conflict
- 不涉及业务交付物写入动作
- 待执行动作都已显式声明在 `loop_safe_actions` 中

### 4.4 读多写少

Loop 的大部分行为应当保持“读多写少”：

- 读取状态
- 分类状态
- 写运行元数据
- 追加事件

真正的状态变更应尽量经由以下路径发生：

- loop events
- queue rebuild
- loop checkpoints

---

## 5. 工作区目录结构

推荐目录结构如下：

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

## 6. 新增文件

### 6.1 `loop/loop_config.json`

用于定义 Loop 的运行策略。

示例：

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

记录最近一次 Loop cycle 的运行状态。

示例：

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

用于记录 Loop runtime 决策过程的 append-only 事件流。

示例：

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

### 7.1 标准执行流程

每次 heartbeat 唤醒应按以下顺序执行：

1. **加载配置**
   - 读取 `orchestrator.json`
   - 读取 `loop/loop_config.json`

2. **加载状态**
   - 读取任务队列
   - 读取任务事件
   - 读取 checkpoints
   - 读取 locks
   - 读取 reports

3. **评估健康状况**
   - stale task detection
   - blocked task detection
   - dependency readiness
   - lock conflict 检查
   - repeated failure 检查

4. **追加观察事件**
   - `loop.cycle.started`
   - `loop.state.observed`
   - `loop.blocker.detected`
   - `loop.stale.detected`
   - `loop.lock_conflict.detected`

5. **生成派生动作**
   - dispatch suggestions
   - verifier suggestions
   - resume candidates
   - escalation candidates

6. **自动推进可推进任务**
   - 执行双重门禁检查
   - 校验 `loop_safe_actions`
   - 追加任务状态迁移事件
   - 不把“直接改队列”作为主操作手段

7. **重建队列**
   - 根据任务事件推导当前状态
   - 优先从上一轮快照做增量重建
   - 写 `queue/tasks.jsonl`
   - 写 `queue/tasks.snapshot.json`
   - 写 rebuild report

8. **刷新 dashboard**
   - 生成 `dashboard/state.json`

9. **写入 loop checkpoint**
   - 写本轮 loop summary
   - 记录下一轮恢复/续跑建议

10. **更新 loop state**
    - 更新 `loop/loop_state.json`
    - 追加 `loop.cycle.completed`

### 7.2 Stale 检测定义

`stale` 表示任务在配置窗口内没有任何有效进展信号。

v1 默认判定标准为 `no_event_or_heartbeat`：

- 最近 `stale_detection.after_minutes` 分钟内没有新的任务事件
- 最近 `stale_detection.after_minutes` 分钟内没有 heartbeat / progress / report 事件
- 任务状态不在 `stale_detection.exclude_statuses` 中

如果一个长时间运行的任务持续发出 heartbeat 或 progress 事件，即使状态仍是 `running`，也**不算 stale**。

如果某类任务天然运行时间更长，Task Spec 可以覆盖默认阈值：

```yaml
stale_override:
  after_minutes: 90
  reason: "Long-running export task emits progress every batch."
```

覆盖规则：

- override 必须写在 Task Spec 中
- override 只作用于目标 task 或 subtask
- override 不能修改 `exclude_statuses` 中的终态或人工决策态
- override 不能取消 heartbeat / progress 证据要求

### 7.3 Lock 冲突处理

Loop 按以下顺序检查 lock conflict：

1. 识别冲突的 lock type 和 holders
2. 根据 `stale_detection` 判断锁持有者是否 stale
3. 如果持有者 stale 时长超过 `after_minutes * mark_expired_after_stale_multiplier`，标记该锁为 expired
4. 追加 `loop.lock_expired.detected`
5. 将受影响任务标记为 blocked 或 `needs_human_decision`

Loop 可以主动发起释放 lock 请求，但不能直接释放：

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

请求行为：

- 追加 `lock.release.requested`
- 通知 Monitor / 用户看板
- 在人工决策或显式策略授权前，原 lock 继续保持有效
- 不能把“发起请求”视为“已经获准释放”

Loop v1 默认**不得**自动释放 expired lock。只有同时满足以下条件时，才允许未来策略启用自动释放：

- `lock_policy.auto_release_expired_locks: true`
- 目标锁资源被未来策略显式列入 allowlist
- 释放动作不意味着业务交付物写入
- 存在 `lock.release.authorized` 事件或等价授权

---

## 8. 自动推进规则

### 8.1 必须满足的条件

任务只有在以下条件全部通过时，才允许自动推进：

- `status` 属于 allowlist
- Task Spec 包含 `loop_autorun: true`
- `risk` 为 `low` 或 `minimal`
- 所有 dependencies 都已满足
- 不存在冲突的 read/write/exclusive lock
- 不存在未解决的 `needs_human_decision`
- 不包含待执行的业务写入步骤
- 每个待执行动作都包含在 `loop_safe_actions` 中

### 8.2 安全动作

`loop_safe_actions` 必须显式声明。Loop v1 不允许仅根据任务描述文本推断安全性。

推荐允许的安全动作：

```yaml
loop_safe_actions:
  - read_only_checks
  - status_update_to_verifying
  - status_update_to_running
  - report_generation
  - verifier_trigger
```

安全动作边界：

| 安全动作 | 仅当以下条件满足时允许 |
|----------|------------------------|
| `status_update_to_verifying` | 交付物已存在，Worker 已报告完成或部分完成，且 Verifier 输入条件满足。 |
| `status_update_to_running` | 任务当前为 queued 或 checkpoint-resume-ready，dependencies 已满足，locks 可用，授权有效，且不存在待人工决策项。 |
| `verifier_trigger` | 已存在验证方案，所需 artifacts 已存在，verifier 范围为只读或已显式授权，且同一任务当前不在验证中。 |

默认禁止的动作：

```yaml
loop_safe_actions_forbidden_by_default:
  - file_write
  - database_write
  - external_api_write
  - business_deliverable_write
  - lock_release
  - permission_change
```

### 8.3 推荐初始 allowlist

```text
queued
verifying_ready
stale_review
checkpoint_resume_ready
```

### 8.4 禁止自动推进的状态迁移

Loop v1 不允许自动推进以下情况：

- `blocked -> running`，如果阻塞原因尚未解决
- `failed -> running`，如果没有人工确认
- `needs_human_decision -> any-active-state`
- 任何会扩大业务写入范围的迁移

---

## 9. 队列重建策略

### 9.1 已选策略

本次确定的策略是：

**先追加事件，再基于增量快照重建队列**

也就是说：

- task events 是真实来源
- queue 是派生视图
- Loop 先写 transition events
- rebuild 再把事件流映射成当前队列状态
- 默认采用增量重建以控制性能成本
- 保留全量重建作为校验和恢复手段

### 9.2 选择这个策略的原因

相比直接改某一行队列：

- 审计性更强
- 恢复更安全
- 可做确定性回放
- 更不容易写坏部分状态
- 比每轮全量回放性能更可控

### 9.3 增量重建算法

默认重建流程：

1. 加载 `loop/rebuild/queue.snapshot.state.json`
2. 读取 `last_rebuild_event_time`
3. 只加载该时间之后的 task events 和 loop events
4. 将合法状态迁移应用到快照状态
5. 将非法或乱序迁移写入 rebuild warnings
6. 推导当前 status、owner、next step、blocker、timestamps
7. 写入队列输出文件
8. 更新快照元数据和 rebuild report

Snapshot 有效性检查：

- snapshot schema version 落在当前兼容范围内
- snapshot 的 `workspace_id` 或规范化工作区路径与当前工作区一致
- snapshot `last_rebuild_event_time` 不得晚于最新事件时间戳
- snapshot 记录的 event cursor 在事件流中存在
- task 数量与已知 task IDs 不得和当前 Task Spec 输入矛盾
- 上一次 rebuild report 不能以未恢复的 hard error 结束

如果任一有效性检查失败，Loop 必须先执行 full rebuild fallback，再写入新的队列快照。

全量重建 fallback：

1. 按时间顺序加载全部 task events
2. 从初始任务状态开始
3. 回放合法状态迁移
4. 如有增量快照，则与增量结果比对
5. 如果无法恢复一致性，写入 mismatch warnings 并 pause Loop

定期全量校验：

- 每经过 `queue_rebuild.full_rebuild_check_every_n_cycles` 个 cycle，执行一次 full rebuild check
- 推荐默认值是 `12`，按 5 分钟周期约等于 1 小时
- 将 full rebuild 输出和 incremental snapshot 对比
- 将 drift warnings 写入 `loop/rebuild/queue-rebuild-report.json`
- 如果漂移影响授权、locks、dependencies 或终态任务状态，则 pause Loop

Rebuild 输出：

- `queue/tasks.jsonl`
- `queue/tasks.snapshot.json`
- `loop/rebuild/queue.snapshot.state.json`
- `loop/rebuild/queue-rebuild-report.json`

### 9.4 Rebuild warnings

示例：

- unknown status transition
- missing dependency artifact
- lock conflict unresolved
- duplicated completion event
- resume event without checkpoint evidence
- incremental snapshot timestamp gap

这些 warning 不能被静默吞掉，必须写入 rebuild report，并在 dashboard 风险区中体现出来。

---

## 10. Guardrails

### 10.1 自动暂停条件

当出现以下情况时，Loop 应自动 pause：

- consecutive failures 超过阈值
- 同一 lock conflict 重复出现超过阈值
- 同一任务 repeated verifier failure
- queue rebuild 出现不一致
- heartbeat 配置本身无效

### 10.2 Pause 行为

当 Loop 进入 paused 状态时：

- 写 `loop_status: paused`
- 记录 `paused_reason`
- 追加 `loop.paused`
- 允许继续刷新 dashboard
- 停止 auto-advance，直到明确 resume

### 10.3 Resume 行为

Resume 应满足：

- pause 原因已清除或已被确认
- 写入 `loop.resumed`
- 保留历史 loop 运行记录

---

## 11. Dashboard 的 Loop 扩展

Dashboard 应新增一个 Loop 区块，展示：

- loop status
- last run time
- next run time
- iteration count
- consecutive failures
- paused reason
- last cycle 的 auto-advance 数量
- 最近一次 queue rebuild 结果
- last cycle summary
- Loop health
- recent Loop events

推荐新增字段：

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

Dashboard 应将 recent Loop events 展示为独立事件流，让用户能区分 Agent 工作事件和调度器决策。

---

## 12. Codex Heartbeat 接入

### 12.1 Automation 形态

Codex automation 应满足：

- 绑定到指定 workspace
- 每 5 分钟运行一次
- 调用一个 Loop runner 入口
- 不产生工作区允许路径之外的副作用

### 12.2 Runner 入口

Loop runner 应支持独立测试：

```bash
python scripts/loop_runner.py ./workspace --dry-run
python scripts/loop_runner.py ./workspace --once
python scripts/loop_runner.py ./workspace
```

模式语义：

- `--dry-run`：读取状态并输出计划动作；不写 queue、dashboard、checkpoints 或 events
- `--once`：执行一轮有边界的 cycle 后退出
- 不带模式参数：以 automation 兼容模式运行；除非未来显式增加 daemon mode，否则每次调用仍只执行一轮

### 12.3 推荐 prompt 形态

heartbeat automation prompt 应明确要求 runner：

- 读取 `loop/loop_config.json`
- 每次只执行一个 loop cycle
- 严格遵守低风险自动推进规则
- 校验 `loop_safe_actions`
- 追加 loop events
- 根据 events 增量重建 queue
- 刷新 dashboard state
- 当策略不允许时选择 pause，而不是猜测执行

### 12.4 为什么选 heartbeat，而不选 daemon

Heartbeat 更适合 v1，因为它：

- 更容易检查
- 更容易暂停
- 运维复杂度更低
- 不需要自己维护常驻本地进程

---

## 13. 异常处理

### 13.1 Soft failure

示例：

- 临时文件读取失败
- 可选 report 缺失
- dashboard snapshot 过旧

处理方式：

- 追加 warning event
- 如果安全则继续本轮 cycle

### 13.2 Hard failure

示例：

- queue rebuild 不一致
- 配置无效
- 存在重复且冲突的状态迁移
- 尝试发生未经授权的写入

处理方式：

- 追加 failure event
- 增加 consecutive failure 计数
- 视情况触发 loop pause

---

## 14. 安全边界

Loop v1 可以自动做：

- 读取 orchestration 文件
- 追加 loop events
- 重建 queue
- 写 loop 元数据
- 刷新 dashboard state
- 触发低风险 verifier 路径

Loop v1 不能自动做：

- 修改业务交付物内容
- 修复失败输出
- 扩大 allowed paths
- 覆盖或抢占 locks
- 因为“目前没报错”就推断自己有写入授权
- 释放 locks，除非未来显式策略和授权事件允许

---

## 15. 测试与模拟

### 15.1 Runner 测试模式

实现必须支持：

- dry-run mode，用于策略评审
- one-cycle mode，用于确定性测试
- automation mode，用于 heartbeat 集成

所有模式必须使用同一套 guardrail 逻辑。Dry-run 可以跳过写入，但必须报告它原本会产生的事件和变更。

### 15.2 Loop 模拟器

推荐支持工具：

```bash
python scripts/simulate_loop.py ./workspace --cycles 10 --output simulation.json
```

模拟器用途：

- 在启用 automation 前测试 Loop 配置
- 预测自动推进行为
- 调试 guardrail 逻辑
- 展示未来多个 cycle 中可能发生的 queue 和 dashboard 变化

模拟器建议纳入 v1 实现；如果需要控制范围，也可以在核心 runner 之后交付。

---

## 16. 分阶段落地计划

### Phase 1: Runtime skeleton

- 增加 `loop_config.json`
- 增加 `loop_state.json`
- 增加 `loop-events.jsonl`
- 实现 one-cycle runner
- 实现 `--dry-run` 和 `--once`

### Phase 2: Queue rebuild

- 实现基于快照的增量重建
- 实现全量重建 fallback
- 实现默认每 12 个 cycle 一次的全量校验
- 实现 snapshot 有效性检查
- 推导 queue snapshot
- 增加 rebuild report

### Phase 3: Auto-advance

- 实现 double-gate checks
- 实现 `loop_safe_actions` 校验
- 实现精细化状态更新动作
- 实现 verifier trigger 前置条件
- 实现 low-risk verifier trigger
- 实现 pause / resume guards

### Phase 4: Dashboard integration

- 为 `dashboard/state.json` 增加 loop section
- 增加 health 和 last-cycle summary 字段
- 增加 recent Loop events 事件流
- 扩展静态 dashboard 页面

### Phase 5: Simulation support

- 增加 Loop simulator
- 增加示例 simulation output
- 文档化验证流程

---

## 17. 最小验收标准

Loop v1 只有在满足以下条件时才算合格：

1. 能通过 Codex heartbeat 运行一个有边界的 cycle
2. 能读取 orchestrator 状态且不修改业务交付物
3. 能为每轮 cycle 追加 loop events
4. 能识别 stale、blocked、partially completed 任务
5. 将 stale 明确定义为 `no_event_or_heartbeat`，并排除终态和人工决策态
6. 支持 Task Spec 级别的 `stale_override`，且不取消 heartbeat / progress 证据要求
7. 能检测 expired locks，但默认不释放
8. 在策略允许时可以主动发起释放 lock 请求，但不能把请求视为批准
9. 能生成 dispatch actions
10. 只能对通过双重门禁且显式声明 `loop_safe_actions` 的低风险任务自动推进
11. 能区分 `status_update_to_verifying` 和 `status_update_to_running`
12. 只有在 artifacts、plan、scope 和并发条件满足时才触发 verifier
13. 能根据 events 增量重建 queue，并带 snapshot 有效性检查和全量重建 fallback
14. 默认每 12 个 cycle 执行一次全量校验
15. 能在 repeated hard failure 时自动 pause
16. 能在每轮结束后刷新 dashboard state
17. 能在 dashboard 中展示 last-cycle summary、health、recent Loop events
18. 支持 dry-run 和 one-cycle runner 模式
19. 能保持可审计性和可恢复性

---

## 18. 推荐下一步

本设计稿通过后，建议按以下顺序进入实现：

1. loop config schema
2. loop state schema
3. loop event schema
4. 支持 `--dry-run` 和 `--once` 的 one-cycle runner script
5. 增量 queue rebuild script
6. 定期全量校验机制
7. 精细化 auto-advance safe-action checks
8. dashboard loop panel fields
9. Loop simulator

这个版本应被实现为 **Loop v1 runtime support**，而不是一个完全自治的 agent 系统。
