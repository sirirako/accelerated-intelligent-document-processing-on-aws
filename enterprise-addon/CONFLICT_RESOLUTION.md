# Enterprise Fork — Upstream Sync Guide

When syncing the enterprise fork with upstream (`develop` / `main`), the goal
is to **incorporate upstream improvements without breaking enterprise
functionality**. This guide helps AI coding assistants and humans safely merge
upstream changes into the `feature/enterprise-integration` branch.

Include this file in your assistant's context when syncing with upstream.

---

## Mental Model

The enterprise branch sits *on top of* upstream. It adds:
- Hook dispatch states injected **between** upstream SFN states
- Feature-toggle parameters and conditional resources in templates
- `postHook` config schema fields alongside existing step schemas
- UI routes, navigation items, and hooks for the feature platform
- The `enterprise-addon/` directory (entirely additive — no conflict risk)

**Upstream doesn't know about the enterprise layer.** When upstream modifies
the same files, it can silently break enterprise wiring without producing a
git conflict. The most dangerous breakage is **non-conflicting** — upstream
renames a state or changes a `Next` target, and git merges cleanly, but the
SFN chain is now broken at runtime.

---

## Risk Map — What Can Upstream Break?

### High Risk: Step Functions Workflow (`workflow.asl.json`)

The enterprise branch inserts 6 hook states between upstream states:

```
OCR → [PostOcrHook] → Classification → [PostClassificationHook] → ProcessSections
  └─ per section: Extraction → [PostExtractionHook] → Assessment → [PostAssessmentHook] → SectionComplete
RuleValidation → [PostRuleValidationHook] → Summarization → [PostSummarizationHook] → Evaluation
```

Each hook state:
- Changes the **preceding** upstream state's `"Next"` to point to the hook
- Sets its own `"Next"` to the **following** upstream state
- Has a `"Catch"` fallback `"Next"` that skips to the following state on error

**What upstream changes break this (even without git conflicts):**

| Upstream action | What breaks | How to detect |
|----------------|-------------|---------------|
| Rename a state (e.g., `ClassificationStep` → `Classify`) | Hook's `"Next"` and `"Catch"` point to nonexistent state | SFN validation fails at deploy |
| Add a new state between two existing ones | New state's `"Next"` skips the hook (goes directly to downstream) | Hook never fires — silent regression |
| Remove a state that a hook targets | Hook's `"Next"` points to nonexistent state | SFN validation fails at deploy |
| Change state output path (e.g., `$.OCRResult.document` → `$.ocr.doc`) | Hook receives wrong payload structure | Hook dispatcher gets unexpected input — may silently no-op |
| Move states inside/outside a Map iterator | Hook state scope mismatch (top-level vs. inside Map) | SFN validation or runtime failure |

**Post-merge verification (REQUIRED):**
1. Trace the full `"Next"` chain from start to end — every state reachable
2. Verify every hook state's `"Catch"` fallback `"Next"` points to a valid state
3. Verify every hook's `Payload` uses the correct JSONPath for the document
4. Check `DefinitionSubstitutions` in `template.yaml` still passes `PipelineHooksDispatcherLambdaArn`

### Medium Risk: Unified Template Config Schema

The enterprise branch adds `postHook` array schema to each processing step
block (OCR, Classification, Extraction, Assessment, RuleValidation,
Summarization) in `patterns/unified/template.yaml`.

**What upstream changes break this:**

| Upstream action | What breaks |
|----------------|-------------|
| Restructure step schema (e.g., nest under a `processing:` parent) | `postHook` ends up at wrong schema path; UI won't render it |
| Rename step keys (e.g., `classification` → `classify`) | Dispatcher's `_HOOK_TO_STEP` mapping won't match; hooks never fire |
| Add validation that rejects unknown fields | `postHook` rejected as invalid config |

**Post-merge verification:**
1. Check that `postHook` still appears under each step block at the correct nesting level
2. Verify step key names in the schema match `_HOOK_TO_STEP` in `pipeline_hooks_function/index.py`
3. Run `make test-config-library` — catches schema validation failures

### Medium Risk: UI Routes and Navigation

The enterprise branch adds:
- A `settingsLoaded` wrapper around all routes in `AuthRoutes.tsx`
- A `/features/*` route
- Dynamic navigation section driven by `useInstalledFeatures` / `useCatalogFeatures`
- `landingPath` logic that overrides the default redirect

**What upstream changes break this:**

| Upstream action | What breaks |
|----------------|-------------|
| Refactor route structure (e.g., add route guards, lazy loading wrapper) | Enterprise `settingsLoaded` wrapper may conflict structurally |
| Change default redirect logic in `AuthRoutes.tsx` | Enterprise `landingPath` override lost |
| Remove or rename `useSettingsContext` | Enterprise's `DefaultFeatureId` lookup fails |
| Change navigation component API | `buildFeaturesNavSection()` returns incompatible shape |

**Post-merge verification:**
1. `make ui-build` — catches type errors and broken imports
2. Check that `/features/*` route still exists in the rendered route tree
3. Check that `settingsLoaded` gate still wraps the route content (if removed, the feature platform landing breaks)

### Low Risk: Config Models, Document Model, Dependencies

| Area | What to watch for |
|------|------------------|
| `config/models.py` | Upstream renames a field that enterprise extends — `make typecheck` catches this |
| `models.py` | Upstream changes `compress()`/`load_document()` signature — verify `config_version` still carried through |
| `pyproject.toml` / `requirements.txt` | Take higher version; verify PyJWT API compatibility for the enterprise layer |

---

## Step-by-Step Sync Process

### 1. Merge upstream into enterprise branch

```bash
git fetch origin
git merge origin/develop  # or origin/main
```

### 2. Resolve any git conflicts

Apply these principles:
- **Keep both sides** for additive changes (parameters, resources, fields)
- **Enterprise params stay grouped** under `# --- Enterprise Integration ---`
- **Never drop enterprise resources** — if unsure, keep and flag
- For SFN conflicts: accept upstream's state structure, then re-apply hook insertions (see below)

### 3. Check for silent breakage (no git conflict but functionally broken)

**This is the critical step most people skip.** Run these checks even when
the merge was clean:

#### SFN Chain Integrity

```bash
# Extract state names and Next targets from the ASL
python3 -c "
import json, sys
with open('patterns/unified/statemachine/workflow.asl.json') as f:
    asl = json.load(f)

def check_states(states, path=''):
    for name, state in states.items():
        nxt = state.get('Next')
        if nxt and nxt not in states:
            # Check parent-level states too for Map/Parallel
            print(f'BROKEN: {path}{name} -> Next: {nxt} (not found)')
        catches = state.get('Catch', [])
        for c in catches:
            if c.get('Next') and c['Next'] not in states:
                print(f'BROKEN: {path}{name} -> Catch Next: {c[\"Next\"]} (not found)')
        # Recurse into Map iterator
        iterator = state.get('Iterator', {}).get('States')
        if iterator:
            check_states(iterator, path=f'{path}{name}/')
        # Parallel branches
        for branch in state.get('Branches', []):
            check_states(branch.get('States', {}), path=f'{path}{name}/')

check_states(asl['States'])
print('SFN chain check complete.')
"
```

If this prints any `BROKEN` lines, fix the `Next` / `Catch` targets before proceeding.

#### Hook Dispatch Wiring

```bash
# Verify all 6 hook states exist and reference the dispatcher
grep -c "PipelineHooksDispatcherLambdaArn" patterns/unified/statemachine/workflow.asl.json
# Expected: 6 (one per hook point)

# Verify hook points match dispatcher's mapping
grep "hookPoint" patterns/unified/statemachine/workflow.asl.json
# Expected: postOcr, postClassification, postExtraction, postAssessment,
#           postRuleValidation, postSummarization
```

#### Config Schema Alignment

```bash
# Verify postHook appears under each step in the template schema
grep -c "postHook" patterns/unified/template.yaml
# Expected: 6 (one per processing step)

# Verify step keys in schema match dispatcher's _HOOK_TO_STEP
grep "HOOK_TO_STEP" patterns/unified/src/pipeline_hooks_function/index.py
```

#### UI Feature Platform

```bash
# Verify feature routes still present
grep "FEATURES_PATH_PREFIX" src/ui/src/routes/AuthRoutes.tsx
grep "FeaturesRoutes" src/ui/src/routes/AuthRoutes.tsx

# Verify navigation hooks still imported
grep "useInstalledFeatures\|useCatalogFeatures\|buildFeaturesNavSection" \
  src/ui/src/components/genaiidp-layout/navigation.tsx
```

### 4. Run the full validation suite

```bash
make lint          # Catches broken YAML, ARN issues, formatting
make typecheck     # Catches broken imports, renamed fields
make test          # Catches dispatcher logic, config model, compression
make ui-build      # Catches broken UI imports and types
```

### 5. Enterprise-specific tests

```bash
# Pipeline hooks dispatcher
pytest lib/idp_common_pkg/tests/unit/lambdas/test_pipeline_hooks_dispatcher.py -v

# Config models (postHook schema)
pytest lib/idp_common_pkg/tests/unit/config/test_config_models.py -v

# Document compression (config_version carry-through)
pytest lib/idp_common_pkg/tests/unit/test_document_compression.py -v
```

---

## Re-Inserting Hook States After SFN Restructure

When upstream significantly changes the SFN and you need to re-apply hooks:

### Hook State Template

Each hook state follows this pattern:

```json
"Post<Step>Hook": {
    "Type": "Task",
    "Resource": "arn:aws:states:::lambda:invoke",
    "Parameters": {
        "FunctionName": "${PipelineHooksDispatcherLambdaArn}",
        "Payload": {
            "hookPoint": "post<step>",
            "executionArn.$": "$$.Execution.Id",
            "document.$": "<path-to-document-in-state-output>"
        }
    },
    "ResultPath": "$.HookResults.post<step>",
    "Retry": [
        {
            "ErrorEquals": ["Lambda.ServiceException", "Lambda.SdkClientException", "Lambda.TooManyRequestsException"],
            "IntervalSeconds": 2,
            "MaxAttempts": 3,
            "BackoffRate": 2
        }
    ],
    "Catch": [
        {
            "ErrorEquals": ["States.ALL"],
            "ResultPath": "$.HookResults.post<step>.error",
            "Next": "<next-upstream-state>"
        }
    ],
    "Next": "<next-upstream-state>"
}
```

### Insertion Points

| Hook state | Insert after | Document path | Falls through to |
|-----------|-------------|---------------|-----------------|
| `PostOcrHook` | OCR step | `$.OCRResult.document` | Classification step |
| `PostClassificationHook` | Classification step | `$.ClassificationResult.document` | ProcessSections (Map) |
| `PostExtractionHook` | Extraction step (inside Map iterator) | `$.document` + `section.$: "$"` | Assessment step |
| `PostAssessmentHook` | Assessment step (inside Map iterator) | `$.document` + `section.$: "$"` | SectionComplete |
| `PostRuleValidationHook` | RuleValidation orchestration step | `$.RuleValidationOrchestrationResult.document` | Summarization step |
| `PostSummarizationHook` | Summarization step | `$` (full state) | Evaluation step |

### Wiring Checklist

For each hook state:
1. Change the **preceding** state's `"Next"` from `<downstream>` to `Post<Step>Hook`
2. Set the hook state's `"Next"` to `<downstream>`
3. Set the hook state's `"Catch"[0]."Next"` to `<downstream>` (fail-open: skip hook on error)
4. Verify `"document.$"` path matches what the preceding state actually outputs

---

## When to Escalate (Don't Auto-Resolve)

Stop and ask a human if:

- Upstream **removed** `PostProcessingLambdaHookFunctionArn` — the completion hook depends on this
- Upstream **restructured the SFN into parallel branches** — hooks assume sequential flow
- Upstream **replaced Cognito with a different auth mechanism** — Ping auth switch logic may conflict
- Upstream **renamed the Configuration DynamoDB table or changed its key schema** — dispatcher breaks
- Upstream **removed or renamed step keys** (`ocr`, `classification`, `extraction`, `assessment`, `rule_validation`, `summarization`) — dispatcher mapping breaks
- After a clean merge, enterprise tests **fail on the dispatcher or config models** with errors you can't trace to a simple rename
- Upstream **changed the EventBridge rule pattern** for Step Functions completion — completion hook may stop firing

---

## AI Assistant Instructions

When syncing this enterprise fork with upstream:

1. **Read this guide first** — understand what enterprise functionality exists
2. **Resolve git conflicts** preserving both sides (enterprise additions are isolated)
3. **Run the silent-breakage checks** (Section 3) — this is where most bugs hide
4. **Pay special attention to the SFN** — run the chain integrity script
5. **Never remove enterprise states, parameters, or conditions** — if upstream makes them seem redundant, verify before removing
6. **Verify document JSONPaths** — if upstream changed a state's output shape, the hook's `"document.$"` path must be updated
7. **Run enterprise tests** even if `make test` passes — the dispatcher test specifically validates hook dispatch behavior

### Prompt Template

```
I just merged upstream develop into feature/enterprise-integration. There
were [no conflicts / conflicts in X, Y, Z]. Please run the silent-breakage
checks from enterprise-addon/CONFLICT_RESOLUTION.md and verify that all
enterprise functionality (hooks, Ping auth, MQ completion) is intact.
```
