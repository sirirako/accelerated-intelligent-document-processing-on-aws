// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

const COMPARE_TEST_RUNS = `
  query CompareTestRuns($testRunIds: [String!]!) {
    compareTestRuns(testRunIds: $testRunIds) {
      metrics {
        metric
        values
      }
      configDifferences {
        setting
        values
      }
      costs {
        component
        values
      }
    }
  }
`;

export default COMPARE_TEST_RUNS;
