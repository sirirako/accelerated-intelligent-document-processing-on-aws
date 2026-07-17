# AI Agent Knowledge Base

This directory contains shared context for any AI agent working on this
enterprise fork. Read the memory files before starting work — they contain
decisions, architecture state, and known issues that save re-discovery time.

## For AI agents: start here

1. Read `memory/architecture.md` — what this project is and how it's structured
2. Read `memory/decisions.md` — key decisions made and why
3. Read `memory/enterprise-state.md` — current state of enterprise features
4. Read `memory/open-work.md` — active workstreams and blockers
5. Read the relevant `skills/` file for your task

## For humans

Point your AI tool at this directory:
- **Claude Code**: Add to CLAUDE.md: `Read enterprise/.ai/memory/ for project context`
- **Kiro**: Reference in your spec: `context: enterprise/.ai/memory/`
- **Cursor**: Add to `.cursor/rules`: `@enterprise/.ai/memory/`
- **Any agent**: Include these files in your prompt context

## Structure

```
.ai/
├── memory/              # What we know (read on every session start)
│   ├── architecture.md  # System architecture and component map
│   ├── decisions.md     # Key decisions and their rationale
│   ├── enterprise-state.md  # Feature status, what's deployed, known issues
│   └── open-work.md     # Active workstreams, blockers, coordination
├── skills/              # How to do things (read when doing a specific task)
│   ├── upstream-sync.md
│   ├── deploy.md
│   ├── test-api.md
│   └── new-environment.md
└── README.md            # This file
```
