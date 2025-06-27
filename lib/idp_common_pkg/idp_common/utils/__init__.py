# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import random
import time
import logging
from typing import Tuple, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Common backoff constants
MAX_RETRIES = 7
INITIAL_BACKOFF = 2  # seconds
MAX_BACKOFF = 300    # 5 minutes

def calculate_backoff(attempt: int, initial_backoff: float = INITIAL_BACKOFF, 
                     max_backoff: float = MAX_BACKOFF) -> float:
    """
    Calculate exponential backoff with jitter
    
    Args:
        attempt: The current retry attempt number (0-based)
        initial_backoff: Starting backoff in seconds
        max_backoff: Maximum backoff cap in seconds
        
    Returns:
        Backoff time in seconds
    """
    backoff = min(max_backoff, initial_backoff * (2 ** attempt))
    jitter = random.uniform(0, 0.1 * backoff)  # 10% jitter
    return backoff + jitter

def parse_s3_uri(s3_uri: str) -> Tuple[str, str]:
    """
    Parse an S3 URI into bucket and key
    
    Args:
        s3_uri: The S3 URI in format s3://bucket/key
        
    Returns:
        Tuple of (bucket, key)
    """
    if not s3_uri.startswith('s3://'):
        raise ValueError(f"Invalid S3 URI: {s3_uri}. Must start with s3://")
        
    parts = s3_uri.split('/', 3)
    if len(parts) < 4:
        raise ValueError(f"Invalid S3 URI: {s3_uri}. Format should be s3://bucket/key")
        
    bucket = parts[2]
    key = parts[3]
    return bucket, key

def build_s3_uri(bucket: str, key: str) -> str:
    """
    Build an S3 URI from bucket and key
    
    Args:
        bucket: The S3 bucket name
        key: The S3 object key
        
    Returns:
        S3 URI in format s3://bucket/key
    """
    return f"s3://{bucket}/{key}"

def merge_metering_data(existing_metering: Dict[str, Any], 
                       new_metering: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge metering data from multiple sources
    
    Args:
        existing_metering: Existing metering data to merge into
        new_metering: New metering data to add
        
    Returns:
        Merged metering data
    """
    merged = existing_metering.copy()
    
    for service_api, metrics in new_metering.items():
        if isinstance(metrics, dict):
            for unit, value in metrics.items():
                if service_api not in merged:
                    merged[service_api] = {}
                merged[service_api][unit] = merged[service_api].get(unit, 0) + value
        else:
            logger.warning(f"Unexpected metering data format for {service_api}: {metrics}")
            
    return merged

def extract_json_from_text(text: str) -> str:
    """
    Extract JSON string from LLM response text with improved multi-line handling.
    
    This enhanced version handles JSON with literal newlines and provides
    multiple fallback strategies for robust JSON extraction.
    
    This function handles multiple common formats:
    - JSON wrapped in ```json code blocks
    - JSON wrapped in ``` code blocks
    - Raw JSON objects with proper brace matching
    - Multi-line JSON with literal newlines in string values
    
    Args:
        text: The text response from the model
        
    Returns:
        Extracted JSON string, or original text if no JSON found
    """
    import json
    import re
    
    if not text:
        logger.warning("Empty text provided to extract_json_from_text")
        return text

    # Strategy 1: Check for code block format with json tag
    if "```json" in text:
        start_idx = text.find("```json") + len("```json")
        end_idx = text.find("```", start_idx)
        if end_idx > start_idx:
            json_str = text[start_idx:end_idx].strip()
            try:
                # Test if it's valid JSON
                json.loads(json_str)
                return json_str
            except json.JSONDecodeError:
                logger.debug(
                    "Found code block but content is not valid JSON, trying other strategies"
                )
    
    # Strategy 2: Check for generic code block format
    elif "```" in text:
        start_idx = text.find("```") + len("```")
        end_idx = text.find("```", start_idx)
        if end_idx > start_idx:
            json_str = text[start_idx:end_idx].strip()
            try:
                # Test if it's valid JSON
                json.loads(json_str)
                return json_str
            except json.JSONDecodeError:
                logger.debug(
                    "Found code block but content is not valid JSON, trying other strategies"
                )
    
    # Strategy 3: Extract JSON between braces and try direct parsing
    if "{" in text and "}" in text:
        start_idx = text.find("{")
        # Find matching closing brace
        open_braces = 0
        in_string = False
        escape_next = False
        
        for i in range(start_idx, len(text)):
            char = text[i]
            
            if escape_next:
                escape_next = False
                continue
                
            if char == "\\":
                escape_next = True
                continue
                
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
                
            if not in_string:
                if char == "{":
                    open_braces += 1
                elif char == "}":
                    open_braces -= 1
                    if open_braces == 0:
                        json_str = text[start_idx : i + 1].strip()
                        try:
                            # Test if it's valid JSON as-is
                            json.loads(json_str)
                            return json_str
                        except json.JSONDecodeError:
                            # If direct parsing fails, continue to next strategy
                            logger.debug(
                                "Found JSON-like content but direct parsing failed, trying normalization"
                            )
                            break

    # Strategy 4: Try to extract JSON using more aggressive methods
    try:
        # Find the outermost braces
        if "{" in text and "}" in text:
            start_idx = text.find("{")
            end_idx = text.rfind("}")  # Use rfind to get the last closing brace
            if end_idx > start_idx:
                json_str = text[start_idx : end_idx + 1]

                # Try parsing as-is first
                try:
                    json.loads(json_str)
                    return json_str
                except json.JSONDecodeError:
                    pass

                # Try normalizing the JSON string
                try:
                    # Method 1: Handle literal newlines by replacing with spaces
                    normalized_json = " ".join(
                        line.strip() for line in json_str.splitlines()
                    )
                    json.loads(normalized_json)
                    return normalized_json
                except json.JSONDecodeError:
                    pass

                # Method 2: Try a more aggressive approach with regex
                try:
                    # Remove extra whitespace but preserve structure
                    normalized_json = re.sub(r"\s+", " ", json_str)
                    json.loads(normalized_json)
                    return normalized_json
                except json.JSONDecodeError:
                    logger.debug("All normalization attempts failed")
    except Exception as e:
        logger.warning(f"Error during JSON extraction: {str(e)}")

    # If all strategies fail, return the original text
    logger.warning("Could not extract valid JSON, returning original text")
    return text