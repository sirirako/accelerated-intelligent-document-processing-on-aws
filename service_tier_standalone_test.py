#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Standalone test script for serviceTier parameter with boto3 Bedrock Runtime API."""

import boto3

MODEL_ID = "us.amazon.nova-2-lite-v1:0"
REGION = "us-west-2"


def test_flex_service_tier():
    """Test Flex service tier with Nova 2 Lite."""
    client = boto3.client("bedrock-runtime", region_name=REGION)
    response = client.converse(
        modelId=MODEL_ID,
        messages=[
            {"role": "user", "content": [{"text": "What is 2+2? Answer in one word."}]}
        ],
        inferenceConfig={"maxTokens": 10},
        serviceTier={"type": "flex"},
    )
    assert "output" in response
    print("✅ FLEX tier test passed")
    return response


def test_priority_service_tier():
    """Test Priority service tier with Nova 2 Lite."""
    client = boto3.client("bedrock-runtime", region_name=REGION)
    response = client.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": "Say hello in one word."}]}],
        inferenceConfig={"maxTokens": 5},
        serviceTier={"type": "priority"},
    )
    assert "output" in response
    print("✅ PRIORITY tier test passed")
    return response


def test_default_service_tier():
    """Test Default service tier with Nova 2 Lite."""
    client = boto3.client("bedrock-runtime", region_name=REGION)
    response = client.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": "Count to 3."}]}],
        inferenceConfig={"maxTokens": 20},
        serviceTier={"type": "default"},
    )
    assert "output" in response
    print("✅ DEFAULT tier test passed")
    return response


def test_no_service_tier():
    """Test without service tier (backward compatibility)."""
    client = boto3.client("bedrock-runtime", region_name=REGION)
    response = client.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": "Say yes or no."}]}],
        inferenceConfig={"maxTokens": 5},
    )
    assert "output" in response
    print("✅ NO tier test passed (backward compatible)")
    return response


if __name__ == "__main__":
    print(f"Testing serviceTier parameter with {MODEL_ID} in {REGION}\n")

    try:
        print("Test 1: Flex Service Tier")
        test_flex_service_tier()
        print()

        print("Test 2: Priority Service Tier")
        test_priority_service_tier()
        print()

        print("Test 3: Default Service Tier")
        test_default_service_tier()
        print()

        print("Test 4: No Service Tier (Backward Compatibility)")
        test_no_service_tier()
        print()

        print("=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nVerification:")
        print(
            "- serviceTier parameter correctly formatted as {'type': 'flex|priority|default'}"
        )
        print("- All service tiers work with Nova 2 Lite model")
        print("- Backward compatibility maintained (no serviceTier works)")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {type(e).__name__}: {e}")
        raise
