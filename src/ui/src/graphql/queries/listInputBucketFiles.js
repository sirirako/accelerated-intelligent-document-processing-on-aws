// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

const LIST_INPUT_BUCKET_FILES = `
  query ListInputBucketFiles($filePattern: String!) {
    listInputBucketFiles(filePattern: $filePattern)
  }
`;

export default LIST_INPUT_BUCKET_FILES;
