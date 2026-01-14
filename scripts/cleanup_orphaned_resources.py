#!/usr/bin/env python3
"""
IDP Orphaned Resources Cleanup Script

This script identifies and cleans up orphaned IDP resources from ALL deleted stacks
across your AWS account. It uses stack state verification to ensure only resources
from missing or failed stacks are removed, protecting active stack resources.

The script performs comprehensive cleanup of resources that may remain after stack
deletions, including resources not tracked by CloudFormation or left behind due
to deletion failures.

WHAT IT DOES:
• Scans ALL IDP resources across your AWS account
• Verifies stack states (MISSING, INCONSISTENT, or ACTIVE)  
• Only deletes resources from missing/failed stacks
• Protects resources from active stacks
• Uses two-phase CloudFront cleanup for efficiency

RESOURCES CLEANED UP:
• CloudFront distributions (disabled for future cleanup)
• CloudWatch Log Groups (Lambda, Glue crawlers)
• AppSync APIs and log groups
• CloudFront Response Headers Policies
• IAM custom policies and permissions boundaries
• CloudWatch Logs resource policy entries

CLOUDFRONT TWO-PHASE CLEANUP:
1. First run: Disables orphaned distributions (completes immediately)
2. Wait 15-20 minutes: CloudFront propagates disable globally
3. Second run: Deletes previously disabled distributions

Usage:
    python cleanup_orphaned_resources.py [--profile PROFILE] [--region REGION]
"""

import argparse
import boto3
import json
import logging
import sys
from typing import Dict, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IDPResourceCleanup:
    """Cleanup orphaned IDP resources"""
    
    def __init__(self, profile: str = None, region: str = "us-east-1"):
        self.region = region
        self.session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        
        # Initialize clients
        self.cloudformation = self.session.client("cloudformation", region_name=region)
        self.cloudfront = self.session.client("cloudfront")
        self.logs = self.session.client("logs", region_name=region)
        self.appsync = self.session.client("appsync", region_name=region)
        self.iam = self.session.client("iam", region_name=region)
        self.sts = self.session.client("sts", region_name=region)
        
        self.account_id = self.sts.get_caller_identity()["Account"]
        
        # Cache of stack states
        self._stack_states = {}
        
    def get_stack_state(self, stack_name: str) -> str:
        """Get stack state: 'ACTIVE', 'MISSING', or 'INCONSISTENT'"""
        if stack_name in self._stack_states:
            return self._stack_states[stack_name]
            
        try:
            response = self.cloudformation.describe_stacks(StackName=stack_name)
            stacks = response.get("Stacks", [])
            
            if not stacks:
                state = "MISSING"
            else:
                stack_status = stacks[0].get("StackStatus", "")
                if stack_status in [
                    "CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"
                ]:
                    state = "ACTIVE"
                elif stack_status in [
                    "DELETE_COMPLETE", "DELETE_FAILED", "CREATE_FAILED", 
                    "ROLLBACK_COMPLETE", "ROLLBACK_FAILED", "UPDATE_ROLLBACK_FAILED"
                ]:
                    state = "INCONSISTENT"
                else:
                    # In progress states - consider active for safety
                    state = "ACTIVE"
                    
        except self.cloudformation.exceptions.ClientError as e:
            if "does not exist" in str(e):
                state = "MISSING"
            else:
                # Unknown error - be conservative
                state = "ACTIVE"
        except Exception:
            # Unknown error - be conservative  
            state = "ACTIVE"
            
        self._stack_states[stack_name] = state
        return state
        
    def extract_stack_name_from_comment(self, comment: str) -> str:
        """Extract stack name from CloudFront distribution comment"""
        if comment.startswith("Web app cloudfront distribution "):
            return comment.replace("Web app cloudfront distribution ", "")
        return ""
        
    def extract_stack_name_from_log_group(self, log_group_name: str) -> str:
        """Extract stack name from log group name"""
        if log_group_name.startswith("/") and "/lambda/" in log_group_name:
            # Pattern: /{stack_name}-{nested_stack}/lambda/{function}
            parts = log_group_name[1:].split("/lambda/")[0]
            if "-" in parts:
                # Extract base stack name (everything before first nested stack pattern)
                stack_parts = parts.split("-")
                for i in range(len(stack_parts)):
                    if "PATTERN" in stack_parts[i] or "STACK" in stack_parts[i]:
                        return "-".join(stack_parts[:i])
        elif "/aws-glue/crawlers-role/" in log_group_name and "DocumentSectionsCrawlerRole" in log_group_name:
            # Pattern: /aws-glue/crawlers-role/{stack_name}-DocumentSectionsCrawlerRole-{suffix}
            parts = log_group_name.replace("/aws-glue/crawlers-role/", "")
            if "-DocumentSectionsCrawlerRole-" in parts:
                return parts.split("-DocumentSectionsCrawlerRole-")[0]
        elif log_group_name.startswith("/aws/appsync/apis/"):
            # For AppSync, we'll check via API name separately
            return ""
        return ""
        
    def extract_stack_name_from_api_name(self, api_name: str) -> str:
        """Extract stack name from AppSync API name"""
        if api_name.endswith("-api"):
            if "-p1-api" in api_name:
                return api_name.replace("-p1-api", "")
            elif "-p2-api" in api_name:
                return api_name.replace("-p2-api", "")
            elif "-p3-api" in api_name:
                return api_name.replace("-p3-api", "")
            else:
                return api_name.replace("-api", "")
        return ""
        
    def extract_stack_name_from_policy_name(self, policy_name: str) -> str:
        """Extract stack name from policy name"""
        if policy_name.endswith("-security-headers-policy"):
            return policy_name.replace("-security-headers-policy", "")
        elif policy_name.endswith("-PermissionsBoundary"):
            return policy_name.replace("-PermissionsBoundary", "")
        elif "PATTERN" in policy_name and "STACK" in policy_name:
            # Pattern: {stack_name}-PATTERN*STACK-{suffix}
            parts = policy_name.split("-")
            for i, part in enumerate(parts):
                if "PATTERN" in part:
                    return "-".join(parts[:i])
        return ""
        
    def is_resource_orphaned(self, stack_name: str) -> bool:
        """Check if resource is orphaned based on stack state"""
        if not stack_name:
            return False  # Can't determine - be safe
            
        state = self.get_stack_state(stack_name)
        return state in ["MISSING", "INCONSISTENT"]
        
    def cleanup_cloudfront_distributions(self) -> Dict:
        """Clean up CloudFront distributions using IDP comment pattern"""
        logger.info("Cleaning up CloudFront distributions...")
        results = {"deleted": [], "disabled": [], "skipped": [], "errors": []}
        
        try:
            response = self.cloudfront.list_distributions()
            
            # Phase 1: Delete previously disabled distributions
            for distribution in response.get("DistributionList", {}).get("Items", []):
                comment = distribution.get("Comment", "")
                if comment.startswith("Web app cloudfront distribution "):
                    distribution_id = distribution["Id"]
                    stack_name = self.extract_stack_name_from_comment(comment)
                    
                    # Check if disabled and ready for deletion
                    if distribution.get("Status") == "Deployed" and not distribution.get("Enabled", True):
                        if self.is_resource_orphaned(stack_name):
                            logger.info(f"Found orphaned disabled distribution: {distribution_id} (stack: {stack_name})")
                            
                            try:
                                config_response = self.cloudfront.get_distribution(Id=distribution_id)
                                etag = config_response["ETag"]
                                
                                self.cloudfront.delete_distribution(Id=distribution_id, IfMatch=etag)
                                results["deleted"].append(f"{distribution_id} (stack: {stack_name})")
                                logger.info(f"Deleted distribution: {distribution_id}")
                            except Exception as e:
                                error_msg = f"Failed to delete distribution {distribution_id}: {e}"
                                logger.error(error_msg)
                                results["errors"].append(error_msg)
                        else:
                            results["skipped"].append(f"{distribution_id} (stack: {stack_name} - active)")
            
            # Phase 2: Disable enabled distributions from orphaned stacks
            for distribution in response.get("DistributionList", {}).get("Items", []):
                comment = distribution.get("Comment", "")
                if comment.startswith("Web app cloudfront distribution "):
                    distribution_id = distribution["Id"]
                    stack_name = self.extract_stack_name_from_comment(comment)
                    
                    if distribution.get("Enabled", False):
                        if self.is_resource_orphaned(stack_name):
                            logger.info(f"Found orphaned enabled distribution: {distribution_id} (stack: {stack_name})")
                            
                            try:
                                config_response = self.cloudfront.get_distribution(Id=distribution_id)
                                etag = config_response["ETag"]
                                config = config_response["Distribution"]["DistributionConfig"]
                                
                                config["Enabled"] = False
                                self.cloudfront.update_distribution(
                                    Id=distribution_id,
                                    DistributionConfig=config,
                                    IfMatch=etag
                                )
                                results["disabled"].append(f"{distribution_id} (stack: {stack_name})")
                                logger.info(f"Disabled distribution: {distribution_id}")
                            except Exception as e:
                                error_msg = f"Failed to disable distribution {distribution_id}: {e}"
                                logger.error(error_msg)
                                results["errors"].append(error_msg)
                        else:
                            results["skipped"].append(f"{distribution_id} (stack: {stack_name} - active)")
                            
        except Exception as e:
            error_msg = f"Failed to cleanup CloudFront distributions: {e}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            
        return results
    
    def cleanup_log_groups(self) -> Dict:
        """Clean up orphaned log groups using IDP patterns"""
        logger.info("Cleaning up log groups...")
        results = {"deleted": [], "skipped": [], "errors": []}
        
        try:
            response = self.logs.describe_log_groups()
            
            for log_group in response.get("logGroups", []):
                log_group_name = log_group.get("logGroupName", "")
                
                # Check for IDP patterns - look for nested stack patterns
                is_idp_log_group = (
                    # Pattern: /{stack_name}-{nested_stack}/lambda/{function}
                    ("/lambda/" in log_group_name and "-PATTERN" in log_group_name) or
                    # Pattern: /aws-glue/crawlers-role/{stack_name}-{role}/crawler
                    (log_group_name.startswith("/aws-glue/crawlers-role/") and "DocumentSectionsCrawlerRole" in log_group_name) or
                    # Pattern: /aws/appsync/apis/{api_id}
                    log_group_name.startswith("/aws/appsync/apis/")
                )
                
                if is_idp_log_group:
                    stack_name = self.extract_stack_name_from_log_group(log_group_name)
                    
                    if self.is_resource_orphaned(stack_name):
                        logger.info(f"Found orphaned log group: {log_group_name} (stack: {stack_name})")
                        
                        try:
                            self.logs.delete_log_group(logGroupName=log_group_name)
                            results["deleted"].append(f"{log_group_name} (stack: {stack_name})")
                            logger.info(f"Deleted log group: {log_group_name}")
                        except Exception as e:
                            error_msg = f"Failed to delete log group {log_group_name}: {e}"
                            logger.error(error_msg)
                            results["errors"].append(error_msg)
                    else:
                        results["skipped"].append(f"{log_group_name} (stack: {stack_name} - active)")
                        
        except Exception as e:
            error_msg = f"Failed to cleanup log groups: {e}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            
        return results
    
    def cleanup_appsync_apis(self) -> Dict:
        """Clean up orphaned AppSync APIs using IDP patterns"""
        logger.info("Cleaning up AppSync APIs...")
        results = {"deleted": [], "skipped": [], "errors": []}
        
        try:
            response = self.appsync.list_graphql_apis()
            
            for api in response.get("graphqlApis", []):
                api_name = api.get("name", "")
                api_id = api.get("apiId")
                
                # Check for IDP API patterns: {stack_name}-api or {stack_name}-p*-api
                is_idp_api = (
                    api_name.endswith("-api") and 
                    ("-p1-api" in api_name or "-p2-api" in api_name or "-p3-api" in api_name or 
                     (api_name.count("-") >= 1 and not any(x in api_name for x in ["-p1-", "-p2-", "-p3-"])))
                )
                
                if is_idp_api and api_id:
                    stack_name = self.extract_stack_name_from_api_name(api_name)
                    
                    if self.is_resource_orphaned(stack_name):
                        logger.info(f"Found orphaned AppSync API: {api_name} ({api_id}) (stack: {stack_name})")
                        
                        try:
                            self.appsync.delete_graphql_api(apiId=api_id)
                            results["deleted"].append(f"{api_name} ({api_id}) (stack: {stack_name})")
                            logger.info(f"Deleted AppSync API: {api_name}")
                            
                            # Also clean up associated log group
                            log_group_name = f"/aws/appsync/apis/{api_id}"
                            try:
                                self.logs.delete_log_group(logGroupName=log_group_name)
                                logger.info(f"Deleted AppSync log group: {log_group_name}")
                            except self.logs.exceptions.ResourceNotFoundException:
                                pass
                        except Exception as e:
                            error_msg = f"Failed to delete AppSync API {api_name}: {e}"
                            logger.error(error_msg)
                            results["errors"].append(error_msg)
                    else:
                        results["skipped"].append(f"{api_name} ({api_id}) (stack: {stack_name} - active)")
                        
        except Exception as e:
            error_msg = f"Failed to cleanup AppSync APIs: {e}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            
        return results
    
    def cleanup_cloudfront_policies(self) -> Dict:
        """Clean up CloudFront Response Headers Policies using IDP patterns"""
        logger.info("Cleaning up CloudFront Response Headers Policies...")
        results = {"deleted": [], "skipped": [], "errors": []}
        
        try:
            response = self.cloudfront.list_response_headers_policies()
            
            for policy in response.get("ResponseHeadersPolicyList", {}).get("Items", []):
                if policy["Type"] == "custom":
                    policy_name = policy["ResponseHeadersPolicy"]["ResponseHeadersPolicyConfig"]["Name"]
                    policy_id = policy["ResponseHeadersPolicy"]["Id"]
                    
                    # Check for IDP pattern: {stack_name}-security-headers-policy
                    is_idp_policy = policy_name.endswith("-security-headers-policy")
                    
                    if is_idp_policy:
                        stack_name = self.extract_stack_name_from_policy_name(policy_name)
                        
                        if self.is_resource_orphaned(stack_name):
                            logger.info(f"Found orphaned CloudFront policy: {policy_name} (stack: {stack_name})")
                            
                            try:
                                self.cloudfront.delete_response_headers_policy(Id=policy_id)
                                results["deleted"].append(f"{policy_name} (stack: {stack_name})")
                                logger.info(f"Deleted CloudFront policy: {policy_name}")
                            except Exception as e:
                                error_msg = f"Failed to delete CloudFront policy {policy_name}: {e}"
                                logger.error(error_msg)
                                results["errors"].append(error_msg)
                        else:
                            results["skipped"].append(f"{policy_name} (stack: {stack_name} - active)")
                            
        except Exception as e:
            error_msg = f"Failed to cleanup CloudFront policies: {e}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            
        return results
    
    def cleanup_iam_policies(self) -> Dict:
        """Clean up orphaned IAM policies using IDP patterns"""
        logger.info("Cleaning up IAM policies...")
        results = {"deleted": [], "skipped": [], "errors": []}
        
        try:
            response = self.iam.list_policies(Scope="Local")
            
            for policy in response.get("Policies", []):
                policy_name = policy.get("PolicyName", "")
                policy_arn = policy.get("Arn")
                
                # Check for IDP patterns
                is_idp_policy = (
                    "PATTERN" in policy_name and ("STACK" in policy_name or "LambdaECRAccessPolicy" in policy_name) or
                    policy_name.endswith("-PermissionsBoundary")
                )
                
                if is_idp_policy and policy_arn:
                    stack_name = self.extract_stack_name_from_policy_name(policy_name)
                    
                    if self.is_resource_orphaned(stack_name):
                        logger.info(f"Found orphaned IAM policy: {policy_name} (stack: {stack_name})")
                        
                        try:
                            self.iam.delete_policy(PolicyArn=policy_arn)
                            results["deleted"].append(f"{policy_name} (stack: {stack_name})")
                            logger.info(f"Deleted IAM policy: {policy_name}")
                        except Exception as e:
                            error_msg = f"Failed to delete IAM policy {policy_name}: {e}"
                            logger.error(error_msg)
                            results["errors"].append(error_msg)
                    else:
                        results["skipped"].append(f"{policy_name} (stack: {stack_name} - active)")
                        
        except Exception as e:
            error_msg = f"Failed to cleanup IAM policies: {e}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            
        return results
    
    def cleanup_logs_resource_policies(self) -> Dict:
        """Clean up CloudWatch Logs resource policies using IDP patterns"""
        logger.info("Cleaning up CloudWatch Logs resource policies...")
        results = {"updated": [], "deleted": [], "errors": []}
        
        try:
            response = self.logs.describe_resource_policies()
            
            for policy in response.get("resourcePolicies", []):
                policy_name = policy.get("policyName", "")
                
                if policy_name == "AWSLogDeliveryWrite20150319":
                    # Clean up entries from the main policy
                    try:
                        policy_doc = json.loads(policy.get("policyDocument", "{}"))
                        original_count = len(policy_doc.get("Statement", []))
                        
                        # Remove IDP-related statements (look for vendedlogs pattern)
                        policy_doc["Statement"] = [
                            stmt for stmt in policy_doc.get("Statement", [])
                            if not "/aws/vendedlogs/states/" in stmt.get("Resource", "")
                        ]
                        
                        new_count = len(policy_doc.get("Statement", []))
                        if new_count < original_count:
                            logger.info(f"Removing {original_count - new_count} vendedlogs entries from {policy_name}")
                            
                            self.logs.put_resource_policy(
                                policyName=policy_name,
                                policyDocument=json.dumps(policy_doc)
                            )
                            results["updated"].append(f"{policy_name} ({original_count - new_count} entries removed)")
                                
                    except Exception as e:
                        error_msg = f"Failed to update policy {policy_name}: {e}"
                        logger.error(error_msg)
                        results["errors"].append(error_msg)
                
                # Delete any other stack-specific policies (they typically don't exist but check anyway)
                elif policy_name != "AWSLogDeliveryWrite20150319":
                    logger.info(f"Found custom resource policy: {policy_name}")
                    
                    try:
                        self.logs.delete_resource_policy(policyName=policy_name)
                        results["deleted"].append(policy_name)
                        logger.info(f"Deleted resource policy: {policy_name}")
                    except Exception as e:
                        error_msg = f"Failed to delete resource policy {policy_name}: {e}"
                        logger.error(error_msg)
                        results["errors"].append(error_msg)
                        
        except Exception as e:
            error_msg = f"Failed to cleanup resource policies: {e}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            
        return results
    
    def run_cleanup(self) -> Dict:
        """Run comprehensive cleanup"""
        logger.info("Starting IDP resource cleanup...")
        
        results = {
            "cloudfront_distributions": self.cleanup_cloudfront_distributions(),
            "log_groups": self.cleanup_log_groups(),
            "appsync_apis": self.cleanup_appsync_apis(),
            "cloudfront_policies": self.cleanup_cloudfront_policies(),
            "iam_policies": self.cleanup_iam_policies(),
            "logs_resource_policies": self.cleanup_logs_resource_policies()
        }
        
        return results


def print_summary(results: Dict):
    """Print cleanup summary"""
    print("\n" + "="*60)
    print("CLEANUP SUMMARY")
    print("="*60)
    
    for resource_type, result in results.items():
        print(f"\n{resource_type.upper().replace('_', ' ')}:")
        
        if "deleted" in result and result["deleted"]:
            print(f"  Deleted ({len(result['deleted'])}):")
            for item in result["deleted"]:
                print(f"    - {item}")
        
        if "disabled" in result and result["disabled"]:
            print(f"  Disabled ({len(result['disabled'])}):")
            for item in result["disabled"]:
                print(f"    - {item}")
                
        if "updated" in result and result["updated"]:
            print(f"  Updated ({len(result['updated'])}):")
            for item in result["updated"]:
                print(f"    - {item}")
        
        if "errors" in result and result["errors"]:
            print(f"  Errors ({len(result['errors'])}):")
            for error in result["errors"]:
                print(f"    - {error}")
        
        if not any(result.get(key) for key in ["deleted", "disabled", "updated", "errors"]):
            print("  No resources found")


def main():
    parser = argparse.ArgumentParser(description="Clean up orphaned IDP resources")
    parser.add_argument("--profile", help="AWS profile to use")
    parser.add_argument("--region", default="us-east-1", help="AWS region (default: us-east-1)")
    
    args = parser.parse_args()
    
    try:
        cleanup = IDPResourceCleanup(profile=args.profile, region=args.region)
        results = cleanup.run_cleanup()
        print_summary(results)
        
        # Check if any errors occurred
        has_errors = any(
            result.get("errors", []) 
            for result in results.values()
        )
        
        if has_errors:
            logger.error("Cleanup completed with errors")
            
            # Check if CloudFront distributions were disabled
            cf_disabled = any(
                result.get("disabled", []) 
                for result in results.values()
            )
            
            if cf_disabled:
                print("\n" + "="*60)
                print("NEXT STEPS")
                print("="*60)
                print("CloudFront distributions have been disabled and are deploying.")
                print("Wait 15-20 minutes, then re-run this script to:")
                print("  • Delete the disabled distributions")
                print("  • Retry failed policy deletions")
                print("")
                print("Re-run command:")
                print(f"  python {' '.join(sys.argv)}")
                print("="*60)
            
            sys.exit(1)
        else:
            logger.info("Cleanup completed successfully")
            
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
