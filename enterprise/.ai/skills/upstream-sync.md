# Skill: Upstream Sync

## When to use
Merging upstream develop/main into the enterprise fork.

## Steps

1. Fetch upstream:
   ```bash
   git fetch upstream develop
   ```

2. Merge:
   ```bash
   git merge upstream/develop
   ```

3. Resolve conflicts (see `enterprise/docs/upstream-sync-guide.md` for detailed rules):
   - `template.yaml`: keep enterprise params/conditions/resources alongside upstream's
   - `Dockerfile.optimized`: keep our ARGs, update base image version if upstream bumped it
   - `patterns/unified/buildspec.yml`: keep our install-phase guards
   - `enterprise/` directory: never conflicts (ours only)

4. Run silent-breakage checks (even if merge was clean):
   ```bash
   # YAML valid
   python3 -c "import yaml; yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None); yaml.safe_load(open('template.yaml')); print('OK')"
   
   # Enterprise markers intact
   grep -n "Enterprise Integration" template.yaml
   grep -n "DeployCompletionHook" template.yaml
   grep -n "EnterprisePingAuthorizerFunction" template.yaml
   
   # SFN chain integrity (if pipeline hooks exist)
   python3 -c "..." # see upstream-sync-guide.md for full script
   ```

5. Build and test:
   ```bash
   ./enterprise/build.sh
   make lint
   make test
   ```

6. Update `enterprise/.ai/memory/enterprise-state.md` if upstream changed something relevant.

## Key rules
- Never delete enterprise resources during conflict resolution
- If upstream renamed something our overlay references, update our reference
- If unsure, keep both sides and test
- Escalate if: upstream removed PostProcessingLambdaHookFunctionArn, restructured SFN into parallel branches, or replaced Cognito entirely
