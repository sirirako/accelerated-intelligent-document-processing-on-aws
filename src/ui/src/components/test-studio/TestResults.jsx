// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import {
  Container,
  Header,
  SpaceBetween,
  Box,
  ColumnLayout,
  ProgressBar,
  Badge,
  Alert,
  Table,
  Button,
} from '@cloudscape-design/components';
import { generateClient } from 'aws-amplify/api';
import GET_TEST_RUN from '../../graphql/queries/getTestResults';
import TestStudioHeader from './TestStudioHeader';

const client = generateClient();

/* eslint-disable react/prop-types */
const ComprehensiveBreakdown = ({ costBreakdown, usageBreakdown, accuracyBreakdown }) => {
  if (!costBreakdown && !usageBreakdown && !accuracyBreakdown) {
    return <Box>No breakdown data available</Box>;
  }

  return (
    <SpaceBetween direction="vertical" size="l">
      {/* Accuracy breakdown */}
      {accuracyBreakdown && (
        <Container header={<Header variant="h3">Accuracy Breakdown</Header>}>
          <Table
            items={Object.entries(accuracyBreakdown).map(([key, value]) => ({
              metric: key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase()),
              value: value !== null && value !== undefined ? `${(value * 100).toFixed(1)}%` : '0.0%',
            }))}
            columnDefinitions={[
              { id: 'metric', header: 'Metric', cell: (item) => item.metric },
              { id: 'value', header: 'Value', cell: (item) => item.value },
            ]}
            variant="embedded"
          />
        </Container>
      )}

      {/* Cost breakdown */}
      {costBreakdown && (
        <Container header={<Header variant="h3">Cost Breakdown</Header>}>
          <Table
            items={(() => {
              const costItems = [];
              Object.entries(costBreakdown).forEach(([category, data]) => {
                Object.entries(data).forEach(([api, cost]) => {
                  costItems.push({
                    metric: `${category} ${api}`,
                    value: `$${cost.toFixed(4)}`,
                  });
                });
              });
              return costItems;
            })()}
            columnDefinitions={[
              { id: 'metric', header: 'Metric', cell: (item) => item.metric },
              { id: 'value', header: 'Amount', cell: (item) => item.value },
            ]}
            variant="embedded"
          />
        </Container>
      )}

      {/* Usage breakdown */}
      {usageBreakdown && (
        <Container header={<Header variant="h3">Usage Breakdown</Header>}>
          <Table
            items={(() => {
              const usageItems = [];
              Object.entries(usageBreakdown).forEach(([service, metrics]) => {
                Object.entries(metrics).forEach(([metric, value]) => {
                  usageItems.push({
                    metric: `${service} ${metric}`,
                    value: value.toLocaleString(),
                  });
                });
              });
              return usageItems;
            })()}
            columnDefinitions={[
              { id: 'metric', header: 'Metric', cell: (item) => item.metric },
              { id: 'value', header: 'Count', cell: (item) => item.value },
            ]}
            variant="embedded"
          />
        </Container>
      )}
    </SpaceBetween>
  );
};

const TestResults = ({ testRunId, setSelectedTestRunId }) => {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchResults = async () => {
      try {
        const result = await client.graphql({
          query: GET_TEST_RUN,
          variables: { testRunId },
        });
        const testRun = result.data.getTestRun;
        console.log('Test results:', testRun);
        setResults(testRun);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchResults();
  }, [testRunId]);

  if (loading) return <ProgressBar status="in-progress" label="Loading test results..." />;
  if (error) return <Box>Error loading test results: {error}</Box>;
  if (!results) {
    const handleBackClick = () => {
      if (setSelectedTestRunId) {
        setSelectedTestRunId(null);
      } else {
        window.location.replace('#/test-studio?tab=results');
      }
    };

    return (
      <Container header={<TestStudioHeader title={`Test Results: ${testRunId}`} onBackClick={handleBackClick} />}>
        <Box>No test results found</Box>
      </Container>
    );
  }

  const getStatusColor = (status) => {
    if (status === 'COMPLETE') return 'green';
    if (status === 'RUNNING') return 'blue';
    return 'red';
  };

  const hasAccuracyData = results.overallAccuracy !== null && results.overallAccuracy !== undefined;

  let costBreakdown = null;
  let usageBreakdown = null;
  let accuracyBreakdown = null;

  try {
    if (results.costBreakdown) {
      costBreakdown = typeof results.costBreakdown === 'string' ? JSON.parse(results.costBreakdown) : results.costBreakdown;
    }
    if (results.usageBreakdown) {
      usageBreakdown = typeof results.usageBreakdown === 'string' ? JSON.parse(results.usageBreakdown) : results.usageBreakdown;
    }
    if (results.accuracyBreakdown) {
      accuracyBreakdown = typeof results.accuracyBreakdown === 'string' ? JSON.parse(results.accuracyBreakdown) : results.accuracyBreakdown;
    }
  } catch (e) {
    console.error('Error parsing breakdown data:', e);
  }

  const downloadConfig = () => {
    if (!results?.config) {
      console.error('No config data available');
      return;
    }

    const configData = JSON.stringify(results.config, null, 2);
    const blob = new Blob([configData], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `test-run-${results.testRunId}-config.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const configButton = (
    <Button onClick={downloadConfig} iconName="download">
      Config
    </Button>
  );

  const contextDescription = results.context ? (
    <Box variant="p" color="text-body-secondary" margin={{ top: 'xs' }}>
      Context: {results.context}
    </Box>
  ) : null;

  const handleBackClick = () => {
    if (setSelectedTestRunId) {
      setSelectedTestRunId(null);
    } else {
      window.location.replace('#/test-studio?tab=results');
    }
  };

  return (
    <Container
      header={
        <TestStudioHeader
          title={`Test Results: ${results.testRunId} (${results.testSetName})`}
          description={contextDescription}
          showPrintButton={true}
          additionalActions={[configButton]}
          onBackClick={handleBackClick}
        />
      }
    >
      <SpaceBetween direction="vertical" size="l">
        {/* Overall Status */}
        <Box>
          <Badge color={getStatusColor(results.status)}>{results.status}</Badge>
          <Box margin={{ left: 's' }} display="inline">
            {results.completedFiles}/{results.filesCount} files processed
          </Box>
        </Box>

        {/* Test Results Alert */}
        {hasAccuracyData && (
          <Alert type="success" header="Test Results Available">
            Test run completed with accuracy and performance metrics
          </Alert>
        )}

        {!hasAccuracyData && results.status === 'COMPLETE' && (
          <Alert type="warning" header="No Accuracy Data">
            Test run completed but accuracy metrics are not available
          </Alert>
        )}

        {/* Key Metrics */}
        <ColumnLayout columns={3} variant="text-grid">
          <Box>
            <Box variant="awsui-key-label">Total Cost</Box>
            <Box fontSize="heading-l">
              {results.totalCost !== null && results.totalCost !== undefined ? `$${results.totalCost.toFixed(4)}` : 'N/A'}
            </Box>
          </Box>
          <Box>
            <Box variant="awsui-key-label">Average Confidence</Box>
            <Box fontSize="heading-l">
              {results.averageConfidence !== null && results.averageConfidence !== undefined
                ? `${(results.averageConfidence * 100).toFixed(1)}%`
                : 'N/A'}
            </Box>
          </Box>
          <Box>
            <Box variant="awsui-key-label">Overall Accuracy</Box>
            <Box fontSize="heading-l">
              {results.overallAccuracy !== null && results.overallAccuracy !== undefined
                ? `${(results.overallAccuracy * 100).toFixed(1)}%`
                : 'N/A'}
            </Box>
          </Box>
        </ColumnLayout>

        {/* Breakdown Tables */}
        {(costBreakdown || usageBreakdown || accuracyBreakdown) && (
          <ComprehensiveBreakdown costBreakdown={costBreakdown} usageBreakdown={usageBreakdown} accuracyBreakdown={accuracyBreakdown} />
        )}
      </SpaceBetween>
    </Container>
  );
};

TestResults.propTypes = {
  testRunId: PropTypes.string.isRequired,
};

export default TestResults;
