# Secure All-Patterns Deployer Role for GenAI IDP Accelerator

This directory contains the `all-patterns-deployer-role-secure.yaml` CloudFormation template that creates a secure IAM role for deploying, managing and modifying all GenAI IDP Accelerator patterns deployments.

## What This Role Does

The **AllPatternsDeployerRole** provides comprehensive permissions to deploy, update, and manage GenAI IDP Accelerator CloudFormation stacks across all patterns (Pattern 1: BDA, Pattern 2: Textract+Bedrock, Pattern 3: Textract+UDOP+Bedrock).

### Key Capabilities
- **Full CloudFormation Management**: Create, update, delete IDP stacks
- **All Pattern Support**: Works with Pattern 1 (BDA), Pattern 2 (Textract+Bedrock), and Pattern 3 (UDOP)
- **Comprehensive AWS Service Access**: All services required by IDP Accelerator


## Security Features

### Region Restrictions
- **Deployment Regions**: Limited to `us-east-1` and `us-west-2` only
- **Cross-Region Prevention**: Denies all actions outside approved regions
- **Same-Region Assumption**: Role can only be assumed in the region where it's deployed

### Session Management
- **Session Duration**: Maximum 1 hour (3600 seconds)
- **Forced Re-authentication**: Requires frequent credential refresh

### Access Control
- **Account-Scoped**: Only IAM entities within the same AWS account can assume the role
- **Permission-Based**: roles/users need individual `sts:AssumeRole` permissions
- **CloudFormation Service**: AWS CloudFormation service can also assume the role

## Files in this Directory

- `all-patterns-deployer-role-secure.yaml` - CloudFormation template for the secure IAM role
- `README.md` - This documentation file
- `testing-guide.md` - Testing procedures and validation steps

## Parameters

- **MasterStackName**: Name of the master GenAI IDP stack (used in role naming)
- Must follow CloudFormation stack naming pattern: `^[a-zA-Z][a-zA-Z0-9-]*$`

## Quick Start

1. **Deploy the IAM Role** *(Administrator Required)*:
   ```bash
   aws cloudformation deploy \
     --template-file all-patterns-deployer-role-secure.yaml \
     --stack-name idp-deployer-role \
     --parameter-overrides MasterStackName=my-idp-project \
     --capabilities CAPABILITY_NAMED_IAM
   ```

2. **Grant Assumption Permissions** (to your user/role) *(Administrator Required)* :
   ```bash
   # Add this policy to your user/role
   {
     "Effect": "Allow",
     "Action": "sts:AssumeRole",
     "Resource": "arn:aws:iam::ACCOUNT:role/my-idp-project-AllPatterns-Deployer-Secure"
   }
   ```

3. **Assume the Role**:
   ```bash
   aws sts assume-role \
     --role-arn arn:aws:iam::123456789012:role/my-idp-project-AllPatterns-Deployer-Secure \
     --role-session-name idp-deployment
   ```

4. **Deploy IDP Accelerator**:
   ```bash
   # Export the assumed role credentials first, then:
   aws cloudformation deploy \
     --template-file ../../template.yaml \
     --stack-name my-idp-stack \
     --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM
   ```

## AWS Service Permissions

The role provides comprehensive access to AWS services required by all IDP patterns:

### Core Infrastructure Services
- **CloudFormation**: `cloudformation:*` - Full stack management
- **IAM**: Complete role and policy management for IDP components
- **Lambda**: `lambda:*` - Function creation and management
- **Step Functions**: `states:*` - State machine orchestration
- **S3**: `s3:*` - Bucket and object management
- **DynamoDB**: `dynamodb:*` - Table and data management
- **SQS**: `sqs:*` - Queue management
- **EventBridge**: `events:*` - Event rule configuration
- **KMS**: `kms:*` - Encryption key management
- **CloudWatch**: `logs:*`, `cloudwatch:*` - Monitoring and logging

### AI/ML Services
- **Amazon Bedrock**: `bedrock:*` - All foundation models and features
- **Amazon Textract**: `textract:*` - Document OCR capabilities
- **Amazon SageMaker**: `sagemaker:*` - Model endpoint management
- **AWS Glue**: `glue:*` - Data catalog and ETL
- **OpenSearch Serverless**: `aoss:*` - Vector search capabilities

### Web & API Services
- **Amazon Cognito**: `cognito-idp:*`, `cognito-identity:*` - Authentication
- **AWS AppSync**: `appsync:*` - GraphQL API management
- **CloudFront**: `cloudfront:*` - Content delivery
- **AWS WAF**: `wafv2:*` - Web application firewall
- **SNS**: `sns:*` - Notification services
- **Systems Manager**: `ssm:*` - Parameter management
- **CodeBuild**: `codebuild:*` - Build automation

### Network & Compute
- **EC2**: Limited VPC, subnet, and security group management
- **Application Auto Scaling**: `application-autoscaling:*`
- **EventBridge Scheduler**: `scheduler:*`

### Additional Permissions
- **ReadOnlyAccess**: AWS managed policy for read operations
- **STS**: `sts:AssumeRole` for service integrations

## Security Considerations

### Regional Restrictions
- **Hard Limit**: All actions denied outside `us-east-1` and `us-west-2`
- **Deployment Region**: Role assumption restricted to deployment region
- **Compliance**: Helps meet data residency requirements

### Session Security
- **Short Sessions**: 1-hour maximum reduces credential exposure
- **Account Isolation**: Cannot be assumed cross-account

### Permission Scope
- **Broad Service Access**: Full service permissions for comprehensive IDP deployment
- **No Resource Restrictions**: Allows flexibility but requires careful usage
- **Service Trust**: CloudFormation service can assume role for stack operations
- **Compliance Note**: Organizations may need to refine and make more granular the service action permissions based on their specific security compliance guidelines and least privilege requirements

## Troubleshooting

### Common Issues

1. **Access Denied when Assuming Role**:
   - Verify your user/role has `sts:AssumeRole` permission for this specific role ARN
   - Check you're in the correct AWS region (must match role deployment region)
   - Ensure the role exists and is in the same account

2. **Region Restriction Errors**:
   - All operations must be in `us-east-1` or `us-west-2`
   - Deploy the role in your target deployment region
   - Check AWS CLI region configuration

3. **Session Timeout**:
   - Sessions expire after 1 hour maximum
   - Re-assume the role to get fresh credentials
   - Consider automation for long-running deployments

4. **CloudFormation Deployment Failures**:
   - Ensure you're using `CAPABILITY_IAM` and `CAPABILITY_NAMED_IAM`
   - Check CloudWatch logs for specific service errors

### Getting Help

For additional support:
1. Review the `testing-guide.md` for validation procedures
2. Check the main IDP Accelerator documentation
3. Consult AWS IAM best practices documentation

## Best Practices

1. **Regular Auditing**: Periodically review who has access to assume this role
2. **Least Privilege**: Only grant this role to users who need to manage IDP stacks
3. **Session Management**: Use temporary credentials and limit session duration
4. **Monitoring**: Enable CloudTrail logging for role assumption and usage
5. **Rotation**: Regularly review and update the role permissions as needed
