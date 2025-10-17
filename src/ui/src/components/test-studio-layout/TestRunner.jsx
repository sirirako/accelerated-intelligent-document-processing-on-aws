// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { Container, Header, SpaceBetween, Button, FormField, Select, Alert, Box } from '@awsui/components-react';
import { API, graphqlOperation, Logger } from 'aws-amplify';
import START_TEST_RUN from '../../graphql/queries/startTestRun';
import GET_TEST_SETS from '../../graphql/queries/getTestSets';

const logger = new Logger('TestRunner');

const TestRunner = ({ onTestStart, currentTestRunId, testStarted }) => {
  const [testSets, setTestSets] = useState([]);
  const [selectedTestSet, setSelectedTestSet] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const loadTestSets = async () => {
    try {
      console.log('TestRunner: Loading test sets...');
      const result = await API.graphql(graphqlOperation(GET_TEST_SETS));
      console.log('TestRunner: GraphQL result:', result);
      const testSetsData = result.data.getTestSets || [];
      console.log('TestRunner: Test sets data:', testSetsData);
      setTestSets(testSetsData);
    } catch (err) {
      console.error('TestRunner: Failed to load test sets:', err);
      setError(`Failed to load test sets: ${err.message}`);
    }
  };

  React.useEffect(() => {
    loadTestSets();
  }, []);

  const handleRunTest = async () => {
    if (!selectedTestSet) {
      setError('Please select a test set');
      return;
    }

    setLoading(true);
    try {
      const input = { testSetId: selectedTestSet.value };
      const result = await API.graphql(graphqlOperation(START_TEST_RUN, { input }));

      if (!result?.data?.startTestRun) {
        throw new Error('No response data from startTestRun mutation');
      }

      logger.info('Test run started:', result.data.startTestRun);
      onTestStart(result.data.startTestRun.testRunId);
      setError('');
    } catch (err) {
      logger.error('Failed to start test run:', err);
      let errorMessage = 'Failed to start test run';
      if (err.errors && err.errors.length > 0) {
        errorMessage = err.errors.map((e) => e.message).join('; ');
      }
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const testSetOptions = testSets.map((testSet) => ({
    label: `${testSet.name} (${testSet.filePattern}) - ${testSet.fileCount} ${
      testSet.fileCount === 1 ? 'file' : 'files'
    }`,
    value: testSet.id,
    description: `Pattern: ${testSet.filePattern}`,
  }));

  return (
    <Container
      header={
        <Header variant="h2" description="Select a test set and execute test runs for document processing">
          {testStarted ? `Test Running: ${currentTestRunId}` : 'Run Test Set'}
        </Header>
      }
    >
      <SpaceBetween size="l">
        {error && (
          <Alert type="error" dismissible onDismiss={() => setError('')}>
            {error}
          </Alert>
        )}

        {testStarted && (
          <Alert type="warning" header="Test Already Running">
            A test is currently running. Please wait for it to complete before starting a new test.
          </Alert>
        )}

        {!testStarted ? (
          <>
            <FormField label="Select Test Set" description="Choose an existing test set to run">
              <Select
                selectedOption={selectedTestSet}
                onChange={({ detail }) => setSelectedTestSet(detail.selectedOption)}
                options={testSetOptions}
                placeholder="Choose a test set..."
                empty="No test sets available"
              />
            </FormField>

            <Box float="right">
              <Button
                variant="primary"
                onClick={handleRunTest}
                loading={loading}
                disabled={!selectedTestSet || testStarted}
              >
                Run Test
              </Button>
            </Box>
          </>
        ) : (
          <Box textAlign="center">
            <Alert type="success" header="Test Started Successfully">
              Test run {currentTestRunId} is now running. Monitor progress in the status bar above.
            </Alert>
          </Box>
        )}
      </SpaceBetween>
    </Container>
  );
};

TestRunner.propTypes = {
  onTestStart: PropTypes.func.isRequired,
  currentTestRunId: PropTypes.string,
  testStarted: PropTypes.bool.isRequired,
};

TestRunner.defaultProps = {
  currentTestRunId: null,
};

export default TestRunner;
