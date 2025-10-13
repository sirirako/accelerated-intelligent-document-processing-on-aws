// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Container, Header, SpaceBetween, Table, Box, Button } from '@awsui/components-react';
import { API, graphqlOperation } from 'aws-amplify';
import COMPARE_TEST_RUNS from '../../graphql/queries/compareTestRuns';

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

// Helper function for cost change with colored arrows
const costChangeCell = (item) => {
  const changeValue = item.change || item.costChange;
  if (!changeValue || changeValue === 'N/A') return 'N/A';
  const match = changeValue.match(/^([-+]?\d+\.?\d*)%/);
  if (!match) return changeValue;

  const value = parseFloat(match[1]);
  const isPositive = value > 0;
  return (
    <>
      {Math.abs(value).toFixed(2)}%
      <span style={{ color: isPositive ? 'red' : 'green' }}>{isPositive ? ' ↑' : ' ↓'}</span>
    </>
  );
};

// Helper function for usage change with colored arrows
const usageChangeCell = (item) => {
  if (item.totalTokensChange === 'N/A') return 'N/A';
  const match = item.totalTokensChange.match(/^([-+]?\d+\.?\d*)%/);
  if (!match) return item.totalTokensChange;

  const value = parseFloat(match[1]);
  const isPositive = value > 0;
  return (
    <>
      {Math.abs(value).toFixed(2)}%
      <span style={{ color: isPositive ? 'red' : 'green' }}>{isPositive ? ' ↑' : ' ↓'}</span>
    </>
  );
};

// Component to handle config differences table
const ConfigDifferencesTable = ({ comparisonData, preSelectedTestRunIds }) => {
  if (!comparisonData.configs || comparisonData.configs.length === 0) {
    return <Box>No configuration data found</Box>;
  }

  const differentConfigs = comparisonData.configs.filter((config) => {
    const values = typeof config.values === 'string' ? JSON.parse(config.values) : config.values;
    const testRunValues = preSelectedTestRunIds.map((runId) => values[runId]);
    // Skip if all values are N/A or undefined
    if (testRunValues.every((value) => !value || value === 'N/A')) return false;
    // Show if values differ
    return testRunValues.some((value) => value !== testRunValues[0]);
  });

  if (differentConfigs.length === 0) {
    return <Box>All configurations are identical across test runs</Box>;
  }

  return (
    <Table
      items={differentConfigs}
      columnDefinitions={[
        { id: 'setting', header: 'Setting', cell: (item) => item.setting },
        ...preSelectedTestRunIds.map((runId) => ({
          id: runId,
          header: runId,
          cell: (item) => {
            const values = typeof item.values === 'string' ? JSON.parse(item.values) : item.values;
            return values[runId] ?? 'N/A';
          },
        })),
      ]}
    />
  );
};

ConfigDifferencesTable.propTypes = {
  comparisonData: PropTypes.shape({
    configs: PropTypes.arrayOf(
      PropTypes.shape({
        setting: PropTypes.string,
        values: PropTypes.oneOfType([PropTypes.string, PropTypes.object]),
      }),
    ),
  }).isRequired,
  preSelectedTestRunIds: PropTypes.arrayOf(PropTypes.string).isRequired,
};

const TestComparison = ({ preSelectedTestRunIds = [], onTestRunSelect }) => {
  const [comparisonData, setComparisonData] = useState(null);
  const [comparing, setComparing] = useState(false);

  useEffect(() => {
    const fetchComparison = async () => {
      if (preSelectedTestRunIds.length >= 2) {
        setComparing(true);
        console.log('=== STARTING COMPARISON ===');
        console.log('Selected test run IDs:', preSelectedTestRunIds);

        // Backup timeout to prevent infinite loading
        const backupTimeout = setTimeout(() => {
          console.log('BACKUP TIMEOUT: Forcing stop after 15 seconds');
          setComparing(false);
          setComparisonData({ error: 'Lambda function timed out - comparison is too expensive' });
        }, 15000);

        try {
          console.log('Making GraphQL request...');
          const result = await Promise.race([
            API.graphql(
              graphqlOperation(COMPARE_TEST_RUNS, {
                testRunIds: preSelectedTestRunIds,
              }),
            ),
            new Promise((_, reject) => {
              setTimeout(() => reject(new Error('Request timeout after 10 seconds')), 10000);
            }),
          ]);

          clearTimeout(backupTimeout);
          const compareData = result.data.compareTestRuns;

          // Parse metrics if it's a JSON string
          if (typeof compareData.metrics === 'string') {
            compareData.metrics = JSON.parse(compareData.metrics);
          }

          setComparisonData(compareData);
        } catch (error) {
          clearTimeout(backupTimeout);
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
    if (onTestRunSelect) {
      return (
        <Button variant="link" onClick={() => onTestRunSelect(testRunId)}>
          {testRunId}
        </Button>
      );
    }
    return testRunId;
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
  if (Array.isArray(comparisonData.metrics)) {
    console.log('First metric item:', comparisonData.metrics[0]);
  }

  // Filter out incomplete test runs
  const completeTestRuns = comparisonData.metrics
    ? Object.fromEntries(Object.entries(comparisonData.metrics).filter(([, testRun]) => testRun.status === 'COMPLETE'))
    : {};

  const hasIncompleteRuns = comparisonData.metrics
    ? Object.values(comparisonData.metrics).some((testRun) => testRun.status !== 'COMPLETE')
    : false;

  return (
    <Container header={<Header variant="h2">Compare Test Runs</Header>}>
      <SpaceBetween direction="vertical" size="l">
        {/* Comparison Results */}
        {comparisonData && (
          <SpaceBetween direction="vertical" size="l">
            {/* Config Differences - Main Focus */}
            <Box>
              <Header variant="h3">Configuration Differences</Header>
              {/* eslint-disable-next-line no-nested-ternary */}
              {preSelectedTestRunIds.length === 2 ? (
                comparisonData.configs && comparisonData.configs.length > 0 ? (
                  (() => {
                    // Backend already provides flattened configuration differences
                    const differentConfigs = comparisonData.configs || [];

                    return differentConfigs.length > 0 ? (
                      <Table
                        items={differentConfigs}
                        columnDefinitions={[
                          { id: 'setting', header: 'Setting', cell: (item) => item.setting },
                          ...preSelectedTestRunIds.map((runId) => ({
                            id: runId,
                            header: createTestRunHeader(runId),
                            cell: (item) => {
                              const values = typeof item.values === 'string' ? JSON.parse(item.values) : item.values;
                              return values[runId] ?? 'N/A';
                            },
                          })),
                        ]}
                      />
                    ) : (
                      <Box>All configurations are identical across test runs</Box>
                    );
                  })()
                ) : (
                  <Box>No configuration data found</Box>
                )
              ) : (
                <Box variant="awsui-key-label" color="text-status-success" padding="s">
                  {/* eslint-disable-next-line max-len */}
                  Configuration differences are only available when comparing exactly 2 test runs. Currently comparing{' '}
                  {preSelectedTestRunIds.length} test runs.
                </Box>
              )}
            </Box>

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
                      metric: 'Accuracy',
                      ...Object.fromEntries(
                        Object.entries(completeTestRuns).map(([testRunId, metrics]) => {
                          const test = typeof metrics.test === 'string' ? JSON.parse(metrics.test) : metrics.test;
                          return [
                            testRunId,
                            test?.accuracy?.accuracy !== null && test?.accuracy?.accuracy !== undefined
                              ? `${(test.accuracy.accuracy * 100).toFixed(2)}%`
                              : 'N/A',
                          ];
                        }),
                      ),
                    },
                    {
                      metric: 'Accuracy Change',
                      ...Object.fromEntries(
                        Object.entries(completeTestRuns).map(([testRunId, metrics]) => [
                          testRunId,
                          metrics.accuracySimilarity !== null && metrics.accuracySimilarity !== undefined
                            ? metrics.accuracySimilarity.toFixed(2)
                            : 'N/A',
                        ]),
                      ),
                    },
                    {
                      metric: 'Confidence',
                      ...Object.fromEntries(
                        Object.entries(completeTestRuns).map(([testRunId, metrics]) => {
                          const test = typeof metrics.test === 'string' ? JSON.parse(metrics.test) : metrics.test;
                          return [
                            testRunId,
                            test?.confidence?.average_confidence !== null &&
                            test?.confidence?.average_confidence !== undefined
                              ? `${(test.confidence.average_confidence * 100).toFixed(2)}%`
                              : 'N/A',
                          ];
                        }),
                      ),
                    },
                    {
                      metric: 'Confidence Change',
                      ...Object.fromEntries(
                        Object.entries(completeTestRuns).map(([testRunId, metrics]) => [
                          testRunId,
                          metrics.confidenceSimilarity !== null && metrics.confidenceSimilarity !== undefined
                            ? metrics.confidenceSimilarity.toFixed(2)
                            : 'N/A',
                        ]),
                      ),
                    },
                    {
                      metric: 'Files Processed',
                      ...Object.fromEntries(
                        Object.entries(completeTestRuns).map(([testRunId, metrics]) => [
                          testRunId,
                          metrics.filesCount || 'N/A',
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
                        if (item.metric === 'Accuracy Change' || item.metric === 'Confidence Change') {
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

            {/* Accuracy Breakdown */}
            <Box>
              <Header variant="h3">Accuracy Breakdown</Header>
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
                      metric: 'Test Precision',
                      ...Object.fromEntries(
                        Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                          const test = typeof testRun.test === 'string' ? JSON.parse(testRun.test) : testRun.test;
                          return [
                            testRunId,
                            test?.accuracy?.precision ? `${(test.accuracy.precision * 100).toFixed(2)}%` : 'N/A',
                          ];
                        }),
                      ),
                    },
                    {
                      metric: 'Test Recall',
                      ...Object.fromEntries(
                        Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                          const test = typeof testRun.test === 'string' ? JSON.parse(testRun.test) : testRun.test;
                          return [
                            testRunId,
                            test?.accuracy?.recall ? `${(test.accuracy.recall * 100).toFixed(2)}%` : 'N/A',
                          ];
                        }),
                      ),
                    },
                    {
                      metric: 'Test F1 Score',
                      ...Object.fromEntries(
                        Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                          const test = typeof testRun.test === 'string' ? JSON.parse(testRun.test) : testRun.test;
                          return [
                            testRunId,
                            test?.accuracy?.f1_score ? `${(test.accuracy.f1_score * 100).toFixed(2)}%` : 'N/A',
                          ];
                        }),
                      ),
                    },
                  ]}
                  columnDefinitions={[
                    { id: 'metric', header: 'Metric', cell: (item) => item.metric },
                    ...Object.keys(completeTestRuns).map((testRunId) => ({
                      id: testRunId,
                      header: createTestRunHeader(testRunId),
                      cell: (item) => item[testRunId],
                    })),
                  ]}
                  variant="embedded"
                />
              ) : (
                <Box>No completed test runs available</Box>
              )}
            </Box>

            {/* Cost Breakdown */}
            <Box>
              <Header variant="h3">Cost Breakdown</Header>
              {Object.keys(completeTestRuns).length > 0 ? (
                <>
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
                        metric: 'Test Cost',
                        ...Object.fromEntries(
                          Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                            const test = typeof testRun.test === 'string' ? JSON.parse(testRun.test) : testRun.test;
                            return [testRunId, test?.cost?.total_cost ? `$${test.cost.total_cost.toFixed(4)}` : 'N/A'];
                          }),
                        ),
                      },
                      {
                        metric: 'Baseline Cost',
                        ...Object.fromEntries(
                          Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                            const baseline =
                              typeof testRun.baseline === 'string' ? JSON.parse(testRun.baseline) : testRun.baseline;
                            return [
                              testRunId,
                              baseline?.cost?.total_cost ? `$${baseline.cost.total_cost.toFixed(4)}` : 'N/A',
                            ];
                          }),
                        ),
                      },
                      {
                        metric: 'Cost Change',
                        ...Object.fromEntries(
                          Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                            const test = typeof testRun.test === 'string' ? JSON.parse(testRun.test) : testRun.test;
                            const baseline =
                              typeof testRun.baseline === 'string' ? JSON.parse(testRun.baseline) : testRun.baseline;
                            return [
                              testRunId,
                              test?.cost?.total_cost && baseline?.cost?.total_cost
                                ? `${(
                                    ((test.cost.total_cost - baseline.cost.total_cost) / baseline.cost.total_cost) *
                                    100
                                  ).toFixed(2)}%${
                                    (test.cost.total_cost - baseline.cost.total_cost) / baseline.cost.total_cost > 0
                                      ? ' ↑'
                                      : ' ↓'
                                  }`
                                : 'N/A',
                            ];
                          }),
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
                          if (item.metric === 'Cost Change') {
                            return costChangeCell({ costChange: value });
                          }
                          return value;
                        },
                      })),
                    ]}
                    variant="embedded"
                  />

                  {/* Service Cost Breakdown */}
                  <Box margin={{ top: 'm' }}>
                    <Header variant="h4">Service Cost Breakdown</Header>
                    <Table
                      items={(() => {
                        const calculateChange = (testVal, baselineVal) => {
                          if (!baselineVal || baselineVal === 0) return 'N/A';
                          const change = (((testVal - baselineVal) / baselineVal) * 100).toFixed(2);
                          const isIncrease = parseFloat(change) > 0;
                          let arrow = '';
                          if (parseFloat(change) !== 0) {
                            arrow = isIncrease ? ' ↑' : ' ↓';
                          }
                          return `${Math.abs(change)}%${arrow}`;
                        };

                        const serviceMetrics = new Map();

                        // Collect all service cost metrics across test runs
                        Object.entries(completeTestRuns).forEach(([testRunId, testRun]) => {
                          const test = typeof testRun.test === 'string' ? JSON.parse(testRun.test) : testRun.test;
                          const baseline =
                            typeof testRun.baseline === 'string' ? JSON.parse(testRun.baseline) : testRun.baseline;

                          if (baseline?.cost && test?.cost) {
                            // Get all unique service keys from both baseline and test
                            const allCostKeys = new Set([
                              ...Object.keys(baseline.cost).filter((key) => key !== 'total_cost'),
                              ...Object.keys(test.cost).filter((key) => key !== 'total_cost'),
                            ]);

                            allCostKeys.forEach((service) => {
                              const baselineServiceCost = baseline.cost[service];
                              const testServiceCost = test.cost[service];

                              // Sum all cost values within the service object (same as TestResults.jsx)
                              const baselineValue = baselineServiceCost
                                ? Object.values(baselineServiceCost).reduce(
                                    (sum, val) => sum + (typeof val === 'number' ? val : 0),
                                    0,
                                  )
                                : 0;
                              const testValue = testServiceCost
                                ? Object.values(testServiceCost).reduce(
                                    (sum, val) => sum + (typeof val === 'number' ? val : 0),
                                    0,
                                  )
                                : 0;

                              if (baselineValue > 0 || testValue > 0) {
                                if (!serviceMetrics.has(service)) {
                                  serviceMetrics.set(service, {});
                                }
                                const change = calculateChange(testValue, baselineValue);
                                serviceMetrics.get(service)[testRunId] = {
                                  baseline: baselineValue.toFixed(4),
                                  test: testValue.toFixed(4),
                                  change,
                                };
                              }
                            });
                          }
                        });

                        // Convert to table format
                        return Array.from(serviceMetrics.entries()).map(([metric, values]) => ({
                          metric,
                          ...values,
                        }));
                      })()}
                      columnDefinitions={[
                        { id: 'metric', header: 'Service/Type', cell: (item) => item.metric },
                        ...Object.keys(completeTestRuns).map((testRunId) => ({
                          id: testRunId,
                          header: createTestRunHeader(testRunId),
                          // eslint-disable-next-line react/no-unstable-nested-components
                          cell: (item) => {
                            const data = item[testRunId];
                            if (!data) return 'N/A';

                            // Parse change to get color for arrow only
                            const changeStr = data.change;
                            if (changeStr === 'N/A') return `$${data.baseline} → $${data.test} (N/A)`;

                            // Check if there's an arrow
                            if (!changeStr.includes('↑') && !changeStr.includes('↓')) {
                              return (
                                <span>
                                  ${data.baseline} → ${data.test} ({changeStr})
                                </span>
                              );
                            }

                            const isIncrease = changeStr.includes('↑');
                            const color = isIncrease ? 'red' : 'green';
                            const arrow = isIncrease ? ' ↑' : ' ↓';
                            const percentage = changeStr.replace(arrow, '');

                            return (
                              <span>
                                ${data.baseline} → ${data.test} ({percentage}
                                <span style={{ color }}>{arrow}</span>)
                              </span>
                            );
                          },
                        })),
                      ]}
                      variant="embedded"
                    />
                  </Box>
                </>
              ) : (
                <Box>No cost data available</Box>
              )}
            </Box>

            {/* Usage Breakdown */}
            <Box>
              <Header variant="h3">Usage Breakdown</Header>
              {Object.keys(completeTestRuns).length > 0 ? (
                <>
                  <Table
                    items={(() => {
                      const calculateChange = (testVal, baselineVal) => {
                        if (!baselineVal || baselineVal === 0) return 'N/A';
                        const change = (((testVal - baselineVal) / baselineVal) * 100).toFixed(2);
                        const isIncrease = parseFloat(change) > 0;
                        let arrow = '';
                        if (parseFloat(change) !== 0) {
                          arrow = isIncrease ? ' ↑' : ' ↓';
                        }
                        return `${Math.abs(change)}%${arrow}`;
                      };

                      const aggregateTokens = (usage) => {
                        const tokens = { inputTokens: 0, outputTokens: 0, totalTokens: 0 };
                        if (usage) {
                          Object.keys(usage).forEach((key) => {
                            if (key.includes('bedrock') && usage[key]) {
                              tokens.inputTokens += usage[key].inputTokens || 0;
                              tokens.outputTokens += usage[key].outputTokens || 0;
                              tokens.totalTokens += usage[key].totalTokens || 0;
                            }
                          });
                        }
                        return tokens;
                      };

                      return [
                        {
                          metric: 'Test Input Tokens',
                          ...Object.fromEntries(
                            Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                              const test = typeof testRun.test === 'string' ? JSON.parse(testRun.test) : testRun.test;
                              const testTokens = aggregateTokens(test?.usage);
                              return [testRunId, testTokens.inputTokens.toLocaleString()];
                            }),
                          ),
                        },
                        {
                          metric: 'Baseline Input Tokens',
                          ...Object.fromEntries(
                            Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                              const baseline =
                                typeof testRun.baseline === 'string' ? JSON.parse(testRun.baseline) : testRun.baseline;
                              const baselineTokens = aggregateTokens(baseline?.usage);
                              return [testRunId, baselineTokens.inputTokens.toLocaleString()];
                            }),
                          ),
                        },
                        {
                          metric: 'Input Token Change',
                          ...Object.fromEntries(
                            Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                              const test = typeof testRun.test === 'string' ? JSON.parse(testRun.test) : testRun.test;
                              const baseline =
                                typeof testRun.baseline === 'string' ? JSON.parse(testRun.baseline) : testRun.baseline;
                              const testTokens = aggregateTokens(test?.usage);
                              const baselineTokens = aggregateTokens(baseline?.usage);
                              return [testRunId, calculateChange(testTokens.inputTokens, baselineTokens.inputTokens)];
                            }),
                          ),
                        },
                        {
                          metric: 'Test Output Tokens',
                          ...Object.fromEntries(
                            Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                              const test = typeof testRun.test === 'string' ? JSON.parse(testRun.test) : testRun.test;
                              const testTokens = aggregateTokens(test?.usage);
                              return [testRunId, testTokens.outputTokens.toLocaleString()];
                            }),
                          ),
                        },
                        {
                          metric: 'Baseline Output Tokens',
                          ...Object.fromEntries(
                            Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                              const baseline =
                                typeof testRun.baseline === 'string' ? JSON.parse(testRun.baseline) : testRun.baseline;
                              const baselineTokens = aggregateTokens(baseline?.usage);
                              return [testRunId, baselineTokens.outputTokens.toLocaleString()];
                            }),
                          ),
                        },
                        {
                          metric: 'Output Token Change',
                          ...Object.fromEntries(
                            Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                              const test = typeof testRun.test === 'string' ? JSON.parse(testRun.test) : testRun.test;
                              const baseline =
                                typeof testRun.baseline === 'string' ? JSON.parse(testRun.baseline) : testRun.baseline;
                              const testTokens = aggregateTokens(test?.usage);
                              const baselineTokens = aggregateTokens(baseline?.usage);
                              return [testRunId, calculateChange(testTokens.outputTokens, baselineTokens.outputTokens)];
                            }),
                          ),
                        },
                        {
                          metric: 'Test Total Tokens',
                          ...Object.fromEntries(
                            Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                              const test = typeof testRun.test === 'string' ? JSON.parse(testRun.test) : testRun.test;
                              const testTokens = aggregateTokens(test?.usage);
                              return [testRunId, testTokens.totalTokens.toLocaleString()];
                            }),
                          ),
                        },
                        {
                          metric: 'Baseline Total Tokens',
                          ...Object.fromEntries(
                            Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                              const baseline =
                                typeof testRun.baseline === 'string' ? JSON.parse(testRun.baseline) : testRun.baseline;
                              const baselineTokens = aggregateTokens(baseline?.usage);
                              return [testRunId, baselineTokens.totalTokens.toLocaleString()];
                            }),
                          ),
                        },
                        {
                          metric: 'Total Token Change',
                          ...Object.fromEntries(
                            Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                              const test = typeof testRun.test === 'string' ? JSON.parse(testRun.test) : testRun.test;
                              const baseline =
                                typeof testRun.baseline === 'string' ? JSON.parse(testRun.baseline) : testRun.baseline;
                              const testTokens = aggregateTokens(test?.usage);
                              const baselineTokens = aggregateTokens(baseline?.usage);
                              return [testRunId, calculateChange(testTokens.totalTokens, baselineTokens.totalTokens)];
                            }),
                          ),
                        },
                      ];
                    })()}
                    columnDefinitions={[
                      { id: 'metric', header: 'Metric', cell: (item) => item.metric },
                      ...Object.keys(completeTestRuns).map((testRunId) => ({
                        id: testRunId,
                        header: createTestRunHeader(testRunId),
                        cell: (item) => {
                          const value = item[testRunId];
                          if (item.metric.includes('Change')) {
                            return usageChangeCell({ totalTokensChange: value });
                          }
                          return value;
                        },
                      })),
                    ]}
                    variant="embedded"
                  />

                  {/* Service Usage Breakdown */}
                  <Box margin={{ top: 'm' }}>
                    <Header variant="h4">Service Usage Breakdown</Header>
                    <Table
                      items={(() => {
                        const calculateChange = (testVal, baselineVal) => {
                          if (!baselineVal || baselineVal === 0) return 'N/A';
                          const change = (((testVal - baselineVal) / baselineVal) * 100).toFixed(2);
                          const isIncrease = parseFloat(change) > 0;
                          let arrow = '';
                          if (parseFloat(change) !== 0) {
                            arrow = isIncrease ? ' ↑' : ' ↓';
                          }
                          return `${Math.abs(change)}%${arrow}`;
                        };

                        const serviceMetrics = new Map();

                        // Collect all service usage metrics across test runs
                        Object.entries(completeTestRuns).forEach(([testRunId, testRun]) => {
                          const test = typeof testRun.test === 'string' ? JSON.parse(testRun.test) : testRun.test;
                          const baseline =
                            typeof testRun.baseline === 'string' ? JSON.parse(testRun.baseline) : testRun.baseline;

                          if (baseline?.usage && test?.usage) {
                            // Add other non-token metrics (same as TestResults.jsx)
                            Object.keys(baseline.usage).forEach((key) => {
                              if (!key.includes('bedrock')) {
                                const baselineUsage = baseline.usage[key];
                                const testUsage = test.usage[key] || {};

                                if (typeof baselineUsage === 'object') {
                                  Object.keys(baselineUsage).forEach((subKey) => {
                                    const baselineValue = baselineUsage[subKey];
                                    const testValue = testUsage[subKey] || 0;

                                    if (baselineValue > 0 || testValue > 0) {
                                      const metricName = `${key.replace(/\//g, ' - ')} (${subKey})`;

                                      if (!serviceMetrics.has(metricName)) {
                                        serviceMetrics.set(metricName, {});
                                      }
                                      const change = calculateChange(testValue, baselineValue);
                                      serviceMetrics.get(metricName)[testRunId] = {
                                        baseline: baselineValue,
                                        test: testValue,
                                        change,
                                      };
                                    }
                                  });
                                }
                              }
                            });
                          }
                        });

                        // Convert to table format
                        return Array.from(serviceMetrics.entries()).map(([metric, values]) => ({
                          metric,
                          ...values,
                        }));
                      })()}
                      columnDefinitions={[
                        { id: 'metric', header: 'Service Metric', cell: (item) => item.metric },
                        ...Object.keys(completeTestRuns).map((testRunId) => ({
                          id: testRunId,
                          header: createTestRunHeader(testRunId),
                          // eslint-disable-next-line react/no-unstable-nested-components
                          cell: (item) => {
                            const data = item[testRunId];
                            if (!data) return 'N/A';

                            // Parse change to get color for arrow only
                            const changeStr = data.change;
                            if (changeStr === 'N/A') return `${data.baseline} → ${data.test} (N/A)`;

                            // Check if there's an arrow
                            if (!changeStr.includes('↑') && !changeStr.includes('↓')) {
                              return (
                                <span>
                                  {data.baseline} → {data.test} ({changeStr})
                                </span>
                              );
                            }

                            const isIncrease = changeStr.includes('↑');
                            const color = isIncrease ? 'red' : 'green';
                            const arrow = isIncrease ? ' ↑' : ' ↓';
                            const percentage = changeStr.replace(arrow, '');

                            return (
                              <span>
                                {data.baseline} → {data.test} ({percentage}
                                <span style={{ color }}>{arrow}</span>)
                              </span>
                            );
                          },
                        })),
                      ]}
                      variant="embedded"
                    />
                  </Box>
                </>
              ) : (
                <Box>No completed test runs available</Box>
              )}
            </Box>
          </SpaceBetween>
        )}
      </SpaceBetween>
    </Container>
  );
};

TestComparison.propTypes = {
  preSelectedTestRunIds: PropTypes.arrayOf(PropTypes.string),
  onTestRunSelect: PropTypes.func,
};

TestComparison.defaultProps = {
  preSelectedTestRunIds: [],
  onTestRunSelect: null,
};

export default TestComparison;
