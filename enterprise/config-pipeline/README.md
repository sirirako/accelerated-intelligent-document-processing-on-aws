# Document Configuration Pipeline

Lightweight pipeline for promoting IDP document processing configurations
(extraction rules, classification schemas) to a target stack. Separate from the
main deployment pipeline — configs change more often than infrastructure.

## How it works

```
S3 source bucket:
├── configs/config.zip        ← zip of the WHOLE repo (see note below)
└── deploy/config-pipeline.yaml  ← (optional) which versions to upload
```

1. Drop/update `configs/config.zip` in S3
2. Pipeline triggers automatically
3. CodeBuild runs `upload_configs.py` → calls `idp-cli config-upload` for each config
4. Done in seconds (no Docker build, no stack update)

> **Important — what goes into `config.zip`:** the CodeBuild buildspec runs
> `pip install -e lib/idp_cli_pkg` and
> `python3 enterprise/config-pipeline/scripts/upload_configs.py`, and the
> script globs `configs/*.yaml` relative to the artifact root. CodeBuild
> extracts `config.zip` to the build root, so the zip must contain the whole
> repo tree (`lib/idp_cli_pkg/`, `enterprise/config-pipeline/scripts/`, and
> `configs/*.yaml`) — not just the `configs/` directory. See "Trigger the
> pipeline" below.

## Deploy the pipeline

```bash
aws cloudformation deploy \
  --stack-name idp-config-pipeline \
  --template-file enterprise/config-pipeline/cfn/config-pipeline.yml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    SourceBucketName=<your-source-bucket> \
    IdpStackName=<your-idp-stack-name>
```

## Trigger the pipeline

```bash
# Put the config YAMLs you want to promote in configs/, then zip the WHOLE
# repo (the buildspec needs lib/idp_cli_pkg and enterprise/config-pipeline/).
# Run from the repo root:
zip -r config.zip . -x '.git/*' -x '*/node_modules/*'
aws s3 cp config.zip s3://<source-bucket>/configs/config.zip
```

The pipeline triggers automatically on upload.

## Pipeline config (optional)

If `deploy/config-pipeline.yaml` exists in the source bucket (the key is
configurable via the `ConfigPipelineConfigKey` template parameter, default
`deploy/config-pipeline.yaml`), the pipeline reads it to determine which
configs to upload:

```yaml
# deploy/config-pipeline.yaml
stack_name: idp-prod                # override target stack
config_versions:                    # only upload these (skip others)
  - lending-v2
  - claims-v1
```

If the file is missing, all `configs/*.yaml` files are uploaded.

## Exporting configs from the Web UI

To version-control a config that was created/edited in the Web UI:

```bash
idp-cli config-download --stack-name <STACK> --config-version <VERSION> --output configs/<version>.yaml
```

This exports the DynamoDB config to a YAML file you can commit to git.
