# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Module for saving document data to reporting storage.
"""

import datetime
import io
import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import boto3
import pyarrow as pa
import pyarrow.parquet as pq

from idp_common.models import Document
from idp_common.s3 import get_json_content

# Configure logging
logger = logging.getLogger(__name__)


class SaveReportingData:
    """
    Class for saving document data to reporting storage.

    This class provides methods to save different types of document data
    to a reporting bucket in Parquet format for analytics.
    """

    def __init__(self, reporting_bucket: str):
        """
        Initialize the SaveReportingData class.

        Args:
            reporting_bucket: S3 bucket name for reporting data
        """
        self.reporting_bucket = reporting_bucket
        self.s3_client = boto3.client("s3")

    def _serialize_value(self, value: Any) -> str:
        """
        Serialize complex values for Parquet storage as strings.

        Args:
            value: The value to serialize

        Returns:
            Serialized value as string, or None if input is None
        """
        if value is None:
            return None
        elif isinstance(value, str):
            return value
        elif isinstance(value, (int, float, bool)):
            # Convert numeric/boolean values to strings
            return str(value)
        elif isinstance(value, (list, dict)):
            # Convert complex types to JSON strings
            return json.dumps(value)
        else:
            # Convert other types to string
            return str(value)

    def _save_records_as_parquet(
        self, records: List[Dict], s3_key: str, schema: pa.Schema
    ) -> None:
        """
        Save a list of records as a Parquet file to S3 with explicit schema.

        Args:
            records: List of dictionaries to save
            s3_key: S3 key path
            schema: PyArrow schema for the table
        """
        if not records:
            logger.warning("No records to save")
            return

        # Create PyArrow table from records with explicit schema
        table = pa.Table.from_pylist(records, schema=schema)

        # Create in-memory buffer
        buffer = io.BytesIO()

        # Write parquet data to buffer
        pq.write_table(table, buffer, compression="snappy")

        # Upload to S3
        buffer.seek(0)
        self.s3_client.put_object(
            Bucket=self.reporting_bucket,
            Key=s3_key,
            Body=buffer.getvalue(),
            ContentType="application/octet-stream",
        )
        logger.info(
            f"Saved {len(records)} records as Parquet to s3://{self.reporting_bucket}/{s3_key}"
        )

    def _parse_s3_uri(self, uri: str) -> tuple:
        """
        Parse an S3 URI into bucket and key.

        Args:
            uri: S3 URI in the format s3://bucket/key

        Returns:
            Tuple of (bucket, key)
        """
        parsed = urlparse(uri)
        if parsed.scheme != "s3":
            raise ValueError(f"Not an S3 URI: {uri}")

        bucket = parsed.netloc
        # Remove leading slash from key
        key = parsed.path.lstrip("/")

        return bucket, key

    def save(self, document: Document, data_to_save: List[str]) -> List[Dict[str, Any]]:
        """
        Save document data based on the data_to_save list.

        Args:
            document: Document object containing data to save
            data_to_save: List of data types to save

        Returns:
            List of results from each save operation
        """
        results = []

        # Process each data type based on data_to_save
        if "evaluation_results" in data_to_save:
            logger.info("Processing evaluation results")
            result = self.save_evaluation_results(document)
            if result:
                results.append(result)

        if "metering" in data_to_save:
            logger.info("Processing metering data")
            result = self.save_metering_data(document)
            if result:
                results.append(result)

        # Add more data types here as needed
        # if 'document_metadata' in data_to_save:
        #     logger.info("Processing document metadata")
        #     result = self.save_document_metadata(document)
        #     if result:
        #         results.append(result)

        return results

    def save_evaluation_results(self, document: Document) -> Optional[Dict[str, Any]]:
        """
        Save evaluation results for a document to the reporting bucket.

        Args:
            document: Document object containing evaluation results URI

        Returns:
            Dict with status and message, or None if no evaluation results
        """
        if not document.evaluation_results_uri:
            warning_msg = (
                f"No evaluation_results_uri available for document {document.id}"
            )
            logger.warning(warning_msg)
            return None

        try:
            # Load evaluation results from S3
            logger.info(
                f"Loading evaluation results from {document.evaluation_results_uri}"
            )
            eval_result = get_json_content(document.evaluation_results_uri)

            if not eval_result:
                warning_msg = f"Empty evaluation results for document {document.id}"
                logger.warning(warning_msg)
                return None

        except Exception as e:
            error_msg = f"Error loading evaluation results from {document.evaluation_results_uri}: {str(e)}"
            logger.error(error_msg)
            return {"statusCode": 500, "body": error_msg}

        # Define schemas specific to evaluation results
        document_schema = pa.schema(
            [
                ("document_id", pa.string()),
                ("input_key", pa.string()),
                ("evaluation_date", pa.timestamp("ms")),
                ("accuracy", pa.float64()),
                ("precision", pa.float64()),
                ("recall", pa.float64()),
                ("f1_score", pa.float64()),
                ("false_alarm_rate", pa.float64()),
                ("false_discovery_rate", pa.float64()),
                ("execution_time", pa.float64()),
            ]
        )

        section_schema = pa.schema(
            [
                ("document_id", pa.string()),
                ("section_id", pa.string()),
                ("section_type", pa.string()),
                ("accuracy", pa.float64()),
                ("precision", pa.float64()),
                ("recall", pa.float64()),
                ("f1_score", pa.float64()),
                ("false_alarm_rate", pa.float64()),
                ("false_discovery_rate", pa.float64()),
                ("evaluation_date", pa.timestamp("ms")),
            ]
        )

        attribute_schema = pa.schema(
            [
                ("document_id", pa.string()),
                ("section_id", pa.string()),
                ("section_type", pa.string()),
                ("attribute_name", pa.string()),
                ("expected", pa.string()),
                ("actual", pa.string()),
                ("matched", pa.bool_()),
                ("score", pa.float64()),
                ("reason", pa.string()),
                ("evaluation_method", pa.string()),
                ("confidence", pa.string()),
                ("confidence_threshold", pa.string()),
                ("evaluation_date", pa.timestamp("ms")),
            ]
        )

        # Use document.initial_event_time if available, otherwise use current time
        if document.initial_event_time:
            try:
                # Try to parse the initial_event_time string into a datetime object
                doc_time = datetime.datetime.fromisoformat(
                    document.initial_event_time.replace("Z", "+00:00")
                )
                evaluation_date = doc_time
                year, month, day = (
                    doc_time.strftime("%Y"),
                    doc_time.strftime("%Y-%m"),
                    doc_time.strftime("%Y-%m-%d"),
                )
                logger.info(
                    f"Using document initial_event_time: {document.initial_event_time} for partitioning"
                )
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Could not parse document.initial_event_time: {document.initial_event_time}, using current time instead. Error: {str(e)}"
                )
                evaluation_date = datetime.datetime.now()
                year, month, day = (
                    evaluation_date.strftime("%Y"),
                    evaluation_date.strftime("%Y-%m"),
                    evaluation_date.strftime("%Y-%m-%d"),
                )
        else:
            logger.warning(
                "Document initial_event_time not available, using current time instead"
            )
            evaluation_date = datetime.datetime.now()
            year, month, day = (
                evaluation_date.strftime("%Y"),
                evaluation_date.strftime("%Y-%m"),
                evaluation_date.strftime("%Y-%m-%d"),
            )

        # Escape document ID by replacing slashes with underscores
        document_id = document.id
        escaped_doc_id = re.sub(r"[/\\]", "_", document_id)

        # 1. Document level metrics
        document_record = {
            "document_id": document_id,
            "input_key": document.input_key,
            "evaluation_date": evaluation_date,  # Use document's initial_event_time
            "accuracy": eval_result.get("overall_metrics", {}).get("accuracy", 0.0),
            "precision": eval_result.get("overall_metrics", {}).get("precision", 0.0),
            "recall": eval_result.get("overall_metrics", {}).get("recall", 0.0),
            "f1_score": eval_result.get("overall_metrics", {}).get("f1_score", 0.0),
            "false_alarm_rate": eval_result.get("overall_metrics", {}).get(
                "false_alarm_rate", 0.0
            ),
            "false_discovery_rate": eval_result.get("overall_metrics", {}).get(
                "false_discovery_rate", 0.0
            ),
            "execution_time": eval_result.get("execution_time", 0.0),
        }

        # Save document metrics in Parquet format
        doc_key = f"evaluation_metrics/document_metrics/year={year}/month={month}/day={day}/document={escaped_doc_id}/results.parquet"
        self._save_records_as_parquet([document_record], doc_key, document_schema)

        # 2. Section level metrics
        section_records = []
        # 3. Attribute level records
        attribute_records = []

        # Log section results count
        section_results = eval_result.get("section_results", [])
        logger.info(f"Processing {len(section_results)} section results")

        for section_result in section_results:
            section_id = section_result.get("section_id")
            section_type = section_result.get("document_class", "")

            # Section record
            section_record = {
                "document_id": document_id,
                "section_id": section_id,
                "section_type": section_type,
                "accuracy": section_result.get("metrics", {}).get("accuracy", 0.0),
                "precision": section_result.get("metrics", {}).get("precision", 0.0),
                "recall": section_result.get("metrics", {}).get("recall", 0.0),
                "f1_score": section_result.get("metrics", {}).get("f1_score", 0.0),
                "false_alarm_rate": section_result.get("metrics", {}).get(
                    "false_alarm_rate", 0.0
                ),
                "false_discovery_rate": section_result.get("metrics", {}).get(
                    "false_discovery_rate", 0.0
                ),
                "evaluation_date": evaluation_date,  # Use document's initial_event_time
            }
            section_records.append(section_record)

            # Log section metrics
            logger.debug(
                f"Added section record for section_id={section_id}, section_type={section_type}"
            )

            # Attribute records
            attributes = section_result.get("attributes", [])
            logger.debug(f"Section {section_id} has {len(attributes)} attributes")

            for attr in attributes:
                attribute_record = {
                    "document_id": document_id,
                    "section_id": section_id,
                    "section_type": section_type,
                    "attribute_name": self._serialize_value(attr.get("name", "")),
                    "expected": self._serialize_value(attr.get("expected", "")),
                    "actual": self._serialize_value(attr.get("actual", "")),
                    "matched": attr.get("matched", False),
                    "score": attr.get("score", 0.0),
                    "reason": self._serialize_value(attr.get("reason", "")),
                    "evaluation_method": self._serialize_value(
                        attr.get("evaluation_method", "")
                    ),
                    "confidence": self._serialize_value(attr.get("confidence")),
                    "confidence_threshold": self._serialize_value(
                        attr.get("confidence_threshold")
                    ),
                    "evaluation_date": evaluation_date,  # Use document's initial_event_time
                }
                attribute_records.append(attribute_record)
                logger.debug(
                    f"Added attribute record for attribute_name={attr.get('name', '')}"
                )

        # Log counts
        logger.info(
            f"Collected {len(section_records)} section records and {len(attribute_records)} attribute records"
        )

        # Save section metrics in Parquet format
        if section_records:
            section_key = f"evaluation_metrics/section_metrics/year={year}/month={month}/day={day}/document={escaped_doc_id}/results.parquet"
            self._save_records_as_parquet(section_records, section_key, section_schema)
        else:
            logger.warning("No section records to save")

        # Save attribute metrics in Parquet format
        if attribute_records:
            attr_key = f"evaluation_metrics/attribute_metrics/year={year}/month={month}/day={day}/document={escaped_doc_id}/results.parquet"
            self._save_records_as_parquet(attribute_records, attr_key, attribute_schema)
        else:
            logger.warning("No attribute records to save")

        logger.info(
            f"Completed saving evaluation results to s3://{self.reporting_bucket}"
        )

        return {
            "statusCode": 200,
            "body": "Successfully saved evaluation results to reporting bucket",
        }

    def save_metering_data(self, document: Document) -> Optional[Dict[str, Any]]:
        """
        Save metering data for a document to the reporting bucket.

        Args:
            document: Document object containing metering data

        Returns:
            Dict with status and message, or None if no metering data
        """
        if not document.metering:
            warning_msg = f"No metering data to save for document {document.id}"
            logger.warning(warning_msg)
            return None

        # Define schema for metering data
        metering_schema = pa.schema(
            [
                ("document_id", pa.string()),
                ("context", pa.string()),
                ("service_api", pa.string()),
                ("unit", pa.string()),
                ("value", pa.float64()),
                ("number_of_pages", pa.int32()),
                ("timestamp", pa.timestamp("ms")),
            ]
        )

        # Use document.initial_event_time if available, otherwise use current time
        if document.initial_event_time:
            try:
                # Try to parse the initial_event_time string into a datetime object
                doc_time = datetime.datetime.fromisoformat(
                    document.initial_event_time.replace("Z", "+00:00")
                )
                timestamp = doc_time
                year, month, day = (
                    doc_time.strftime("%Y"),
                    doc_time.strftime("%Y-%m"),
                    doc_time.strftime("%Y-%m-%d"),
                )
                logger.info(
                    f"Using document initial_event_time: {document.initial_event_time} for partitioning"
                )
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Could not parse document.initial_event_time: {document.initial_event_time}, using current time instead. Error: {str(e)}"
                )
                timestamp = datetime.datetime.now()
                year, month, day = (
                    timestamp.strftime("%Y"),
                    timestamp.strftime("%Y-%m"),
                    timestamp.strftime("%Y-%m-%d"),
                )
        else:
            logger.warning(
                "Document initial_event_time not available, using current time instead"
            )
            timestamp = datetime.datetime.now()
            year, month, day = (
                timestamp.strftime("%Y"),
                timestamp.strftime("%Y-%m"),
                timestamp.strftime("%Y-%m-%d"),
            )

        # Escape document ID by replacing slashes with underscores
        document_id = document.id
        escaped_doc_id = re.sub(r"[/\\]", "_", document_id)

        # Process metering data
        metering_records = []

        for key, metrics in document.metering.items():
            # Split the key into context and service_api
            parts = key.split("/", 1)
            if len(parts) == 2:
                context, service_api = parts
            else:
                context = ""
                service_api = key

            # Process each unit and value
            for unit, value in metrics.items():
                # Convert value to float if possible
                try:
                    float_value = float(value)
                except (ValueError, TypeError):
                    # If conversion fails, use 1.0 as default
                    float_value = 1.0
                    logger.warning(
                        f"Could not convert metering value to float: {value}, using 1.0 instead"
                    )

                # Get the number of pages from the document
                num_pages = document.num_pages if document.num_pages is not None else 0

                metering_record = {
                    "document_id": document_id,
                    "context": context,
                    "service_api": service_api,
                    "unit": unit,
                    "value": float_value,
                    "number_of_pages": num_pages,
                    "timestamp": timestamp,
                }
                metering_records.append(metering_record)

        # Save metering data in Parquet format
        if metering_records:
            metering_key = f"metering/year={year}/month={month}/day={day}/document={escaped_doc_id}/results.parquet"
            self._save_records_as_parquet(
                metering_records, metering_key, metering_schema
            )
            logger.info(f"Saved {len(metering_records)} metering records")
        else:
            logger.warning("No metering records to save")

        return {
            "statusCode": 200,
            "body": "Successfully saved metering data to reporting bucket",
        }
