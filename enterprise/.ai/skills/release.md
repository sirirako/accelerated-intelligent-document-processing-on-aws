# Cutting an Enterprise Release

How to ship an enterprise build to the customer. Read this whenever the task is
"release", "prerelease", "cut a version", "tag", or "ship to the customer".

## The two version files — do NOT confuse them

| File | Tracks | Who owns it | When it changes |
|------|--------|-------------|-----------------|
| root `VERSION` | the **upstream** application release we've merged | mirrors upstream | only on an upstream merge (see `upstream-sync.md`) |
| `enterprise/VERSION` | **our** fork iteration | enterprise-owned | every enterprise build shipped to the customer |

`enterprise/VERSION` format is `<upstream-base>-ent.<n>`, e.g. `0.6.1-ent.1`:
"upstream 0.6.1 base, enterprise iteration 1." Rationale and alternatives are in
`memory/knowledge/decisions.md` ("Enterprise version tracked separately from
upstream"). `enterprise/*` is never overwritten by upstream, so the file is
merge-safe.

## MANDATORY: bump `enterprise/VERSION` on every enterprise release

Any time you cut a customer-facing enterprise build, you MUST update
`enterprise/VERSION` **before** tagging. This is not optional and is easy to
forget because the root `VERSION` looks like it already covers it — it does not.

Rules for the new value:

- **Same upstream base, new enterprise work** → increment the `-ent.<n>` counter.
  `0.6.1-ent.1` → `0.6.1-ent.2`.
- **After an upstream merge rolled the base** → set base to the new upstream
  version and reset the counter to 1. Upstream 0.6.1 → 0.6.2 makes the next
  enterprise release `0.6.2-ent.1` (NOT `0.6.1-ent.3`). This step lives in the
  `upstream-sync.md` post-merge checklist too.

## Release steps

1. **Confirm the tree is clean** and on `enterprise/develop`. All intended
   changes committed. `local-*` env files are gitignored — never part of a
   release.
2. **Bump `enterprise/VERSION`** per the rules above.
3. **Write an activity log** under `memory/activities/YYYY-MM-DD-<topic>.md`
   describing what shipped. This is the enterprise changelog — do NOT edit the
   root `CHANGELOG.md`, which is upstream-facing (see decisions.md). Convert any
   relative dates to absolute.
4. **Reconcile knowledge files** in the same session if anything material
   changed (constraints, decisions) — stale notes are worse than none.
5. **Commit** the version bump + activity log together.
6. **Tag** `enterprise-v<enterprise-version>`, e.g. `enterprise-v0.6.1-ent.1`.
   Annotated tag; message summarizes the iteration.

## Prerelease vs release

There is no separate prerelease suffix — the `-ent.<n>` counter already marks
every enterprise build as a fork iteration on top of upstream. A build handed to
the customer for testing is just the next `-ent.<n>`; note "prerelease / for
testing" in the activity log and tag message rather than mangling the version
string.

## Do NOT

- Do NOT touch the root `VERSION` or root `CHANGELOG.md` for an enterprise-only
  release — those are upstream's clock.
- Do NOT reuse an upstream version number as-is for an enterprise tag (e.g.
  tagging `v0.6.2` for enterprise work collides with upstream's real 0.6.2).
- Do NOT commit `local-*` env files or customer-specific config.
