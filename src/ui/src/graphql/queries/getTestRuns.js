const GET_TEST_RUNS = `
  query GetTestRuns($timePeriodHours: Int) {
    getTestRuns(timePeriodHours: $timePeriodHours) {
      testRunId
      testSetName
      status
      filesCount
      completedFiles
      failedFiles
      accuracySimilarity
      confidenceSimilarity
      baseline
      test
      createdAt
      completedAt
    }
  }
`;

export default GET_TEST_RUNS;
