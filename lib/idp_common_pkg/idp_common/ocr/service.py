# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
OCR Service for document processing with AWS Textract or Amazon Bedrock.

This module provides a service for extracting text from PDF documents
using either AWS Textract or Amazon Bedrock LLMs, with support for concurrent
processing of multiple pages.
"""

import concurrent.futures
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import boto3
import fitz  # PyMuPDF
from botocore.config import Config

from idp_common import bedrock, image, s3, utils
from idp_common.models import Document, Page, Status

logger = logging.getLogger(__name__)


class OcrService:
    """Service for OCR processing of documents using AWS Textract or Amazon Bedrock."""

    def __init__(
        self,
        region: Optional[str] = None,
        max_workers: int = 20,
        enhanced_features: Union[bool, List[str]] = False,
        dpi: Optional[int] = None,
        resize_config: Optional[Dict[str, Any]] = None,
        bedrock_config: Dict[str, Any] = None,
        backend: str = "textract",  # New parameter: "textract" or "bedrock"
        preprocessing_config: Optional[
            Dict[str, Any]
        ] = None,  # New parameter for preprocessing
    ):
        """
        Initialize the OCR service.

        Args:
            region: AWS region for services
            max_workers: Maximum number of concurrent workers for page processing
            enhanced_features: Controls Textract FeatureTypes for analyze_document API:
                           - If False: Uses basic detect_document_text (faster, no features)
                           - If List[str]: Uses analyze_document with specified features
                              Valid features: TABLES, FORMS, SIGNATURES, LAYOUT
            dpi: DPI (dots per inch) for image generation from PDF pages
            resize_config: Optional dictionary containing image resizing configuration
                          with 'target_width' and 'target_height' keys
            backend: OCR backend to use ("textract" or "bedrock")
            bedrock_config: Optional dictionary containing bedrock configuration if backend is "bedrock"
            config: Configuration dictionary

        Raises:
            ValueError: If invalid features are specified in enhanced_features
                       or if an invalid backend is specified
        """
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        self.max_workers = max_workers
        self.dpi = dpi
        self.resize_config = resize_config
        self.backend = backend.lower()
        self.bedrock_config = bedrock_config
        self.preprocessing_config = preprocessing_config

        # Log DPI setting for debugging
        logger.info(f"OCR Service initialized with DPI: {self.dpi}")

        # Log resize config if provided
        if self.resize_config:
            logger.info(
                f"OCR Service initialized with resize config: {self.resize_config}"
            )

        # Validate backend
        if self.backend not in ["textract", "bedrock", "none"]:
            raise ValueError(
                f"Invalid backend: {backend}. Must be 'textract', 'bedrock', or 'none'"
            )

        # Initialize clients based on backend
        if self.backend == "textract":
            # Define valid Textract feature types
            VALID_FEATURES = ["TABLES", "FORMS", "SIGNATURES", "LAYOUT"]

            # Validate features if provided as a list
            if isinstance(enhanced_features, list):
                # Check for invalid features
                invalid_features = [
                    feature
                    for feature in enhanced_features
                    if feature not in VALID_FEATURES
                ]
                if invalid_features:
                    error_msg = f"Invalid Textract feature(s) specified: {invalid_features}. Valid features are: {VALID_FEATURES}"
                    logger.error(error_msg)
                    raise ValueError(error_msg)

                # Log the validated features
                logger.info(
                    f"OCR Service initialized with features: {enhanced_features}"
                )

            self.enhanced_features = enhanced_features

            # Initialize Textract client with adaptive retries
            adaptive_config = Config(
                retries={"max_attempts": 100, "mode": "adaptive"},
                max_pool_connections=max_workers * 3,
            )
            self.textract_client = boto3.client(
                "textract", region_name=self.region, config=adaptive_config
            )

            logger.info("OCR Service initialized with Textract backend")
        elif self.backend == "bedrock":
            # Enhanced features not used with Bedrock
            self.enhanced_features = False

            # Validate bedrock_config is provided
            if not self.bedrock_config:
                raise ValueError(
                    "bedrock_config is required when using 'bedrock' backend"
                )

            # Validate required bedrock_config fields
            required_fields = ["model_id", "system_prompt", "task_prompt"]
            missing_fields = [
                field for field in required_fields if not self.bedrock_config.get(field)
            ]
            if missing_fields:
                raise ValueError(
                    f"Missing required bedrock_config fields: {missing_fields}"
                )

            logger.info(
                f"OCR Service initialized with Bedrock backend, config: {self.bedrock_config}"
            )
        elif self.backend == "none":
            # No OCR processing - image-only mode
            self.enhanced_features = False
            logger.info(
                "OCR Service initialized with 'none' backend - image-only processing"
            )

        # Initialize S3 client (used by all backends for image storage)
        self.s3_client = boto3.client("s3")

    def process_document(self, document: Document) -> Document:
        """
        Process a PDF document with OCR and update the Document model.

        Args:
            document: Document model object to update with OCR results

        Returns:
            Updated Document object with OCR results
        """
        t0 = time.time()

        # Get the PDF from S3
        try:
            response = self.s3_client.get_object(
                Bucket=document.input_bucket, Key=document.input_key
            )
            pdf_content = response["Body"].read()
            t1 = time.time()
            logger.debug(f"Time taken for S3 GetObject: {t1 - t0:.6f} seconds")
        except Exception as e:
            import traceback

            error_msg = f"Error retrieving document from S3: {str(e)}"
            stack_trace = traceback.format_exc()
            logger.error(f"{error_msg}\nStack trace:\n{stack_trace}")
            document.errors.append(f"{error_msg} (see logs for full trace)")
            document.status = Status.FAILED
            return document

        # Process the PDF content
        try:
            pdf_document = fitz.open(stream=pdf_content, filetype="pdf")
            num_pages = len(pdf_document)
            document.num_pages = num_pages

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers
            ) as executor:
                future_to_page = {
                    executor.submit(
                        self._process_single_page,
                        i,
                        pdf_document,
                        document.output_bucket,
                        document.input_key,
                    ): i
                    for i in range(num_pages)
                }

                for future in concurrent.futures.as_completed(future_to_page):
                    page_index = future_to_page[future]
                    page_id = str(page_index + 1)
                    try:
                        ocr_result, page_metering = future.result()

                        # Create Page object and add to document
                        document.pages[page_id] = Page(
                            page_id=page_id,
                            image_uri=ocr_result["image_uri"],
                            raw_text_uri=ocr_result["raw_text_uri"],
                            parsed_text_uri=ocr_result["parsed_text_uri"],
                            text_confidence_uri=ocr_result["text_confidence_uri"],
                        )

                        # Merge metering data
                        document.metering = utils.merge_metering_data(
                            document.metering, page_metering
                        )

                    except Exception as e:
                        import traceback

                        error_msg = f"Error processing page {page_index + 1}: {str(e)}"
                        stack_trace = traceback.format_exc()
                        logger.error(f"{error_msg}\nStack trace:\n{stack_trace}")
                        document.errors.append(f"{error_msg} (see logs for full trace)")

            pdf_document.close()

            # Sort the pages dictionary by ascending page number
            logger.info(f"Sorting {len(document.pages)} pages by page number")

            # Create a new ordered dictionary with sorted pages
            sorted_pages = {}
            # Convert page_id to int for sorting, then back to string for the keys
            for page_id in sorted(document.pages.keys(), key=lambda x: int(x)):
                sorted_pages[page_id] = document.pages[page_id]

            # Replace the original pages dictionary with the sorted one
            document.pages = sorted_pages

            if document.errors:
                document.status = Status.FAILED

        except Exception as e:
            import traceback

            error_msg = f"Error processing document: {str(e)}"
            stack_trace = traceback.format_exc()
            logger.error(f"{error_msg}\nStack trace:\n{stack_trace}")
            document.errors.append(f"{error_msg} (see logs for full trace)")
            document.status = Status.FAILED

        t2 = time.time()
        logger.info(f"OCR processing completed in {t2 - t0:.2f} seconds")
        logger.info(
            f"Processed {len(document.pages)} pages, with {len(document.errors)} errors"
        )
        return document

    def _feature_combo(self):
        """Return the pricing feature combination string based on enhanced_features.

        Returns one of: "Tables", "Forms", "Tables+Forms", "Signatures", "Layout", or ""

        Note:
        - Layout feature is included free with any combination of Forms, Tables
        - Signatures feature is included free with Forms, Tables, and Layout
        """
        # TODO: Uncomment this when needed
        # Define valid Textract feature types
        # VALID_FEATURES = ["TABLES", "FORMS", "SIGNATURES", "LAYOUT"]

        # We assume features have already been validated in _analyze_document
        # This is just a safety check
        if not isinstance(self.enhanced_features, list) or not self.enhanced_features:
            return ""

        # All features should be valid at this point
        features = set(self.enhanced_features)

        # Check for feature combinations
        has_tables = "TABLES" in features
        has_forms = "FORMS" in features
        has_layout = "LAYOUT" in features
        has_signatures = "SIGNATURES" in features

        # Tables + Forms
        if has_tables and has_forms:
            return "-Tables+Forms"
        # Tables only
        elif has_tables:
            return "-Tables"
        # Forms only
        elif has_forms:
            return "-Forms"
        # Layout (only charged if not with Forms/Tables)
        elif has_layout:
            return "-Layout"
        # Signatures (only charged if used alone)
        elif has_signatures:
            return "-Signatures"
        return ""

    def _process_single_page(
        self,
        page_index: int,
        pdf_document: fitz.Document,
        output_bucket: str,
        prefix: str,
    ) -> Tuple[Dict[str, str], Dict[str, Any]]:
        """
        Process a single page of a document (PDF or image).

        Args:
            page_index: Zero-based index of the page
            pdf_document: PyMuPDF document object
            output_bucket: S3 bucket to store results
            prefix: S3 prefix for storing results

        Returns:
            Tuple of (page_result_dict, metering_data)
        """
        # Use the appropriate backend
        if self.backend == "none":
            return self._process_single_page_none(
                page_index, pdf_document, output_bucket, prefix
            )
        elif self.backend == "bedrock":
            return self._process_single_page_bedrock(
                page_index, pdf_document, output_bucket, prefix
            )
        else:
            # Textract backend (default)
            return self._process_single_page_textract(
                page_index, pdf_document, output_bucket, prefix
            )

    def _process_single_page_textract(
        self,
        page_index: int,
        pdf_document: fitz.Document,
        output_bucket: str,
        prefix: str,
    ) -> Tuple[Dict[str, str], Dict[str, Any]]:
        """
        Process a single page using AWS Textract.

        Args:
            page_index: Zero-based index of the page
            pdf_document: PyMuPDF document object
            output_bucket: S3 bucket to store results
            prefix: S3 prefix for storing results

        Returns:
            Tuple of (page_result_dict, metering_data)
        """
        t0 = time.time()
        page_id = page_index + 1

        # Extract page image - use DPI only for PDF files to prevent upscaling of images
        page = pdf_document.load_page(page_index)
        img_bytes = self._extract_page_image(page, pdf_document.is_pdf, page_id)

        # Upload original image to S3
        image_key = f"{prefix}/pages/{page_id}/image.jpg"
        s3.write_content(img_bytes, output_bucket, image_key, content_type="image/jpeg")

        t1 = time.time()
        logger.debug(
            f"Time for image conversion (page {page_id}): {t1 - t0:.6f} seconds"
        )

        # Resize image for OCR processing if configured
        ocr_img_bytes = img_bytes  # Default to original image
        if self.resize_config:
            from idp_common import image

            target_width = self.resize_config.get("target_width")
            target_height = self.resize_config.get("target_height")

            ocr_img_bytes = image.resize_image(img_bytes, target_width, target_height)
            logger.debug(
                f"Resized image for OCR processing (page {page_id}) to {target_width}x{target_height}"
            )

        # Apply preprocessing if enabled (only for OCR processing, not saved image)
        if self.preprocessing_config and self.preprocessing_config.get("enabled"):
            from idp_common.image import apply_adaptive_binarization

            ocr_img_bytes = apply_adaptive_binarization(ocr_img_bytes)
            logger.debug(
                f"Applied adaptive binarization preprocessing for OCR processing (page {page_id})"
            )

        # Process with OCR using potentially resized image
        if isinstance(self.enhanced_features, list) and self.enhanced_features:
            textract_result = self._analyze_document(ocr_img_bytes, page_id)
        else:
            textract_result = self.textract_client.detect_document_text(
                Document={"Bytes": ocr_img_bytes}
            )

        # Extract metering data
        feature_combo = self._feature_combo()
        metering = {
            f"OCR/textract/{self._get_api_name()}{feature_combo}": {
                "pages": textract_result["DocumentMetadata"]["Pages"]
            }
        }

        # Store raw Textract response
        raw_text_key = f"{prefix}/pages/{page_id}/rawText.json"
        s3.write_content(
            textract_result,
            output_bucket,
            raw_text_key,
            content_type="application/json",
        )

        # Generate and store text confidence data for efficient assessment
        text_confidence_data = self._generate_text_confidence_data(textract_result)
        text_confidence_key = f"{prefix}/pages/{page_id}/textConfidence.json"
        s3.write_content(
            text_confidence_data,
            output_bucket,
            text_confidence_key,
            content_type="application/json",
        )

        # Parse and store text content with markdown
        parsed_result = self._parse_textract_response(textract_result, page_id)
        parsed_text_key = f"{prefix}/pages/{page_id}/result.json"
        s3.write_content(
            parsed_result,
            output_bucket,
            parsed_text_key,
            content_type="application/json",
        )

        t2 = time.time()
        logger.debug(f"Time for Textract (page {page_id}): {t2 - t1:.6f} seconds")

        # Create and return page result
        result = {
            "raw_text_uri": f"s3://{output_bucket}/{raw_text_key}",
            "parsed_text_uri": f"s3://{output_bucket}/{parsed_text_key}",
            "text_confidence_uri": f"s3://{output_bucket}/{text_confidence_key}",
            "image_uri": f"s3://{output_bucket}/{image_key}",
        }

        return result, metering

    def _extract_page_image(self, page: fitz.Page, is_pdf: bool, page_id: int) -> bytes:
        """
        Extract image bytes from a page, using DPI only for PDF files.

        Args:
            page: PyMuPDF page object
            is_pdf: Whether the document is a PDF file
            page_id: Page number for logging

        Returns:
            Image bytes in JPEG format
        """
        if is_pdf:
            # For PDF files, use specified DPI for quality rendering
            pix = page.get_pixmap(dpi=self.dpi)
            logger.debug(f"Processing PDF page {page_id} at {self.dpi} DPI")
        else:
            # For image files (JPEG, PNG, etc.), preserve original dimensions
            pix = page.get_pixmap()
            logger.debug(f"Processing image page {page_id} at original dimensions")

        return pix.tobytes("jpeg")

    def _process_single_page_bedrock(
        self,
        page_index: int,
        pdf_document: fitz.Document,
        output_bucket: str,
        prefix: str,
    ) -> Tuple[Dict[str, str], Dict[str, Any]]:
        """
        Process a single page using Amazon Bedrock LLM.

        Args:
            page_index: Zero-based index of the page
            pdf_document: PyMuPDF document object
            output_bucket: S3 bucket to store results
            prefix: S3 prefix for storing results

        Returns:
            Tuple of (page_result_dict, metering_data)
        """
        t0 = time.time()
        page_id = page_index + 1

        # Extract page image at specified DPI (consistent with Textract)
        page = pdf_document.load_page(page_index)
        img_bytes = self._extract_page_image(page, pdf_document.is_pdf, page_id)

        # Upload image to S3
        image_key = f"{prefix}/pages/{page_id}/image.jpg"
        s3.write_content(img_bytes, output_bucket, image_key, content_type="image/jpeg")

        t1 = time.time()
        logger.debug(
            f"Time for image conversion (page {page_id}): {t1 - t0:.6f} seconds"
        )

        # Apply resize config if provided (consistent with Textract)
        ocr_img_bytes = img_bytes  # Default to original image
        if self.resize_config:
            target_width = self.resize_config.get("target_width")
            target_height = self.resize_config.get("target_height")

            ocr_img_bytes = image.resize_image(img_bytes, target_width, target_height)
            logger.debug(
                f"Resized image for Bedrock OCR processing (page {page_id}) to {target_width}x{target_height}"
            )

        # Apply preprocessing if enabled (only for OCR processing, not saved image)
        if self.preprocessing_config and self.preprocessing_config.get("enabled"):
            from idp_common.image import apply_adaptive_binarization

            ocr_img_bytes = apply_adaptive_binarization(ocr_img_bytes)
            logger.debug(
                f"Applied adaptive binarization preprocessing for Bedrock OCR processing (page {page_id})"
            )

        # Prepare image for Bedrock
        image_content = image.prepare_bedrock_image_attachment(ocr_img_bytes)

        # Prepare content for Bedrock
        content = [{"text": self.bedrock_config["task_prompt"]}, image_content]

        # Invoke Bedrock
        response_with_metering = bedrock.invoke_model(
            model_id=self.bedrock_config["model_id"],
            system_prompt=self.bedrock_config["system_prompt"],
            content=content,
            temperature=0.0,  # Use lowest temperature for OCR accuracy
            top_p=0.1,
            top_k=5,
            max_tokens=4096,
            context="OCR",
        )

        # Extract text from response
        extracted_text = bedrock.extract_text_from_response(response_with_metering)
        metering = response_with_metering.get("metering", {})

        t2 = time.time()
        logger.debug(f"Time for Bedrock OCR (page {page_id}): {t2 - t1:.6f} seconds")

        # Store raw Bedrock response
        raw_text_key = f"{prefix}/pages/{page_id}/rawText.json"
        s3.write_content(
            response_with_metering["response"],
            output_bucket,
            raw_text_key,
            content_type="application/json",
        )

        # Generate and store text confidence data
        # For Bedrock, we use empty confidence data since LLM OCR doesn't provide real confidence scores
        text_confidence_data = {
            "page_count": 1,
            "text_blocks": [],  # Empty - no confidence data available from LLM OCR
        }

        text_confidence_key = f"{prefix}/pages/{page_id}/textConfidence.json"
        s3.write_content(
            text_confidence_data,
            output_bucket,
            text_confidence_key,
            content_type="application/json",
        )

        # Store parsed text result
        parsed_result = {"text": extracted_text}
        parsed_text_key = f"{prefix}/pages/{page_id}/result.json"
        s3.write_content(
            parsed_result,
            output_bucket,
            parsed_text_key,
            content_type="application/json",
        )

        # Create and return page result
        result = {
            "raw_text_uri": f"s3://{output_bucket}/{raw_text_key}",
            "parsed_text_uri": f"s3://{output_bucket}/{parsed_text_key}",
            "text_confidence_uri": f"s3://{output_bucket}/{text_confidence_key}",
            "image_uri": f"s3://{output_bucket}/{image_key}",
        }

        return result, metering

    def _process_single_page_none(
        self,
        page_index: int,
        pdf_document: fitz.Document,
        output_bucket: str,
        prefix: str,
    ) -> Tuple[Dict[str, str], Dict[str, Any]]:
        """
        Process a single page with no OCR (image-only processing).

        Args:
            page_index: Zero-based index of the page
            pdf_document: PyMuPDF document object
            output_bucket: S3 bucket to store results
            prefix: S3 prefix for storing results

        Returns:
            Tuple of (page_result_dict, metering_data)
        """
        t0 = time.time()
        page_id = page_index + 1

        # Extract page image at specified DPI (consistent with other backends)
        page = pdf_document.load_page(page_index)
        img_bytes = self._extract_page_image(page, pdf_document.is_pdf, page_id)

        # Upload image to S3
        image_key = f"{prefix}/pages/{page_id}/image.jpg"
        s3.write_content(img_bytes, output_bucket, image_key, content_type="image/jpeg")

        t1 = time.time()
        logger.debug(
            f"Time for image conversion (page {page_id}): {t1 - t0:.6f} seconds"
        )

        # Create empty OCR response structure for compatibility
        empty_ocr_response = {"DocumentMetadata": {"Pages": 1}, "Blocks": []}

        # Store empty raw OCR response
        raw_text_key = f"{prefix}/pages/{page_id}/rawText.json"
        s3.write_content(
            empty_ocr_response,
            output_bucket,
            raw_text_key,
            content_type="application/json",
        )

        # Generate minimal text confidence data (empty)
        text_confidence_data = {"page_count": 1, "text_blocks": []}

        text_confidence_key = f"{prefix}/pages/{page_id}/textConfidence.json"
        s3.write_content(
            text_confidence_data,
            output_bucket,
            text_confidence_key,
            content_type="application/json",
        )

        # Store empty parsed text result
        parsed_result = {"text": ""}
        parsed_text_key = f"{prefix}/pages/{page_id}/result.json"
        s3.write_content(
            parsed_result,
            output_bucket,
            parsed_text_key,
            content_type="application/json",
        )

        t2 = time.time()
        logger.debug(
            f"Time for image-only processing (page {page_id}): {t2 - t1:.6f} seconds"
        )

        # No metering data for image-only processing
        metering = {}

        # Create and return page result
        result = {
            "raw_text_uri": f"s3://{output_bucket}/{raw_text_key}",
            "parsed_text_uri": f"s3://{output_bucket}/{parsed_text_key}",
            "text_confidence_uri": f"s3://{output_bucket}/{text_confidence_key}",
            "image_uri": f"s3://{output_bucket}/{image_key}",
        }

        return result, metering

    def _analyze_document(
        self, document_bytes: bytes, page_id: int = None
    ) -> Dict[str, Any]:
        """
        Analyze document using enhanced Textract features.

        Args:
            document_bytes: Binary content of the document image
            page_id: Optional page number for logging purposes

        Returns:
            Textract API response
        """
        # Use specified feature types
        # Valid types are TABLES, FORMS, SIGNATURES, and LAYOUT
        # Note: QUERIES is not supported as it requires additional parameters

        # Features are already validated in __init__, so we can use them directly
        page_info = f" for page {page_id}" if page_id else ""
        logger.debug(
            f"Analyzing document{page_info} with features: {self.enhanced_features}"
        )

        try:
            response = self.textract_client.analyze_document(
                Document={"Bytes": document_bytes}, FeatureTypes=self.enhanced_features
            )

            # Log the types of response blocks received
            if logger.isEnabledFor(logging.DEBUG):
                block_types = {}
                for block in response.get("Blocks", []):
                    block_type = block.get("BlockType")
                    if block_type not in block_types:
                        block_types[block_type] = 0
                    block_types[block_type] += 1
                logger.debug(f"Received response with block types: {block_types}")

            return response

        except Exception as e:
            import traceback

            page_info = f" for page {page_id}" if page_id else ""
            logger.error(
                f"Error in _analyze_document{page_info} with features {self.enhanced_features}: {str(e)}\nStack trace:\n{traceback.format_exc()}"
            )
            raise

    def _get_api_name(self) -> str:
        """Get the name of the Textract API being used."""
        # If enhanced_features is a non-empty list, we're using analyze_document
        # Otherwise, we're using detect_document_text
        return (
            "analyze_document"
            if isinstance(self.enhanced_features, list) and self.enhanced_features
            else "detect_document_text"
        )

    def _generate_text_confidence_data(
        self, raw_ocr_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate text confidence data from raw OCR to reduce token usage while preserving essential information.

        This method transforms verbose Textract output into a minimal format containing:
        - Essential text content (LINE blocks only)
        - OCR confidence scores
        - Text type (PRINTED/HANDWRITING)
        - Page count

        Removes geometric data, relationships, block IDs, and other verbose metadata
        that aren't needed for assessment purposes.

        Args:
            raw_ocr_data: Raw Textract API response

        Returns:
            Text confidence data with ~80-90% token reduction
        """
        text_confidence_data = {
            "page_count": raw_ocr_data.get("DocumentMetadata", {}).get("Pages", 1),
            "text_blocks": [],
        }

        blocks = raw_ocr_data.get("Blocks", [])

        for block in blocks:
            if block.get("BlockType") == "LINE" and block.get("Text"):
                text_block = {
                    "text": block.get("Text", ""),
                    "confidence": block.get("Confidence"),
                }

                # Include text type if available (PRINTED vs HANDWRITING)
                if "TextType" in block:
                    text_block["type"] = block["TextType"]

                text_confidence_data["text_blocks"].append(text_block)

        return text_confidence_data

    def _parse_textract_response(
        self, response: Dict[str, Any], page_id: int = None
    ) -> Dict[str, str]:
        """
        Parse Textract response into text.

        Args:
            response: Raw Textract API response
            page_id: Optional page number for logging purposes

        Returns:
            Dictionary with 'text' key containing extracted text
        """
        from textractor.parsers import response_parser

        # Create page identifier for logging
        page_info = f" for page {page_id}" if page_id else ""

        # Log enhanced features at debug level
        logger.debug(f"Enhanced features{page_info}: {self.enhanced_features}")

        try:
            # Parse the response with textractor - debug level
            logger.debug(f"Parsing Textract response{page_info} with textractor")
            parsed_response = response_parser.parse(response)

            try:
                # First try to convert to markdown
                text = parsed_response.to_markdown()
                logger.info(f"Successfully extracted markdown text{page_info}")
            except Exception as e:
                # If markdown conversion fails, use plain text instead
                logger.warning(f"Markdown conversion failed{page_info}: {str(e)}")

                # Identify if it's a known issue - keep these as warnings
                if "reading_order" in str(e):
                    if "Signature" in str(e):
                        logger.warning(
                            f"Detected Signature object error{page_info} with SIGNATURES feature"
                        )
                    elif "KeyValue" in str(e):
                        logger.warning(
                            f"Detected KeyValue object error{page_info} with FORMS feature"
                        )

                # Use plain text instead
                logger.warning(f"Falling back to plain text extraction{page_info}")
                text = parsed_response.text
                logger.info(f"Successfully extracted plain text{page_info}")

        except Exception as e:
            # If parsing completely fails, extract text directly from blocks
            logger.warning(f"Textractor parsing failed{page_info}: {str(e)}")

            # Simple extraction from LINE blocks as final fallback
            logger.warning(
                f"Falling back to basic text extraction from blocks{page_info}"
            )
            blocks = response.get("Blocks", [])

            text_lines = []
            for block in blocks:
                if block.get("BlockType") == "LINE" and "Text" in block:
                    text_lines.append(block["Text"])

            text = "\n".join(text_lines)
            if not text:
                text = f"Error extracting text from document{page_info}. No text content found."
                logger.error(f"No text content found in document{page_info}")
            else:
                logger.info(f"Successfully extracted basic text{page_info}")

        return {"text": text}
