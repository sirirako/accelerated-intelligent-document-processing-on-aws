# AI Agent Knowledge Base

This directory contains shared context for any AI agent working on this
enterprise fork. Read the memory files before starting work — they contain
decisions, architecture state, and known issues that save re-discovery time.

## For AI agents: start here

1. Read all of `memory/knowledge/` — architecture, constraints, decisions, merge rules
2. Skim the most recent 2-3 files in `memory/activities/` for continuity
3. Read the relevant `skills/` file for your task
4. If your task matches an agent in `agents/`, read that agent file — it has hard
   rules and a workflow, not just reference material

`memory/knowledge/constraints.md` is the highest-value file: the customer runs
air-gapped with TLS inspection, and most past failures came from violating
something listed there.

## For humans

Point your AI tool at this directory:
- **Claude Code**: Add to CLAUDE.md: `Read enterprise/.ai/memory/knowledge/ for project context`
- **Kiro**: Reference in your spec: `context: enterprise/.ai/memory/`
- **Cursor**: Add to `.cursor/rules`: `@enterprise/.ai/memory/`
- **Any agent**: Include these files in your prompt context

## Structure

```
.ai/
├── memory/                     # What we know
│   ├── knowledge/              # Stable, long-term. Read at session start.
│   │   ├── architecture.md     # What this project is, how it's structured
│   │   ├── constraints.md      # Air-gapped rules, what's blocked, what breaks
│   │   ├── decisions.md        # Key decisions with reasoning (why + alternatives)
│   │   └── merge-rules.md      # How to merge upstream without breaking things
│   ├── activities/             # Append-only session logs (YYYY-MM-DD-<topic>.md)
│   └── README.md               # Memory system rules + curation process
├── skills/                     # How to do things (read when doing a specific task)
│   ├── code-review.md          # Reviewing changes in this fork
│   ├── completion-hook.md      # ActiveMQ completion hook: params, testing, TLS
│   ├── deploy.md               # Publish + deploy a stack
│   ├── new-environment.md      # Stand up a new environment
│   ├── pipeline-merge.md       # Merging pipeline template changes
│   ├── pipeline-setup.md       # SDLC pipeline setup end-to-end
│   ├── private-registry.md     # JFrog / air-gapped registry configuration
│   ├── test.md                 # Test suites, Jobs API testing (incl. Ping auth)
│   └── upstream-sync.md        # Full upstream merge checklist
├── agents/                     # Personas with hard rules and workflows
│   ├── compliance-reviewer.md  # Review changes for customer policy violations
│   ├── customer-merge.md       # Customer-side air-gapped repo merge
│   ├── deployer.md             # Publishing and deploying stacks
│   ├── memory-curator.md       # Periodic memory maintenance (dreaming/GC)
│   ├── merge-resolver.md       # Merging upstream releases into enterprise/develop
│   └── README.md               # Agent index + invocation templates
└── README.md                   # This file
```

## Keeping this current

`memory/README.md` defines the curation rules: knowledge files are edited in
place, activity logs are append-only. When an activity log records that
something shipped, reconcile the corresponding knowledge file in the same
session — stale "TBD" notes in `constraints.md` are worse than no note.
