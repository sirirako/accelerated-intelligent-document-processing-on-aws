# Testing Guide for Secure All-Patterns Deployer Role

This guide provides testing procedures to validate the `all-patterns-deployer-role-secure.yaml` IAM role for GenAI IDP Accelerator management.

## Table of Contents

- [Administrator Prerequisites](#administrator-prerequisites)
- [Test Scenario: Pattern Migration](#test-scenario-pattern-migration)
- [Validation Checklist](#validation-checklist)
- [Troubleshooting](#troubleshooting)

## Administrator Prerequisites

**IMPORTANT**: The following steps require AWS Administrator privileges:

### 1. Deploy the Deployer Role (Administrator Required)

```bash
# Must be run by an AWS Administrator
aws cloudformation deploy \
  --template-file all-patterns-deployer-role-secure.yaml \
  --stack-name idp-deployer-role \
  --parameter-overrides MasterStackName=test-idp-project \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

### 2. Initial IDP Stack Deployment (Administrator Required)

```bash
# Must be run by an AWS Administrator
# NOTE: Update ../../template.yaml with the actual path to your IDP template.yaml file
# NOTE: The stack name 'test-idp-migration' is just an example - use your preferred name
aws cloudformation deploy \
  --template-file ../../template.yaml \
  --stack-name test-idp-migration \
  --parameter-overrides \
    AdminEmail="test@example.com" \
    IDPPattern="Pattern2 - Packet processing with Textract and Bedrock" \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --region us-east-1
```

### 3. Grant Role Assumption Permissions (Administrator Required)

```bash
# Administrator must attach this policy to the test user/role
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::ACCOUNT:role/test-idp-project-AllPatterns-Deployer-Secure"
    }
  ]
}
```

### Environment Setup
# NOTE: The role ARN can be found in the CloudFormation stack outputs under 'AllPatternsDeployerRoleArn'


```bash
export TEST_ACCOUNT_ID="123456789012"
export TEST_REGION="us-east-1"
export DEPLOYER_ROLE_ARN="arn:aws:iam::${TEST_ACCOUNT_ID}:role/test-idp-project-AllPatterns-Deployer-Secure"
export TEST_STACK_NAME="test-idp-migration"
```

## Test Scenario: Pattern Migration

**Objective**: Test the deployer role's ability to migrate an existing IDP stack from Pattern 2 (Textract+Bedrock) to Pattern 1 (BDA).

**Prerequisites**: Administrator must complete the setup steps above.

### Step 1: Verify Initial Stack (Pattern 2)

```bash
# Verify the initial Pattern 2 stack exists
aws cloudformation describe-stacks --stack-name test-idp-migration --query 'Stacks[0].Parameters[?ParameterKey==`IDPPattern`].ParameterValue' --output text

# Should return: "Pattern2 - Packet processing with Textract and Bedrock"
```

### Step 2: Assume the Deployer Role

```bash
# Assume the deployer role (non-administrator user can do this)
# NOTE: The role ARN can be found in the CloudFormation stack outputs under 'AllPatternsDeployerRoleArn'

ASSUME_ROLE_OUTPUT=$(aws sts assume-role \
  --role-arn "$DEPLOYER_ROLE_ARN" \ 
  --role-session-name "pattern-migration-test")

# Export the assumed role credentials
export AWS_ACCESS_KEY_ID=$(echo $ASSUME_ROLE_OUTPUT | jq -r '.Credentials.AccessKeyId')
export AWS_SECRET_ACCESS_KEY=$(echo $ASSUME_ROLE_OUTPUT | jq -r '.Credentials.SecretAccessKey')
export AWS_SESSION_TOKEN=$(echo $ASSUME_ROLE_OUTPUT | jq -r '.Credentials.SessionToken')

# Verify assumed identity
aws sts get-caller-identity
```

### Step 3: Migrate to Pattern 1 (BDA)

```bash
# Update the stack to Pattern 1 using the assumed role
# NOTE: Update ../../template.yaml with the actual path to your IDP template.yaml file
# NOTE: Use the same stack name from the initial deployment
# Update AdminEmail= parameter with your administrator email 
aws cloudformation deploy \
  --template-file ../../template.yaml \
  --stack-name test-idp-migration \
  --parameter-overrides \
    AdminEmail="test@example.com" \
    IDPPattern="Pattern1 - Packet or Media processing with Bedrock Data Automation (BDA)" \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --region us-east-1
```

### Step 4: Verify Pattern Migration

```bash
# Verify the stack now uses Pattern 1
aws cloudformation describe-stacks --stack-name test-idp-migration --query 'Stacks[0].Parameters[?ParameterKey==`IDPPattern`].ParameterValue' --output text

# Should return: "Pattern1 - Packet or Media processing with Bedrock Data Automation (BDA)"

# Check nested stacks to confirm Pattern 1 resources
aws cloudformation list-stack-resources --stack-name test-idp-migration --query 'StackResourceSummaries[?ResourceType==`AWS::CloudFormation::Stack`]'
```

## AWS Console Testing (Alternative Method)

**Objective**: Perform the same pattern migration using the AWS Management Console interface.

**Prerequisites**: Administrator must complete the setup steps above.

### Step 1: Assume Role via Console

1. **Log into AWS Console** with your regular user account
2. **Switch Role**:
   - Click your username in top-right corner
   - Select "Switch Role"
   - Enter the following details:
     - **Account**: Your current account ID
     - **Role**: `test-idp-project-AllPatterns-Deployer-Secure`
     - **Display Name**: `IDP Deployer`
   - Click "Switch Role"
3. **Verify Role**: Top-right should show `IDP Deployer @ ACCOUNT-ID`

### Step 2: Navigate to CloudFormation

1. **Open CloudFormation Service**:
   - Search for "CloudFormation" in AWS Console
   - Ensure you're in the correct region (`us-east-1` or `us-west-2`)
2. **Locate Stack**:
   - Find `test-idp-migration` in the stacks list
   - Verify status is `CREATE_COMPLETE` or `UPDATE_COMPLETE`

### Step 3: Update Stack Parameters

1. **Initiate Update**:
   - Select the `test-idp-migration` stack
   - Click "Update" button
   - Choose "Use current template"
   - Click "Next"

2. **Modify Parameters**:
   - Locate the `IDPPattern` parameter
   - Change from: `Pattern2 - Packet processing with Textract and Bedrock`
   - Change to: `Pattern1 - Packet or Media processing with Bedrock Data Automation (BDA)`
   - Leave other parameters unchanged
   - Click "Next"

3. **Configure Stack Options**:
   - Leave all options as default
   - Click "Next"

4. **Review and Execute**:
   - Review the parameter changes
   - Check "I acknowledge that AWS CloudFormation might create IAM resources with custom names"
   - Click "Submit"

### Step 4: Monitor Stack Update

1. **Watch Events Tab**:
   - Click on "Events" tab
   - Monitor real-time update progress
   - Look for `UPDATE_IN_PROGRESS` events

2. **Monitor Resources Tab**:
   - Click on "Resources" tab
   - Watch for resource deletions (Pattern 2 stack)
   - Watch for resource creations (Pattern 1 stack)

3. **Check Parameters Tab**:
   - Click on "Parameters" tab
   - Verify `IDPPattern` shows new value

### Step 5: Validate Migration Success

1. **Stack Status**:
   - Wait for status to change to `UPDATE_COMPLETE`
   - Verify no errors in Events tab

2. **Nested Stacks**:
   - In Resources tab, look for nested CloudFormation stacks
   - Should see Pattern 1 (BDA) stack instead of Pattern 2

3. **Stack Outputs**:
   - Click "Outputs" tab
   - Verify all outputs are present and valid

### Console Testing Benefits

- **Visual Validation**: See parameter changes in real-time
- **Progress Monitoring**: Watch stack update events as they happen
- **Error Identification**: Easily spot failures in the Events tab
- **Resource Tracking**: Visual confirmation of resource changes
- **No CLI Setup**: No need to manage AWS credentials or CLI configuration


## Expected Results

### Successful Pattern Migration
- **Stack Update**: CloudFormation update completes without errors
- **Resource Changes**: Pattern 2 nested stack removed, Pattern 1 (BDA) nested stack created
- **Parameter Update**: IDPPattern parameter reflects new value
- **Functional Resources**: New BDA resources are created and operational

### Role Permission Validation
- **Assumption Success**: Non-administrator can assume the deployer role
- **CloudFormation Access**: Full stack management capabilities
- **Service Access**: All required AWS services accessible
- **Regional Restriction**: Operations work in us-east-1/us-west-2 only

### Security Validation
- **Session Timeout**: Role sessions expire after 1 hour
- **Region Enforcement**: Actions denied outside approved regions
- **Account Isolation**: Role cannot be assumed cross-account

## Validation Checklist

### Administrator Setup (Required)
- [ ] Deployer role deployed successfully by administrator
- [ ] Initial IDP stack (Pattern 2) deployed by administrator
- [ ] Test user granted `sts:AssumeRole` permission for deployer role
- [ ] Environment variables configured correctly

### Role Assumption Test
- [ ] Non-administrator can assume deployer role successfully
- [ ] Assumed role identity shows correct role ARN
- [ ] Role session has 1-hour maximum duration
- [ ] Role assumption works only in deployment region

### Pattern Migration Test
- [ ] Initial stack shows Pattern 2 configuration
- [ ] Stack update to Pattern 1 completes successfully
- [ ] Updated stack shows Pattern 1 configuration
- [ ] Pattern 2 nested stack resources removed
- [ ] Pattern 1 (BDA) nested stack resources created
- [ ] No permission errors during migration

### Security Validation
- [ ] Operations fail outside us-east-1/us-west-2 regions
- [ ] Role cannot be assumed without proper permissions
- [ ] Session expires after maximum duration
- [ ] All AWS service permissions work as expected

## Cleanup Procedures

**Note**: Cleanup requires administrator privileges for stack deletion.

### Test Resource Cleanup

```bash
# Unset assumed role credentials first
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN

# Administrator: Delete test IDP stack
aws cloudformation delete-stack --stack-name test-idp-migration --region us-east-1

# Wait for stack deletion
aws cloudformation wait stack-delete-complete --stack-name test-idp-migration --region us-east-1

# Administrator: Delete deployer role stack
aws cloudformation delete-stack --stack-name idp-deployer-role --region us-east-1

# Clean up environment variables
unset TEST_ACCOUNT_ID TEST_REGION DEPLOYER_ROLE_ARN TEST_STACK_NAME
```

## Troubleshooting

### Common Issues

#### Issue: Role Assumption Fails
```bash
# Check if role exists
aws iam get-role --role-name "test-idp-project-AllPatterns-Deployer-Secure"

# Verify your user has assume role permission
aws iam simulate-principal-policy \
  --policy-source-arn "arn:aws:iam::ACCOUNT:user/YOUR-USER" \
  --action-names "sts:AssumeRole" \
  --resource-arns "$DEPLOYER_ROLE_ARN"
```

#### Issue: Region Restriction Errors
```bash
# Verify you're in an approved region
aws configure get region
# Must be us-east-1 or us-west-2

# Check if role was deployed in same region
aws iam get-role --role-name "test-idp-project-AllPatterns-Deployer-Secure" --region us-east-1
```

#### Issue: Pattern Migration Fails
```bash
# Check CloudFormation events for specific errors
aws cloudformation describe-stack-events --stack-name test-idp-migration

# Verify Bedrock model access is enabled
aws bedrock list-foundation-models --region us-east-1

# Check for BDA project creation issues
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda" --region us-east-1
```

#### Issue: Session Timeout
```bash
# Re-assume role for fresh credentials
ASSUME_ROLE_OUTPUT=$(aws sts assume-role \
  --role-arn "$DEPLOYER_ROLE_ARN" \
  --role-session-name "pattern-migration-test-retry")

# Export new credentials
export AWS_ACCESS_KEY_ID=$(echo $ASSUME_ROLE_OUTPUT | jq -r '.Credentials.AccessKeyId')
# ... (repeat for other credentials)
```

### Test Success Criteria

✅ **Successful Test Completion**:
- Deployer role deployed by administrator
- Non-administrator successfully assumes role
- Pattern migration (2→1) completes without errors
- All security restrictions work as expected
- Resources cleaned up successfully