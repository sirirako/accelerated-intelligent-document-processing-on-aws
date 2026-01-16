# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Lambda function to complete HITL section review."""

import json
import logging
import os
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

dynamodb = boto3.resource("dynamodb")
s3_client = boto3.client("s3")
sfn_client = boto3.client("stepfunctions")

TRACKING_TABLE_NAME = os.environ.get("TRACKING_TABLE_NAME", "")
OUTPUT_BUCKET = os.environ.get("OUTPUT_BUCKET", "")


def handler(event, context):
    """Handle section review completion from AppSync."""
    logger.info(f"Received event: {json.dumps(event)}")

    field_name = event.get("info", {}).get("fieldName", "")
    arguments = event.get("arguments", {})
    object_key = arguments.get("objectKey")
    section_id = arguments.get("sectionId")
    edited_data = arguments.get("editedData")

    # Extract user identity from AppSync event
    identity = event.get("identity", {})
    username = identity.get("username", "")
    user_email = identity.get("claims", {}).get("email", "")
    user_groups = identity.get("claims", {}).get("cognito:groups", [])
    is_admin = "Admin" in user_groups

    if field_name == "claimReview":
        if not object_key:
            raise ValueError("objectKey is required")
        return claim_review(object_key, username, user_email)

    if field_name == "releaseReview":
        if not object_key:
            raise ValueError("objectKey is required")
        return release_review(object_key, username, user_email, is_admin)

    if field_name == "skipAllSectionsReview":
        if not is_admin:
            raise ValueError("Only administrators can skip all sections review")
        if not object_key:
            raise ValueError("objectKey is required")
        return skip_all_sections_review(object_key, username, user_email)

    if not object_key or not section_id:
        raise ValueError("objectKey and sectionId are required")

    return complete_section_review(
        object_key, section_id, edited_data, username, user_email
    )


def complete_section_review(
    object_key, section_id, edited_data=None, username="", user_email=""
):
    """Mark a section as review complete and update document status."""
    logger.info(
        f"Completing review for section {section_id} of document {object_key} by user {username}"
    )

    table = dynamodb.Table(TRACKING_TABLE_NAME)

    # Get current document - use lowercase 'doc#' prefix
    response = table.get_item(Key={"PK": f"doc#{object_key}", "SK": "none"})

    if "Item" not in response:
        raise ValueError(f"Document {object_key} not found")

    doc = response["Item"]
    sections = doc.get("Sections", [])

    # Find the section and get its output URI
    section_output_uri = None
    for section in sections:
        if section.get("Id") == section_id:
            section_output_uri = section.get("OutputJSONUri")
            break

    # Save edited data to S3 if provided
    if edited_data and section_output_uri:
        save_edited_data_to_s3(section_output_uri, edited_data)

    # Get current pending and completed sections
    pending = set(doc.get("HITLSectionsPending", []) or [])
    completed = set(doc.get("HITLSectionsCompleted", []) or [])
    skipped = set(doc.get("HITLSectionsSkipped", []) or [])

    # If HITLSectionsPending was never initialized, initialize it from all sections
    # (excluding the current section being completed and any already completed/skipped)
    if not pending and not completed and not skipped:
        # Initialize pending with all section IDs except the one being completed
        all_section_ids = {
            section.get("Id") for section in sections if section.get("Id")
        }
        pending = all_section_ids - {section_id}
        logger.info(f"Initialized HITLSectionsPending from sections: {pending}")

    # Move section from pending to completed
    if section_id in pending:
        pending.remove(section_id)
    completed.add(section_id)

    # Check if all sections are reviewed (completed or skipped)
    all_completed = len(pending) == 0
    has_skipped = len(skipped) > 0

    # Create review record for this section
    review_record = {
        "sectionId": section_id,
        "reviewedBy": username or "unknown",
        "reviewedByEmail": user_email or "",
        "reviewedAt": datetime.now(timezone.utc).isoformat(),
    }

    # Get existing review history or initialize empty list
    review_history = doc.get("HITLReviewHistory", []) or []
    review_history.append(review_record)

    # Build update expression
    update_expr = "SET HITLSectionsPending = :pending, HITLSectionsCompleted = :completed, HITLReviewHistory = :history, #status = :status"
    expr_values = {
        ":pending": list(pending),
        ":completed": list(completed),
        ":history": review_history,
    }
    expr_names = {"#status": "HITLStatus"}

    if all_completed:
        update_expr += ", HITLCompleted = :hitlCompleted, ObjectStatus = :objStatus"
        expr_values[":hitlCompleted"] = True
        # If any sections were skipped, set status to "Skipped", otherwise "Completed"
        expr_values[":status"] = "Skipped" if has_skipped else "Completed"
        expr_values[":objStatus"] = "SUMMARIZING"
    else:
        expr_values[":status"] = "InProgress"

    logger.info(
        f"Updating HITLStatus to '{expr_values[':status']}' for document {object_key}. "
        f"Pending: {list(pending)}, Completed: {list(completed)}, All done: {all_completed}"
    )

    update_kwargs = {
        "Key": {"PK": f"doc#{object_key}", "SK": "none"},
        "UpdateExpression": update_expr,
        "ExpressionAttributeValues": expr_values,
    }
    if expr_names:
        update_kwargs["ExpressionAttributeNames"] = expr_names

    table.update_item(**update_kwargs)

    logger.info(
        f"Section {section_id} marked complete. Remaining: {len(pending)}. All done: {all_completed}"
    )

    # If all sections are completed, trigger workflow continuation
    if all_completed:
        trigger_workflow_continuation(doc, object_key)

    # Return full document data for subscription to work
    # Get the updated document from DynamoDB
    updated_response = table.get_item(Key={"PK": f"doc#{object_key}", "SK": "none"})
    updated_doc = updated_response.get("Item", {})

    # Use HITLStatus from updated document, fallback to calculated value
    if all_completed:
        hitl_status = updated_doc.get("HITLStatus", "Skipped" if has_skipped else "Completed")
    else:
        hitl_status = updated_doc.get("HITLStatus", "InProgress")

    return {
        "ObjectKey": object_key,
        "ObjectStatus": updated_doc.get("ObjectStatus", ""),
        "InitialEventTime": updated_doc.get("InitialEventTime", ""),
        "QueuedTime": updated_doc.get("QueuedTime", ""),
        "WorkflowStartTime": updated_doc.get("WorkflowStartTime", ""),
        "CompletionTime": updated_doc.get("CompletionTime", ""),
        "WorkflowExecutionArn": updated_doc.get("WorkflowExecutionArn", ""),
        "WorkflowStatus": updated_doc.get("WorkflowStatus", ""),
        "PageCount": updated_doc.get("PageCount", 0),
        "Sections": updated_doc.get("Sections", []),
        "Pages": updated_doc.get("Pages", []),
        "Metering": updated_doc.get("Metering", ""),
        "EvaluationReportUri": updated_doc.get("EvaluationReportUri", ""),
        "EvaluationStatus": updated_doc.get("EvaluationStatus", ""),
        "SummaryReportUri": updated_doc.get("SummaryReportUri", ""),
        "HITLStatus": hitl_status,
        "HITLReviewURL": updated_doc.get("HITLReviewURL", ""),
        "HITLSectionsPending": list(pending),
        "HITLSectionsCompleted": list(completed),
        "HITLSectionsSkipped": updated_doc.get("HITLSectionsSkipped", []),
        "TraceId": updated_doc.get("TraceId", ""),
    }


def save_edited_data_to_s3(s3_uri, edited_data):
    """Save edited JSON data back to S3."""
    try:
        # Parse S3 URI: s3://bucket/key
        if not s3_uri.startswith("s3://"):
            logger.error(f"Invalid S3 URI: {s3_uri}")
            return

        parts = s3_uri[5:].split("/", 1)
        if len(parts) != 2:
            logger.error(f"Invalid S3 URI format: {s3_uri}")
            return

        bucket = parts[0]
        key = parts[1]

        # Parse edited_data if it's a string
        if isinstance(edited_data, str):
            data = json.loads(edited_data)
        else:
            data = edited_data

        # UI sends full JSON structure (with inference_result, explainability_info, etc.)
        # Save it directly - no transformation needed
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(data, indent=2),
            ContentType="application/json",
        )
        logger.info(f"Saved edited data to {s3_uri}")

    except Exception as e:
        logger.error(f"Failed to save edited data to S3: {str(e)}")
        raise


def trigger_workflow_continuation(doc, object_key):
    """Trigger continuation of the Step Functions workflow after HITL completion."""
    task_token = doc.get("HITLTaskToken")

    if not task_token:
        logger.warning(
            f"No task token found for document {object_key}, cannot continue workflow"
        )
        return

    try:
        logger.info(
            f"Sending task success to continue workflow for document {object_key}"
        )
        sfn_client.send_task_success(
            taskToken=task_token,
            output=json.dumps(
                {
                    "HITLCompleted": True,
                    "HITLStatus": "Completed",
                    "ObjectKey": object_key,
                }
            ),
        )
        logger.info(f"Successfully triggered workflow continuation for {object_key}")
    except Exception as e:
        logger.error(f"Failed to continue workflow for document {object_key}: {str(e)}")


def skip_all_sections_review(object_key, username="", user_email=""):
    """Skip all pending section reviews and mark document as complete (Admin only)."""
    logger.info(f"Skipping all sections review for document {object_key} by admin {username}")

    table = dynamodb.Table(TRACKING_TABLE_NAME)

    # Get current document
    response = table.get_item(Key={"PK": f"doc#{object_key}", "SK": "none"})

    if "Item" not in response:
        raise ValueError(f"Document {object_key} not found")

    doc = response["Item"]
    completed = set(doc.get("HITLSectionsCompleted", []) or [])
    existing_skipped = set(doc.get("HITLSectionsSkipped", []) or [])
    
    # Get all section IDs from the document
    sections = doc.get("Sections", [])
    all_section_ids = {section.get("Id") for section in sections if section.get("Id")}
    
    # Sections to skip = all sections that are not already completed
    sections_to_skip = all_section_ids - completed - existing_skipped
    # Combine with any existing skipped sections
    all_skipped = list(sections_to_skip | existing_skipped)

    # Create review record for skip action
    review_record = {
        "sectionId": "ALL_SKIPPED",
        "reviewedBy": username or "unknown",
        "reviewedByEmail": user_email or "",
        "reviewedAt": datetime.now(timezone.utc).isoformat(),
        "action": "skip_all",
        "skippedSections": list(sections_to_skip),
    }

    review_history = doc.get("HITLReviewHistory", []) or []
    review_history.append(review_record)

    # Update document - mark pending sections as skipped, keep completed as is
    table.update_item(
        Key={"PK": f"doc#{object_key}", "SK": "none"},
        UpdateExpression="SET HITLSectionsPending = :pending, HITLSectionsCompleted = :completed, "
        "HITLSectionsSkipped = :skipped, HITLReviewHistory = :history, #status = :status, "
        "HITLCompleted = :hitlCompleted, ObjectStatus = :objStatus",
        ExpressionAttributeValues={
            ":pending": [],
            ":completed": list(completed),
            ":skipped": all_skipped,
            ":history": review_history,
            ":status": "Skipped",
            ":hitlCompleted": True,
            ":objStatus": "SUMMARIZING",
        },
        ExpressionAttributeNames={"#status": "HITLStatus"},
    )

    logger.info(f"All sections skipped for document {object_key}. Skipped: {all_skipped}, Completed: {list(completed)}")

    # Trigger workflow continuation
    trigger_workflow_continuation(doc, object_key)

    # Return updated document
    updated_response = table.get_item(Key={"PK": f"doc#{object_key}", "SK": "none"})
    updated_doc = updated_response.get("Item", {})

    return {
        "ObjectKey": object_key,
        "ObjectStatus": updated_doc.get("ObjectStatus", ""),
        "InitialEventTime": updated_doc.get("InitialEventTime", ""),
        "QueuedTime": updated_doc.get("QueuedTime", ""),
        "WorkflowStartTime": updated_doc.get("WorkflowStartTime", ""),
        "CompletionTime": updated_doc.get("CompletionTime", ""),
        "WorkflowExecutionArn": updated_doc.get("WorkflowExecutionArn", ""),
        "WorkflowStatus": updated_doc.get("WorkflowStatus", ""),
        "PageCount": updated_doc.get("PageCount", 0),
        "Sections": updated_doc.get("Sections", []),
        "Pages": updated_doc.get("Pages", []),
        "Metering": updated_doc.get("Metering", ""),
        "EvaluationReportUri": updated_doc.get("EvaluationReportUri", ""),
        "EvaluationStatus": updated_doc.get("EvaluationStatus", ""),
        "SummaryReportUri": updated_doc.get("SummaryReportUri", ""),
        "HITLStatus": "Skipped",
        "HITLReviewURL": updated_doc.get("HITLReviewURL", ""),
        "HITLSectionsPending": [],
        "HITLSectionsCompleted": list(completed),
        "HITLSectionsSkipped": all_skipped,
        "HITLReviewOwner": updated_doc.get("HITLReviewOwner", ""),
        "HITLReviewOwnerEmail": updated_doc.get("HITLReviewOwnerEmail", ""),
        "HITLReviewHistory": updated_doc.get("HITLReviewHistory", []),
        "TraceId": updated_doc.get("TraceId", ""),
    }


def claim_review(object_key, username="", user_email=""):
    """Claim a document for review (assigns reviewer as owner)."""
    logger.info(f"Claiming review for document {object_key} by {username}")

    table = dynamodb.Table(TRACKING_TABLE_NAME)
    response = table.get_item(Key={"PK": f"doc#{object_key}", "SK": "none"})

    if "Item" not in response:
        raise ValueError(f"Document {object_key} not found")

    doc = response["Item"]
    current_owner = doc.get("HITLReviewOwner", "")

    if current_owner and current_owner != username:
        raise ValueError(f"Document is already claimed by {current_owner}")

    table.update_item(
        Key={"PK": f"doc#{object_key}", "SK": "none"},
        UpdateExpression="SET HITLReviewOwner = :owner, HITLReviewOwnerEmail = :email",
        ExpressionAttributeValues={":owner": username, ":email": user_email},
    )

    logger.info(f"Review claimed for document {object_key} by {username}")
    return build_document_response(object_key)


def release_review(object_key, username="", user_email="", is_admin=False):
    """Release a document review (removes owner assignment)."""
    logger.info(f"Releasing review for document {object_key} by {username}")

    table = dynamodb.Table(TRACKING_TABLE_NAME)
    response = table.get_item(Key={"PK": f"doc#{object_key}", "SK": "none"})

    if "Item" not in response:
        raise ValueError(f"Document {object_key} not found")

    doc = response["Item"]
    current_owner = doc.get("HITLReviewOwner", "")

    if not is_admin and current_owner and current_owner != username:
        raise ValueError("Only the review owner or an admin can release this review")

    table.update_item(
        Key={"PK": f"doc#{object_key}", "SK": "none"},
        UpdateExpression="REMOVE HITLReviewOwner, HITLReviewOwnerEmail",
    )

    logger.info(f"Review released for document {object_key}")
    return build_document_response(object_key)


def build_document_response(object_key):
    """Build standard document response."""
    table = dynamodb.Table(TRACKING_TABLE_NAME)
    response = table.get_item(Key={"PK": f"doc#{object_key}", "SK": "none"})
    doc = response.get("Item", {})

    return {
        "ObjectKey": object_key,
        "ObjectStatus": doc.get("ObjectStatus", ""),
        "InitialEventTime": doc.get("InitialEventTime", ""),
        "QueuedTime": doc.get("QueuedTime", ""),
        "WorkflowStartTime": doc.get("WorkflowStartTime", ""),
        "CompletionTime": doc.get("CompletionTime", ""),
        "WorkflowExecutionArn": doc.get("WorkflowExecutionArn", ""),
        "WorkflowStatus": doc.get("WorkflowStatus", ""),
        "PageCount": doc.get("PageCount", 0),
        "Sections": doc.get("Sections", []),
        "Pages": doc.get("Pages", []),
        "Metering": doc.get("Metering", ""),
        "EvaluationReportUri": doc.get("EvaluationReportUri", ""),
        "EvaluationStatus": doc.get("EvaluationStatus", ""),
        "SummaryReportUri": doc.get("SummaryReportUri", ""),
        "HITLStatus": doc.get("HITLStatus", ""),
        "HITLReviewURL": doc.get("HITLReviewURL", ""),
        "HITLSectionsPending": doc.get("HITLSectionsPending", []),
        "HITLSectionsCompleted": doc.get("HITLSectionsCompleted", []),
        "HITLSectionsSkipped": doc.get("HITLSectionsSkipped", []),
        "HITLReviewOwner": doc.get("HITLReviewOwner", ""),
        "HITLReviewOwnerEmail": doc.get("HITLReviewOwnerEmail", ""),
        "HITLReviewHistory": doc.get("HITLReviewHistory", []),
        "TraceId": doc.get("TraceId", ""),
    }
