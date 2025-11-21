// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

const GET_TEST_SETS = `
  query GetTestSets {
    getTestSets {
      id
      name
      filePattern
      fileCount
      status
      createdAt
    }
  }
`;

export default GET_TEST_SETS;
