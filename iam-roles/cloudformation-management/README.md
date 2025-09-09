# CloudFormation Service Role for GenAI IDP Accelerator

This directory contains the `all-patterns-deployer-role-secure.yaml` CloudFormation template that creates a dedicated IAM service role for CloudFormation to deploy, manage and modify all GenAI IDP Accelerator patterns deployments.

## What This Role Does

The **AllPatternsDeployerRole** is a CloudFormation service role that provides the necessary permissions for AWS CloudFormation to deploy, update, and manage GenAI IDP Accelerator stacks across all patterns (Pattern 1: BDA, Pattern 2: Textract+Bedrock, Pattern 3: Textract+UDOP+Bedrock). This role can only be assumed by the CloudFormation service, not by users directly.

### Key Capabilities
- **Full CloudFormation Management**: Create, update, delete IDP stacks - This IAM role (which CloudFormation assumes) gives necessary privileges to create/update/delete the stack which is helpful in development and sandbox environments. In production environments, admins can further limit these permissions to their discretion (e.g. disabling stack deletion).
- **All Pattern Support**: Works with Pattern 1 (BDA), Pattern 2 (Textract+Bedrock), and Pattern 3 (UDOP)
- **Comprehensive AWS Service Access**: All services required by IDP Accelerator


## Security Features

### Region Restrictions
- **Same-Region Operations**: Only allows the role to be assumed in the region where the master/existing deployment stack already exists
- **Cross-Region Prevention**: Denies all actions outside the deployment region
- **Regional Isolation**: Ensures all operations remain within the same region as the existing IDP infrastructure

### Session Management
- **Session Duration**: Maximum 1 hour (3600 seconds)
- **Forced Re-authentication**: Requires frequent credential refresh
- **Administrator Note**: Administrators must add an inline IAM policy to users wanting to deploy CloudFormation stacks with this service role, allowing them to pass the `IDP-AllPatterns-Deployer-Secure` role to the CloudFormation principal:

  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Action": "iam:PassRole",
        "Resource": "arn:aws:iam::*:role/IDP-AllPatterns-Deployer-Secure"
      }
    ]
  }
  ```

### Access Control
- **Account-Scoped**: Only IAM entities within the same AWS account can assume the role


## Files in this Directory

- `all-patterns-deployer-role-secure.yaml` - CloudFormation template for the secure IAM role
- `README.md` - This documentation file
- `testing-guide.md` - Testing procedures and validation steps

## Parameters

- **ExistingIDPStackName**: Name of an existing IDP stack (must start with IDP or idp). It is assumed that the administrator has deployed the first IDP solution deployment.
- Must follow CloudFormation stack naming pattern: `^[Ii][Dd][Pp][a-zA-Z0-9-]*$`

## Quick Start

1. **Deploy the IAM Role** *(Administrator Required)*:
   ```bash
   aws cloudformation deploy \
     --template-file all-patterns-deployer-role-secure.yaml \ # (Note: Ensure the template file is in your current directory or provide the full path to your template file location)
     --stack-name idp-deployer-role \
     --parameter-overrides ExistingIDPStackName=my-existing-idp-stack \ (the name of your existing IDP stack)
     --capabilities CAPABILITY_NAMED_IAM
   ```

2. **Deploy IDP Accelerator**:
   ```bash
   aws cloudformation deploy \
     --template-file ../../template.yaml \ (path to your template.yaml file)
     --stack-name my-idp-stack \ (Name of your stack, starting with prefix IDP or idp)
     --role-arn arn:aws:iam::123456789012:role/All-Patterns-Deployer-Role-Secure \ (The ARN of the idp-deployer-role provided in the Output tab of the deployed role stack)
     --region us-east-1 \ (your selected region)
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

1. **Access Denied when Using Role**:
   - Verify your user/role has `iam:PassRole` permission for this specific role ARN
   - Check you're in the correct AWS region (must match role deployment region)
   - Ensure the role exists and is in the same account
   - Remember: Users cannot assume this role directly - only CloudFormation service can

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



## Best Practices

1. **Regular Auditing**: Periodically review who has access to assume this role
2. **Least Privilege**: Only grant this role to users who need to manage IDP stacks
3. **Session Management**: Use temporary credentials and limit session duration
4. **Monitoring**: Enable CloudTrail logging for role assumption and usage
5. **Rotation**: Regularly review and update the role permissions as needed
