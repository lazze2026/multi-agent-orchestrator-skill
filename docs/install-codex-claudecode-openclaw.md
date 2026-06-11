# Install Multi-Agent Orchestrator for Codex, ClaudeCode, and OpenClaw

This Skill is tool-agnostic. It coordinates logical agents inside one AI tool session and does not require a background service.

## Recommended Shared Install

Clone once into a shared skills directory:

```bash
git clone https://github.com/lazze2026/multi-agent-orchestrator-skill.git ~/.shared-skills/multi-agent-orchestrator
```

Then link it into each tool's skills directory.

## Codex

```bash
mkdir -p ~/.codex/skills
ln -s ~/.shared-skills/multi-agent-orchestrator ~/.codex/skills/multi-agent-orchestrator
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force $HOME\.codex\skills
New-Item -ItemType Junction -Path $HOME\.codex\skills\multi-agent-orchestrator -Target $HOME\.shared-skills\multi-agent-orchestrator
```

## ClaudeCode

```bash
mkdir -p ~/.claude/skills
ln -s ~/.shared-skills/multi-agent-orchestrator ~/.claude/skills/multi-agent-orchestrator
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force $HOME\.claude\skills
New-Item -ItemType Junction -Path $HOME\.claude\skills\multi-agent-orchestrator -Target $HOME\.shared-skills\multi-agent-orchestrator
```

## OpenClaw

```bash
mkdir -p ~/.openclaw/skills
ln -s ~/.shared-skills/multi-agent-orchestrator ~/.openclaw/skills/multi-agent-orchestrator
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force $HOME\.openclaw\skills
New-Item -ItemType Junction -Path $HOME\.openclaw\skills\multi-agent-orchestrator -Target $HOME\.shared-skills\multi-agent-orchestrator
```

## Smoke Test

Ask your AI tool:

```text
Use multi-agent-orchestrator to create a Task Spec, Worker Brief, event log, checkpoint, verifier report, and dashboard state for a small simulated batch export.
```

Expected result:

- It creates or references a Task Spec before execution.
- It separates Worker and Verifier responsibilities.
- It records partial completion and checkpoint behavior when relevant.
- It treats the dashboard as read-only.

## Dashboard Enhanced Features

After installation, the three tools can all use the same `v1.3.0` dashboard enhancement set because they point to the same shared Skill directory.

Recommended demo workflow:

```bash
python -m http.server 8765 --bind 127.0.0.1 --directory tests/simulations/dashboard-static-html
```

Open:

```text
http://127.0.0.1:8765/index.html
```

Enhancements included in this version:

- top KPI cards through `summary.metrics`
- richer Agent cards through `current_work`, `detail`, and `last_observed`
- generic entity matrix support through `entity_grid`
- localized status and risk text through `display_dictionary`
- readable event names through `event_display_rules`
- optional business-specific display sections through `domain_extensions`

Recommended production refresh:

```bash
python scripts/generate_dashboard_state.py ./workspace --output ./workspace/dashboard/state.json --refresh-interval 180
```

Windows PowerShell loop:

```powershell
while($true) {
  python scripts/generate_dashboard_state.py .\workspace --output .\workspace\dashboard\state.json --refresh-interval 180
  Start-Sleep -Seconds 180
}
```

Tool-specific notes:

- `Codex`: best fit when you want the static HTML board visible in the in-app browser while coding continues in the same thread
- `ClaudeCode`: best fit when you want the Skill to act as a disciplined orchestration protocol with explicit specs, briefs, and checkpoints
- `OpenClaw`: best fit when you want the shared protocol and demo assets available from the same local Skill checkout
