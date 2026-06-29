# Upstream Sync — Conflict Resolution Guide

When syncing from upstream (`git merge upstream/main`), conflicts will only occur in `template.yaml`. The `enterprise-addon/` directory is ours alone — upstream will never touch it.

## What can conflict

| Section in template.yaml | Why it might conflict | Risk level |
|---|---|---|
| Parameters block (our enterprise params) | Upstream adds new params near the same location | Low — just keep both |
| Conditions block (our 2 conditions) | Upstream adds new conditions | Low — just keep both |
| API Gateway `Auth:` block | Upstream changes the Cognito authorizer config | **Medium** — must preserve our `!If` switch |
| PostJob / GetJob event `Auth:` | Upstream changes method-level auth or scopes | **Medium** — must preserve our `!If` wrappers |
| `ShouldEnablePostProcessingLambdaHook` condition | Upstream modifies this condition | **Medium** — must keep our `!Or` addition |
| Decompressor `CUSTOM_POST_PROCESSOR_ARN` | Upstream changes how the hook ARN is passed | **Medium** — must preserve our `!If` |
| Enterprise Resources block | Won't conflict (our section is self-contained) | None |

## How to resolve each type

### 1. Parameters block (trivial)

Our enterprise parameters sit between these markers:
```yaml
  # =========================================================================
  # === Enterprise Integration (optional) ===================================
  # =========================================================================
  ...
  # =========================================================================
  # === Enterprise Integration — END ========================================
  # =========================================================================
```

**Resolution:** Keep both upstream's new parameters and our block. They're additive — order doesn't matter.

### 2. Conditions block (trivial)

Our two lines:
```yaml
  # Enterprise integration conditions
  UsePingAuth: !Equals [!Ref EnablePingAuth, 'true']
  DeployCompletionHook: !Equals [!Ref EnableCompletionHook, 'true']
```

**Resolution:** Keep both. These just sit alongside the other conditions.

### 3. API Gateway Auth block (careful)

This is the most likely conflict point. Our version:
```yaml
Auth:
  DefaultAuthorizer: !If
    - UsePingAuth
    - PingAuthorizer
    - CognitoAuthorizer
  Authorizers:
    CognitoAuthorizer:
      UserPoolArn: !GetAtt ApiUserPool.Arn
    PingAuthorizer:
      FunctionPayloadType: REQUEST
      FunctionArn: !If
        - UsePingAuth
        - !GetAtt EnterprisePingAuthorizerFunction.Arn
        - !Ref AWS::NoValue
      Identity:
        Headers:
          - Authorization
        ReauthorizeEvery: 0
```

**If upstream changes the CognitoAuthorizer config** (e.g. adds scopes, changes UserPoolArn reference):
- Accept their change to the `CognitoAuthorizer:` block
- Keep our `PingAuthorizer:` block and the `DefaultAuthorizer: !If` wrapper intact

**If upstream renames `CognitoAuthorizer`:**
- Update our `!If` to reference the new name

### 4. PostJob / GetJob method auth (careful)

Our version wraps the per-method authorizer in `!If`:
```yaml
Auth:
  Authorizer: !If
    - UsePingAuth
    - PingAuthorizer
    - CognitoAuthorizer
  AuthorizationScopes: !If
    - UsePingAuth
    - !Ref AWS::NoValue
    - - idp-api/jobs.write
```

**If upstream changes the scopes** (e.g. `idp-api/jobs.write` → something else):
- Update the scope in the `!If` false branch (the Cognito path) to match their new value

**If upstream adds new API methods:**
- Add the same `!If` pattern to the new method's `Auth:` block

### 5. ShouldEnablePostProcessingLambdaHook condition (careful)

Our version:
```yaml
ShouldEnablePostProcessingLambdaHook:
  !Or
    - !Not [ !Equals [ !Ref PostProcessingLambdaHookFunctionArn, "" ] ]
    - !Equals [ !Ref EnableCompletionHook, 'true' ]
```

Upstream's original:
```yaml
ShouldEnablePostProcessingLambdaHook:
  !Not [ !Equals [ !Ref PostProcessingLambdaHookFunctionArn, "" ] ]
```

**Resolution:** Always keep the `!Or` wrapper. If upstream changes how this condition works, wrap their new logic inside our `!Or` as the first branch.

### 6. Decompressor CUSTOM_POST_PROCESSOR_ARN (careful)

Our version:
```yaml
CUSTOM_POST_PROCESSOR_ARN: !If
  - DeployCompletionHook
  - !GetAtt EnterpriseCompletionHookFunction.Arn
  - !Ref PostProcessingLambdaHookFunctionArn
```

**Resolution:** If upstream changes how `CUSTOM_POST_PROCESSOR_ARN` is set, put their new value in the `!If` false branch (the non-enterprise path).

### 7. Enterprise Resources block (no conflict)

Our resources sit in their own section:
```yaml
##########################################################################
# Enterprise Integration — Ping Authorizer + Completion Hook
##########################################################################
```

This block is entirely ours. Upstream won't touch it. If a conflict appears here, something went wrong — investigate before resolving.

---

## Sync workflow

```bash
# Fetch upstream
git fetch upstream main

# Merge (conflicts likely only in template.yaml)
git merge upstream/main

# If conflicts:
# 1. Open template.yaml
# 2. For each conflict, apply the rules above
# 3. Verify the enterprise markers are intact:
grep -n "Enterprise Integration" template.yaml
grep -n "UsePingAuth\|DeployCompletionHook" template.yaml

# Validate YAML syntax
python -c "
import yaml
yaml.SafeLoader.add_multi_constructor('!', lambda l,s,n: None)
yaml.safe_load(open('template.yaml'))
print('YAML valid')
"

# Test (if you have the env set up)
./enterprise-addon/build.sh
sam build --template-file template.yaml
```

---

## Quick checklist after resolving conflicts

- [ ] Enterprise parameters block is intact (between the markers)
- [ ] `UsePingAuth` and `DeployCompletionHook` conditions exist
- [ ] `ShouldEnablePostProcessingLambdaHook` still has our `!Or` wrapper
- [ ] API Gateway `DefaultAuthorizer` is `!If [UsePingAuth, PingAuthorizer, CognitoAuthorizer]`
- [ ] `PingAuthorizer` block exists under `Authorizers:`
- [ ] PostJob and GetJob events have `!If` on `Authorizer:` and `AuthorizationScopes:`
- [ ] Decompressor `CUSTOM_POST_PROCESSOR_ARN` has `!If [DeployCompletionHook, ...]`
- [ ] Enterprise Resources section exists (4 resources: 2 layers + 2 functions)
- [ ] YAML parses without errors
