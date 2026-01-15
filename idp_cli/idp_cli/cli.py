# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
IDP CLI - Main Command Line Interface

Command-line tool for batch document processing with the IDP Accelerator.
"""

import logging
import os
import subprocess
import sys
import time
from typing import Optional

import boto3
import click
from rich.console import Console
from rich.live import Live
from rich.table import Table

from . import display
from .batch_processor import BatchProcessor
from .deployer import StackDeployer, build_parameters
from .manifest_parser import validate_manifest
from .progress_monitor import ProgressMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

console = Console()


def _build_from_local_code(from_code_dir: str, region: str, stack_name: str) -> tuple:
    """
    Build project from local code using publish.py

    Args:
        from_code_dir: Path to project root directory
        region: AWS region
        stack_name: CloudFormation stack name (unused but kept for signature compatibility)

    Returns:
        Tuple of (template_path, None) on success

    Raises:
        SystemExit: On build failure
    """
    # Verify publish.py exists
    publish_script = os.path.join(from_code_dir, "publish.py")
    if not os.path.isfile(publish_script):
        console.print(f"[red]✗ Error: publish.py not found in {from_code_dir}[/red]")
        console.print(
            "[yellow]Tip: --from-code should point to the project root directory[/yellow]"
        )
        sys.exit(1)

    # Get AWS account ID
    try:
        sts = boto3.client("sts", region_name=region)
        account_id = sts.get_caller_identity()["Account"]
    except Exception as e:
        console.print(f"[red]✗ Error: Failed to get AWS account ID: {e}[/red]")
        sys.exit(1)

    # Set parameters for publish.py
    cfn_bucket_basename = f"idp-accelerator-artifacts-{account_id}"
    cfn_prefix = "idp-cli"

    console.print("[bold cyan]Building project from source...[/bold cyan]")
    console.print(f"[dim]Bucket: {cfn_bucket_basename}[/dim]")
    console.print(f"[dim]Prefix: {cfn_prefix}[/dim]")
    console.print(f"[dim]Region: {region}[/dim]")
    console.print()

    # Build command
    cmd = [
        sys.executable,  # Use same Python interpreter
        publish_script,
        cfn_bucket_basename,
        cfn_prefix,
        region,
    ]

    console.print(f"[dim]Running: {' '.join(cmd)}[/dim]")
    console.print()

    # Run with streaming output
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=from_code_dir,
        )

        # Stream output line by line
        for line in process.stdout or []:  # type: ignore
            # Print each line immediately (preserve formatting from publish.py)
            print(line, end="")

        process.wait()

        if process.returncode != 0:
            console.print("[red]✗ Build failed. See output above for details.[/red]")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]✗ Error running publish.py: {e}[/red]")
        sys.exit(1)

    # Verify template was created
    template_path = os.path.join(from_code_dir, ".aws-sam", "idp-main.yaml")
    if not os.path.isfile(template_path):
        console.print(
            f"[red]✗ Error: Built template not found at {template_path}[/red]"
        )
        console.print(
            "[yellow]The build may have failed or the template was not generated.[/yellow]"
        )
        sys.exit(1)

    console.print()
    console.print(f"[green]✓ Build complete. Using template: {template_path}[/green]")
    console.print()

    return template_path, None


# Region-specific template URLs
TEMPLATE_URLS = {
    "us-west-2": "https://s3.us-west-2.amazonaws.com/aws-ml-blog-us-west-2/artifacts/genai-idp/idp-main.yaml",
    "us-east-1": "https://s3.us-east-1.amazonaws.com/aws-ml-blog-us-east-1/artifacts/genai-idp/idp-main.yaml",
    "eu-central-1": "https://s3.eu-central-1.amazonaws.com/aws-ml-blog-eu-central-1/artifacts/genai-idp/idp-main.yaml",
}


@click.group()
@click.version_option(version="0.4.11")
def cli():
    """
    IDP CLI - Batch document processing for IDP Accelerator

    This tool provides commands for:
    - Stack deployment
    - Batch document upload and processing
    - Progress monitoring with live updates
    - Status checking and reporting
    """
    pass


@cli.command()
@click.option("--stack-name", required=True, help="CloudFormation stack name")
@click.option(
    "--pattern",
    type=click.Choice(["pattern-1", "pattern-2", "pattern-3"]),
    help="IDP pattern to deploy (required for new stacks)",
)
@click.option(
    "--admin-email", help="Admin user email address (required for new stacks)"
)
@click.option(
    "--from-code",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Deploy from local code by building with publish.py (path to project root)",
)
@click.option(
    "--template-url",
    help="URL to CloudFormation template in S3 (default: auto-selected based on region)",
)
@click.option(
    "--max-concurrent",
    default=100,
    type=int,
    help="Maximum concurrent workflows (default: 100)",
)
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARN", "ERROR"]),
    help="Logging level (default: INFO)",
)
@click.option(
    "--enable-hitl",
    default="false",
    type=click.Choice(["true", "false"]),
    help="Enable Human-in-the-Loop (default: false)",
)
@click.option("--pattern-config", help="Pattern configuration preset")
@click.option(
    "--custom-config",
    help="Path to local config file or S3 URI (e.g., ./config.yaml or s3://bucket/config.yaml)",
)
@click.option("--parameters", help="Additional parameters as key=value,key2=value2")
@click.option("--wait", is_flag=True, help="Wait for stack creation to complete")
@click.option(
    "--no-rollback", is_flag=True, help="Disable rollback on stack creation failure"
)
@click.option("--region", help="AWS region (optional)")
@click.option("--role-arn", help="CloudFormation service role ARN")
def deploy(
    stack_name: str,
    pattern: str,
    admin_email: str,
    from_code: Optional[str],
    template_url: str,
    max_concurrent: int,
    log_level: str,
    enable_hitl: str,
    pattern_config: Optional[str],
    custom_config: Optional[str],
    parameters: Optional[str],
    wait: bool,
    no_rollback: bool,
    region: Optional[str],
    role_arn: Optional[str],
):
    """
    Deploy or update IDP stack from command line
    
    For new stacks, --pattern and --admin-email are required.
    For existing stacks, only specify parameters you want to update.
    
    Examples:
    
      # Create new stack with Pattern 2
      idp-cli deploy --stack-name my-idp --pattern pattern-2 --admin-email user@example.com
      
      # Deploy from local code (NEW!)
      idp-cli deploy --stack-name my-idp --from-code . --pattern pattern-2 --admin-email user@example.com --wait
      
      # Update existing stack with local config file
      idp-cli deploy --stack-name my-idp --custom-config ./my-config.yaml
      
      # Update existing stack from local code
      idp-cli deploy --stack-name my-idp --from-code . --wait
      
      # Update existing stack with custom settings
      idp-cli deploy --stack-name my-idp --max-concurrent 200 --wait
      
      # Create with additional parameters
      idp-cli deploy --stack-name my-idp --pattern pattern-2 \\
          --admin-email user@example.com \\
          --parameters "DataRetentionInDays=90,ErrorThreshold=5"
    """
    try:
        # Validate mutually exclusive options
        if from_code and template_url:
            console.print(
                "[red]✗ Error: Cannot specify both --from-code and --template-url[/red]"
            )
            sys.exit(1)

        # Auto-detect region if not provided
        if not region:
            import boto3

            session = boto3.session.Session()  # type: ignore
            region = session.region_name
            if not region:
                raise ValueError(
                    "Region could not be determined. Please specify --region or configure AWS_DEFAULT_REGION"
                )

        # Handle deployment from local code
        template_path = None
        if from_code:
            template_path, template_url = _build_from_local_code(
                from_code, region, stack_name
            )

        # Determine template URL (user-provided takes precedence)
        elif not template_url:
            if region in TEMPLATE_URLS:
                template_url = TEMPLATE_URLS[region]
                console.print(f"[bold]Using template for region: {region}[/bold]")
            else:
                supported_regions = ", ".join(TEMPLATE_URLS.keys())
                raise ValueError(
                    f"Region '{region}' is not supported. "
                    f"Supported regions: {supported_regions}. "
                    f"Please provide --template-url explicitly for other regions."
                )

        # Initialize deployer
        deployer = StackDeployer(region=region)

        # Check if stack exists
        stack_exists = deployer._stack_exists(stack_name)

        if stack_exists:
            # Stack exists - updating (all parameters are optional)
            console.print(
                f"[bold blue]Updating existing IDP stack: {stack_name}[/bold blue]"
            )
            if pattern:
                console.print(f"Pattern: {pattern}")
            if admin_email:
                console.print(f"Admin Email: {admin_email}")
        else:
            # New stack - require pattern and admin_email
            console.print(
                f"[bold blue]Creating new IDP stack: {stack_name}[/bold blue]"
            )

            if not pattern:
                console.print(
                    "[red]✗ Error: --pattern is required when creating a new stack[/red]"
                )
                sys.exit(1)

            if not admin_email:
                console.print(
                    "[red]✗ Error: --admin-email is required when creating a new stack[/red]"
                )
                sys.exit(1)

            console.print(f"Pattern: {pattern}")
            console.print(f"Admin Email: {admin_email}")

        console.print()

        # Parse additional parameters
        additional_params = {}
        if parameters:
            for param in parameters.split(","):
                if "=" in param:
                    key, value = param.split("=", 1)
                    additional_params[key.strip()] = value.strip()

        # Build parameters - only pass explicitly provided values
        # Convert Click defaults to None when not explicitly provided by user
        cfn_parameters = build_parameters(
            pattern=pattern,
            admin_email=admin_email,
            max_concurrent=max_concurrent if max_concurrent != 100 else None,
            log_level=log_level if log_level != "INFO" else None,
            enable_hitl=enable_hitl if enable_hitl != "false" else None,
            pattern_config=pattern_config,
            custom_config=custom_config,
            additional_params=additional_params,
            region=region,
            stack_name=stack_name,
        )

        # Debug: Show CustomConfigPath if present
        if "CustomConfigPath" in cfn_parameters:
            console.print(
                f"[yellow]DEBUG: CustomConfigPath = {cfn_parameters['CustomConfigPath']}[/yellow]"
            )

        # Deploy stack
        with console.status("[bold green]Deploying stack..."):
            if template_path:
                # Deploy from local template (built from code)
                result = deployer.deploy_stack(
                    stack_name=stack_name,
                    template_path=template_path,
                    parameters=cfn_parameters,
                    wait=wait,
                    no_rollback=no_rollback,
                    role_arn=role_arn,
                )
            else:
                # Deploy from template URL
                result = deployer.deploy_stack(
                    stack_name=stack_name,
                    template_url=template_url,
                    parameters=cfn_parameters,
                    wait=wait,
                    no_rollback=no_rollback,
                    role_arn=role_arn,
                )

        # Show results
        # Success if operation completed successfully OR was successfully initiated
        is_success = result.get("success") or result.get("status") == "INITIATED"

        if is_success:
            if result.get("success"):
                # Completed (with --wait)
                console.print(
                    f"\n[green]✓ Stack {result['operation']} completed successfully![/green]\n"
                )

                # Show outputs
                outputs = result.get("outputs", {})
                if outputs:
                    console.print("[bold]Important Outputs:[/bold]")
                    console.print(
                        f"  Application URL: [cyan]{outputs.get('ApplicationWebURL', 'N/A')}[/cyan]"
                    )
                    console.print(
                        f"  Input Bucket: {outputs.get('S3InputBucketName', 'N/A')}"
                    )
                    console.print(
                        f"  Output Bucket: {outputs.get('S3OutputBucketName', 'N/A')}"
                    )
                    console.print()

                console.print("[bold]Next Steps:[/bold]")
                console.print("1. Check your email for temporary admin password")
                console.print("2. Enable Bedrock model access (see README)")
                console.print("3. Process documents:")
                console.print(
                    f"   [cyan]idp-cli run-inference --stack-name {stack_name} --manifest docs.csv[/cyan]"
                )
                console.print()
            else:
                # Initiated (without --wait)
                console.print(
                    f"\n[green]✓ Stack {result['operation']} initiated successfully![/green]\n"
                )
                console.print("[bold]Monitor progress:[/bold]")
                console.print(f"  AWS Console: CloudFormation → Stacks → {stack_name}")
                console.print()
                console.print("[bold]Or use --wait flag to monitor in CLI:[/bold]")
                console.print(
                    f"  [cyan]idp-cli deploy --stack-name {stack_name} --wait[/cyan]"
                )
                console.print()
        else:
            console.print(f"\n[red]✗ Stack {result['operation']} failed![/red]")
            console.print(f"Status: {result.get('status')}")
            console.print(f"Error: {result.get('error', 'Unknown')}")
            sys.exit(1)

    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/red]")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error deploying stack: {e}", exc_info=True)
        console.print(f"[red]✗ Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--stack-name", required=True, help="CloudFormation stack name")
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
@click.option(
    "--empty-buckets",
    is_flag=True,
    help="Empty S3 buckets before deletion (required if buckets contain data)",
)
@click.option(
    "--force-delete-all",
    is_flag=True,
    help="Force delete ALL remaining resources after CloudFormation deletion (S3 buckets, CloudWatch logs, DynamoDB tables). This cannot be undone.",
)
@click.option(
    "--wait/--no-wait",
    default=True,
    help="Wait for deletion to complete (default: wait)",
)
@click.option("--region", help="AWS region (optional)")
def delete(
    stack_name: str,
    force: bool,
    empty_buckets: bool,
    force_delete_all: bool,
    wait: bool,
    region: Optional[str],
):
    """
    Delete an IDP CloudFormation stack

    ⚠️  WARNING: This permanently deletes all stack resources.

    S3 buckets configured with RetainExceptOnCreate will be deleted if empty.
    Use --empty-buckets to automatically empty buckets before deletion.
    Use --force-delete-all to delete ALL remaining resources after CloudFormation deletion.

    Examples:

      # Interactive deletion with confirmation
      idp-cli delete --stack-name test-stack

      # Automated deletion (skip confirmation)
      idp-cli delete --stack-name test-stack --force

      # Delete with automatic bucket emptying
      idp-cli delete --stack-name test-stack --empty-buckets --force

      # Force delete ALL remaining resources (S3, logs, DynamoDB)
      idp-cli delete --stack-name test-stack --force-delete-all --force

      # Delete without waiting for completion
      idp-cli delete --stack-name test-stack --force --no-wait
    """
    try:
        deployer = StackDeployer(region=region)

        # Check if stack exists
        if not deployer._stack_exists(stack_name):
            console.print(f"[red]✗ Stack '{stack_name}' does not exist[/red]")
            sys.exit(1)

        # Get bucket information
        console.print(f"[bold blue]Analyzing stack: {stack_name}[/bold blue]")
        bucket_info = deployer.get_bucket_info(stack_name)

        # Show warning with bucket details
        console.print()
        if force_delete_all:
            console.print("[bold red]⚠️  WARNING: FORCE DELETE ALL RESOURCES[/bold red]")
        else:
            console.print("[bold red]⚠️  WARNING: Stack Deletion[/bold red]")
        console.print("━" * 60)
        console.print(f"Stack: [cyan]{stack_name}[/cyan]")
        console.print(f"Region: {region or 'default'}")

        if bucket_info:
            console.print()
            console.print("[bold]S3 Buckets:[/bold]")
            has_data = False
            for bucket in bucket_info:
                obj_count = bucket.get("object_count", 0)
                size = bucket.get("size_display", "Unknown")
                logical_id = bucket.get("logical_id", "Unknown")

                if obj_count > 0:
                    has_data = True
                    console.print(
                        f"  • {logical_id}: [yellow]{obj_count} objects ({size})[/yellow]"
                    )
                else:
                    console.print(f"  • {logical_id}: [green]empty[/green]")

            if has_data and not empty_buckets and not force_delete_all:
                console.print()
                console.print("[bold red]⚠️  Buckets contain data![/bold red]")
                console.print("Deletion will FAIL unless you:")
                console.print("  1. Use --empty-buckets flag to auto-delete data, OR")
                console.print("  2. Use --force-delete-all to delete everything, OR")
                console.print("  3. Manually empty buckets first")

        if force_delete_all:
            console.print()
            console.print("[bold red]⚠️  FORCE DELETE ALL will remove:[/bold red]")
            console.print("  • All S3 buckets (including LoggingBucket)")
            console.print("  • All CloudWatch Log Groups")
            console.print("  • All DynamoDB Tables")
            console.print("  • Any other retained resources")
            console.print()
            console.print(
                "[bold yellow]This happens AFTER CloudFormation deletion completes[/bold yellow]"
            )

        console.print()
        console.print("[bold red]This action cannot be undone.[/bold red]")
        console.print("━" * 60)
        console.print()

        # Confirmation unless --force
        if not force:
            if force_delete_all:
                response = click.confirm(
                    "Are you ABSOLUTELY sure you want to force delete ALL resources?",
                    default=False,
                )
            else:
                response = click.confirm(
                    "Are you sure you want to delete this stack?", default=False
                )

            if not response:
                console.print("[yellow]Deletion cancelled[/yellow]")
                return

            # Double confirmation if --empty-buckets (and not force-delete-all)
            if empty_buckets and not force_delete_all:
                console.print()
                console.print(
                    "[bold red]⚠️  You are about to permanently delete all bucket data![/bold red]"
                )
                response = click.confirm(
                    "Are you ABSOLUTELY sure you want to empty buckets and delete the stack?",
                    default=False,
                )
                if not response:
                    console.print("[yellow]Deletion cancelled[/yellow]")
                    return

        # Perform deletion
        console.print()
        with console.status("[bold red]Deleting stack..."):
            result = deployer.delete_stack(
                stack_name=stack_name,
                empty_buckets=empty_buckets,
                wait=wait,
            )

        # Show CloudFormation deletion results
        if result.get("success"):
            console.print("\n[green]✓ Stack deleted successfully![/green]")
            console.print(f"Stack: {stack_name}")
            console.print(f"Status: {result.get('status')}")
        else:
            console.print("\n[red]✗ Stack deletion failed![/red]")
            console.print(f"Status: {result.get('status')}")
            console.print(f"Error: {result.get('error', 'Unknown')}")

            if "bucket" in result.get("error", "").lower():
                console.print()
                console.print(
                    "[yellow]Tip: Try again with --empty-buckets or --force-delete-all flag[/yellow]"
                )

            if not force_delete_all:
                sys.exit(1)
            else:
                console.print()
                console.print(
                    "[yellow]Stack deletion failed, but continuing with force cleanup...[/yellow]"
                )

        # Post-deletion cleanup if --force-delete-all
        cleanup_result = None
        if force_delete_all:
            console.print()
            console.print("[bold blue]━" * 60 + "[/bold blue]")
            console.print(
                "[bold blue]Starting force cleanup of retained resources...[/bold blue]"
            )
            console.print("[bold blue]━" * 60 + "[/bold blue]")

            try:
                # Use stack ID for deleted stacks (CloudFormation requires ID for deleted stacks)
                stack_identifier = result.get("stack_id", stack_name)
                cleanup_result = deployer.cleanup_retained_resources(stack_identifier)

                # Show cleanup summary
                console.print()
                console.print("[bold green]✓ Cleanup phase complete![/bold green]")
                console.print()

                total_deleted = (
                    len(cleanup_result.get("dynamodb_deleted", []))
                    + len(cleanup_result.get("logs_deleted", []))
                    + len(cleanup_result.get("buckets_deleted", []))
                )

                if total_deleted > 0:
                    console.print("[bold]Resources deleted:[/bold]")

                    if cleanup_result.get("dynamodb_deleted"):
                        console.print(
                            f"  • DynamoDB Tables: {len(cleanup_result['dynamodb_deleted'])}"
                        )
                        for table in cleanup_result["dynamodb_deleted"]:
                            console.print(f"    - {table}")

                    if cleanup_result.get("logs_deleted"):
                        console.print(
                            f"  • CloudWatch Log Groups: {len(cleanup_result['logs_deleted'])}"
                        )
                        for log_group in cleanup_result["logs_deleted"]:
                            console.print(f"    - {log_group}")

                    if cleanup_result.get("buckets_deleted"):
                        console.print(
                            f"  • S3 Buckets: {len(cleanup_result['buckets_deleted'])}"
                        )
                        for bucket in cleanup_result["buckets_deleted"]:
                            console.print(f"    - {bucket}")

                if cleanup_result.get("errors"):
                    console.print()
                    console.print(
                        "[bold yellow]⚠️  Some resources could not be deleted:[/bold yellow]"
                    )
                    for error in cleanup_result["errors"]:
                        console.print(f"  • {error['type']}: {error['resource']}")
                        console.print(f"    Error: {error['error']}")

                console.print()

            except Exception as e:
                logger.error(f"Error during cleanup: {e}", exc_info=True)
                console.print(f"\n[red]✗ Cleanup phase error: {e}[/red]")
                console.print(
                    "[yellow]Some resources may remain - check AWS Console[/yellow]"
                )
        else:
            # Standard deletion without force-delete-all
            if result.get("success"):
                console.print()
                console.print(
                    "[bold]Note:[/bold] LoggingBucket (if exists) is retained by design."
                )
                console.print("Delete it manually if no longer needed:")
                console.print(
                    "  [cyan]aws s3 rb s3://<logging-bucket-name> --force[/cyan]"
                )
                console.print()

    except Exception as e:
        logger.error(f"Error deleting stack: {e}", exc_info=True)
        console.print(f"[red]✗ Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--stack-name", required=True, help="CloudFormation stack name")
@click.option(
    "--step",
    required=True,
    type=click.Choice(["classification", "extraction"]),
    help="Pipeline step to rerun from",
)
@click.option(
    "--document-ids",
    help="Comma-separated list of document IDs to reprocess",
)
@click.option(
    "--batch-id",
    help="Batch ID to get document IDs from (alternative to --document-ids)",
)
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
@click.option("--monitor", is_flag=True, help="Monitor progress until completion")
@click.option(
    "--refresh-interval",
    default=5,
    type=int,
    help="Seconds between status checks (default: 5)",
)
@click.option("--region", help="AWS region (optional)")
def rerun_inference(
    stack_name: str,
    step: str,
    document_ids: Optional[str],
    batch_id: Optional[str],
    force: bool,
    monitor: bool,
    refresh_interval: int,
    region: Optional[str],
):
    """
    Rerun processing for existing documents from a specific step
    
    Reprocesses documents already in InputBucket, leveraging existing OCR data.
    
    Steps:
      - classification: Reruns classification and all subsequent steps
      - extraction: Reruns extraction and assessment (keeps classification)
    
    Document ID Format: Use the S3 key format (e.g., "batch-id/document.pdf")
    
    Examples:
    
      # Rerun classification for specific documents
      idp-cli rerun-inference \\
          --stack-name my-stack \\
          --step classification \\
          --document-ids "batch-123/doc1.pdf,batch-123/doc2.pdf" \\
          --monitor
      
      # Rerun extraction for all documents in a batch
      idp-cli rerun-inference \\
          --stack-name my-stack \\
          --step extraction \\
          --batch-id cli-batch-20251015-143000 \\
          --monitor
    """
    try:
        # Validate mutually exclusive options
        if not document_ids and not batch_id:
            console.print(
                "[red]✗ Error: Must specify either --document-ids or --batch-id[/red]"
            )
            sys.exit(1)

        if document_ids and batch_id:
            console.print(
                "[red]✗ Error: Cannot specify both --document-ids and --batch-id[/red]"
            )
            sys.exit(1)

        from .rerun_processor import RerunProcessor

        # Initialize processor
        console.print(
            f"[bold blue]Initializing rerun processor for stack: {stack_name}[/bold blue]"
        )
        processor = RerunProcessor(stack_name=stack_name, region=region)

        # Get document IDs
        if document_ids:
            doc_id_list = [doc_id.strip() for doc_id in document_ids.split(",")]
            console.print(f"Processing {len(doc_id_list)} specified documents")
        else:
            console.print(f"Getting document IDs from batch: {batch_id}")
            doc_id_list = processor.get_batch_document_ids(batch_id)
            console.print(f"Found {len(doc_id_list)} documents in batch")

        # Show what will be cleared based on step
        console.print()
        console.print(f"[bold yellow]⚠️  Rerun Step: {step}[/bold yellow]")
        console.print("━" * 60)

        if step == "classification":
            console.print("[bold]What will be cleared:[/bold]")
            console.print("  • All page classifications")
            console.print("  • All document sections")
            console.print("  • All extraction results")
            console.print()
            console.print("[bold]What will be kept:[/bold]")
            console.print("  • OCR data (pages, images, text)")
        else:  # extraction
            console.print("[bold]What will be cleared:[/bold]")
            console.print("  • Section extraction results")
            console.print("  • Section attributes")
            console.print()
            console.print("[bold]What will be kept:[/bold]")
            console.print("  • OCR data (pages, images, text)")
            console.print("  • Page classifications")
            console.print("  • Document sections structure")

        console.print("━" * 60)
        console.print()

        # Confirmation unless --force
        if not force:
            if not click.confirm(
                f"Reprocess {len(doc_id_list)} documents from {step} step?",
                default=True,
            ):
                console.print("[yellow]Rerun cancelled[/yellow]")
                return

        # Perform rerun
        console.print()
        with console.status(
            f"[bold green]Reprocessing {len(doc_id_list)} documents..."
        ):
            results = processor.rerun_documents(
                document_ids=doc_id_list, step=step, monitor=monitor
            )

        # Show results
        console.print()
        if results["documents_queued"] > 0:
            console.print(
                f"[green]✓ Queued {results['documents_queued']} documents for {step} reprocessing[/green]"
            )

        if results["documents_failed"] > 0:
            console.print(
                f"[red]✗ Failed to queue {results['documents_failed']} documents[/red]"
            )
            for failed in results["failed_documents"]:
                console.print(f"  • {failed['object_key']}: {failed['error']}")

        console.print()

        if monitor and results["documents_queued"] > 0:
            # Monitor progress using existing monitoring function
            _monitor_progress(
                stack_name=stack_name,
                batch_id=batch_id or "rerun",
                document_ids=doc_id_list,
                refresh_interval=refresh_interval,
                region=region,
                resources=processor.resources,
            )

    except Exception as e:
        logger.error(f"Error rerunning documents: {e}", exc_info=True)
        console.print(f"[red]✗ Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--stack-name", required=True, help="CloudFormation stack name")
@click.option(
    "--manifest",
    type=click.Path(exists=True),
    help="Path to manifest file (CSV or JSON)",
)
@click.option(
    "--dir",
    "directory",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Local directory containing documents to process",
)
@click.option("--s3-uri", help="S3 URI to process (e.g., s3://bucket/prefix/)")
@click.option("--test-set", help="Test set ID to process from test set bucket")
@click.option(
    "--context", help="Context description for test run (used with --test-set)"
)
@click.option(
    "--batch-id",
    help="Custom batch ID (auto-generated if not provided, ignored with --test-set)",
)
@click.option(
    "--file-pattern",
    default="*.pdf",
    help="File pattern for directory/S3 scanning (default: *.pdf)",
)
@click.option(
    "--recursive/--no-recursive",
    default=True,
    help="Include subdirectories when scanning (default: recursive)",
)
@click.option(
    "--config",
    type=click.Path(exists=True),
    help="Path to configuration YAML file (optional)",
)
@click.option(
    "--batch-prefix",
    default="cli-batch",
    help="Batch ID prefix (used only if --batch-id not provided, default: cli-batch)",
)
@click.option("--monitor", is_flag=True, help="Monitor progress until completion")
@click.option(
    "--refresh-interval",
    default=5,
    type=int,
    help="Seconds between status checks (default: 5)",
)
@click.option("--region", help="AWS region (optional)")
@click.option(
    "--number-of-files",
    type=int,
    help="Limit number of files to process (for testing purposes)",
)
def run_inference(
    stack_name: str,
    manifest: Optional[str],
    directory: Optional[str],
    s3_uri: Optional[str],
    test_set: Optional[str],
    context: Optional[str],
    batch_id: Optional[str],
    file_pattern: str,
    recursive: bool,
    config: Optional[str],
    batch_prefix: str,
    monitor: bool,
    refresh_interval: int,
    region: Optional[str],
    number_of_files: Optional[int],
):
    """
    Run inference on a batch of documents

    Specify documents using ONE of:
      --manifest: Explicit manifest file (CSV or JSON)
                 If manifest contains baseline_source column, automatically creates
                 "idp-cli" test set for Test Studio integration and evaluation
      --dir: Local directory (auto-generates manifest)
      --s3-uri: S3 URI (auto-generates manifest, any bucket)
      --test-set: Process existing test set from test set bucket (use test set ID)

    Test Studio Integration:
      - --test-set: Processes existing test sets and tracks results in Test Studio UI
      - --context: Adds descriptive labels to test runs (e.g., "Model v2.1", "Production validation")
      - Manifests with baselines: Automatically creates test sets for accuracy evaluation
      - All processing appears in Test Studio dashboard for analysis and comparison

    Examples:

      # Process from manifest file
      idp-cli run-inference --stack-name my-stack --manifest docs.csv --monitor

      # Process all PDFs in local directory
      idp-cli run-inference --stack-name my-stack --dir ./documents/ --monitor

      # Process with custom batch ID
      idp-cli run-inference --stack-name my-stack --dir ./docs/ --batch-id my-experiment-v1 --monitor

      # Process S3 URI (any bucket)
      idp-cli run-inference --stack-name my-stack --s3-uri s3://data-lake/archive/2024/ --monitor

      # Process with file pattern
      idp-cli run-inference --stack-name my-stack --dir ./docs/ --file-pattern "invoice*.pdf"

      # Process test set (integrates with Test Studio UI - use test set ID)
      idp-cli run-inference --stack-name my-stack --test-set fcc-example-test --monitor

      # Process test set with custom context
      idp-cli run-inference --stack-name my-stack --test-set fcc-example-test --context "Experiment v2.1" --monitor

      # Process test set with limited files for quick testing
      idp-cli run-inference --stack-name my-stack --test-set fcc-example-test --number-of-files 5 --monitor

      # Process manifest with baselines (automatically creates "idp-cli" test set for Test Studio integration)
      idp-cli run-inference --stack-name my-stack --manifest docs_with_baselines.csv --monitor
    """
    try:
        # Validate mutually exclusive options
        sources = [manifest, directory, s3_uri, test_set]
        sources_provided = sum(1 for s in sources if s is not None)

        if sources_provided == 0:
            console.print(
                "[red]✗ Error: Must specify exactly one source: --manifest, --dir, --s3-uri, or --test-set[/red]"
            )
            sys.exit(1)
        elif sources_provided > 1:
            console.print(
                "[red]✗ Error: Cannot specify more than one of: --manifest, --dir, --s3-uri, --test-set[/red]"
            )
            sys.exit(1)

        # Validate number_of_files parameter
        if number_of_files is not None:
            if number_of_files <= 0:
                console.print(
                    "[red]✗ Error: --number-of-files must be greater than 0[/red]"
                )
                sys.exit(1)

        # Validate manifest if provided
        if manifest:
            console.print("[bold blue]Validating manifest...[/bold blue]")
            is_valid, error = validate_manifest(manifest)
            if not is_valid:
                console.print(f"[red]✗ Manifest validation failed: {error}[/red]")
                sys.exit(1)

            # Validate number_of_files against manifest size
            if number_of_files is not None:
                from .manifest_parser import parse_manifest

                documents = parse_manifest(manifest)
                if number_of_files > len(documents):
                    console.print(
                        f"[red]✗ Error: --number-of-files ({number_of_files}) cannot exceed manifest size ({len(documents)})[/red]"
                    )
                    sys.exit(1)
            console.print("[green]✓ Manifest validated successfully[/green]")

        # Initialize processor
        console.print(
            f"[bold blue]Initializing batch processor for stack: {stack_name}[/bold blue]"
        )
        processor = BatchProcessor(
            stack_name=stack_name, config_path=config, region=region
        )

        # Process batch based on source type
        with console.status("[bold green]Processing batch..."):
            if test_set:
                batch_result = _process_test_set(
                    stack_name, test_set, context, region, processor, number_of_files
                )
            elif manifest:
                # Check if manifest has baselines for test studio integration
                has_baselines = _manifest_has_baselines(manifest)

                if has_baselines:
                    # Create test set and copy files for test studio integration
                    test_set_name = "idp-cli"
                    _create_test_set_from_manifest(
                        manifest, test_set_name, stack_name, region, processor.resources
                    )

                    # Use common test set processing logic
                    batch_result = _process_test_set(
                        stack_name,
                        test_set_name,
                        context,
                        region,
                        processor,
                        number_of_files,
                    )
                else:
                    # Normal manifest processing without test studio
                    batch_result = processor.process_batch(
                        manifest_path=manifest,
                        output_prefix=batch_prefix,
                        batch_id=batch_id,
                        number_of_files=number_of_files,
                    )
            elif directory:
                batch_result = processor.process_batch_from_directory(
                    dir_path=directory,
                    file_pattern=file_pattern,
                    recursive=recursive,
                    output_prefix=batch_prefix,
                    batch_id=batch_id,
                    number_of_files=number_of_files,
                )
            else:  # s3_uri
                batch_result = processor.process_batch_from_s3_uri(
                    s3_uri=s3_uri,
                    file_pattern=file_pattern,
                    recursive=recursive,
                    output_prefix=batch_prefix,
                    batch_id=batch_id,
                )

        # Show submission results
        display.show_batch_submission_summary(batch_result)

        if monitor:
            # Monitor until completion
            _monitor_progress(
                stack_name=stack_name,
                batch_id=batch_result["batch_id"],
                document_ids=batch_result["document_ids"],
                refresh_interval=refresh_interval,
                region=region,
                resources=processor.resources,
            )
        else:
            # Show how to monitor later
            display.show_monitoring_instructions(stack_name, batch_result["batch_id"])

    except Exception as e:
        logger.error(f"Error processing batch: {e}", exc_info=True)
        console.print(f"[red]✗ Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--stack-name", required=True, help="CloudFormation stack name")
@click.option("--batch-id", help="Batch identifier")
@click.option("--document-id", help="Single document ID (alternative to --batch-id)")
@click.option("--wait", is_flag=True, help="Wait for all documents to complete")
@click.option(
    "--refresh-interval",
    default=5,
    type=int,
    help="Seconds between status checks (default: 5)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format: table (default) or json",
)
@click.option("--region", help="AWS region (optional)")
def status(
    stack_name: str,
    batch_id: Optional[str],
    document_id: Optional[str],
    wait: bool,
    refresh_interval: int,
    output_format: str,
    region: Optional[str],
):
    """
    Check status of a batch or single document

    Specify ONE of:
      --batch-id: Check status of all documents in a batch
      --document-id: Check status of a single document

    Examples:

      # Check batch status
      idp-cli status --stack-name my-stack --batch-id cli-batch-20250110-153045-abc12345

      # Check single document status
      idp-cli status --stack-name my-stack --document-id batch-123/invoice.pdf

      # Monitor single document until completion
      idp-cli status --stack-name my-stack --document-id batch-123/invoice.pdf --wait

      # Get JSON output for scripting
      idp-cli status --stack-name my-stack --document-id batch-123/invoice.pdf --format json
    """
    try:
        # Validate mutually exclusive options
        if not batch_id and not document_id:
            console.print(
                "[red]✗ Error: Must specify either --batch-id or --document-id[/red]"
            )
            sys.exit(1)

        if batch_id and document_id:
            console.print(
                "[red]✗ Error: Cannot specify both --batch-id and --document-id[/red]"
            )
            sys.exit(1)

        # Initialize processor to get resources
        processor = BatchProcessor(stack_name=stack_name, region=region)

        # Get document IDs to monitor
        if batch_id:
            # Get batch info
            batch_info = processor.get_batch_info(batch_id)
            if not batch_info:
                console.print(f"[red]✗ Batch not found: {batch_id}[/red]")
                sys.exit(1)
            document_ids = batch_info["document_ids"]
            identifier = batch_id
        else:
            # Single document
            document_ids = [document_id]
            identifier = document_id

        if wait:
            # JSON format not compatible with live monitoring
            if output_format == "json":
                console.print(
                    "[yellow]Warning: --format json ignored with --wait (using table display for live monitoring)[/yellow]"
                )
                console.print()

            # Monitor until completion
            _monitor_progress(
                stack_name=stack_name,
                batch_id=identifier,
                document_ids=document_ids,
                refresh_interval=refresh_interval,
                region=region,
                resources=processor.resources,
            )
        else:
            # Show current status once
            monitor = ProgressMonitor(
                stack_name=stack_name, resources=processor.resources, region=region
            )
            status_data = monitor.get_batch_status(document_ids)
            stats = monitor.calculate_statistics(status_data)

            if output_format == "json":
                # JSON output for programmatic use
                json_output = display.format_status_json(status_data, stats)
                console.print(json_output)

                # Determine exit code from JSON
                import json as json_module

                result = json_module.loads(json_output)
                sys.exit(result.get("exit_code", 2))
            else:
                # Table output for human viewing
                console.print()
                if batch_id:
                    console.print(f"[bold blue]Batch: {batch_id}[/bold blue]")
                else:
                    console.print(f"[bold blue]Document: {document_id}[/bold blue]")

                display.display_status_table(status_data)

                # Show statistics
                console.print(display.create_statistics_panel(stats))

                # Show final status summary and exit with appropriate code
                exit_code = display.show_final_status_summary(status_data, stats)
                sys.exit(exit_code)

    except Exception as e:
        logger.error(f"Error checking status: {e}", exc_info=True)
        console.print(f"[red]✗ Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--stack-name", required=True, help="CloudFormation stack name")
@click.option("--limit", default=10, type=int, help="Maximum number of batches to list")
@click.option("--region", help="AWS region (optional)")
def list_batches(stack_name: str, limit: int, region: Optional[str]):
    """
    List recent batch processing jobs

    Example:

      idp-cli list-batches --stack-name my-stack --limit 5
    """
    try:
        processor = BatchProcessor(stack_name=stack_name, region=region)
        batches = processor.list_batches(limit=limit)

        if not batches:
            console.print("[yellow]No batches found[/yellow]")
            return

        # Create table
        table = Table(title=f"Recent Batches (Last {limit})", show_header=True)
        table.add_column("Batch ID", style="cyan")
        table.add_column("Documents", justify="right")
        table.add_column("Queued", justify="right")
        table.add_column("Failed", justify="right")
        table.add_column("Timestamp")

        for batch in batches:
            table.add_row(
                batch["batch_id"],
                str(len(batch["document_ids"])),
                str(batch["queued"]),
                str(batch["failed"]),
                batch["timestamp"][:19],  # Trim timestamp
            )

        console.print()
        console.print(table)
        console.print()

    except Exception as e:
        logger.error(f"Error listing batches: {e}", exc_info=True)
        console.print(f"[red]✗ Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--stack-name", required=True, help="CloudFormation stack name")
@click.option("--batch-id", required=True, help="Batch identifier")
@click.option(
    "--output-dir",
    required=True,
    type=click.Path(),
    help="Output directory for downloaded results",
)
@click.option(
    "--file-types",
    default="all",
    help="File types to download: pages, sections, summary, evaluation, or 'all' (default: all)",
)
@click.option("--region", help="AWS region (optional)")
def download_results(
    stack_name: str,
    batch_id: str,
    output_dir: str,
    file_types: str,
    region: Optional[str],
):
    """
    Download processing results from OutputBucket

    Examples:

      # Download all results
      idp-cli download-results --stack-name my-stack --batch-id cli-batch-20251015-143000 --output-dir ./results/

      # Download only extraction results (sections)
      idp-cli download-results --stack-name my-stack --batch-id <id> --output-dir ./results/ --file-types sections

      # Download evaluations only
      idp-cli download-results --stack-name my-stack --batch-id <id> --output-dir ./results/ --file-types evaluation
    """
    try:
        console.print(
            f"[bold blue]Downloading results for batch: {batch_id}[/bold blue]"
        )

        processor = BatchProcessor(stack_name=stack_name, region=region)

        # Parse file types
        if file_types == "all":
            types_list = ["pages", "sections", "summary", "evaluation"]
        else:
            types_list = [t.strip() for t in file_types.split(",")]

        # Download results
        result = processor.download_batch_results(
            batch_id=batch_id, output_dir=output_dir, file_types=types_list
        )

        console.print(
            f"\n[green]✓ Downloaded {result['files_downloaded']} files to {output_dir}[/green]"
        )
        console.print(f"  Documents: {result['documents_downloaded']}")
        console.print(f"  Output: {output_dir}/{batch_id}/")
        console.print()

    except Exception as e:
        logger.error(f"Error downloading results: {e}", exc_info=True)
        console.print(f"[red]✗ Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option(
    "--dir",
    "directory",
    type=click.Path(exists=True, file_okay=False),
    help="Local directory to scan",
)
@click.option("--s3-uri", help="S3 URI to scan (e.g., s3://bucket/prefix/)")
@click.option(
    "--baseline-dir",
    type=click.Path(exists=True, file_okay=False),
    help="Baseline directory to auto-match (only with --dir)",
)
@click.option(
    "--output",
    type=click.Path(),
    help="Output manifest file path (CSV) - optional when using --test-set",
)
@click.option("--file-pattern", default="*.pdf", help="File pattern (default: *.pdf)")
@click.option(
    "--recursive/--no-recursive",
    default=True,
    help="Include subdirectories (default: recursive)",
)
@click.option("--region", help="AWS region (optional)")
@click.option(
    "--test-set",
    help="Test set name - creates folder in test set bucket and uploads files (backend generates ID)",
)
@click.option(
    "--stack-name", help="CloudFormation stack name (required with --test-set)"
)
def generate_manifest(
    directory: Optional[str],
    s3_uri: Optional[str],
    baseline_dir: Optional[str],
    output: Optional[str],
    file_pattern: str,
    recursive: bool,
    region: Optional[str],
    test_set: Optional[str],
    stack_name: Optional[str],
):
    """
    Generate a manifest file from directory or S3 URI

    The manifest can then be edited to add baseline_source or customize document_id values.
    Use --baseline-dir to automatically match baseline directories by document ID.
    Use --test-set to upload files to test set bucket and create test set folder structure.

    Examples:

      # Generate from local directory
      idp-cli generate-manifest --dir ./documents/ --output manifest.csv

      # With automatic baseline matching
      idp-cli generate-manifest --dir ./documents/ --baseline-dir ./baselines/ --output manifest.csv

      # Generate from S3 URI
      idp-cli generate-manifest --s3-uri s3://bucket/prefix/ --output manifest.csv

      # With file pattern
      idp-cli generate-manifest --dir ./docs/ --output manifest.csv --file-pattern "W2*.pdf"

      # Create test set and upload files (output optional) - use test set name
      idp-cli generate-manifest --dir ./documents/ --baseline-dir ./baselines/ --test-set "fcc example test" --stack-name IDP

      # Create test set with baseline matching and manifest output
      idp-cli generate-manifest --dir ./documents/ --baseline-dir ./baselines/ --test-set "fcc example test" --stack-name IDP --output manifest.csv
    """
    try:
        import csv
        import os

        # Validate test set requirements
        if test_set and not stack_name:
            console.print(
                "[red]✗ Error: --stack-name is required when using --test-set[/red]"
            )
            sys.exit(1)

        if test_set and not baseline_dir:
            console.print(
                "[red]✗ Error: --baseline-dir is required when using --test-set[/red]"
            )
            sys.exit(1)

        if test_set and s3_uri:
            console.print(
                "[red]✗ Error: --test-set requires --dir (not --s3-uri) to work with --baseline-dir[/red]"
            )
            sys.exit(1)

        # Validate output requirements
        if not test_set and not output:
            console.print(
                "[red]✗ Error: --output is required when not using --test-set[/red]"
            )
            sys.exit(1)

        # Validate mutually exclusive options
        if not directory and not s3_uri:
            console.print("[red]✗ Error: Must specify either --dir or --s3-uri[/red]")
            sys.exit(1)
        if directory and s3_uri:
            console.print("[red]✗ Error: Cannot specify both --dir and --s3-uri[/red]")
            sys.exit(1)

        # Import here to avoid circular dependency during scanning

        documents = []

        # Initialize test set bucket info if needed
        test_set_bucket = None
        s3_client = None
        if test_set:
            import boto3

            from .stack_info import StackInfo

            stack_info = StackInfo(stack_name, region)
            resources = stack_info.get_resources()
            test_set_bucket = resources.get("TestSetBucket")
            if not test_set_bucket:
                console.print(
                    "[red]✗ Error: TestSetBucket not found in stack resources[/red]"
                )
                sys.exit(1)

            s3_client = boto3.client("s3", region_name=region)
            console.print(f"[bold blue]Test set bucket: {test_set_bucket}[/bold blue]")

        if directory:
            console.print(f"[bold blue]Scanning directory: {directory}[/bold blue]")

            # Import scan method directly
            import glob as glob_module

            dir_path = os.path.abspath(directory)
            if recursive:
                search_pattern = os.path.join(dir_path, "**", file_pattern)
            else:
                search_pattern = os.path.join(dir_path, file_pattern)

            for file_path in glob_module.glob(search_pattern, recursive=recursive):
                if os.path.isfile(file_path):
                    documents.append({"document_path": file_path})
        else:  # s3_uri
            console.print(f"[bold blue]Scanning S3 URI: {s3_uri}[/bold blue]")

            # Parse S3 URI
            if not s3_uri.startswith("s3://"):
                console.print("[red]✗ Error: Invalid S3 URI[/red]")
                sys.exit(1)

            uri_parts = s3_uri[5:].split("/", 1)
            bucket = uri_parts[0]
            prefix = uri_parts[1] if len(uri_parts) > 1 else ""

            # List S3 objects
            import fnmatch

            import boto3

            s3 = boto3.client("s3", region_name=region)
            paginator = s3.get_paginator("list_objects_v2")

            if prefix and not prefix.endswith("/"):
                prefix = prefix + "/"

            pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

            for page in pages:
                for obj in page.get("Contents", []):
                    key = obj["Key"]

                    if key.endswith("/"):
                        continue

                    if not recursive:
                        rel_key = key[len(prefix) :]
                        if "/" in rel_key:
                            continue

                    filename = os.path.basename(key)
                    if not fnmatch.fnmatch(filename, file_pattern):
                        continue

                    full_uri = f"s3://{bucket}/{key}"

                    documents.append({"document_path": full_uri})

        if not documents:
            console.print("[yellow]No documents found[/yellow]")
            sys.exit(1)

        console.print(f"Found {len(documents)} documents")

        # Match baselines if baseline_dir provided
        baseline_map = {}
        if baseline_dir:
            if s3_uri:
                console.print(
                    "[yellow]Warning: --baseline-dir only works with --dir, ignoring[/yellow]"
                )
            else:
                console.print(
                    f"[bold blue]Matching baselines from: {baseline_dir}[/bold blue]"
                )

                import os

                baseline_path = os.path.abspath(baseline_dir)

                # Scan for baseline subdirectories
                for item in os.listdir(baseline_path):
                    item_path = os.path.join(baseline_path, item)
                    if os.path.isdir(item_path):
                        baseline_map[item] = item_path

                console.print(f"Found {len(baseline_map)} baseline directories")

                # Show matching statistics
                matched = 0
                for doc in documents:
                    filename = os.path.basename(doc["document_path"])
                    if filename in baseline_map:
                        matched += 1

                console.print(
                    f"Matched {matched}/{len(documents)} documents to baselines"
                )
                console.print()

        # Upload to test set bucket if test_set is specified
        if test_set:
            # Check if test set already exists
            try:
                response = s3_client.list_objects_v2(
                    Bucket=test_set_bucket, Prefix=f"{test_set}/", MaxKeys=1
                )
                if response.get("Contents"):
                    console.print(
                        f"[yellow]Warning: Test set '{test_set}' already exists in bucket[/yellow]"
                    )
                    console.print(
                        "[yellow]Files will be overwritten. Continue? [y/N][/yellow]",
                        end=" ",
                    )

                    response = input().strip().lower()
                    if response not in ["y", "yes"]:
                        console.print("[red]✗ Aborted[/red]")
                        sys.exit(1)
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Could not check existing test set: {e}[/yellow]"
                )

            console.print(
                f"[bold blue]Uploading files to test set: {test_set}[/bold blue]"
            )

            # Clear existing test set folder if it exists
            try:
                response = s3_client.list_objects_v2(
                    Bucket=test_set_bucket, Prefix=f"{test_set}/"
                )

                if "Contents" in response:
                    # Delete all existing objects in the test set folder
                    objects_to_delete = [
                        {"Key": obj["Key"]} for obj in response["Contents"]
                    ]

                    if objects_to_delete:
                        s3_client.delete_objects(
                            Bucket=test_set_bucket,
                            Delete={"Objects": objects_to_delete},
                        )
                        console.print(
                            f"  Cleared {len(objects_to_delete)} existing files"
                        )

            except Exception as e:
                console.print(
                    f"[yellow]Warning: Could not clear existing files: {e}[/yellow]"
                )

            # Upload input documents
            for i, doc in enumerate(documents):
                doc_path = doc["document_path"]
                filename = os.path.basename(doc_path)
                s3_key = f"{test_set}/input/{filename}"

                s3_client.upload_file(doc_path, test_set_bucket, s3_key)
                doc["document_path"] = f"s3://{test_set_bucket}/{s3_key}"
                console.print(f"  Uploaded input {i + 1}/{len(documents)}: {filename}")

            # Upload baseline files
            for filename, baseline_path in baseline_map.items():
                # Upload all files in the baseline directory recursively
                import glob as glob_module
                import os

                baseline_files = glob_module.glob(
                    os.path.join(baseline_path, "**", "*"), recursive=True
                )
                for baseline_file in baseline_files:
                    if os.path.isfile(baseline_file):
                        # Preserve directory structure relative to baseline_path
                        rel_path = os.path.relpath(baseline_file, baseline_path)
                        s3_key = f"{test_set}/baseline/{filename}/{rel_path}"
                        s3_client.upload_file(baseline_file, test_set_bucket, s3_key)

                # Update baseline_map to point to S3 location
                baseline_map[filename] = (
                    f"s3://{test_set_bucket}/{test_set}/baseline/{filename}/"
                )
                console.print(f"  Uploaded baseline: {filename}")

        # Write manifest (2 columns only)
        if output:
            with open(output, "w", newline="") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["document_path", "baseline_source"]
                )
                writer.writeheader()
                for doc in documents:
                    # Match baseline using full filename (including extension)
                    filename = os.path.basename(doc["document_path"])
                    baseline_source = baseline_map.get(filename, "")

                    writer.writerow(
                        {
                            "document_path": doc["document_path"],
                            "baseline_source": baseline_source,
                        }
                    )

            console.print(f"[green]✓ Generated manifest: {output}[/green]")
            console.print()

        if test_set:
            # Auto-register test set in tracking table
            from idp_cli.stack_info import StackInfo

            stack_info = StackInfo(stack_name, region=region)
            resources = stack_info.get_resources()
            _invoke_test_set_resolver(stack_name, test_set, region, resources)

            console.print(
                f"[green]✓ Test set '{test_set}' created successfully[/green]"
            )
            console.print(f"  Input files: s3://{test_set_bucket}/{test_set}/input/")
            console.print(
                f"  Baseline files: s3://{test_set_bucket}/{test_set}/baseline/"
            )
            console.print()
            console.print("[bold]Next Steps: Run inference[/bold]")
            console.print(
                f"  - Using test set: [cyan]idp-cli run-inference --test-set {test_set} --stack-name {stack_name} --monitor[/cyan]"
            )
            console.print(
                f"  - With limited files: [cyan]idp-cli run-inference --test-set {test_set} --stack-name {stack_name} --number-of-files {{N}} --monitor[/cyan]"
            )
            if output:
                console.print(
                    f"  - Using manifest: [cyan]idp-cli run-inference --stack-name {stack_name} --manifest {output} --monitor[/cyan]"
                )
                console.print(
                    f"  - With limited files: [cyan]idp-cli run-inference --stack-name {stack_name} --manifest {output} --number-of-files {{N}} --monitor[/cyan]"
                )
        elif baseline_map:
            console.print("[bold]Baseline matching complete[/bold]")
            console.print("Ready to process with evaluations!")
        else:
            console.print("[bold]Next steps:[/bold]")
            console.print(
                "  1. Edit manifest to add baseline_source or customize document_id"
            )
            if output:
                console.print(
                    f"  2. Process: [cyan]idp-cli run-inference --stack-name <stack> --manifest {output}[/cyan]"
                )
        console.print()

    except Exception as e:
        logger.error(f"Error generating manifest: {e}", exc_info=True)
        console.print(f"[red]✗ Error: {e}[/red]")
        sys.exit(1)


@cli.command(name="validate-manifest")
@click.option(
    "--manifest",
    required=True,
    type=click.Path(exists=True),
    help="Path to manifest file to validate",
)
def validate_manifest_cmd(manifest: str):
    """
    Validate a manifest file without processing

    Example:

      idp-cli validate-manifest --manifest documents.csv
    """
    try:
        is_valid, error = validate_manifest(manifest)

        if is_valid:
            console.print(f"[green]✓ Manifest is valid: {manifest}[/green]")
        else:
            console.print("[red]✗ Manifest validation failed:[/red]")
            console.print(f"  {error}")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Error validating manifest: {e}", exc_info=True)
        console.print(f"[red]✗ Error: {e}[/red]")
        sys.exit(1)


def _monitor_progress(
    stack_name: str,
    batch_id: str,
    document_ids: list,
    refresh_interval: int,
    region: Optional[str],
    resources: dict,
):
    """
    Monitor batch progress with live updates

    Args:
        stack_name: CloudFormation stack name
        batch_id: Batch identifier
        document_ids: List of document IDs to monitor
        refresh_interval: Seconds between status checks
        region: AWS region
        resources: Stack resources dictionary
    """
    monitor = ProgressMonitor(stack_name=stack_name, resources=resources, region=region)

    display.show_monitoring_header(batch_id)

    start_time = time.time()

    try:
        with Live(console=console, refresh_per_second=1) as live:
            while True:
                # Get current status
                status_data = monitor.get_batch_status(document_ids)
                stats = monitor.calculate_statistics(status_data)
                elapsed_time = time.time() - start_time

                # Update display
                layout = display.create_live_display(
                    batch_id=batch_id,
                    status_data=status_data,
                    stats=stats,
                    elapsed_time=elapsed_time,
                )
                live.update(layout)

                # Check if all complete
                if stats["all_complete"]:
                    break

                # Wait before next check
                time.sleep(refresh_interval)

    except KeyboardInterrupt:
        logger.info("Monitoring interrupted by user")
        console.print()
        console.print(
            "[yellow]Monitoring stopped. Processing continues in background.[/yellow]"
        )
        display.show_monitoring_instructions(stack_name, batch_id)
        return
    except Exception as e:
        logger.error(f"Monitoring error: {e}", exc_info=True)
        console.print()
        console.print(f"[red]Monitoring error: {e}[/red]")
        console.print("[yellow]You can check status later with:[/yellow]")
        display.show_monitoring_instructions(stack_name, batch_id)
        return

    # Show final summary
    logger.info("Showing final summary")
    elapsed_time = time.time() - start_time
    display.show_final_summary(status_data, stats, elapsed_time)


def _process_test_set(
    stack_name: str,
    test_set_name: str,
    context: Optional[str],
    region: Optional[str],
    processor,
    number_of_files: Optional[int] = None,
):
    """Common function to process test sets"""
    # Auto-detect test set using test_set_resolver lambda
    _invoke_test_set_resolver(stack_name, test_set_name, region, processor.resources)

    # Invoke test runner lambda
    test_run_result = _invoke_test_runner(
        stack_name, test_set_name, context, region, processor.resources, number_of_files
    )
    batch_id = test_run_result["testRunId"]

    # Get document IDs from test set for monitoring
    document_ids = _get_test_set_document_ids(
        stack_name, test_set_name, batch_id, region, processor.resources
    )

    # If numberOfFiles was specified, limit document_ids to match actual queued count
    if (
        number_of_files is not None
        and len(document_ids) > test_run_result["filesCount"]
    ):
        document_ids = document_ids[: test_run_result["filesCount"]]

    # Create mock batch_result for monitoring
    batch_result = {
        "batch_id": batch_id,
        "documents_queued": test_run_result["filesCount"],
        "documents": [],  # Test runner handles document tracking
        "document_ids": document_ids,
        "uploaded": 0,  # No files uploaded by CLI for test sets
        "skipped": 0,
        "failed": 0,
        "queued": test_run_result["filesCount"],  # Files queued by test runner
    }

    return batch_result


def _invoke_test_set_resolver(
    stack_name: str, test_set_name: str, region: Optional[str], resources: dict
):
    """Invoke test set resolver lambda for auto-detection"""
    import json

    import boto3

    lambda_client = boto3.client("lambda", region_name=region)

    # Handle pagination to get all functions - EXACT same logic as test runner
    all_functions = []
    paginator = lambda_client.get_paginator("list_functions")
    for page in paginator.paginate():
        all_functions.extend(page["Functions"])

    test_set_resolver_function = next(
        (
            f["FunctionName"]
            for f in all_functions
            if stack_name in f["FunctionName"]
            and "TestSetResolverFunction" in f["FunctionName"]
        ),
        None,
    )

    if not test_set_resolver_function:
        console.print(
            "[yellow]Warning: TestSetResolverFunction not found, skipping auto-detection[/yellow]"
        )
        return

    # Call getTestSets to trigger auto-detection and registration
    payload = {"info": {"fieldName": "getTestSets"}, "arguments": {}}

    console.print(f"[bold blue]Auto-detecting test set: {test_set_name}[/bold blue]")

    try:
        response = lambda_client.invoke(
            FunctionName=test_set_resolver_function, Payload=json.dumps(payload)
        )

        result = json.loads(response["Payload"].read())

        if response["StatusCode"] == 200:
            console.print("[green]✓ Test set auto-detection completed[/green]")
        else:
            console.print(
                f"[yellow]Warning: Test set resolver failed: {result}[/yellow]"
            )

    except Exception as e:
        console.print(f"[yellow]Warning: Could not auto-detect test set: {e}[/yellow]")


def _invoke_test_runner(
    stack_name: str,
    test_set: str,
    context: Optional[str],
    region: Optional[str],
    resources: dict,
    number_of_files: Optional[int] = None,
):
    """Invoke test runner lambda to start test set processing"""
    import json

    import boto3

    # Find test runner function by name pattern
    lambda_client = boto3.client("lambda", region_name=region)

    # Handle pagination to get all functions
    all_functions = []
    paginator = lambda_client.get_paginator("list_functions")
    for page in paginator.paginate():
        all_functions.extend(page["Functions"])

    test_runner_function = next(
        (
            f["FunctionName"]
            for f in all_functions
            if stack_name in f["FunctionName"]
            and "TestRunnerFunction" in f["FunctionName"]
        ),
        None,
    )

    if not test_runner_function:
        raise ValueError(f"TestRunnerFunction not found for stack {stack_name}")

    # Prepare payload
    payload = {
        "arguments": {
            "input": {
                "testSetId": test_set,
            }
        }
    }

    # Add context if provided
    if context:
        payload["arguments"]["input"]["context"] = context

    # Add numberOfFiles if provided
    if number_of_files is not None:
        payload["arguments"]["input"]["numberOfFiles"] = number_of_files

    console.print(f"[bold blue]Starting test run for test set: {test_set}[/bold blue]")
    if number_of_files:
        console.print(f"[blue]Limiting to {number_of_files} files[/blue]")

    # Invoke test runner lambda
    response = lambda_client.invoke(
        FunctionName=test_runner_function, Payload=json.dumps(payload)
    )

    # Parse response
    result = json.loads(response["Payload"].read())

    if response["StatusCode"] != 200:
        raise ValueError(f"Test runner invocation failed: {result}")

    console.print(f"[green]✓ Test run started: {result['testRunId']}[/green]")
    return result


def _get_test_set_document_ids(
    stack_name: str,
    test_set: str,
    batch_id: str,
    region: Optional[str],
    resources: dict,
):
    """Get document IDs from test set for monitoring"""
    import boto3

    # Get test set bucket from resources
    test_set_bucket = resources.get("TestSetBucket")
    if not test_set_bucket:
        raise ValueError("TestSetBucket not found in stack resources")

    # List files in test set input directory
    s3_client = boto3.client("s3", region_name=region)

    try:
        response = s3_client.list_objects_v2(
            Bucket=test_set_bucket, Prefix=f"{test_set}/input/"
        )

        document_ids = []
        if "Contents" in response:
            for obj in response["Contents"]:
                key = obj["Key"]
                if key.endswith("/"):  # Skip directories
                    continue
                # Create document_id as batch_id/filename
                filename = key.split("/")[-1]
                doc_id = f"{batch_id}/{filename}"
                document_ids.append(doc_id)

        return document_ids

    except Exception as e:
        console.print(
            f"[yellow]Warning: Could not get document IDs from test set: {e}[/yellow]"
        )
        return []  # Return empty list if we can't get IDs


def _manifest_has_baselines(manifest_path: str) -> bool:
    """Check if manifest has baseline_source column populated"""
    import pandas as pd

    try:
        if manifest_path.endswith(".json"):
            df = pd.read_json(manifest_path)
        else:
            df = pd.read_csv(manifest_path)

        return "baseline_source" in df.columns and df["baseline_source"].notna().any()
    except Exception:
        return False


def _create_test_set_from_manifest(
    manifest_path: str,
    test_set_name: str,
    stack_name: str,
    region: Optional[str],
    resources: dict,
):
    """Create test set structure from manifest files"""
    import os

    import boto3
    import pandas as pd

    # Get test set bucket
    test_set_bucket = resources.get("TestSetBucket")
    if not test_set_bucket:
        raise ValueError("TestSetBucket not found in stack resources")

    s3_client = boto3.client("s3", region_name=region)

    # Read manifest
    if manifest_path.endswith(".json"):
        df = pd.read_json(manifest_path)
    else:
        df = pd.read_csv(manifest_path)

    console.print(
        f"[bold blue]Creating test set '{test_set_name}' from manifest...[/bold blue]"
    )

    # Clear existing test set folder if it exists
    try:
        response = s3_client.list_objects_v2(
            Bucket=test_set_bucket, Prefix=f"{test_set_name}/"
        )

        if "Contents" in response:
            # Delete all existing objects in the test set folder
            objects_to_delete = [{"Key": obj["Key"]} for obj in response["Contents"]]

            if objects_to_delete:
                s3_client.delete_objects(
                    Bucket=test_set_bucket,
                    Delete={"Objects": objects_to_delete},
                )
                console.print("  Cleared existing test set files")

    except Exception as e:
        console.print(f"[yellow]Warning: Could not clear existing files: {e}[/yellow]")

    # Copy input files
    for _, row in df.iterrows():
        source_path = row["document_path"]
        filename = os.path.basename(source_path)

        # Upload to test set input directory
        s3_key = f"{test_set_name}/input/{filename}"

        if source_path.startswith("s3://"):
            # Copy from S3 to S3
            source_bucket, source_key = source_path[5:].split("/", 1)
            s3_client.copy_object(
                CopySource={"Bucket": source_bucket, "Key": source_key},
                Bucket=test_set_bucket,
                Key=s3_key,
            )
        else:
            # Upload from local file
            s3_client.upload_file(source_path, test_set_bucket, s3_key)

        # Copy baseline if exists
        if "baseline_source" in row and pd.notna(row["baseline_source"]):
            baseline_path = row["baseline_source"]

            # Upload all files in the baseline directory recursively
            import glob as glob_module

            baseline_files = glob_module.glob(
                os.path.join(baseline_path, "**", "*"), recursive=True
            )
            for baseline_file in baseline_files:
                if os.path.isfile(baseline_file):
                    # Preserve directory structure relative to baseline_path
                    rel_path = os.path.relpath(baseline_file, baseline_path)
                    s3_key = f"{test_set_name}/baseline/{filename}/{rel_path}"
                    s3_client.upload_file(baseline_file, test_set_bucket, s3_key)

    console.print(
        f"[green]✓ Test set '{test_set_name}' created with {len(df)} files[/green]"
    )


def main():
    """Main entry point for the CLI"""
    cli()


if __name__ == "__main__":
    main()
