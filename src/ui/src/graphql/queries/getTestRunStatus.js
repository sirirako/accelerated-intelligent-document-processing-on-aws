// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

const GET_TEST_RUN_STATUS = `
  query GetTestRunStatus($testRunId: String!) {
    getTestRunStatus(testRunId: $testRunId) {
      testRunId
      status
      filesCount
      completedFiles
      failedFiles
      evaluatingFiles
      progress
    }
  }
`;

export default GET_TEST_RUN_STATUS;
