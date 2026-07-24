# Agents

Task-specific agent definitions. Each agent has a role, context requirements,
rules, and a workflow.

## Available agents

| Agent | File | When to use |
|-------|------|-------------|
| Merge Resolver | `merge-resolver.md` | Merging upstream releases into enterprise/develop |
| Compliance Reviewer | `compliance-reviewer.md` | Reviewing changes for customer policy violations |
| Memory Curator | `memory-curator.md` | Periodic memory maintenance (dreaming/GC) |
| Deployer | `deployer.md` | Publishing and deploying stacks |

## Difference from skills

- **Skills** (`../skills/`) = "how to do X" — reference docs, checklists, step-by-step
- **Agents** = "you ARE the thing that does X" — persona, hard rules, judgment, workflow

An agent reads skills as reference material. A skill doesn't have opinions or
constraints — an agent does.

## Universal rules (all agents)

1. **Read knowledge first** — load all files in `../memory/knowledge/` before starting
2. **Log your work** — when done, create/update an activity log in `../memory/activities/YYYY-MM-DD-<topic>.md`
3. **Log failures** — if something breaks, document what happened and how it was fixed (this prevents repeating mistakes)
4. **Update knowledge if needed** — if you discover a new constraint, rule, or decision, add it to the appropriate knowledge file

## How to invoke

When starting a task that matches an agent, read the agent file first. It tells
you:
1. What knowledge to load (context)
2. What you must NEVER do (rules)
3. What steps to follow (workflow)
4. How to verify success
5. What mistakes were made before (so you don't repeat them)

## Invocation template

Copy-paste this to bootstrap an agent session:

```
Read these files in order, then perform your task:

1. enterprise/.ai/agents/README.md
2. enterprise/.ai/memory/knowledge/architecture.md
3. enterprise/.ai/memory/knowledge/constraints.md
4. enterprise/.ai/memory/knowledge/decisions.md
5. enterprise/.ai/memory/knowledge/merge-rules.md
6. enterprise/.ai/agents/<AGENT_NAME>.md
7. enterprise/.ai/memory/activities/ (most recent 2-3 files)

You are the <AGENT_NAME> agent. Follow your workflow. Log what you do.
```

### Shorthand (if tool supports glob reads)

```
Read enterprise/.ai/agents/README.md
Read enterprise/.ai/memory/knowledge/*
Read enterprise/.ai/agents/<AGENT_NAME>.md
Skim enterprise/.ai/memory/activities/ (latest 2-3)
```

### Example: invoking merge-resolver

```
Read these files in order, then perform your task:

1. enterprise/.ai/agents/README.md
2. enterprise/.ai/memory/knowledge/architecture.md
3. enterprise/.ai/memory/knowledge/constraints.md
4. enterprise/.ai/memory/knowledge/decisions.md
5. enterprise/.ai/memory/knowledge/merge-rules.md
6. enterprise/.ai/agents/merge-resolver.md
7. enterprise/.ai/memory/activities/ (most recent)

You are the merge-resolver agent. Upstream main has new commits.
Merge them into enterprise/develop following your workflow.
```

## Adding new agents

Create a new `.md` file with these sections:
- **Role** — one paragraph, what this agent does
- **Context** — which knowledge/skills files to read
- **Rules** — hard constraints (NEVER/ALWAYS)
- **Workflow** — numbered steps
- **Verification** — how to confirm success
- **Common mistakes** — past failures to avoid (optional but valuable)
- **Logging** — what to document in activities when done
