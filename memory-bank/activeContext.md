# Active Context

## Current Work Focus

### Pattern Unification: Phase 3 — Cleanup Complete (February 26, 2026)
**Status:** ✅ All cleanup work streams complete. Ready for deploy & test.

#### What Was Done (This Session)

**Work Stream A: GovCloud Script** ✅ (previous session)
- Updated `scripts/generate_govcloud_template.py` with 6 changes for unified pattern

**Work Stream B: Delete Old Pattern Directories** ✅
- Deleted `patterns/pattern-1/` and `patterns/pattern-2/` (source now in `patterns/unified/`)
- Fixed all active code references before deletion:
  - `patterns/unified/buildspec-bda.yml` — paths → `patterns/unified/src/`
  - `patterns/unified/buildspec-pipeline.yml` — paths → `patterns/unified/src/`
  - `publish.py` — removed dead pattern-2 container code, cleaned image-repository list
  - `scripts/sdlc/validate_service_role_permissions.py` — templates list → `patterns/unified/template.yaml`
  - `scripts/sdlc/README_validate_buildspec.md` — example paths updated

**Config Library Cleanup** ✅
- Added missing `healthcare-multisection-package` to `config_library/unified/`
- Deleted `config_library/pattern-1/` and `config_library/pattern-2/`
- Updated all 11 preset `config.yaml` notes (removed "Pattern2 (Bedrock LLM)" references)
- Updated all 11 preset `README.md` files (Pattern Association → Processing Mode)
- Updated few-shot example image paths from `config_library/pattern-2/` → `config_library/unified/`
- Rewrote `config_library/unified/README.md` and `config_library/README.md`

**Rule Validation for Unified Pattern** ✅
- Moved rule validation from pipeline-only to shared workflow (5 state machine pointer changes)
- Added `is_rule_validation_enabled()` to BDA processresults function + `rule_validation_enabled` in all 3 response dicts
- Updated UI to always show Rule Schema tab (`showRuleSchema = !isPattern1`)

**Work Stream C: Docs Updates** ✅
- Added deprecation banners to `docs/pattern-1.md` and `docs/pattern-2.md`
- Updated `docs/architecture.md` — new Unified Pattern Architecture section replacing old pattern sections
- Updated `docs/deployment.md` — unified processing mode description replacing pattern selector
- Updated `docs/configuration.md` — parameter updates, processing mode description
- Updated `docs/README.md` — updated diagram references

**Work Stream D: BDA Presets** ✅ — Decided no action needed. All configs stay as pipeline mode; users toggle `use_bda` in UI.

#### Architecture Summary (Unified)
```
Main template (template.yaml)
  └── PATTERNSTACK (patterns/unified/)
        ├── 1 ECR Repository (all 12 images)
        ├── 1 CodeBuild Project (sequential build via buildspec.yml)
        ├── 1 ImageVersion (content-based hash)
        ├── 1 SourceZipfile (unified-source-{hash}.zip)
        ├── Unified State Machine (routes via use_bda flag)
        │     ├── BDA branch: InvokeBDA → BDAProcessResults → shared tail
        │     └── Pipeline branch: OCR → Classification → Extraction → Assessment → ProcessResults → shared tail
        │     └── Shared tail: HITL check → Rule Validation → Summarization → Evaluation
        ├── 12 Lambda Functions:
        │     BDA: InvokeBDAFunction, BDAProcessResultsFunction, BDACompletionFunction
        │     Pipeline: OCRFunction, ClassificationFunction, ExtractionFunction,
        │               AssessmentFunction, ProcessResultsFunction, RuleValidationFunction,
        │               RuleValidationOrchestrationFunction
        │     Shared: SummarizationFunction, EvaluationFunction
        └── Supporting: BDAMetadataTable, BDAEventRule, CloudWatch Dashboard
```

### Remaining Work

#### 🔴 High Priority
1. **Deploy & Test** — `python publish.py <bucket> <prefix> <region> --clean-build` → deploy as new stack
2. **Fix any deploy issues** — Watch for template validation errors, CodeBuild failures, etc.

#### 🟡 Medium Priority
3. **Validate Makefile/CI** — `make validate-buildspec` checks `patterns/*/buildspec.yml`
4. **CI/CD pipeline** — `.gitlab-ci.yml` may reference old pattern paths (check needed)

#### 🟢 Low Priority (Incremental)
5. **Update remaining 25+ docs** — Other doc files still mention Pattern-1/2 in contextual ways; can be updated incrementally
6. **CLAUDE.md** — Still references old pattern paths in some examples

---

### Configuration Storage: Full Configs Per Version (February 14, 2026)
**Status:** ✅ Completed

Each config version stores a complete, self-contained configuration snapshot (no more sparse deltas).

---

## Important Patterns and Preferences

### Template Outputs Interface (Unified Pattern)
Same outputs as before — no breaking changes:
- `StateMachineName`, `StateMachineArn`, `StateMachineLogGroup`
- `PatternLogGroups` (all 12 function log groups + state machine)
- `DashboardName`, `DashboardArn`

### Config Library Structure
```
config_library/
├── unified/          # 11 presets, all use_bda: false by default
│   ├── bank-statement-sample/
│   ├── docsplit/
│   ├── healthcare-multisection-package/
│   ├── lending-package-sample/
│   ├── lending-package-sample-govcloud/
│   ├── ocr-benchmark/
│   ├── realkie-fcc-verified/
│   ├── rule-extraction/
│   ├── rule-validation/
│   ├── rvl-cdip/
│   └── rvl-cdip-with-few-shot-examples/
├── pricing.yaml
├── README.md
└── TEMPLATE_README.md
```
