# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Stickler-based Evaluation Service for document extraction results.

This module provides a service for evaluating extraction results using
the Stickler library for structured object comparison.
"""

import concurrent.futures
import logging
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, Tuple, Type, Union

from idp_common import s3
from idp_common.config.models import IDPConfig
from idp_common.evaluation.metrics import calculate_metrics
from idp_common.evaluation.models import (
    AttributeEvaluationResult,
    DocumentEvaluationResult,
    SectionEvaluationResult,
)
from idp_common.evaluation.stickler_mapper import SticklerConfigMapper
from idp_common.models import Document, Section, Status

logger = logging.getLogger(__name__)

# Check if Stickler is available
try:
    from stickler import StructuredModel

    STICKLER_AVAILABLE = True
except ImportError:
    STICKLER_AVAILABLE = False
    logger.warning(
        "Stickler library not available - evaluation features will be limited"
    )


class EvaluationService:
    """
    Stickler-based evaluation service for document extraction results.

    This service maintains the same API as the legacy implementation but uses
    Stickler internally for comparison logic, providing enhanced features like
    field weighting and optimized list matching.
    """

    def __init__(
        self,
        region: Optional[str] = None,
        config: Optional[Union[Dict[str, Any], IDPConfig]] = None,
        max_workers: int = 10,
    ):
        """
        Initialize the evaluation service.

        Args:
            region: AWS region
            config: Configuration dictionary or IDPConfig model containing evaluation settings
            max_workers: Maximum number of concurrent workers for section evaluation
        """
        if not STICKLER_AVAILABLE:
            raise ImportError(
                "Stickler library is required for evaluation. "
                "Install with: pip install -e '.[evaluation]'"
            )

        # Convert dict to IDPConfig if needed
        if config is not None and isinstance(config, dict):
            config_model: IDPConfig = IDPConfig(**config)
        elif config is None:
            config_model = IDPConfig()
        else:
            config_model = config

        self.config = config_model
        self.region = region or os.environ.get("AWS_REGION")
        self.max_workers = max_workers

        # Build Stickler configurations using mapper
        if hasattr(config_model, "dict"):
            config_dict = config_model.dict()
        elif hasattr(config_model, "model_dump"):
            config_dict = config_model.model_dump()
        else:
            # Assume it's already a dict or dict-like
            config_dict = (
                dict(config_model)
                if not isinstance(config_model, dict)
                else config_model
            )

        self.stickler_models = SticklerConfigMapper.build_all_stickler_configs(
            config_dict
        )

        # Cache for Stickler model classes
        self._model_cache: Dict[str, Type[StructuredModel]] = {}

        logger.info(
            f"Initialized Stickler-based evaluation service with "
            f"{len(self.stickler_models)} document classes, max_workers={max_workers}"
        )

    def _get_stickler_model(self, document_class: str) -> Type[StructuredModel]:
        """
        Get or create Stickler model for document class.

        Uses stickler_mapper to translate IDP config to Stickler config,
        then creates dynamic model class using Stickler's model_from_json().

        Args:
            document_class: Document class name

        Returns:
            Stickler StructuredModel class for this document type

        Raises:
            ValueError: If no configuration found for document class
        """
        # Check cache
        cache_key = document_class.lower()
        if cache_key in self._model_cache:
            logger.debug(f"Using cached Stickler model for class: {document_class}")
            return self._model_cache[cache_key]

        # Get Stickler config for this class
        stickler_config = self.stickler_models.get(cache_key)
        if not stickler_config:
            raise ValueError(
                f"No schema configuration found for document class: {document_class}"
            )

        # Create dynamic model using Stickler's JSON Schema construction
        logger.info(f"Creating Stickler model for class: {document_class}")
        model_class = StructuredModel.model_from_json(stickler_config)

        # Cache for reuse
        self._model_cache[cache_key] = model_class
        logger.debug(f"Cached Stickler model: {model_class.__name__}")

        return model_class

    def _prepare_stickler_data(self, uri: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Load extraction results and confidence scores from S3.

        Args:
            uri: S3 URI to the extraction results

        Returns:
            Tuple of (extraction_data, confidence_scores)
        """
        try:
            content = s3.get_json_content(uri)

            # Extract inference result
            if isinstance(content, dict) and "inference_result" in content:
                extraction_data = content["inference_result"]
            else:
                extraction_data = content

            # Extract confidence scores from explainability_info
            confidence_scores = {}
            if isinstance(content, dict) and "explainability_info" in content:
                explainability_info = content["explainability_info"]
                if (
                    isinstance(explainability_info, list)
                    and len(explainability_info) > 0
                ):
                    confidence_scores = explainability_info[0]

            return extraction_data, confidence_scores

        except Exception as e:
            logger.error(
                f"Error loading extraction results from {uri}: {str(e)}", exc_info=True
            )
            return {}, {}

    def _get_nested_value(self, obj: Any, path: str) -> Any:
        """
        Get value from nested object using dot notation path.

        Args:
            obj: Object to extract value from (Stickler model instance or dict)
            path: Dot-notation path (e.g., "address.city" or "items[0].name")

        Returns:
            Value at the specified path, or None if not found
        """
        import re

        try:
            # Handle list indices in path (e.g., "items[0].name")
            parts = []
            for part in path.split("."):
                # Check for list index notation
                match = re.match(r"^([^\[]+)\[(\d+)\]$", part)
                if match:
                    parts.append(("field", match.group(1)))
                    parts.append(("index", int(match.group(2))))
                else:
                    parts.append(("field", part))

            # Navigate through the path
            current = obj
            for part_type, part_value in parts:
                if part_type == "field":
                    if hasattr(current, part_value):
                        current = getattr(current, part_value)
                    elif isinstance(current, dict):
                        current = current.get(part_value)
                    else:
                        return None
                elif part_type == "index":
                    if isinstance(current, (list, tuple)):
                        if part_value < len(current):
                            current = current[part_value]
                        else:
                            return None
                    else:
                        return None

            return current

        except Exception as e:
            logger.debug(f"Error getting nested value for path '{path}': {str(e)}")
            return None

    def _get_confidence_for_field(
        self, confidence_scores: Dict[str, Any], field_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get confidence information for a specific field.

        Args:
            confidence_scores: Nested confidence scores dictionary
            field_name: Field name (may use dot notation or list indices)

        Returns:
            Dictionary with confidence and confidence_threshold, or None
        """
        try:
            # Try to get confidence using the same path logic
            confidence_value = self._get_nested_value(confidence_scores, field_name)

            if isinstance(confidence_value, dict) and "confidence" in confidence_value:
                conf_threshold = confidence_value.get("confidence_threshold")
                return {
                    "confidence": float(confidence_value["confidence"]),
                    "confidence_threshold": float(conf_threshold)
                    if conf_threshold is not None
                    else None,
                }

            return None

        except Exception as e:
            logger.debug(
                f"Error extracting confidence for field '{field_name}': {str(e)}"
            )
            return None

    def _generate_reason(
        self,
        field_name: str,
        expected_value: Any,
        actual_value: Any,
        score: float,
        matched: bool,
        comparator: Optional[str],
    ) -> str:
        """
        Generate a reason explanation for the comparison result.

        Args:
            field_name: Name of the field
            expected_value: Expected value
            actual_value: Actual value
            score: Comparison score
            matched: Whether the values matched
            comparator: Comparator type used

        Returns:
            Reason string explaining the result
        """
        # Check for empty values
        exp_empty = expected_value is None or (
            isinstance(expected_value, str) and not expected_value.strip()
        )
        act_empty = actual_value is None or (
            isinstance(actual_value, str) and not actual_value.strip()
        )

        if exp_empty and act_empty:
            return "Both values are empty"

        if matched:
            if score >= 0.99:
                return "Exact match"
            elif score >= 0.9:
                return f"Very close match (score: {score:.2f})"
            else:
                return f"Match above threshold (score: {score:.2f})"
        else:
            if exp_empty:
                return "Expected value missing but actual value present"
            elif act_empty:
                return "Actual value missing but expected value present"
            else:
                return f"Values do not match (score: {score:.2f}, comparator: {comparator or 'default'})"

    def _transform_stickler_result(
        self,
        section: Section,
        expected_instance: StructuredModel,
        actual_instance: StructuredModel,
        stickler_result: Dict[str, Any],
        confidence_scores: Dict[str, Any],
    ) -> SectionEvaluationResult:
        """
        Transform Stickler comparison result to IDP SectionEvaluationResult.

        Extracts field scores from Stickler, creates AttributeEvaluationResult
        objects, injects confidence scores, and calculates metrics.

        Args:
            section: Document section being evaluated
            expected_instance: Stickler model instance with expected values
            actual_instance: Stickler model instance with actual values
            stickler_result: Result from Stickler's compare_with() method
            confidence_scores: Confidence scores from assessment

        Returns:
            SectionEvaluationResult with all attribute results and metrics
        """
        attribute_results = []

        # Get field scores from Stickler result
        field_scores = stickler_result.get("field_scores", {})

        # Get Stickler configuration for this document class
        stickler_config = self.stickler_models.get(section.classification.lower(), {})
        field_configs = stickler_config.get("fields", {})
        match_threshold = stickler_config.get("match_threshold", 0.8)

        # Track metrics
        tp = fp = fn = tn = fp1 = fp2 = 0

        for field_name, score in field_scores.items():
            # Get field configuration
            field_config = field_configs.get(field_name, {})

            # Extract expected and actual values from instances
            expected_value = self._get_nested_value(expected_instance, field_name)
            actual_value = self._get_nested_value(actual_instance, field_name)

            # Get confidence from assessment if available
            confidence_info = self._get_confidence_for_field(
                confidence_scores, field_name
            )

            # Determine match based on Stickler score and threshold
            field_threshold = field_config.get("threshold", match_threshold)
            matched = score >= field_threshold

            # Check for empty values
            exp_empty = expected_value is None or (
                isinstance(expected_value, str) and not str(expected_value).strip()
            )
            act_empty = actual_value is None or (
                isinstance(actual_value, str) and not str(actual_value).strip()
            )

            # Update metrics
            if exp_empty and act_empty:
                tn += 1
                matched = True  # Both empty is considered a match
            elif exp_empty and not act_empty:
                fp += 1
                fp1 += 1
                matched = False
            elif not exp_empty and act_empty:
                fn += 1
                matched = False
            elif matched:
                tp += 1
            else:
                fp += 1
                fp2 += 1

            # Generate reason
            reason = self._generate_reason(
                field_name,
                expected_value,
                actual_value,
                score,
                matched,
                field_config.get("comparator"),
            )

            # Build formatted evaluation method string that matches markdown display
            comparator_method = field_config.get("comparator")

            if comparator_method:
                # Simple field with comparator (EXACT, FUZZY, NumericComparator, etc.)
                evaluation_method_value = comparator_method
                # Add threshold for methods that use it
                if (
                    field_threshold
                    and field_threshold != match_threshold
                    and comparator_method
                    in [
                        "FUZZY",
                        "SEMANTIC",
                        "NumericComparator",
                        "LEVENSHTEIN",
                    ]
                ):
                    evaluation_method_value = (
                        f"{comparator_method} (threshold: {field_threshold:.2f})"
                    )
            elif isinstance(expected_value, list) or isinstance(actual_value, list):
                # Arrays ALWAYS use Hungarian matching (Stickler's built-in default)
                evaluation_method_value = "HUNGARIAN"
                if field_threshold and field_threshold != match_threshold:
                    evaluation_method_value = (
                        f"HUNGARIAN (threshold: {field_threshold:.2f})"
                    )
            elif isinstance(expected_value, dict) or isinstance(actual_value, dict):
                # Aggregate object
                evaluation_method_value = "AGGREGATE_OBJECT"
            else:
                # Fallback
                evaluation_method_value = "STICKLER"

            # Create AttributeEvaluationResult
            attribute_result = AttributeEvaluationResult(
                name=field_name,
                expected=expected_value,
                actual=actual_value,
                matched=matched,
                score=score,
                reason=reason,
                evaluation_method=evaluation_method_value,
                evaluation_threshold=field_threshold,
                comparator_type=field_config.get("comparator"),
                confidence=confidence_info.get("confidence")
                if confidence_info
                else None,
                confidence_threshold=confidence_info.get("confidence_threshold")
                if confidence_info
                else None,
                weight=field_config.get("weight"),  # Stickler field weight
            )

            attribute_results.append(attribute_result)

        # Sort attribute results for consistent output
        attribute_results.sort(key=lambda ar: ar.name)

        # Calculate metrics
        metrics = calculate_metrics(tp=tp, fp=fp, fn=fn, tn=tn, fp1=fp1, fp2=fp2)

        return SectionEvaluationResult(
            section_id=section.section_id,
            document_class=section.classification,
            attributes=attribute_results,
            metrics=metrics,
        )

    def evaluate_section(
        self,
        section: Section,
        expected_results: Dict[str, Any],
        actual_results: Dict[str, Any],
        confidence_scores: Optional[Dict[str, Any]] = None,
    ) -> SectionEvaluationResult:
        """
        Evaluate extraction results for a document section using Stickler.

        Args:
            section: Document section
            expected_results: Expected extraction results
            actual_results: Actual extraction results
            confidence_scores: Confidence scores for actual values from assessment

        Returns:
            Evaluation results for the section
        """
        class_name = section.classification
        logger.debug(
            f"Evaluating Section {section.section_id} - class: {class_name} using Stickler"
        )

        try:
            # Get Stickler model for this document class
            ModelClass = self._get_stickler_model(class_name)

            # Create model instances from data
            # Stickler handles validation and structure
            expected_instance = ModelClass(**expected_results)
            actual_instance = ModelClass(**actual_results)

            # Compare using Stickler
            stickler_result = expected_instance.compare_with(actual_instance)

            logger.debug(
                f"Stickler comparison complete. Overall score: {stickler_result.get('overall_score', 'N/A'):.3f}"
            )

            # Transform Stickler result to IDP format
            section_result = self._transform_stickler_result(
                section,
                expected_instance,
                actual_instance,
                stickler_result,
                confidence_scores or {},
            )

            return section_result

        except Exception as e:
            logger.error(
                f"Error evaluating section {section.section_id}: {str(e)}",
                exc_info=True,
            )
            # Return empty result on error
            return SectionEvaluationResult(
                section_id=section.section_id,
                document_class=class_name,
                attributes=[],
                metrics={},
            )

    def _process_section(
        self, actual_section: Section, expected_section: Section
    ) -> Tuple[Optional[SectionEvaluationResult], Dict[str, int]]:
        """
        Process a single section for evaluation.

        Args:
            actual_section: Section with actual extraction results
            expected_section: Section with expected extraction results

        Returns:
            Tuple of (section_result, metrics_count)
        """
        # Load extraction results from S3
        actual_uri = actual_section.extraction_result_uri
        expected_uri = expected_section.extraction_result_uri

        if not actual_uri or not expected_uri:
            logger.warning(
                f"Missing extraction URI for section: {actual_section.section_id}"
            )
            return None, {}

        # Load data and confidence scores
        actual_results, confidence_scores = self._prepare_stickler_data(actual_uri)
        expected_results, _ = self._prepare_stickler_data(expected_uri)

        # Evaluate section using Stickler
        section_result = self.evaluate_section(
            section=actual_section,
            expected_results=expected_results,
            actual_results=actual_results,
            confidence_scores=confidence_scores,
        )

        # Extract metrics from section result
        metrics = {
            "tp": 0,
            "fp": 0,
            "fn": 0,
            "tn": 0,
            "fp1": 0,
            "fp2": 0,
        }

        # Count matches and mismatches in the attributes
        for attr in section_result.attributes:
            # Check if both are None/Empty
            is_expected_empty = attr.expected is None or (
                isinstance(attr.expected, str) and not str(attr.expected).strip()
            )
            is_actual_empty = attr.actual is None or (
                isinstance(attr.actual, str) and not str(attr.actual).strip()
            )

            if is_expected_empty and is_actual_empty:
                metrics["tn"] += 1
            elif attr.matched:
                metrics["tp"] += 1
            else:
                # Handle different error cases
                if is_expected_empty:
                    metrics["fp"] += 1
                    metrics["fp1"] += 1
                elif is_actual_empty:
                    metrics["fn"] += 1
                else:
                    metrics["fp"] += 1
                    metrics["fp2"] += 1

        return section_result, metrics

    def evaluate_document(
        self,
        actual_document: Document,
        expected_document: Document,
        store_results: bool = True,
    ) -> Document:
        """
        Evaluate extraction results for an entire document using Stickler.

        This method maintains the same API as the legacy implementation but uses
        Stickler for comparison logic.

        Args:
            actual_document: Document with actual extraction results
            expected_document: Document with expected extraction results
            store_results: Whether to store results in S3 (default: True)

        Returns:
            Updated actual document with evaluation results
        """
        try:
            # Start timing
            start_time = time.time()

            # Track overall metrics
            total_tp = total_fp = total_fn = total_tn = total_fp1 = total_fp2 = 0

            # Create a list of section pairs to evaluate
            section_pairs = []
            for actual_section in actual_document.sections:
                section_id = actual_section.section_id

                # Find corresponding section in expected document
                expected_section = next(
                    (
                        s
                        for s in expected_document.sections
                        if s.section_id == section_id
                    ),
                    None,
                )

                if not expected_section:
                    logger.warning(
                        f"No matching section found for section_id: {section_id}"
                    )
                    continue

                section_pairs.append((actual_section, expected_section))

            section_results = []

            # Process sections in parallel using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all section evaluations to the executor
                future_to_section = {
                    executor.submit(
                        self._process_section, actual_section, expected_section
                    ): actual_section.section_id
                    for actual_section, expected_section in section_pairs
                }

                # Collect results as they complete
                for future in concurrent.futures.as_completed(future_to_section):
                    section_id = future_to_section[future]
                    try:
                        result, metrics = future.result()
                        if result is None:
                            logger.warning(
                                f"Section {section_id} evaluation returned no result"
                            )
                            continue

                        # Add to section results
                        section_results.append(result)

                        # Update overall metrics
                        total_tp += metrics["tp"]
                        total_fp += metrics["fp"]
                        total_fn += metrics["fn"]
                        total_tn += metrics["tn"]
                        total_fp1 += metrics["fp1"]
                        total_fp2 += metrics["fp2"]

                    except Exception as e:
                        logger.error(
                            f"Error evaluating section {section_id}: {traceback.format_exc()}"
                        )
                        actual_document.errors.append(
                            f"Error evaluating section {section_id}: {str(e)}"
                        )

            # Sort section results by section_id for consistent output
            section_results.sort(key=lambda x: x.section_id)

            # Calculate overall metrics
            overall_metrics = calculate_metrics(
                tp=total_tp,
                fp=total_fp,
                fn=total_fn,
                tn=total_tn,
                fp1=total_fp1,
                fp2=total_fp2,
            )

            execution_time = time.time() - start_time

            # Validate required document fields
            if not actual_document.id:
                raise ValueError("Document ID is required for evaluation")
            if not actual_document.output_bucket:
                raise ValueError("Output bucket is required for storing results")
            if not actual_document.input_key:
                raise ValueError("Input key is required for storing results")

            # Create evaluation result
            evaluation_result = DocumentEvaluationResult(
                document_id=actual_document.id,
                section_results=section_results,
                overall_metrics=overall_metrics,
                execution_time=execution_time,
            )

            # Store results if requested
            if store_results:
                # Generate output path
                output_bucket = actual_document.output_bucket
                output_key = f"{actual_document.input_key}/evaluation/results.json"

                # Store evaluation results in S3
                result_dict = evaluation_result.to_dict()
                s3.write_content(
                    content=result_dict,
                    bucket=output_bucket,
                    key=output_key,
                    content_type="application/json",
                )

                # Generate Markdown report
                markdown_report = evaluation_result.to_markdown()
                report_key = f"{actual_document.input_key}/evaluation/report.md"
                s3.write_content(
                    content=markdown_report,
                    bucket=output_bucket,
                    key=report_key,
                    content_type="text/markdown",
                )

                # Update document with evaluation report and results URIs
                actual_document.evaluation_report_uri = (
                    f"s3://{output_bucket}/{report_key}"
                )
                actual_document.evaluation_results_uri = (
                    f"s3://{output_bucket}/{output_key}"
                )
                actual_document.status = Status.COMPLETED

                logger.info(
                    f"Evaluation complete for document {actual_document.id} in {execution_time:.2f} seconds"
                )

            # Attach evaluation result to document for immediate use
            actual_document.evaluation_result = evaluation_result

            return actual_document

        except Exception as e:
            logger.error(f"Error evaluating document: {traceback.format_exc()}")
            actual_document.errors.append(f"Evaluation error: {str(e)}")
            return actual_document
