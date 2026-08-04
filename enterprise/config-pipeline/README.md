# Document Configuration Pipeline

Promotes IDP document processing configurations (extraction rules, classification
schemas) into a deployed IDP stack. Separate from the deployment pipeline because
configs change far more often than infrastructure, need different approvers, and
take seconds rather than 20+ minutes.

## The two-repo flow

Configs are authored and tested in dev, then promoted through a config repo that
is separate from this code repo:

```
1. Author + test a config in the dev stack's Web UI
2. Export it:  idp-cli config-download --format full ...
3. Commit to the CONFIG repo (not this one)
4. That repo's CI zips the configs -> uploads configs/config.zip to S3
5. This pipeline triggers, waits for approval, and uploads to the target stack
```

## Naming: two similarly-named files

| File | What it is |
|------|-----------|
| `cfn/config-pipeline.yml` | The CloudFormation template. **This is the pipeline.** |
| `configs-manifest.yaml` | An optional data file *inside the config zip* listing which versions to upload. Authored by whoever drops the configs. |

## Pipeline shape

Two source actions, one pipeline. Both zips live in the same bucket — normally the
existing SDLC source bucket, which already has the versioning and EventBridge
notifications an S3 source action needs.

| Source | S3 key | Role |
|--------|--------|------|
| `ConfigSource` | `configs/config.zip` | The configs to promote. **The trigger.** |
| `CodeSource` | `deploy/code.zip` | Supplies `idp-cli`. **Not** a trigger. |

Only the config zip starts an execution, so publishing code does not silently
promote configs. `CodeSource` exists because `idp-cli` depends on `idp-sdk`,
which is not published to PyPI and must be installed from the repo.

Stages: **Source** → **Approve** (when `RequireApproval=true`) → **UploadConfigs**.

## Deploy the pipeline

```bash
aws cloudformation deploy \
  --stack-name idp-config-pipeline \
  --template-file enterprise/config-pipeline/cfn/config-pipeline.yml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    SourceBucketName=genaiic-sdlc-sourcecode-<account>-<region> \
    IdpStackName=<your-idp-stack-name> \
    ConfigurationTableKmsKeyArn=<stack CustomerManagedEncryptionKey ARN>
```

`ConfigurationTableKmsKeyArn` is **required in practice**: the stack's
`ConfigurationTable` is encrypted with a customer-managed key, and without a
grant on it every DynamoDB read and write is denied. Find it with:

```bash
aws cloudformation describe-stack-resources \
  --stack-name <idp-stack> \
  --logical-resource-id CustomerManagedEncryptionKey
```

For the air-gapped environment, also pass `VpcId`, `PrivateSubnetIds`,
`CodeBuildSecurityGroupIds`, `PipConfigSecretArn`, `CACertBundleS3Uri`, and
`PermissionsBoundaryArn` — the same values the SDLC pipeline uses. Without the
permissions boundary, role creation is refused where an org boundary is mandated.

| Parameter | Default | Notes |
|-----------|---------|-------|
| `IdpStackName` | — | Target stack. The **only** place the target is set. |
| `RequireApproval` | `true` | Manual approval before configs are written. |
| `ApprovalNotificationEmail` | `''` | Notified when an approval is pending. |
| `ConfigSourceKey` | `configs/config.zip` | Updating this key triggers a run. |
| `CodeSourceKey` | `deploy/code.zip` | Supplies `idp-cli`. |
| `ConfigManifestName` | `configs-manifest.yaml` | Optional manifest in the zip. |

> The source bucket **must** have versioning enabled or the S3 source action
> never triggers. The SDLC source bucket already does.

## Trigger a promotion

Normally the config repo's CI does this. Manually:

```bash
cd <config-repo>/configs/
zip ../config.zip *.yaml            # files at the ZIP ROOT, no configs/ prefix
aws s3 cp ../config.zip s3://<source-bucket>/configs/config.zip
```

To re-run without changing configs, use **Release change** in the CodePipeline
console.

## Optional manifest

Include `configs-manifest.yaml` at the root of the zip to upload only some
configs:

```yaml
config_versions:      # bare version names; .yaml/.yml both resolve
  - lending-v2
  - claims-v1
```

Omit the file and every `*.yaml`/`*.yml` in the zip is uploaded. A version listed
here with no matching file is a **failure**, not a skip.

`stack_name` is **not** supported. It is ignored with a warning: a file travelling
inside the artifact must not be able to retarget which stack gets written, or a
dev config drop could be pointed at production.

## Every config uploads on every run

There is no change detection, deliberately. The config repo is the source of
truth, and a config can also be edited in the Web UI between runs, so a
zip-to-zip diff would silently skip a version that had drifted — the exact
drift a promotion pipeline exists to prevent.

Re-uploading an unchanged config is safe: `ConfigurationManager.save_configuration`
preserves `IsActive` and `CreatedAt`, so re-uploading a non-active version does
not activate it. Only `UpdatedAt` changes.

## `--format full` gives the target an exact copy

Export with `--format full` (the default) and the uploaded version becomes
byte-identical to what you tested in dev, deletions included:

```bash
idp-cli config-download \
  --stack-name <dev-stack> \
  --config-version <version> \
  --format full \
  --output configs/<version>.yaml
```

This is not a code-style merge — there is no three-way merge and no keeping both
sides. `config-upload` applies the YAML as a recursive `dict.update()`: every key
present in your file **overwrites** what the target had. `--format full` emits
every key, so every key is overwritten.

Deleting things in dev therefore propagates. `classes` and `policy_classes` are
lists, and lists are replaced wholesale rather than merged element-by-element, so
removing a class *or an attribute inside a class* takes effect in the target.

The one way stale data survives is a key that is **absent** from the upload —
nothing tells the target to change it, so it keeps its old value. That is what
`--format minimal` causes: it strips every key matching a default, so if dev is
at the default and the target carries an override, the target keeps its override.
Same for a hand-trimmed file. Use `full`, not `minimal`.

Two smaller caveats:

- A `null` means "restore this field to its default", not "set to null". With
  `--format full` this is a no-op for the four fields that default to null
  (`test_set`, `notes`, `pricing`, `summary`).
- Identical **per version**, not a mirror of dev. The pipeline only ever writes;
  it never deletes. A version in the target that the zip does not mention is left
  in place, and `IsActive` is preserved, so uploading does not change which
  version is active.

## Troubleshooting

| Symptom | Cause |
|---------|-------|
| Pipeline never starts | Source bucket versioning disabled, or EventBridge notifications off |
| `AccessDeniedException` on DynamoDB/KMS | `ConfigurationTableKmsKeyArn` not passed |
| `ConfigurationTable not found in stack` | Wrong `IdpStackName`, or missing `cloudformation:ListStackResources` |
| `FATAL: idp-cli not on PATH` | `deploy/code.zip` missing or stale in the bucket |
| Target keeps an old value | Config exported with `--format minimal`, which omits keys at their default; re-export with `full` |
| Role creation refused | `PermissionsBoundaryArn` not passed |
