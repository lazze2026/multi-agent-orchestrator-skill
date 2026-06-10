# Multi-Agent Orchestrator

单个 AI 工具内的逻辑多 Agent 协同调度协议和 Skill 实现。

[![Version](https://img.shields.io/badge/version-1.2.0-blue.svg)](https://github.com/lazze2026/multi-agent-orchestrator-skill)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)

---

## 概述

Multi-Agent Orchestrator 是一个用于在单个 AI 工具会话内协调多个逻辑角色（Coordinator、Worker、Verifier、Monitor）的协议和 Skill 实现。它解决了长任务、批量任务、需要验证的任务在单工具内的：

- 可追踪性（任务队列、事件日志）
- 可恢复性（Checkpoint、部分完成状态）
- 可验证性（独立 Verifier、验收标准）
- 安全性（授权边界、资源锁、取消级联）

**核心特点**：
- ✅ 逻辑 Agent（非独立进程），运行在同一 AI 工具会话
- ✅ 状态机驱动（12个状态，严格迁移规则）
- ✅ 事件溯源（append-only 日志，完整因果链）
- ✅ 断点续跑（Checkpoint + 幂等性验证）
- ✅ 独立验证（Verifier 不继承 Worker 结论）

---

## 快速开始

### 安装

将此 Skill 放入 Claude Code 的 skills 目录：

```bash
cd ~/.claude/skills
git clone https://github.com/lazze2026/multi-agent-orchestrator-skill.git
```

### 使用

在 Claude Code 中调用：

```bash
/multi-agent-orchestrator
```

Skill 会引导你完成：
1. 判断任务是否适合多 Agent 协调
2. 创建 Task Spec（任务规格）
3. 拆分 Worker Brief（子任务卡）
4. 执行 Worker（串行/并行）
5. Verifier 独立验证
6. 生成 Checkpoint 和状态报告

---

## 适用场景

✅ **适合使用的任务**：
- 批量数据处理（按时间、目录、模块分片）
- 多步骤依赖任务（需要记录进度和依赖关系）
- 长时间运行任务（需要 Checkpoint 断点续跑）
- 需要质量保证的任务（独立验证交付物）

❌ **不适合使用的任务**：
- 简单单步任务（10分钟内完成）
- 高度交互式任务（需要用户连续判断）
- 授权边界不清晰的任务
- 跨工具协作任务（本协议仅适用于单工具内）

---

## 核心概念

### 逻辑角色

| 角色 | 职责 | 禁止 |
|------|------|------|
| **Coordinator** | 拆解任务、分配 Worker、汇总结果、决策下一步 | 不能跳过 Verifier 直接宣称完成 |
| **Worker** | 执行子任务、报告进度和风险 | 不能扩大任务范围、不能自动修复问题 |
| **Verifier** | 独立验证交付物、检查验收标准 | 不能继承 Worker 结论、不能自动修复 |
| **Monitor** | 汇总状态、识别异常、预警风险、建议优化 | 不能自主修复、不能自主改变任务状态 |

### 状态机

```
draft → planned → approved → queued → running → verifying → done
                                        ↓
                              partially_completed → verifying
                                        ↓
                                     blocked
```

关键状态：
- **partially_completed**：Worker 完成部分工作后遇到阻塞（如 API 限流），保留已完成数据和恢复点
- **needs_human_decision**：Verifier 发现问题需要人工判断
- **cancelled**：用户取消，不等于失败，不默认回滚

### 核心工件

| 工件 | 用途 | 格式 |
|------|------|------|
| **Task Spec** | 任务规格，包含目标、授权、允许路径、验收标准 | Markdown |
| **Worker Brief** | 子任务卡，包含范围、依赖、允许输入/输出 | Markdown |
| **Event Log** | 状态迁移日志，append-only，完整因果链 | JSONL |
| **Checkpoint** | 恢复点，记录已完成/部分完成/阻塞任务 | Markdown |
| **Verification Report** | 验证报告，包含检查命令、验收证据、风险评估 | Markdown |

---

## 协议版本

**当前版本**: v1.2.0

**主要特性**（v1.2.0）：
- ✅ `partially_completed` 状态支持
- ✅ 事件因果链（trigger_event_id, caused_by）
- ✅ Checkpoint 幂等性验证流程
- ✅ 依赖关系声明（depends_on, requires_artifacts）
- ✅ 读写锁区分（read/write/exclusive）
- ✅ 风险关联验证策略（high=100%, medium=50%, low=20%）
- ✅ Monitor 主动预警（异常模式、资源瓶颈、降级建议）
- ✅ 取消级联规则（按状态分类处理，不默认回滚）
- ✅ 任务优先级机制（priority + FIFO）
- ✅ 降级策略框架

完整协议文档：[references/protocol.md](references/protocol.md)

---

## 目录结构

```
multi-agent-orchestrator/
├── README.md                    # 本文件
├── SKILL.md                     # Skill 入口定义
├── agents/
│   └── openai.yaml             # Agent 配置
├── references/
│   ├── protocol.md             # 完整协议文档（1024行，21章节）
│   └── templates/              # 模板文件
│       ├── task-spec.md
│       ├── worker-brief.md
│       ├── checkpoint.md
│       ├── event.json
│       └── verification-report.md
└── tests/
    └── simulations/            # 测试案例
        ├── api-rate-limit-partial-completion/    # 内置测试：API限流
        └── complete-workflow/                     # 完整工作流测试（7个Phase）
```

---


## 看板使用

Dashboard 是只读视图，页面读取 `dashboard/state.json`，不会修改队列、事件、锁、报告、checkpoint 或任务状态。

### 依赖

- Python 3.9+
- 无需额外依赖，脚本只使用 Python 标准库

### 生成 state.json

```bash
python scripts/generate_dashboard_state.py ./workspace
```

默认输出到：

```text
./workspace/dashboard/state.json
```

指定输出路径：

```bash
python scripts/generate_dashboard_state.py ./workspace --output ./dashboard/state.json --refresh-interval 180
```

Linux/Mac 可使用包装入口：

```bash
chmod +x scripts/dashboard
scripts/dashboard ./workspace --output ./dashboard/state.json
```

### 校验 state.json

```bash
python scripts/validate_state.py ./workspace/dashboard/state.json
```

### 自动化刷新

Linux/Mac：

```bash
watch -n 180 python scripts/generate_dashboard_state.py ./workspace
```

Windows PowerShell：

```powershell
while($true) {
  python scripts/generate_dashboard_state.py ./workspace
  Start-Sleep -Seconds 180
}
```

### 本地预览

```bash
python -m http.server 8765 --bind 127.0.0.1 --directory dashboard
```

然后打开：

```text
http://127.0.0.1:8765/index.html
```

## 测试

Skill 包含两个完整的测试案例：

### 1. API限流部分完成测试
**场景**：模拟导出5000条记录时遇到API限流，完成2000条后部分完成。

**测试覆盖**：
- Task Spec 和 Worker Brief 生成
- 部分完成状态记录（2000/5000）
- 恢复点信息保存（last_id=2000）
- Verifier 独立验证
- Checkpoint 幂等性步骤
- 状态短分诊

**结果**：16/16 测试通过 ✅

测试报告：[tests/simulations/api-rate-limit-partial-completion/reports/simulation-test-report.md](tests/simulations/api-rate-limit-partial-completion/reports/simulation-test-report.md)

---

### 2. 完整工作流测试（7个Phase）
**场景**：钉钉历史聊天记录批量回填（2026年3-5月），覆盖完整生命周期。

**测试覆盖**：
- Phase 1: 初始化（配置、目录、Task Spec）
- Phase 2: Worker-1 执行（状态机、锁、事件日志）
- Phase 3: API限流导致部分完成（3/5条消息）
- Phase 4: Checkpoint 生成和恢复（幂等性验证）
- Phase 5: Verifier 独立验证（发现验收标准不匹配）
- Phase 6: Monitor 状态报告（主动预警、降级建议）
- Phase 7: 取消级联规则（3种状态分类处理，保留交付物）

**结果**：所有协议特性全部通过 ✅

**生成的 Artifacts**：
- 16个事件（完整因果链）
- 2个交付物（3月5条✓，4月3条✓）
- 5个报告（Worker × 2, Verifier × 1, Monitor × 1, Cancellation Plan × 1）
- 1个 Checkpoint（含幂等性验证步骤）

测试报告：[tests/simulations/complete-workflow/TEST_REPORT.md](tests/simulations/complete-workflow/TEST_REPORT.md)

---

### 运行测试

查看测试报告：

```bash
# 内置测试
cat tests/simulations/api-rate-limit-partial-completion/reports/simulation-test-report.md

# 完整工作流测试
cat tests/simulations/complete-workflow/TEST_REPORT.md
```

测试文件结构：

```bash
# 查看测试生成的工件
ls tests/simulations/complete-workflow/
# 输出: orchestrator.json, tasks/, queue/, events/, output/, reports/, checkpoints/
```

---

## 示例

### 示例 1: 批量数据导出

```markdown
用户: 导出2024-2026年的钉钉群聊记录，按季度分批处理

Coordinator:
1. 创建 Task Spec（目标、授权、验收标准）
2. 拆分 12 个 Worker Brief（2024-Q1 ~ 2026-Q4）
3. 串行执行，避免 API 限流
4. 每个 Worker 完成后 Verifier 验证
5. 生成 Checkpoint 记录进度

如遇 API 限流：
- Worker 报告 partially_completed
- 保存已完成数据和恢复点（last_id, timestamp）
- Coordinator 等待限流窗口后恢复
```

### 示例 2: 多模块代码重构

```markdown
用户: 重构项目中的 auth、billing、notification 三个模块

Coordinator:
1. 创建 Task Spec（高风险，需要全量验证）
2. 拆分 3 个 Worker Brief，添加依赖关系
3. Worker-1 处理 auth（基础模块）
4. Worker-2 处理 billing（depends_on: Worker-1）
5. Worker-3 处理 notification（depends_on: Worker-1）
6. Verifier 独立验证每个模块（运行测试、检查 lint）
7. 所有验证通过后标记 done
```

---

## 协议设计亮点

### 1. 部分完成状态
不同于二元的"成功/失败"，`partially_completed` 是一等公民状态：
- 保留已完成工作（避免重复执行）
- 记录恢复点（精确续跑位置）
- 触发 Checkpoint（保存进度）

### 2. 事件因果链
每个事件包含 `trigger_event_id` 和 `caused_by`，完整追溯决策链：
```json
{"event_id":"evt_0008","trigger_event_id":"evt_0007","caused_by":"api_rate_limit"}
```

### 3. Verifier 独立性
Verifier 从任务卡和交付物重新开始，不继承 Worker 的自我评价：
- 重新读取 Task Spec
- 重新读取交付物
- 执行可重复验证命令
- 给出独立结论

### 4. Monitor 主动预警
Monitor 从被动"汇总状态"升级为主动"预警风险"：
- 识别异常模式（失败率突增、锁冲突频繁）
- 预测资源瓶颈（队列积压、API限流）
- 建议调度优化（降低活跃Worker、拆小任务）
- 建议降级策略（切换API、缩小批次）

### 5. 取消不等于回滚
取消任务时按状态分类处理：
- `verifying` 状态：保留交付物和验证证据
- `partially_completed` 状态：保留部分数据和恢复点
- `draft` 状态：直接取消，无交付物
- **任何删除、覆盖都需要重新授权**

---

## 安全边界

协议严格定义了"永远不能自动做的事"：

❌ 未授权写代码、写数据库、修改配置、删除源数据  
❌ 验证失败后自动修复业务逻辑  
❌ 绕过 Task Spec 直接执行复杂任务  
❌ 把 Worker 的完成报告当成最终验收  
❌ 把选项预览当成用户批准  
❌ 优先级绕过授权、资源锁或验证  

✅ 可以自动做的事：

拆解任务草案、生成 Worker Brief、读取允许范围内文件、运行只读检查、生成状态报告、生成 Checkpoint、给出修复建议

---

## 协议遵循度

本 Skill 满足协议 v1.2.0 定义的**最小可用标准**（21.节）全部12条：

1. ✅ 能生成 Task Spec
2. ✅ 能生成独立 Worker Brief
3. ✅ 能维护任务状态机
4. ✅ 能追加事件日志
5. ✅ 能生成 Checkpoint
6. ✅ 能执行 Verifier 复核
7. ✅ 能在授权缺失、资源冲突、验证失败时暂停
8. ✅ 能输出短分诊状态报告
9. ✅ 不把单工具逻辑 Agent 误描述成真实并发进程
10. ✅ 能记录 `partially_completed` 并恢复未完成部分
11. ✅ 能在 resume 时执行幂等性验证
12. ✅ 能处理任务取消和依赖级联

---

## 贡献指南

欢迎提交 Issue 和 Pull Request！

### 开发环境

```bash
# 克隆仓库
git clone https://github.com/lazze2026/multi-agent-orchestrator-skill.git
cd multi-agent-orchestrator

# 查看协议文档
cat references/protocol.md

# 查看测试
ls tests/simulations/
```

### 提交测试案例

如果你有新的测试场景，请：

1. 在 `tests/simulations/` 下创建新目录
2. 包含完整的工件（orchestrator.json, tasks/, events/, reports/, checkpoints/）
3. 提供测试报告（说明场景、覆盖的协议特性、测试结果）

---

## 常见问题

### Q: 这个 Skill 和 OMC 的关系？
A: 这是独立的协议设计，可以被 OMC 或其他工具使用。协议定义了单工具内多角色协作的标准，OMC 可以实现这个协议。

### Q: 可以跨工具使用吗？
A: 当前版本（v1.2.0）仅支持单工具内逻辑 Agent。跨工具协作将在后续版本设计。

### Q: Checkpoint 会占用很多存储吗？
A: 不会。测试中的 Checkpoint 约 2.6KB，事件日志约 2KB（16个事件）。轻量级设计，可快速读取。

### Q: 如何处理长任务的上下文压缩？
A: 生成 Checkpoint 后，可以安全压缩上下文。恢复时从 Checkpoint 读取状态，从事件日志重建完整历史。

### Q: Verifier 会自动修复问题吗？
A: 不会。Verifier 只负责验证和报告，不能自动修复。这避免了"为了通过验证而修改交付物"的风险。

### Q: 取消任务会回滚数据吗？
A: 不会。取消是"停止继续"，不是"撤销已做"。任何删除、覆盖都需要作为新的写操作重新授权。

---

## 版本历史

### v1.2.0 (2026-06-08)
- ✅ 增加 `partially_completed` 状态
- ✅ 增加事件因果链（trigger_event_id, caused_by）
- ✅ 增加 Checkpoint 幂等性验证流程
- ✅ 增加依赖关系声明
- ✅ 增加读写锁区分
- ✅ 增加风险关联验证策略
- ✅ 增加 Monitor 主动预警
- ✅ 增加取消级联规则
- ✅ 增加任务优先级机制
- ✅ 增加降级策略框架
- ✅ 增加完整工作流测试（7个Phase）

### v1.1.0
- 基础协议设计
- API限流部分完成测试

---

## 许可证

MIT License

---

## 致谢

感谢所有贡献者和测试者！

特别感谢：
- Claude Code 团队提供的 Skill 框架
- 数据中心项目实践中的真实场景验证

---

## 联系方式

- GitHub Issues: https://github.com/lazze2026/multi-agent-orchestrator-skill/issues
- 协议讨论: 欢迎在 Issue 中讨论协议改进建议

---

**Multi-Agent Orchestrator v1.2.0** - 让单工具内的多角色协作可追踪、可恢复、可验证。
