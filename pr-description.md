## feat: optional enterprise artifact bucket hardening (req #4, #5, #10)

### Summary

Adds three optional flags to `publish.py` and `publish.sh` that allow enterprise customers to harden the artifact S3 bucket without affecting standard deployments.

### Changes

#### `publish.py` + `publish.sh`

| Flag | Requirement | What it does |
|------|-------------|--------------|
| `--kms-key-arn ARN` | #4 — Artifact bucket CMK | Applies SSE-KMS encryption with a customer-managed CMK via `put_bucket_encryption`. `BucketKeyEnabled=True` is set to reduce KMS API costs. |
| `--enterprise-bucket-policy` | #5 — Artifact bucket policy | Applies a bucket policy with two `Deny` statements: `DenyInsecureTransport` (enforces HTTPS) and `DenyExternalAccess` (restricts to same AWS account). |
| `--tags Key1=Value1,...` | #10 — Artifact bucket tags | Applies key/value tags to the artifact bucket via `put_bucket_tagging`. Enterprise standards typically require tags for cost allocation, compliance, and inventory tracking. |

All flags **default to off** — existing deployments including the standard `aws-ml-blog-*` public buckets are completely unaffected.

Also moved `account_id` resolution before `setup_artifacts_bucket()` in `run()` so the enterprise bucket policy has the account ID available.

#### `docs/deployment-private-network.md` (new)

End-to-end runbook for deploying IDP in a private/enterprise network environment. This document will grow as additional private network requirements (private AppSync, SSO, etc.) are implemented. For the ALB hosting feature reference, see `docs/alb-hosting.md`.

#### `scripts/alb-test-vpc.yaml` (new)

CloudFormation template that creates a test VPC with 2 private subnets in different AZs and a self-signed ACM certificate (via Lambda custom resource). Used to simulate a customer private network for ALB hosting tests. Outputs `VpcId`, `SubnetIds`, `CertificateArn`, `PrivateSubnet1Id`, and `PrivateSubnet2Id`.

### Usage

```bash
# Standard deployment — no change
./publish.sh idp-<account-id> idp us-east-1

# Enterprise: enforce SSL + account-only access on artifact bucket
./publish.sh idp-<account-id> idp us-east-1 --enterprise-bucket-policy

# Enterprise: use KMS CMK for artifact bucket encryption
./publish.sh idp-<account-id> idp us-east-1 --kms-key-arn arn:aws:kms:us-east-1:123456789012:key/xxx

# Enterprise: tag the artifact bucket
./publish.sh idp-<account-id> idp us-east-1 --tags CostCenter=IDP,Environment=prod

# Enterprise: all three flags together
./publish.sh idp-<account-id> idp us-east-1 \
  --kms-key-arn arn:aws:kms:us-east-1:123456789012:key/xxx \
  --enterprise-bucket-policy \
  --tags CostCenter=IDP,Environment=prod
```

### Testing

- `--enterprise-bucket-policy` tested end-to-end — bucket policy confirmed on S3 with correct `DenyInsecureTransport` and `DenyExternalAccess` statements ✅
- `--kms-key-arn` tested end-to-end with CMK `alias/IDP-ALB-customer-encryption-key` — bucket encryption confirmed on S3 with `SSEAlgorithm=aws:kms` and `BucketKeyEnabled=true` ✅
- `make fastlint` passes (ruff auto-formatted 1 line)
- 546 unit tests pass

### Checklist

- [x] Code linting passes (`make fastlint`)
- [x] Unit tests pass (546 passed)
- [x] Both new flags default to off (backward compatible)
- [x] New methods documented with docstrings
- [x] `print_usage()` updated in both `publish.py` and `publish.sh`
- [x] End-to-end tested on AWS

### Related

- Customer requirement: `private_network.md` req #4 (Artifact bucket CMK), req #5 (Artifact bucket policy), req #10 (Artifact bucket tags)
- Part of a series of PRs for enterprise private network deployment support
- Next: `feature/private-appsync-api` (req #2)
