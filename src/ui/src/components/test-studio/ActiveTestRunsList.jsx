// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React from 'react';
import PropTypes from 'prop-types';
import { Container, Header, Table, Box } from '@cloudscape-design/components';
import TestRunnerStatus from './TestRunnerStatus';

const StatusCell = ({ testRunId, onComplete }) => <TestRunnerStatus testRunId={testRunId} onComplete={onComplete} />;

StatusCell.propTypes = {
  testRunId: PropTypes.string.isRequired,
  onComplete: PropTypes.func.isRequired,
};

const ActiveTestRunsList = ({ activeTestRuns, onTestComplete }) => {
  if (activeTestRuns.length === 0) {
    return null;
  }

  const renderStatusCell = (item) => <StatusCell testRunId={item.testRunId} onComplete={() => onTestComplete(item.testRunId)} />;

  const columnDefinitions = [
    {
      id: 'testRunId',
      header: 'Test Run ID',
      cell: (item) => item.testRunId,
      width: 250,
    },
    {
      id: 'testSetName',
      header: 'Test Set',
      cell: (item) => item.testSetName,
      width: 200,
    },
    {
      id: 'startTime',
      header: 'Started',
      cell: (item) => new Date(item.startTime).toLocaleString(),
      width: 150,
    },
    {
      id: 'status',
      header: 'Status',
      cell: renderStatusCell,
      minWidth: 200,
    },
  ];

  return (
    <Container
      header={
        <Header variant="h3" counter={`(${activeTestRuns.length})`}>
          Active Test Runs
        </Header>
      }
    >
      <Table
        columnDefinitions={columnDefinitions}
        items={activeTestRuns}
        trackBy="testRunId"
        variant="borderless"
        empty={
          <Box textAlign="center" color="inherit">
            <b>No active test runs</b>
          </Box>
        }
      />
    </Container>
  );
};

ActiveTestRunsList.propTypes = {
  activeTestRuns: PropTypes.arrayOf(
    PropTypes.shape({
      testRunId: PropTypes.string.isRequired,
      testSetName: PropTypes.string.isRequired,
      startTime: PropTypes.instanceOf(Date).isRequired,
    }),
  ).isRequired,
  onTestComplete: PropTypes.func.isRequired,
};

export default ActiveTestRunsList;
