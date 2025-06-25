#!/usr/bin/env python

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Unit tests for Document model."""

import pytest
from idp_common.models import Document, HitlMetadata, Status


@pytest.mark.unit
def test_document_hitl_metadata():
    """Test that Document can handle hitl_metadata attribute."""
    # Create a document with hitl_metadata
    doc = Document(
        id="test-doc",
        input_key="test.pdf",
        status=Status.QUEUED,
        hitl_metadata=[
            HitlMetadata(
                execution_id="test-execution",
                hitl_triggered=True,
                page_array=["1", "2"],
            )
        ],
    )

    # Convert to dict and verify hitl_metadata is included
    doc_dict = doc.to_dict()
    assert "hitl_metadata" in doc_dict
    assert len(doc_dict["hitl_metadata"]) == 1
    assert doc_dict["hitl_metadata"][0]["execution_id"] == "test-execution"
    assert doc_dict["hitl_metadata"][0]["hitl_triggered"] is True
    assert doc_dict["hitl_metadata"][0]["page_array"] == ["1", "2"]

    # Convert to JSON and back
    doc_json = doc.to_json()
    doc2 = Document.from_json(doc_json)

    # Verify hitl_metadata was preserved
    assert len(doc2.hitl_metadata) == 1
    assert doc2.hitl_metadata[0].execution_id == "test-execution"
    assert doc2.hitl_metadata[0].hitl_triggered is True
    assert doc2.hitl_metadata[0].page_array == ["1", "2"]


@pytest.mark.unit
def test_document_without_hitl_metadata():
    """Test that Document works correctly without hitl_metadata."""
    # Create a document without hitl_metadata
    doc = Document(
        id="test-doc",
        input_key="test.pdf",
        status=Status.QUEUED,
    )

    # Convert to dict and verify no hitl_metadata is included
    doc_dict = doc.to_dict()
    assert "hitl_metadata" not in doc_dict

    # Convert to JSON and back
    doc_json = doc.to_json()
    doc2 = Document.from_json(doc_json)

    # Verify hitl_metadata is an empty list
    assert doc2.hitl_metadata == []
