# Active Context

## Current Focus
Scripts directory cleanup and idp-cli enhancement completed.

## Recent Changes (January 2026)

### Scripts Directory Reorganization
1. **Created `scripts/setup/` subdirectory** - Moved all development environment setup scripts:
   - `mac_setup.sh`
   - `dev_setup_ubuntu.sh`
   - `dev_setup_al2023.sh`
   - `wsl_setup.sh`
   - Added `README.md` documenting each script

2. **Removed obsolete scripts**:
   - `add_lambda_layers.py` - One-time migration script, already executed
   - `test_layer_build.py` - Build testing no longer needed
   - `test_pip_extras.py` - Pip extras testing completed

3. **Created `scripts/README.md`** - Comprehensive documentation of all scripts and their purposes

4. **Moved `dynamic_schedule.csv`** to `idp_cli/examples/load-test-schedule.csv`

### New IDP CLI Commands
Added three new operational commands to the CLI:

1. **`idp-cli stop-workflows`** - Stop running workflows
   - Purges SQS queue
   - Stops Step Function executions
   - Options: `--skip-purge`, `--skip-stop`

2. **`idp-cli load-test`** - Load testing utility
   - Copies files to input bucket at specified rates
   - Supports constant rate or scheduled rates
   - Options: `--rate`, `--duration`, `--schedule`

3. **`idp-cli cleanup-orphaned`** - Clean up orphaned resources
   - Delegates to existing `cleanup_orphaned_resources.py`
   - Options: `--dry-run`, `--profile`

### Documentation Updates
- Updated `docs/idp-cli.md` with new commands documentation
- Updated `scripts/README.md` with complete directory documentation
- Added `scripts/setup/README.md` for setup scripts

## Current Scripts Directory Structure
```
scripts/
├── setup/                     # Dev environment setup
│   ├── README.md
│   ├── dev_setup_al2023.sh
│   ├── dev_setup_ubuntu.sh
│   ├── mac_setup.sh
│   └── wsl_setup.sh
├── benchmark_utils/           # Benchmark utilities
├── dsr/                       # DSR security scanning
├── sdlc/                      # SDLC CI/CD templates
├── README.md                  # Main documentation
├── build_rvl_cdip_nmp_testset.py
├── cleanup_orphaned_resources.py  # Used by CLI
├── codebuild_deployment.py
├── compare_json_files.py
├── generate_govcloud_template.py
├── integration_test_deployment.py
├── lookup_file_status.sh      # Legacy (use idp-cli status)
├── simulate_load.py           # Legacy (use idp-cli load-test)
├── simulate_dynamic_load.py   # Legacy (use idp-cli load-test)
├── stop_workflows.sh          # Legacy (use idp-cli stop-workflows)
├── typecheck_pr_changes.py
├── validate_buildspec.py
├── README_validate_buildspec.md
└── validate_service_role_permissions.py
```

## Next Steps
- Consider fully porting `cleanup_orphaned_resources.py` logic to CLI module
- Remove legacy shell scripts once CLI commands are validated in production
- Update setup documentation to reference new `scripts/setup/` location

## Important Patterns
- CLI commands delegate to existing scripts where complex logic already exists
- New CLI modules follow existing patterns (StackInfo, BatchProcessor)
- Rich console output for user-friendly CLI experience

## Decisions Made
- Keep legacy scripts temporarily as CLI wrappers (gradual migration)
- Setup scripts grouped together for discoverability
- Load test schedule moved to CLI examples for easy access