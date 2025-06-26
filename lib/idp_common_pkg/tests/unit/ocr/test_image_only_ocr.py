# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Unit tests for image-only OCR processing (backend="none").
"""

import unittest
from unittest.mock import MagicMock, patch

from idp_common.ocr.service import OcrService


class TestImageOnlyOcr(unittest.TestCase):
    """Test cases for image-only OCR processing."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = {"ocr": {"backend": "none"}}

    @patch("idp_common.ocr.service.boto3")
    def test_ocr_service_initialization_none_backend(self, mock_boto3):
        """Test OCR service initialization with 'none' backend."""
        # Mock S3 client
        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        # Initialize service with 'none' backend
        service = OcrService(region="us-east-1", backend="none", config=self.config)

        # Verify initialization
        self.assertEqual(service.backend, "none")
        self.assertFalse(service.enhanced_features)
        self.assertIsNotNone(service.s3_client)

        # Verify no Textract or Bedrock clients are initialized
        self.assertFalse(hasattr(service, "textract_client"))
        self.assertFalse(hasattr(service, "bedrock_model_id"))

    @patch("idp_common.ocr.service.s3")
    @patch("idp_common.ocr.service.fitz")
    def test_process_single_page_none(self, mock_fitz, mock_s3):
        """Test processing a single page with 'none' backend."""
        # Mock PDF document and page
        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b"fake_image_bytes"
        mock_page.get_pixmap.return_value = mock_pix

        mock_pdf_document = MagicMock()
        mock_pdf_document.load_page.return_value = mock_page

        # Mock S3 write operations
        mock_s3.write_content = MagicMock()

        # Initialize service
        with patch("idp_common.ocr.service.boto3"):
            service = OcrService(backend="none")

        # Process single page
        result, metering = service._process_single_page_none(
            page_index=0,
            pdf_document=mock_pdf_document,
            output_bucket="test-bucket",
            prefix="test-prefix",
        )

        # Verify results
        self.assertIn("raw_text_uri", result)
        self.assertIn("parsed_text_uri", result)
        self.assertIn("text_confidence_uri", result)
        self.assertIn("image_uri", result)

        # Verify URIs are properly formatted
        self.assertTrue(result["raw_text_uri"].startswith("s3://test-bucket/"))
        self.assertTrue(result["parsed_text_uri"].startswith("s3://test-bucket/"))
        self.assertTrue(result["text_confidence_uri"].startswith("s3://test-bucket/"))
        self.assertTrue(result["image_uri"].startswith("s3://test-bucket/"))

        # Verify metering is empty (no OCR processing)
        self.assertEqual(metering, {})

        # Verify S3 write operations were called
        self.assertEqual(
            mock_s3.write_content.call_count, 4
        )  # image, raw_text, confidence, parsed_text

        # Verify the content written to S3
        calls = mock_s3.write_content.call_args_list

        # Check image upload
        image_call = calls[0]
        self.assertEqual(image_call[0][0], b"fake_image_bytes")
        self.assertEqual(image_call[1]["content_type"], "image/jpeg")

        # Check empty OCR response
        raw_text_call = calls[1]
        raw_text_content = raw_text_call[0][0]
        self.assertIn("DocumentMetadata", raw_text_content)
        self.assertIn("Blocks", raw_text_content)
        self.assertEqual(raw_text_content["Blocks"], [])

        # Check empty confidence data
        confidence_call = calls[2]
        confidence_content = confidence_call[0][0]
        self.assertEqual(confidence_content["page_count"], 1)
        self.assertEqual(confidence_content["text_blocks"], [])

        # Check empty parsed text
        parsed_call = calls[3]
        parsed_content = parsed_call[0][0]
        self.assertEqual(parsed_content["text"], "")

    def test_invalid_backend_validation(self):
        """Test that invalid backends are rejected."""
        with patch("idp_common.ocr.service.boto3"):
            with self.assertRaises(ValueError) as context:
                OcrService(backend="invalid_backend")

            self.assertIn("Invalid backend", str(context.exception))
            self.assertIn(
                "Must be 'textract', 'bedrock', or 'none'", str(context.exception)
            )

    def test_valid_backends(self):
        """Test that all valid backends are accepted."""
        with patch("idp_common.ocr.service.boto3"):
            # Test 'none' backend
            service_none = OcrService(backend="none")
            self.assertEqual(service_none.backend, "none")

            # Test 'textract' backend
            service_textract = OcrService(backend="textract")
            self.assertEqual(service_textract.backend, "textract")

            # Test 'bedrock' backend
            service_bedrock = OcrService(
                backend="bedrock", config={"model_id": "test-model"}
            )
            self.assertEqual(service_bedrock.backend, "bedrock")


if __name__ == "__main__":
    unittest.main()
