# Document Configuration Pipeline

Lightweight pipeline for promoting IDP document processing configurations
(extraction rules, classification schemas) to a target stack. Separate from the
main deployment pipeline — configs change more often than infrastructure.

## How it works

```
S3 source bucket:
├── configs/
│   ├── lending-v1.yaml      ← config versions (extraction rules, schemas)
│   ├── lending-v2.yaml
│   └── claims-v1.yaml
└── deploy/
    └── config-pipeline.yaml  ← (optional) which versions to upload
```

1. Drop/update `configs/config.zip` in S3 (zip of the configs/ directory)
2. Pipeline triggers automatically
3. CodeBuild runs `upload_configs.py` → calls `idp-cli config-upload` for each config
4. Done in seconds (no Docker build, no stack update)

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
# Zip your configs and upload
cd configs/
zip ../config.zip *.yaml
aws s3 cp ../config.zip s3://<source-bucket>/configs/config.zip
```

The pipeline triggers automatically on upload.

## Pipeline config (optional)

If `deploy/config-pipeline.yaml` exists in the source bucket, the pipeline
reads it to determine which configs to upload:

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
