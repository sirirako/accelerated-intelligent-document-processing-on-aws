const GET_TEST_RUNS = `
  query GetTestRuns($timePeriodHours: Int) {
    getTestRuns(timePeriodHours: $timePeriodHours) {
      testRunId
      testSetName
      status
      filesCount
      createdAt
      context
    }
  }
`;

export default GET_TEST_RUNS;
