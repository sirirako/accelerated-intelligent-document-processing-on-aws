# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import pytest


@pytest.mark.unit
def test_path_extraction_logic():
    """Test the path extraction logic for testset bucket files"""
    # Simulate the path extraction logic from _copy_input_files_from_test_set_bucket
    file_key = "fcc_benchmark/input/fcc_benchmark/033f718b16cb597c065930410752c294.pdf"
    test_set_id = "fcc_demo_test_set"

    # Extract actual file path from test_set/input/file_path
    path_parts = file_key.split("/")
    if len(path_parts) >= 3 and path_parts[1] == "input":
        actual_file_path = "/".join(path_parts[2:])
        dest_key = f"{test_set_id}/input/{actual_file_path}"
    else:
        dest_key = f"{test_set_id}/input/{file_key}"

    expected = (
        "fcc_demo_test_set/input/fcc_benchmark/033f718b16cb597c065930410752c294.pdf"
    )
    assert dest_key == expected


@pytest.mark.unit
def test_path_extraction_edge_cases():
    """Test edge cases for path extraction"""
    test_set_id = "test-set-1"

    # Test normal file without input path
    file_key = "simple_file.pdf"
    path_parts = file_key.split("/")
    if len(path_parts) >= 3 and path_parts[1] == "input":
        actual_file_path = "/".join(path_parts[2:])
        dest_key = f"{test_set_id}/input/{actual_file_path}"
    else:
        dest_key = f"{test_set_id}/input/{file_key}"

    assert dest_key == "test-set-1/input/simple_file.pdf"

    # Test malformed path
    file_key = "malformed/path.pdf"
    path_parts = file_key.split("/")
    if len(path_parts) >= 3 and path_parts[1] == "input":
        actual_file_path = "/".join(path_parts[2:])
        dest_key = f"{test_set_id}/input/{actual_file_path}"
    else:
        dest_key = f"{test_set_id}/input/{file_key}"

    assert dest_key == "test-set-1/input/malformed/path.pdf"
