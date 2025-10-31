# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Pydantic models for error analyzer tools.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


def epoch_ms_to_iso(timestamp_ms: int) -> str:
    """Convert epoch milliseconds to ISO 8601 string."""
    return datetime.fromtimestamp(timestamp_ms / 1000).isoformat()


class LogGroupMetadata(BaseModel):
    """Represents metadata for a CloudWatch log group."""

    logGroupName: str = Field(..., description="The name of the log group")
    creationTime: str = Field(
        ..., description="ISO 8601 timestamp when the log group was created"
    )
    retentionInDays: Optional[int] = Field(
        default=None, description="Retention period, if set"
    )
    storedBytes: int = Field(..., description="The number of bytes stored")
    logGroupArn: str = Field(
        ..., description="The Amazon Resource Name (ARN) of the log group"
    )

    @field_validator("creationTime", mode="before")
    @classmethod
    def convert_to_iso8601(cls, v):
        """Convert Unix epoch to ISO timestamp string."""
        if isinstance(v, int):
            return epoch_ms_to_iso(v)
        return v


class LogEvent(BaseModel):
    """Represents a CloudWatch log event."""

    timestamp: str = Field(..., description="ISO 8601 timestamp of the log event")
    message: str = Field(..., description="The log message content")
    logStreamName: str = Field(..., description="Name of the log stream")

    @field_validator("timestamp", mode="before")
    @classmethod
    def convert_timestamp(cls, v):
        """Convert Unix epoch to ISO timestamp string."""
        if isinstance(v, int):
            return epoch_ms_to_iso(v)
        return v


class LogPattern(BaseModel):
    """Represents a log pattern analysis result."""

    pattern: str = Field(..., description="The detected log pattern")
    count: int = Field(..., description="Number of occurrences of this pattern")
    sample_messages: List[str] = Field(
        default_factory=list, description="Sample messages matching this pattern"
    )
    percentage: Optional[float] = Field(
        default=None, description="Percentage of total messages this pattern represents"
    )
