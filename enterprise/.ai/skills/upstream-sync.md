# Skill: Upstream Sync

## When to use
Merging upstream develop/main into the enterprise fork.

## Full guide
**Read `enterprise/docs/upstream-sync-guide.md`** — it has the complete conflict
resolution rules, silent-breakage checks, and post-merge checklist.

## Quick steps

1. `git fetch upstream main` (or `develop`)
2. `git merge upstream/main`
3. Resolve conflicts per the rules in the full guide
4. Run silent-breakage checks (YAML valid, enterprise markers intact, SFN chain)
5. `./enterprise/build.sh && make lint && make test`
6. Update `.ai/memory/enterprise-state.md` if something relevant changed

## Key rules (from the full guide)
- Never delete enterprise resources during conflict resolution
- Keep both sides for additive changes (params, conditions)
- `ShouldEnablePostProcessingLambdaHook` must keep our `!Or` wrapper
- API Gateway must keep `PingAuthorizer`
- Escalate if upstream removed `PostProcessingLambdaHookFunctionArn` or restructured SFN
