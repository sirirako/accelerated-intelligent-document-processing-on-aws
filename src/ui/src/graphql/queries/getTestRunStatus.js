const GET_TEST_RUN_STATUS = `
  query GetTestRunStatus($testRunId: ID!) {
    getTestRunStatus(testRunId: $testRunId) {
      id
      status
      progress
      accuracy
      executionTime
      errorMessage
      results
      updatedAt
    }
  }
`;

export default GET_TEST_RUN_STATUS;
