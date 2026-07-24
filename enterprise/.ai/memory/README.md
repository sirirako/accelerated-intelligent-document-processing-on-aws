# Agent Memory System

## Structure

```
memory/
├── knowledge/      ← Stable, long-term. Read at session start.
│   ├── architecture.md     — What this project is, how it's structured
│   ├── constraints.md      — Air-gapped rules, what's blocked, what breaks
│   ├── decisions.md        — Key decisions with reasoning (why + alternatives)
│   └── merge-rules.md     — How to merge upstream without breaking things
├── activities/     ← Append-only session logs. What was done and when.
│   └── YYYY-MM-DD-<topic>.md
└── README.md       ← This file
```

## For agents

### On session start:
1. Read ALL files in `knowledge/` — this is your context
2. Skim recent `activities/` (last 2-3 entries) for continuity

### During work:
- Log what you did in `activities/YYYY-MM-DD-<topic>.md`
- If you discover something that should be permanent knowledge (a new constraint,
  a decision, a rule), add it to the appropriate `knowledge/` file

### On session end:
- Ensure your activity log is complete (what was done, what failed, what's next)

## Dreaming agent (periodic maintenance)

A separate agent runs periodically to:
1. **Promote** — recurring patterns in activities → knowledge (e.g. "this error happened 3 times" → add to constraints)
2. **Prune** — remove stale activities older than 30 days
3. **Reconcile** — if activities contradict knowledge, update knowledge
4. **Summarize** — collapse multiple activity entries into concise knowledge updates

## Rules

- Knowledge files are **edited in place** (updated, never duplicated)
- Activity files are **append-only** (one per session/topic, never edited after the day)
- Never put customer-specific secrets, ARNs, or credentials in memory
- Skills (`.ai/skills/`) are the "how to" — memory is the "what we know"
