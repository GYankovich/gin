---
name: multi-agent-workflow
description: >-
  Four-role Cursor team for GIN: fullstack-analyst → product-designer and/or
  backend → UI, dispatched by the orchestrator. Use when the user asks for a
  multi-agent workflow, “команда”, “оркестратор”, new feature through agents,
  or names analyst / designer / backend / UI as a team.
---

# Multi-agent workflow (GIN)

When this skill applies, **you are the orchestrator**. Read `.cursor/agents/orchestrator.md` and follow it. Do not write the SPEC, UX spec, or production code yourself.

## Team (custom agents in `.cursor/agents/`)

| Subagent | File |
|----------|------|
| Analyst | `fullstack-analyst` |
| Designer | `product-designer` |
| Backend | `senior-python-backend-engineer` |
| UI | `senior-typescript-ui-engineer` |

Launch specialists with the Task tool (`subagent_type` = agent name). After each phase, summarize and **wait for user approval**.

## Sequence

1. Clarify (≤3 questions) if needed  
2. `fullstack-analyst` → `docs/SPEC-XX-*.md`  
3. In parallel when both apply: `product-designer` and `senior-python-backend-engineer`  
4. `senior-typescript-ui-engineer` only with SPEC + `docs/ui/UX-XX-*.md`

Legacy: `business-analyst-trader`, `systems-analyst` — only if the user names them.
