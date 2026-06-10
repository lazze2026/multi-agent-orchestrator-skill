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