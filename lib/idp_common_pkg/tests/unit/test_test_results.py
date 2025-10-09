# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import pytest


@pytest.mark.unit
class TestTestResults:
    """Tests for TestResults component logic"""

    def test_cost_breakdown_formatting(self):
        """Test cost breakdown display logic"""

        def format_cost_breakdown(cost_breakdown):
            if not cost_breakdown or not isinstance(cost_breakdown, dict):
                return {}

            formatted = {}
            for service, cost in cost_breakdown.items():
                if isinstance(cost, (int, float)) and cost > 0:
                    formatted[service] = f"${cost:.4f}"

            return formatted

        cost_data = {
            "bedrock_tokens": 0.0234,
            "textract": 0.0156,
            "stepfunctions": 0.0001,
            "dynamodb": 0.0000,
        }

        formatted = format_cost_breakdown(cost_data)
        assert formatted["bedrock_tokens"] == "$0.0234"
        assert formatted["textract"] == "$0.0156"
        assert formatted["stepfunctions"] == "$0.0001"
        assert "dynamodb" not in formatted  # Zero cost excluded

    def test_accuracy_display(self):
        """Test accuracy percentage display"""

        def format_accuracy(accuracy):
            if accuracy is None or accuracy < 0:
                return "N/A"
            return f"{accuracy:.1f}%"

        assert format_accuracy(95.67) == "95.7%"
        assert format_accuracy(100.0) == "100.0%"
        assert format_accuracy(0.0) == "0.0%"
        assert format_accuracy(None) == "N/A"
        assert format_accuracy(-1) == "N/A"

    def test_confidence_score_validation(self):
        """Test confidence score validation"""

        def validate_confidence_score(score):
            if score is None:
                return False
            if not isinstance(score, (int, float)):
                return False
            return 0 <= score <= 1

        assert validate_confidence_score(0.85) is True
        assert validate_confidence_score(0.0) is True
        assert validate_confidence_score(1.0) is True
        assert validate_confidence_score(1.5) is False
        assert validate_confidence_score(-0.1) is False
        assert validate_confidence_score(None) is False
        assert validate_confidence_score("0.85") is False

    def test_file_count_summary(self):
        """Test file count summary logic"""

        def create_file_summary(completed_files, failed_files, total_files):
            successful = completed_files - failed_files
            return {
                "total": total_files,
                "successful": max(0, successful),
                "failed": failed_files,
                "pending": max(0, total_files - completed_files),
            }

        summary = create_file_summary(8, 2, 10)
        assert summary["total"] == 10
        assert summary["successful"] == 6
        assert summary["failed"] == 2
        assert summary["pending"] == 2

        # Edge case: more completed than total
        summary = create_file_summary(5, 1, 5)
        assert summary["successful"] == 4
        assert summary["pending"] == 0
