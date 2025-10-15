// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { Container, Header, SpaceBetween, Button, FormField, Input, Alert, Box } from '@awsui/components-react';
import { API, graphqlOperation, Logger } from 'aws-amplify';
import TestRunnerStatus from '../test-results/TestRunnerStatus';
import START_TEST_RUN from '../../graphql/queries/startTestRun';

const logger = new Logger('TestRunner');

const TestRunner = ({ onTestStart, onTestComplete, currentTestRunId, testStarted }) => {
  const [testSetName, setTestSetName] = useState('');
  const [filePattern, setFilePattern] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleRunTest = async () => {
    if (!testSetName.trim() || !filePattern.trim()) {
      setError('Both test set name and file pattern are required');
      return;
    }

    setLoading(true);
    try {
      const input = { testSetName: testSetName.trim(), filePattern: filePattern.trim() };
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

  const handleTestCompleteLocal = () => {
    setTestSetName('');
    setFilePattern('');
    onTestComplete();
  };

  return (
    <Container
      header={
        <Header variant="h2" description="Configure and execute test runs for document processing">
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

        {!testStarted ? (
          <>
            <FormField label="Test Set Name" description="A descriptive name for this test set">
              <Input
                value={testSetName}
                onChange={({ detail }) => setTestSetName(detail.value)}
                placeholder="e.g., lending-package-v1"
              />
            </FormField>

            <FormField label="File Pattern" description="Pattern to match files in the input bucket (e.g., 'prefix.*')">
              <Input
                value={filePattern}
                onChange={({ detail }) => setFilePattern(detail.value)}
                placeholder="lending_package*.pdf"
              />
            </FormField>

            <Box float="right">
              <Button variant="primary" onClick={handleRunTest} loading={loading}>
                Run Test
              </Button>
            </Box>
          </>
        ) : (
          currentTestRunId && <TestRunnerStatus testRunId={currentTestRunId} onComplete={handleTestCompleteLocal} />
        )}
      </SpaceBetween>
    </Container>
  );
};

TestRunner.propTypes = {
  onTestStart: PropTypes.func.isRequired,
  onTestComplete: PropTypes.func.isRequired,
  currentTestRunId: PropTypes.string,
  testStarted: PropTypes.bool.isRequired,
};

TestRunner.defaultProps = {
  currentTestRunId: null,
};

export default TestRunner;
