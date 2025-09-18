# Pull Request: Add Conditional S3 Vectors KMS Policy and Fix Permission Issues

## 🎯 Summary

This PR implements conditional KMS policy support for S3 Vectors integration with Bedrock Knowledge Base, ensuring the "Allow S3 Vectors indexing service to use the key" policy is only applied when users select `S3_VECTORS` for their `KnowledgeBaseVectorStore`, following security best practices and the principle of least privilege.

## 🔧 Changes Made

### 1. Conditional KMS Policy Implementation
- **File**: `template.yaml`
- **Change**: Modified the `CustomerManagedEncryptionKey` policy to conditionally include S3 Vectors indexing service permissions
- **Condition**: Uses existing `IsS3VectorsVectorStore` condition to check if `KnowledgeBaseVectorStore = "S3_VECTORS"`
- **Security Benefit**: Only grants KMS permissions to S3 Vectors service when actually needed

### 2. S3 Vectors IAM Permission Fixes  
- **File**: `options/bedrockkb/template.yaml`
- **Issue**: `KnowledgeBaseServiceRole` was missing proper resource access patterns for S3 Vectors operations
- **Fix**: Updated IAM policy to include both bucket and bucket contents access:
  - `arn:${AWS::Partition}:s3vectors:${AWS::Region}:${AWS::AccountId}:bucket/${BucketName}`
  - `arn:${AWS::Partition}:s3vectors:${AWS::Region}:${AWS::AccountId}:bucket/${BucketName}/*`

### 3. Bucket Name Normalization Fix
- **Issue**: IAM policy was using raw `${AWS::StackName}-s3-vectors` instead of AWS-normalized bucket name
- **Root Cause**: AWS S3 Vectors service normalizes bucket names (lowercase, special character handling)
- **Fix**: Use actual sanitized bucket name from custom resource: `!GetAtt S3VectorBucketAndIndex.BucketName`

## 🚀 Benefits

- **Security**: Implements least privilege access - S3 Vectors service only gets KMS permissions when selected
- **Reliability**: Eliminates `s3vectors:QueryVectors` and `kms:Decrypt` permission errors
- **Cost Optimization**: Enables users to leverage S3 Vectors for 40-60% lower storage costs vs OpenSearch Serverless
- **Backward Compatibility**: No impact on existing deployments using OpenSearch Serverless

## 🔍 Technical Details

### Before vs After

**Before**: S3 Vectors indexing service always had KMS permissions regardless of vector store selection
```yaml
- Sid: Allow S3 Vectors indexing service to use the key
  Effect: Allow
  Principal:
    Service: !Sub "indexing.s3vectors.${AWS::URLSuffix}"
  # ... always present
```

**After**: Conditional policy based on user selection
```yaml
- !If
  - IsS3VectorsVectorStore
  - Sid: Allow S3 Vectors indexing service to use the key
    Effect: Allow
    Principal:
      Service: !Sub "indexing.s3vectors.${AWS::URLSuffix}"
    # ... only when S3_VECTORS selected
  - !Ref AWS::NoValue
```

### Error Resolution

**Original Error**:
```
User: arn:aws:sts::912625584728:assumed-role/.../... is not authorized to perform: s3vectors:QueryVectors on resource: arn:aws:s3vectors:us-west-2:912625584728:bucket/idp-s3vectors-documentbedrockkb-da107qbjvad6-s3-vectors/index/bedrock-kb-index
```

**Resolution**: Fixed resource ARN patterns and bucket name references to match AWS service expectations.

## 🧪 Testing

- [x] Verified conditional KMS policy only applies when `KnowledgeBaseVectorStore = "S3_VECTORS"`
- [x] Confirmed S3 Vectors Knowledge Base creation succeeds
- [x] Validated data ingestion jobs complete successfully
- [x] Tested backward compatibility with OpenSearch Serverless deployments

## 📚 Documentation

- **Updated**: `CHANGELOG.md` with concise feature summary
- **Reference**: `docs/s3-vectors-knowledge-base.md` for complete S3 Vectors documentation
- **Architecture**: Maintains unified Knowledge Base interface across both vector store types

## 🔄 Deployment Impact

- **Zero Breaking Changes**: Existing stacks continue to function normally
- **Parameter Compatibility**: All existing parameters preserved
- **Default Behavior**: OpenSearch Serverless remains the default (no behavior change)
- **Migration Path**: Users can opt-in to S3 Vectors for new deployments

## 🎉 Related Work

This PR completes the S3 Vectors integration story by:
1. ✅ Adding S3 Vectors as vector store option (previous work)
2. ✅ Implementing custom resources for S3 vector management (previous work) 
3. ✅ **NEW**: Conditional security policies for proper access control
4. ✅ **NEW**: Resolving all permission and normalization issues

## 📋 Checklist

- [x] Code follows project standards and conventions
- [x] Security policies implement least privilege access
- [x] All IAM permissions properly scoped and conditional
- [x] Backward compatibility maintained
- [x] Documentation updated (CHANGELOG.md)
- [x] No breaking changes introduced
- [x] Error scenarios tested and resolved

---

This enhancement enables cost-optimized vector storage for Bedrock Knowledge Base while maintaining security best practices through conditional access control policies.
