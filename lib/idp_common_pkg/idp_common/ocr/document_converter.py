# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Document converter for handling various document formats.

This module provides functionality to convert different document formats
(Plain Text, CSV, Excel, Word) into page images and text outputs
consistent with PDF processing.
"""

import io
import logging
import tempfile
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class DocumentConverter:
    """Converter for various document formats to images and text."""

    def __init__(self, dpi: int = 150):
        """
        Initialize the document converter.

        Args:
            dpi: DPI for image generation
        """
        self.dpi = dpi
        self.page_width = int(8.5 * dpi)  # 8.5 inches at specified DPI
        self.page_height = int(11 * dpi)  # 11 inches at specified DPI
        self.margin = int(0.5 * dpi)  # 0.5 inch margin

    def convert_text_to_pages(self, content: str) -> List[Tuple[bytes, str]]:
        """
        Convert plain text content to page images and text.

        Args:
            content: Plain text content

        Returns:
            List of tuples (image_bytes, page_text)
        """
        try:
            # Use a basic font
            try:
                font = ImageFont.truetype("DejaVuSansMono.ttf", 12)
            except OSError:
                font = ImageFont.load_default()

            # Calculate text area dimensions
            text_width = self.page_width - (2 * self.margin)
            text_height = self.page_height - (2 * self.margin)

            # Split content into lines and wrap long lines
            lines = []
            for line in content.split("\n"):
                if not line.strip():
                    lines.append("")
                    continue

                # Estimate characters per line based on font and width
                avg_char_width = 7  # Approximate for monospace font
                chars_per_line = text_width // avg_char_width

                if len(line) <= chars_per_line:
                    lines.append(line)
                else:
                    # Wrap long lines
                    while len(line) > chars_per_line:
                        lines.append(line[:chars_per_line])
                        line = line[chars_per_line:]
                    if line:
                        lines.append(line)

            # Calculate lines per page
            line_height = 16  # Approximate line height
            lines_per_page = text_height // line_height

            # Split into pages
            pages = []
            for i in range(0, len(lines), lines_per_page):
                page_lines = lines[i : i + lines_per_page]
                page_text = "\n".join(page_lines)

                # Create image
                img = Image.new("RGB", (self.page_width, self.page_height), "white")
                draw = ImageDraw.Draw(img)

                # Draw text
                y_pos = self.margin
                for line in page_lines:
                    draw.text((self.margin, y_pos), line, fill="black", font=font)
                    y_pos += line_height

                # Convert to bytes
                img_buffer = io.BytesIO()
                img.save(img_buffer, format="JPEG", quality=95)
                img_bytes = img_buffer.getvalue()

                pages.append((img_bytes, page_text))

            return pages if pages else [(self._create_empty_page(), "")]

        except Exception as e:
            logger.error(f"Error converting text to pages: {str(e)}")
            return [(self._create_empty_page(), content)]

    def convert_csv_to_pages(self, content: str) -> List[Tuple[bytes, str]]:
        """
        Convert CSV content to page images and text.

        Args:
            content: CSV content as string

        Returns:
            List of tuples (image_bytes, page_text)
        """
        try:
            import csv

            # Parse CSV
            csv_reader = csv.reader(io.StringIO(content))
            rows = list(csv_reader)

            if not rows:
                return [(self._create_empty_page(), "")]

            # Format as table text
            formatted_text = self._format_csv_as_table(rows)

            # Convert formatted text to pages
            return self.convert_text_to_pages(formatted_text)

        except Exception as e:
            logger.error(f"Error converting CSV to pages: {str(e)}")
            return [(self._create_empty_page(), content)]

    def convert_excel_to_pages(self, file_bytes: bytes) -> List[Tuple[bytes, str]]:
        """
        Convert Excel file to page images and text.

        Args:
            file_bytes: Excel file bytes

        Returns:
            List of tuples (image_bytes, page_text)
        """
        try:
            import pandas as pd

            # Read Excel file
            with tempfile.NamedTemporaryFile(suffix=".xlsx") as tmp_file:
                tmp_file.write(file_bytes)
                tmp_file.flush()

                # Read all sheets
                excel_file = pd.ExcelFile(tmp_file.name)
                all_text = []

                for sheet_name in excel_file.sheet_names:
                    df = pd.read_excel(tmp_file.name, sheet_name=sheet_name)

                    # Add sheet header
                    all_text.append(f"=== Sheet: {sheet_name} ===\n")

                    # Convert DataFrame to string
                    sheet_text = df.to_string(index=False)
                    all_text.append(sheet_text)
                    all_text.append("\n\n")

                combined_text = "\n".join(all_text)
                return self.convert_text_to_pages(combined_text)

        except Exception as e:
            logger.error(f"Error converting Excel to pages: {str(e)}")
            return [(self._create_empty_page(), "Error reading Excel file")]

    def convert_word_to_pages(self, file_bytes: bytes) -> List[Tuple[bytes, str]]:
        """
        Convert Word document to page images and text.

        Args:
            file_bytes: Word document bytes

        Returns:
            List of tuples (image_bytes, page_text)
        """
        try:
            from docx import Document

            # Read Word document
            with tempfile.NamedTemporaryFile() as tmp_file:
                tmp_file.write(file_bytes)
                tmp_file.flush()

                doc = Document(tmp_file.name)

                # Extract text from paragraphs
                paragraphs = []
                for paragraph in doc.paragraphs:
                    if paragraph.text.strip():
                        paragraphs.append(paragraph.text)

                # Extract text from tables
                for table in doc.tables:
                    paragraphs.append("\n=== Table ===")
                    for row in table.rows:
                        row_text = " | ".join(cell.text.strip() for cell in row.cells)
                        if row_text.strip():
                            paragraphs.append(row_text)
                    paragraphs.append("=== End Table ===\n")

                combined_text = "\n\n".join(paragraphs)
                return self.convert_text_to_pages(combined_text)

        except Exception as e:
            logger.error(f"Error converting Word to pages: {str(e)}")
            return [(self._create_empty_page(), "Error reading Word document")]

    def _format_csv_as_table(self, rows: List[List[str]]) -> str:
        """Format CSV rows as a readable table."""
        if not rows:
            return ""

        # Calculate column widths
        col_widths = []
        for col_idx in range(len(rows[0])):
            max_width = 0
            for row in rows:
                if col_idx < len(row):
                    max_width = max(max_width, len(str(row[col_idx])))
            col_widths.append(min(max_width, 30))  # Cap at 30 characters

        # Format rows
        formatted_rows = []
        for row_idx, row in enumerate(rows):
            formatted_cells = []
            for col_idx, cell in enumerate(row):
                if col_idx < len(col_widths):
                    cell_str = str(cell)[: col_widths[col_idx]]
                    formatted_cells.append(cell_str.ljust(col_widths[col_idx]))

            formatted_row = " | ".join(formatted_cells)
            formatted_rows.append(formatted_row)

            # Add separator after header
            if row_idx == 0 and len(rows) > 1:
                separator = "-+-".join("-" * width for width in col_widths)
                formatted_rows.append(separator)

        return "\n".join(formatted_rows)

    def _create_empty_page(self) -> bytes:
        """Create an empty white page image."""
        try:
            img = Image.new("RGB", (self.page_width, self.page_height), "white")
            img_buffer = io.BytesIO()
            img.save(img_buffer, format="JPEG", quality=95)
            img_buffer.seek(0)  # Reset buffer position to beginning
            img_bytes = img_buffer.getvalue()

            # Ensure we actually got bytes
            if len(img_bytes) > 0:
                return img_bytes
            else:
                logger.warning("Image save produced 0 bytes, creating minimal JPEG")
                # Create a minimal 1x1 white JPEG as fallback
                minimal_img = Image.new("RGB", (1, 1), "white")
                minimal_buffer = io.BytesIO()
                minimal_img.save(minimal_buffer, format="JPEG", quality=95)
                minimal_buffer.seek(0)
                minimal_bytes = minimal_buffer.getvalue()
                logger.warning(f"Minimal JPEG created with {len(minimal_bytes)} bytes")
                if len(minimal_bytes) > 0:
                    return minimal_bytes
                else:
                    # Fall through to hardcoded JPEG
                    logger.error(
                        "Even minimal JPEG creation failed, using hardcoded bytes"
                    )
                    # Continue to hardcoded fallback below

        except Exception as e:
            logger.error(f"Error creating empty page: {str(e)}")
            # Fall through to hardcoded minimal JPEG

        # Return a hardcoded minimal valid 1x1 white JPEG
        logger.warning("Using hardcoded minimal JPEG")
        return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\x80\xff\xd9"
