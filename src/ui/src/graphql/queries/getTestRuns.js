const GET_TEST_RUNS = `
  query GetTestRuns($timePeriodHours: Int) {
    getTestRuns(timePeriodHours: $timePeriodHours) {
      testRunId
      testSetName
      status
      filesCount
      completedFiles
      failedFiles
      overallAccuracy
      averageConfidence
      accuracyBreakdown
      totalCost
      costBreakdown
      usageBreakdown
      createdAt
      completedAt
      context
    }
  }
`;

export default GET_TEST_RUNS;
