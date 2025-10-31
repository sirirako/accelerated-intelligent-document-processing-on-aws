// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Container, Header, SpaceBetween, Table, Box, Button } from '@cloudscape-design/components';
import { generateClient } from 'aws-amplify/api';
import COMPARE_TEST_RUNS from '../../graphql/queries/compareTestRuns';
import handlePrint from './PrintUtils';

const client = generateClient();

// Helper functions for rendering change values with colored arrows
const renderChangeValue = (value) => {
  if (value === 'N/A') return 'N/A';
  const numValue = parseFloat(value);
  const isPositive = numValue > 0;
  return (
    <>
      {Math.abs(numValue).toFixed(2)}%
      <span style={{ color: isPositive ? 'green' : 'red' }}>{isPositive ? ' ↑' : ' ↓'}</span>
    </>
  );
};

const TestComparison = ({ preSelectedTestRunIds = [] }) => {
  const [comparisonData, setComparisonData] = useState(null);
  const [comparing, setComparing] = useState(false);

  useEffect(() => {
    const fetchComparison = async () => {
      if (preSelectedTestRunIds.length >= 2) {
        setComparing(true);
        console.log('=== STARTING COMPARISON ===');
        console.log('Selected test run IDs:', preSelectedTestRunIds);

        try {
          console.log('Making GraphQL request...');
          const result = await client.graphql({
            query: COMPARE_TEST_RUNS,
            variables: { testRunIds: preSelectedTestRunIds },
          });

          const compareData = result.data.compareTestRuns;

          // Parse metrics if it's a JSON string
          if (typeof compareData.metrics === 'string') {
            compareData.metrics = JSON.parse(compareData.metrics);
          }

          setComparisonData(compareData);
        } catch (error) {
          console.error('Error comparing test runs:', error);

          const errorMessage =
            error.errors?.length > 0
              ? error.errors.map((e) => e.message).join('; ')
              : error.message || 'Error comparing test runs';
          setComparisonData({ error: errorMessage });
        } finally {
          setComparing(false);
        }
      }
    };

    fetchComparison();
  }, [preSelectedTestRunIds]);

  // Helper function to create clickable test run ID headers
  const createTestRunHeader = (testRunId) => {
    return (
      <Button
        variant="link"
        onClick={() => {
          window.location.hash = `#/test-studio?tab=results&testRunId=${testRunId}`;
        }}
      >
        {testRunId}
      </Button>
    );
  };

  if (comparing) {
    return <Box>Loading comparison...</Box>;
  }

  if (!comparisonData) {
    return <Box>No comparison data available</Box>;
  }

  if (comparisonData.error) {
    return <Box>Error: {comparisonData.error}</Box>;
  }

  // Debug logging
  console.log('Comparison data structure:', comparisonData);
  console.log('Metrics structure:', comparisonData.metrics);

  // Filter out incomplete test runs
  const completeTestRuns = comparisonData.metrics
    ? Object.fromEntries(Object.entries(comparisonData.metrics).filter(([, testRun]) => testRun.status === 'COMPLETE'))
    : {};

  const hasIncompleteRuns = comparisonData.metrics
    ? Object.values(comparisonData.metrics).some((testRun) => testRun.status !== 'COMPLETE')
    : false;

  return (
    <Container
      header={
        <Header
          variant="h2"
          actions={
            <SpaceBetween direction="horizontal" size="xs">
              <Button onClick={() => window.history.back()} iconName="arrow-left">
                Back to Test Runs
              </Button>
              <Button onClick={handlePrint} iconName="print">
                Print
              </Button>
            </SpaceBetween>
          }
        >
          Compare Test Runs ({Object.keys(completeTestRuns).length})
        </Header>
      }
    >
      <SpaceBetween direction="vertical" size="l">
        {/* Performance Metrics */}
        <Box>
          <Header variant="h3">Performance Metrics</Header>
          {hasIncompleteRuns && (
            <Box variant="awsui-key-label" color="text-status-warning" padding="s">
              Some test runs are not complete. Only showing results for completed test runs.
            </Box>
          )}
          {Object.keys(completeTestRuns).length > 0 ? (
            <Table
              items={[
                {
                  metric: 'Test Set',
                  ...Object.fromEntries(
                    Object.entries(completeTestRuns).map(([testRunId, testRun]) => [
                      testRunId,
                      testRun.testSetName || 'N/A',
                    ]),
                  ),
                },
                {
                  metric: 'Context',
                  ...Object.fromEntries(
                    Object.entries(completeTestRuns).map(([testRunId, testRun]) => [
                      testRunId,
                      testRun.context || 'N/A',
                    ]),
                  ),
                },
                {
                  metric: 'Files Processed',
                  ...Object.fromEntries(
                    Object.entries(completeTestRuns).map(([testRunId, testRun]) => [
                      testRunId,
                      testRun.filesCount || 'N/A',
                    ]),
                  ),
                },
                {
                  metric: 'Total Cost',
                  ...Object.fromEntries(
                    Object.entries(completeTestRuns).map(([testRunId, testRun]) => [
                      testRunId,
                      testRun.totalCost !== null && testRun.totalCost !== undefined
                        ? `$${testRun.totalCost.toFixed(4)}`
                        : 'N/A',
                    ]),
                  ),
                },
                {
                  metric: 'Overall Accuracy',
                  ...Object.fromEntries(
                    Object.entries(completeTestRuns).map(([testRunId, testRun]) => [
                      testRunId,
                      testRun.overallAccuracy !== null && testRun.overallAccuracy !== undefined
                        ? `${(testRun.overallAccuracy * 100).toFixed(1)}%`
                        : 'N/A',
                    ]),
                  ),
                },
                {
                  metric: 'Overall Confidence',
                  ...Object.fromEntries(
                    Object.entries(completeTestRuns).map(([testRunId, testRun]) => [
                      testRunId,
                      testRun.averageConfidence !== null && testRun.averageConfidence !== undefined
                        ? `${(testRun.averageConfidence * 100).toFixed(1)}%`
                        : 'N/A',
                    ]),
                  ),
                },
              ]}
              columnDefinitions={[
                { id: 'metric', header: 'Metric', cell: (item) => item.metric },
                ...Object.keys(completeTestRuns).map((testRunId) => ({
                  id: testRunId,
                  header: createTestRunHeader(testRunId),
                  cell: (item) => {
                    const value = item[testRunId];
                    if (item.metric === 'Accuracy Change') {
                      return renderChangeValue(value);
                    }
                    return value;
                  },
                })),
              ]}
              variant="embedded"
            />
          ) : (
            <Box>No completed test runs available</Box>
          )}
        </Box>

        {/* Breakdown Tables */}
        <SpaceBetween direction="vertical" size="l">
          {/* Configuration Comparison */}
          <Container header={<Header variant="h3">Configuration Comparison</Header>}>
            {(() => {
              if (preSelectedTestRunIds.length !== 2) {
                return (
                  <Box>
                    Configuration comparison requires exactly 2 test runs. Currently comparing{' '}
                    {preSelectedTestRunIds.length} test runs.
                  </Box>
                );
              }

              if (!comparisonData.configs || comparisonData.configs.length === 0) {
                return <Box>No configuration differences found - all test runs use identical configurations</Box>;
              }

              const differentConfigs = comparisonData.configs || [];
              if (differentConfigs.length === 0) {
                return <Box>No configuration differences found - all test runs use identical configurations</Box>;
              }

              return (
                <Table
                  items={differentConfigs.map((config) => {
                    const values = typeof config.values === 'string' ? JSON.parse(config.values) : config.values;
                    return {
                      setting: config.setting,
                      ...values, // Spread the values object to create columns for each test run
                    };
                  })}
                  columnDefinitions={[
                    { id: 'setting', header: 'Config', cell: (item) => item.setting },
                    ...Object.keys(completeTestRuns).map((testRunId) => ({
                      id: testRunId,
                      header: createTestRunHeader(testRunId),
                      cell: (item) => item[testRunId] || 'N/A',
                    })),
                  ]}
                  variant="embedded"
                />
              );
            })()}
          </Container>

          {/* Accuracy Comparison */}
          <Container header={<Header variant="h3">Accuracy Comparison</Header>}>
            {(() => {
              const hasAccuracyData = Object.values(completeTestRuns).some((testRun) => testRun.accuracyBreakdown);

              if (!hasAccuracyData) {
                return <Box>No accuracy breakdown data available</Box>;
              }

              const allAccuracyMetrics = new Set();
              Object.values(completeTestRuns).forEach((testRun) => {
                if (testRun.accuracyBreakdown) {
                  Object.keys(testRun.accuracyBreakdown).forEach((metric) => {
                    allAccuracyMetrics.add(metric);
                  });
                }
              });

              return (
                <Table
                  items={Array.from(allAccuracyMetrics).map((metricKey) => ({
                    metric: metricKey.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase()),
                    ...Object.fromEntries(
                      Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                        const accuracyBreakdown = testRun.accuracyBreakdown || {};
                        const value = accuracyBreakdown[metricKey];
                        const displayValue =
                          value !== null && value !== undefined ? `${(value * 100).toFixed(1)}%` : '0.0%';
                        return [testRunId, displayValue];
                      }),
                    ),
                  }))}
                  columnDefinitions={[
                    { id: 'metric', header: 'Accuracy Metric', cell: (item) => item.metric },
                    ...Object.keys(completeTestRuns).map((testRunId) => ({
                      id: testRunId,
                      header: createTestRunHeader(testRunId),
                      cell: (item) => item[testRunId],
                    })),
                  ]}
                  variant="embedded"
                />
              );
            })()}
          </Container>

          {/* Cost Comparison */}
          <Container header={<Header variant="h3">Cost Comparison</Header>}>
            {(() => {
              const allCostMetrics = new Set();
              Object.values(completeTestRuns).forEach((testRun) => {
                if (testRun.costBreakdown) {
                  Object.entries(testRun.costBreakdown).forEach(([category, data]) => {
                    if (data && typeof data === 'object') {
                      Object.keys(data).forEach((api) => {
                        allCostMetrics.add(`${category}_${api}`);
                      });
                    }
                  });
                }
              });

              return allCostMetrics.size > 0 ? (
                <Table
                  items={Array.from(allCostMetrics).map((metricKey) => {
                    const [category, api] = metricKey.split('_');
                    return {
                      metric: `${category} ${api}`,
                      ...Object.fromEntries(
                        Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                          const costBreakdown = testRun.costBreakdown || {};
                          const cost = costBreakdown?.[category]?.[api] || 0;
                          return [testRunId, `$${cost.toFixed(4)}`];
                        }),
                      ),
                    };
                  })}
                  columnDefinitions={[
                    {
                      id: 'metric',
                      header: 'Cost Metric',
                      cell: (item) => item.metric,
                      width: 300,
                      wrapLines: true,
                    },
                    ...Object.keys(completeTestRuns).map((testRunId) => ({
                      id: testRunId,
                      header: createTestRunHeader(testRunId),
                      cell: (item) => item[testRunId],
                      width: 150,
                    })),
                  ]}
                  variant="embedded"
                />
              ) : (
                <Box>No cost breakdown data available</Box>
              );
            })()}
          </Container>

          {/* Usage Comparison */}
          <Container header={<Header variant="h3">Usage Comparison</Header>}>
            {(() => {
              const allUsageMetrics = new Set();
              Object.values(completeTestRuns).forEach((testRun) => {
                if (testRun.usageBreakdown) {
                  Object.entries(testRun.usageBreakdown).forEach(([service, metrics]) => {
                    Object.keys(metrics).forEach((metric) => {
                      allUsageMetrics.add(`${service}_${metric}`);
                    });
                  });
                }
              });

              return allUsageMetrics.size > 0 ? (
                <Table
                  items={Array.from(allUsageMetrics).map((metricKey) => {
                    const [service, metric] = metricKey.split('_');
                    return {
                      metric: `${service} ${metric}`,
                      ...Object.fromEntries(
                        Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                          const usageBreakdown = testRun.usageBreakdown || {};
                          const value = usageBreakdown?.[service]?.[metric] || 0;
                          return [testRunId, value.toLocaleString()];
                        }),
                      ),
                    };
                  })}
                  columnDefinitions={[
                    {
                      id: 'metric',
                      header: 'Usage Metric',
                      cell: (item) => item.metric,
                      width: 300,
                      wrapLines: true,
                    },
                    ...Object.keys(completeTestRuns).map((testRunId) => ({
                      id: testRunId,
                      header: createTestRunHeader(testRunId),
                      cell: (item) => item[testRunId],
                      width: 150,
                    })),
                  ]}
                  variant="embedded"
                />
              ) : (
                <Box>No usage breakdown data available</Box>
              );
            })()}
          </Container>
        </SpaceBetween>
      </SpaceBetween>
    </Container>
  );
};

TestComparison.propTypes = {
  preSelectedTestRunIds: PropTypes.arrayOf(PropTypes.string),
};

TestComparison.defaultProps = {
  preSelectedTestRunIds: [],
  onTestRunSelect: null,
};

export default TestComparison;
