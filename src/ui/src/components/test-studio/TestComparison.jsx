// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Container, Header, SpaceBetween, Table, Box, Button, ButtonDropdown } from '@cloudscape-design/components';
import { generateClient } from 'aws-amplify/api';
import COMPARE_TEST_RUNS from '../../graphql/queries/compareTestRuns';
import TestStudioHeader from './TestStudioHeader';

const client = generateClient();

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
            error.errors?.length > 0 ? error.errors.map((e) => e.message).join('; ') : error.message || 'Error comparing test runs';
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

  const downloadToCsv = () => {
    if (!comparisonData || !comparisonData.metrics) return;

    const completeTestRuns = Object.fromEntries(
      Object.entries(comparisonData.metrics).filter(
        ([, testRun]) => testRun.status === 'COMPLETE' || testRun.status === 'PARTIAL_COMPLETE',
      ),
    );

    // Create headers
    const headers = ['Metric', ...Object.keys(completeTestRuns)];

    // Create rows for performance metrics
    const performanceRows = [
      ['Test Set', ...Object.values(completeTestRuns).map((run) => run.testSetName || 'N/A')],
      ['Context', ...Object.values(completeTestRuns).map((run) => run.context || 'N/A')],
      ['Files Processed', ...Object.values(completeTestRuns).map((run) => run.filesCount || 'N/A')],
      ['Files Completed', ...Object.values(completeTestRuns).map((run) => run.completedFiles || 'N/A')],
      ['Files Failed', ...Object.values(completeTestRuns).map((run) => run.failedFiles || 'N/A')],
      [
        'Total Cost',
        ...Object.values(completeTestRuns).map((run) =>
          run.totalCost !== null && run.totalCost !== undefined ? `$${run.totalCost.toFixed(4)}` : 'N/A',
        ),
      ],
      [
        'Overall Accuracy',
        ...Object.values(completeTestRuns).map((run) =>
          run.overallAccuracy !== null && run.overallAccuracy !== undefined ? `${(run.overallAccuracy * 100).toFixed(1)}%` : 'N/A',
        ),
      ],
      [
        'Overall Confidence',
        ...Object.values(completeTestRuns).map((run) =>
          run.averageConfidence !== null && run.averageConfidence !== undefined ? `${(run.averageConfidence * 100).toFixed(1)}%` : 'N/A',
        ),
      ],
      [
        'Duration',
        ...Object.values(completeTestRuns).map((run) => {
          if (run.createdAt && run.completedAt) {
            const duration = new Date(run.completedAt) - new Date(run.createdAt);
            const minutes = Math.floor(duration / 60000);
            const seconds = Math.floor((duration % 60000) / 1000);
            return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
          }
          return 'N/A';
        }),
      ],
    ];

    // Add cost breakdown rows
    const costRows = [];
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

    allCostMetrics.forEach((metricKey) => {
      const [category, api] = metricKey.split('_');
      const row = [
        `Cost: ${category} ${api}`,
        ...Object.keys(completeTestRuns).map((testRunId) => {
          const testRun = completeTestRuns[testRunId];
          const cost = testRun.costBreakdown?.[category]?.[api] || 0;
          return `$${cost.toFixed(4)}`;
        }),
      ];
      costRows.push(row);
    });

    // Add usage breakdown rows
    const usageRows = [];
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

    allUsageMetrics.forEach((metricKey) => {
      const [service, metric] = metricKey.split('_');
      const row = [
        `Usage: ${service} ${metric}`,
        ...Object.keys(completeTestRuns).map((testRunId) => {
          const testRun = completeTestRuns[testRunId];
          const value = testRun.usageBreakdown?.[service]?.[metric] || 0;
          return value.toLocaleString();
        }),
      ];
      usageRows.push(row);
    });

    // Add config comparison rows
    const configRows = [];
    if (comparisonData.configs && comparisonData.configs.length > 0) {
      comparisonData.configs.forEach((config) => {
        const values = typeof config.values === 'string' ? JSON.parse(config.values) : config.values;
        const row = [config.setting, ...Object.keys(completeTestRuns).map((testRunId) => values[testRunId] || 'N/A')];
        configRows.push(row);
      });
    }

    // Combine all data
    const csvData = [
      headers,
      ['=== PERFORMANCE METRICS ==='],
      ...performanceRows,
      [''],
      ['=== COST BREAKDOWN ==='],
      ...costRows,
      [''],
      ['=== USAGE BREAKDOWN ==='],
      ...usageRows,
      [''],
      ['=== CONFIGURATION DIFFERENCES ==='],
      ...configRows,
    ];

    const csvContent = csvData.map((row) => row.map((field) => `"${String(field).replace(/"/g, '""')}"`).join(',')).join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `test-comparison-${new Date().toISOString().split('T')[0]}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const downloadToJson = () => {
    if (!comparisonData) return;

    const completeTestRuns = Object.fromEntries(
      Object.entries(comparisonData.metrics).filter(
        ([, testRun]) => testRun.status === 'COMPLETE' || testRun.status === 'PARTIAL_COMPLETE',
      ),
    );

    // Create JSON structure matching the UI sections
    const filteredData = {
      testRuns: Object.keys(completeTestRuns),
      performanceMetrics: Object.fromEntries(
        Object.entries(completeTestRuns).map(([testRunId, testRun]) => [
          testRunId,
          {
            testSetName: testRun.testSetName,
            context: testRun.context,
            filesCount: testRun.filesCount,
            completedFiles: testRun.completedFiles,
            failedFiles: testRun.failedFiles,
            totalCost: testRun.totalCost,
            overallAccuracy: testRun.overallAccuracy,
            averageConfidence: testRun.averageConfidence,
            duration:
              testRun.createdAt && testRun.completedAt
                ? (() => {
                    const duration = new Date(testRun.completedAt) - new Date(testRun.createdAt);
                    const minutes = Math.floor(duration / 60000);
                    const seconds = Math.floor((duration % 60000) / 1000);
                    return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
                  })()
                : 'N/A',
          },
        ]),
      ),
      costBreakdown: Object.fromEntries(
        Object.entries(completeTestRuns).map(([testRunId, testRun]) => [testRunId, testRun.costBreakdown || {}]),
      ),
      usageBreakdown: Object.fromEntries(
        Object.entries(completeTestRuns).map(([testRunId, testRun]) => [testRunId, testRun.usageBreakdown || {}]),
      ),
      accuracyBreakdown: Object.fromEntries(
        Object.entries(completeTestRuns).map(([testRunId, testRun]) => [testRunId, testRun.accuracyBreakdown || {}]),
      ),
      configurationDifferences: comparisonData.configs || [],
    };

    const jsonData = JSON.stringify(filteredData, null, 2);
    const blob = new Blob([jsonData], { type: 'application/json' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `test-comparison-${new Date().toISOString().split('T')[0]}.json`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (comparing) {
    return <Box>Loading comparison...</Box>;
  }

  if (!comparisonData) {
    return (
      <Container header={<TestStudioHeader title="Compare Test Runs" />}>
        <Box>No comparison data available</Box>
      </Container>
    );
  }

  if (comparisonData.error) {
    return (
      <Container header={<TestStudioHeader title="Compare Test Runs" />}>
        <Box>Error: {comparisonData.error}</Box>
      </Container>
    );
  }

  // Debug logging
  console.log('Comparison data structure:', comparisonData);
  console.log('Metrics structure:', comparisonData.metrics);

  // Filter out incomplete test runs (include COMPLETE and PARTIAL_COMPLETE)
  const completeTestRuns = comparisonData.metrics
    ? Object.fromEntries(
        Object.entries(comparisonData.metrics).filter(
          ([, testRun]) => testRun.status === 'COMPLETE' || testRun.status === 'PARTIAL_COMPLETE',
        ),
      )
    : {};

  const hasIncompleteRuns = comparisonData.metrics
    ? Object.values(comparisonData.metrics).some((testRun) => testRun.status !== 'COMPLETE' && testRun.status !== 'PARTIAL_COMPLETE')
    : false;

  const downloadButton = (
    <ButtonDropdown
      iconName="download"
      variant="normal"
      items={[
        { id: 'csv', text: 'CSV' },
        { id: 'json', text: 'JSON' },
      ]}
      onItemClick={({ detail }) => {
        if (detail.id === 'csv') {
          downloadToCsv();
        } else if (detail.id === 'json') {
          downloadToJson();
        }
      }}
    ></ButtonDropdown>
  );

  return (
    <Container
      header={
        <TestStudioHeader
          title={`Compare Test Runs (${Object.keys(completeTestRuns).length})`}
          showPrintButton={true}
          additionalActions={[downloadButton]}
        />
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
                    Object.entries(completeTestRuns).map(([testRunId, testRun]) => [testRunId, testRun.testSetName || 'N/A']),
                  ),
                },
                {
                  metric: 'Context',
                  ...Object.fromEntries(
                    Object.entries(completeTestRuns).map(([testRunId, testRun]) => [testRunId, testRun.context || 'N/A']),
                  ),
                },
                {
                  metric: 'Files Processed',
                  ...Object.fromEntries(
                    Object.entries(completeTestRuns).map(([testRunId, testRun]) => [testRunId, testRun.filesCount || 'N/A']),
                  ),
                },
                {
                  metric: 'Files Completed',
                  ...Object.fromEntries(
                    Object.entries(completeTestRuns).map(([testRunId, testRun]) => [testRunId, testRun.completedFiles || 'N/A']),
                  ),
                },
                {
                  metric: 'Files Failed',
                  ...Object.fromEntries(
                    Object.entries(completeTestRuns).map(([testRunId, testRun]) => [testRunId, testRun.failedFiles || 'N/A']),
                  ),
                },
                {
                  metric: 'Total Cost',
                  ...Object.fromEntries(
                    Object.entries(completeTestRuns).map(([testRunId, testRun]) => [
                      testRunId,
                      testRun.totalCost !== null && testRun.totalCost !== undefined ? `$${testRun.totalCost.toFixed(4)}` : 'N/A',
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
                  metric: 'Weighted Overall Score',
                  ...Object.fromEntries(
                    Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                      if (testRun.weightedOverallScores && testRun.weightedOverallScores.length > 0) {
                        const avg =
                          testRun.weightedOverallScores.reduce((sum, score) => sum + score, 0) / testRun.weightedOverallScores.length;
                        return [testRunId, `${(avg * 100).toFixed(1)}%`];
                      }
                      return [testRunId, 'N/A'];
                    }),
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
                {
                  metric: 'Duration',
                  ...Object.fromEntries(
                    Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                      if (testRun.createdAt && testRun.completedAt) {
                        const duration = new Date(testRun.completedAt) - new Date(testRun.createdAt);
                        const minutes = Math.floor(duration / 60000);
                        const seconds = Math.floor((duration % 60000) / 1000);
                        return [testRunId, minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`];
                      }
                      return [testRunId, 'N/A'];
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
                    return item[testRunId];
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
              if (!comparisonData.configs || comparisonData.configs.length === 0) {
                return <Box>No configuration differences found - all test runs use identical configurations</Box>;
              }

              return (
                <Table
                  items={comparisonData.configs.map((config) => {
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
                        const displayValue = value !== null && value !== undefined ? `${(value * 100).toFixed(1)}%` : '0.0%';
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
