// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

const GET_TEST_RUNS = `
  query GetTestRuns($timePeriodHours: Int) {
    getTestRuns(timePeriodHours: $timePeriodHours) {
      testRunId
      testSetName
      status
      filesCount
      createdAt
      completedAt
    }
  }
`;

export default GET_TEST_RUNS;
