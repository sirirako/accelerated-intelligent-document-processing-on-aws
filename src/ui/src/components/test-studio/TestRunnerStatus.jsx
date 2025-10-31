// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Badge, ProgressBar, Box } from '@cloudscape-design/components';
import { generateClient } from 'aws-amplify/api';
import GET_TEST_RUN_STATUS from '../../graphql/queries/getTestRunStatus';

const client = generateClient();

const TestRunnerStatus = ({ testRunId, onComplete }) => {
  const [testRunStatus, setTestRunStatus] = useState(null);

  useEffect(() => {
    if (!testRunId) return undefined;

    const fetchStatus = async () => {
      try {
        const result = await client.graphql({ query: GET_TEST_RUN_STATUS, variables: { testRunId } });
        const status = result?.data?.getTestRunStatus;

        if (!status) {
          console.error('No status data returned for test run:', testRunId);
          return;
        }

        setTestRunStatus(status);

        // Close modal when test is complete (progress = 100%)
        if (status.progress === 100 && onComplete) {
          onComplete();
        }
      } catch (error) {
        console.error('Error fetching test status:', error);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, [testRunId, onComplete]);

  if (!testRunStatus) return <span>Loading...</span>;

  const getStatusColor = (status) => {
    const colors = {
      RUNNING: 'blue',
      EVALUATING: 'blue',
      COMPLETE: 'green',
      PARTIAL_COMPLETE: 'yellow',
      FAILED: 'red',
    };
    return colors[status] || 'grey';
  };

  const getStatusLabel = (status) => {
    const labels = {
      RUNNING: 'Processing Documents',
      EVALUATING: 'Evaluating Results',
      COMPLETE: 'Complete',
      PARTIAL_COMPLETE: 'Partially Complete',
      FAILED: 'Failed',
    };
    return labels[status] || status;
  };

  const getProgressLabel = () => {
    const { completedFiles, filesCount, evaluatingFiles, failedFiles } = testRunStatus;

    if (testRunStatus.status === 'EVALUATING') {
      return `${completedFiles}/${filesCount} processed, ${evaluatingFiles} evaluating`;
    }

    if (failedFiles > 0) {
      return `${completedFiles}/${filesCount} completed, ${failedFiles} failed`;
    }

    return `${completedFiles}/${filesCount} files`;
  };

  return (
    <Box>
      <Badge color={getStatusColor(testRunStatus.status)}>{getStatusLabel(testRunStatus.status)}</Badge>
      <ProgressBar
        value={testRunStatus.progress}
        label={getProgressLabel()}
      />
    </Box>
  );
};

TestRunnerStatus.propTypes = {
  testRunId: PropTypes.string,
  onComplete: PropTypes.func,
};

TestRunnerStatus.defaultProps = {
  testRunId: null,
  onComplete: null,
};

export default TestRunnerStatus;
