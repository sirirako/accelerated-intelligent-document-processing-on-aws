// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Container, Header, SpaceBetween, Table, Box, Button, ButtonDropdown, ProgressBar } from '@cloudscape-design/components';
import { generateClient } from 'aws-amplify/api';
import COMPARE_TEST_RUNS from '../../graphql/queries/compareTestRuns';
import TestStudioHeader from './TestStudioHeader';

const client = generateClient();

const TestComparison = ({ preSelectedTestRunIds = [] }) => {
  const [comparisonData, setComparisonData] = useState(null);
  const [comparing, setComparing] = useState(false);
  const [currentAttempt, setCurrentAttempt] = useState(1);

  useEffect(() => {
    const fetchComparison = async () => {
      if (preSelectedTestRunIds.length >= 2) {
        setComparing(true);
        console.log('=== STARTING COMPARISON ===');
        console.log('Selected test run IDs:', preSelectedTestRunIds);

        try {
          console.log('Making GraphQL request...');
          let result;
          let attempt = 1;
          const maxRetries = 5;

          while (attempt <= maxRetries) {
            try {
              setCurrentAttempt(attempt);
              result = await client.graphql({
                query: COMPARE_TEST_RUNS,
                variables: { testRunIds: preSelectedTestRunIds },
              });
              setCurrentAttempt(5); // Set to 100% before completing
              await new Promise((resolve) => setTimeout(resolve, 500)); // Brief pause to show 100%
              break;
            } catch (error) {
              const isTimeout =
                error.message?.toLowerCase().includes('timeout') ||
                error.code === 'TIMEOUT' ||
                error.message?.includes('Request failed with status code 504') ||
                error.name === 'TimeoutError' ||
                error.code === 'NetworkError' ||
                error.errors?.some(
                  (err) => err.errorType === 'Lambda:ExecutionTimeoutException' || err.message?.toLowerCase().includes('timeout'),
                );
              if (isTimeout && attempt < maxRetries) {
                console.log(`COMPARE_TEST_RUNS attempt ${attempt} failed, retrying...`, error.message);
                attempt++;

                // Animate progress during 5-second wait
                const waitTime = 5000;
                const intervalTime = 100;
                const steps = waitTime / intervalTime;
                const startProgress = (attempt - 1) * 20;
                const endProgress = attempt * 20;
                const progressStep = (endProgress - startProgress) / steps;

                let currentProgress = startProgress;
                const progressInterval = setInterval(() => {
                  currentProgress += progressStep;
                  setCurrentAttempt(Math.min(currentProgress / 20, 5));
                }, intervalTime);

                await new Promise((resolve) =>
                  setTimeout(() => {
                    clearInterval(progressInterval);
                    setCurrentAttempt(attempt);
                    resolve();
                  }, waitTime),
                );

                continue;
              }
              throw error;
            }
          }

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
        'Average Accuracy',
        ...Object.values(completeTestRuns).map((run) =>
          run.overallAccuracy !== null && run.overallAccuracy !== undefined ? run.overallAccuracy.toFixed(3) : 'N/A',
        ),
      ],
      [
        'Average Confidence',
        ...Object.values(completeTestRuns).map((run) =>
          run.averageConfidence !== null && run.averageConfidence !== undefined ? `${(run.averageConfidence * 100).toFixed(1)}%` : 'N/A',
        ),
      ],
      [
        'Average Weighted Overall Score',
        ...Object.values(completeTestRuns).map((run) => {
          if (run.weightedOverallScores && run.weightedOverallScores.length > 0) {
            const avg = run.weightedOverallScores.reduce((sum, score) => sum + score, 0) / run.weightedOverallScores.length;
            return avg.toFixed(3);
          }
          return 'N/A';
        }),
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
    const allCostItems = new Set();

    Object.values(completeTestRuns).forEach((testRun) => {
      if (testRun.costBreakdown) {
        Object.entries(testRun.costBreakdown).forEach(([context, services]) => {
          Object.keys(services).forEach((serviceUnit) => {
            // Parse service/api_unit format: find last underscore to separate unit
            const lastUnderscoreIndex = serviceUnit.lastIndexOf('_');
            const serviceApi = serviceUnit.substring(0, lastUnderscoreIndex);
            const unit = serviceUnit.substring(lastUnderscoreIndex + 1);
            const [service, api] = serviceApi.split('/');
            allCostItems.add(`${context}|${service}/${api}|${unit}`);
          });
        });
      }
    });

    // Add cost breakdown header
    costRows.push(['Context', 'Service/Api', 'Unit', ...Object.keys(completeTestRuns)]);

    Array.from(allCostItems)
      .sort()
      .forEach((itemKey) => {
        const [context, serviceApi, unit] = itemKey.split('|');
        const row = [context, serviceApi, unit];

        Object.entries(completeTestRuns).forEach(([testRunId, testRun]) => {
          const services = testRun.costBreakdown?.[context] || {};
          const serviceKey = Object.keys(services).find((key) => {
            const lastUnderscoreIndex = key.lastIndexOf('_');
            const keyServiceApi = key.substring(0, lastUnderscoreIndex);
            const [keyService, keyApi] = keyServiceApi.split('/');
            return `${keyService}/${keyApi}` === serviceApi;
          });

          const details = services[serviceKey] || {};
          const estimatedCost = details.estimated_cost || 0;
          row.push(estimatedCost > 0 ? `$${estimatedCost.toFixed(4)}` : '$0.0000');
        });

        costRows.push(row);
      });

    // Add usage breakdown rows
    const usageRows = [];
    usageRows.push(['Context', 'Service/Api', 'Unit', ...Object.keys(completeTestRuns)]);

    Array.from(allCostItems)
      .sort()
      .forEach((itemKey) => {
        const [context, serviceApi, unit] = itemKey.split('|');
        const row = [context, serviceApi, unit];

        Object.entries(completeTestRuns).forEach(([testRunId, testRun]) => {
          const services = testRun.costBreakdown?.[context] || {};
          const serviceKey = Object.keys(services).find((key) => {
            const lastUnderscoreIndex = key.lastIndexOf('_');
            const keyServiceApi = key.substring(0, lastUnderscoreIndex);
            const [keyService, keyApi] = keyServiceApi.split('/');
            return `${keyService}/${keyApi}` === serviceApi;
          });

          const details = services[serviceKey] || {};
          const value = details.value || 0;
          row.push(value > 0 ? value.toLocaleString() : '0');
        });

        usageRows.push(row);
      });

    // Add accuracy breakdown rows
    const accuracyRows = [];
    const allAccuracyMetrics = new Set();
    Object.values(completeTestRuns).forEach((testRun) => {
      if (testRun.accuracyBreakdown) {
        Object.keys(testRun.accuracyBreakdown).forEach((metric) => {
          allAccuracyMetrics.add(metric);
        });
      }
    });

    // Add accuracy breakdown header
    accuracyRows.push(['Accuracy Metric', ...Object.keys(completeTestRuns)]);

    // Add accuracy breakdown metrics
    Array.from(allAccuracyMetrics).forEach((metricKey) => {
      const row = [metricKey.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())];
      Object.entries(completeTestRuns).forEach(([testRunId, testRun]) => {
        const accuracyBreakdown = testRun.accuracyBreakdown || {};
        const value = accuracyBreakdown[metricKey];
        const displayValue = value !== null && value !== undefined ? value.toFixed(3) : '0.000';
        row.push(displayValue);
      });
      accuracyRows.push(row);
    });

    // Add weighted overall score to accuracy breakdown
    const weightedRow = ['Weighted Overall Score'];
    Object.entries(completeTestRuns).forEach(([testRunId, testRun]) => {
      if (testRun.weightedOverallScores && testRun.weightedOverallScores.length > 0) {
        const avg = testRun.weightedOverallScores.reduce((sum, score) => sum + score, 0) / testRun.weightedOverallScores.length;
        weightedRow.push(avg.toFixed(3));
      } else {
        weightedRow.push('N/A');
      }
    });
    accuracyRows.push(weightedRow);

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
      ['=== CONFIGURATION COMPARISON ==='],
      ...configRows,
      [''],
      ['=== AVERAGE ACCURACY BREAKDOWN ==='],
      ...accuracyRows,
      [''],
      ['=== COST BREAKDOWN ==='],
      ...costRows,
      [''],
      ['=== USAGE BREAKDOWN ==='],
      ...usageRows,
    ];

    const csvContent = csvData.map((row) => row.map((field) => `"${String(field).replace(/"/g, '""')}"`).join(',')).join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    const now = new Date();
    const timestamp = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(
      2,
      '0',
    )}-${String(now.getHours()).padStart(2, '0')}-${String(now.getMinutes()).padStart(2, '0')}-${String(now.getSeconds()).padStart(
      2,
      '0',
    )}`;
    link.setAttribute('href', url);
    link.setAttribute('download', `test-comparison-${timestamp}.csv`);
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
            averageAccuracy: testRun.overallAccuracy,
            averageConfidence: testRun.averageConfidence,
            averageWeightedOverallScore:
              testRun.weightedOverallScores && testRun.weightedOverallScores.length > 0
                ? testRun.weightedOverallScores.reduce((sum, score) => sum + score, 0) / testRun.weightedOverallScores.length
                : null,
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
      configurationDifferences: comparisonData.configs || [],
      accuracyBreakdown: Object.fromEntries(
        Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
          const breakdown = { ...(testRun.accuracyBreakdown || {}) };
          // Add weighted overall score to accuracy breakdown
          if (testRun.weightedOverallScores && testRun.weightedOverallScores.length > 0) {
            breakdown.weightedOverallScore =
              testRun.weightedOverallScores.reduce((sum, score) => sum + score, 0) / testRun.weightedOverallScores.length;
          }
          return [testRunId, breakdown];
        }),
      ),
      costBreakdown: Object.fromEntries(
        Object.entries(completeTestRuns).map(([testRunId, testRun]) => [testRunId, testRun.costBreakdown || {}]),
      ),
    };

    const jsonData = JSON.stringify(filteredData, null, 2);
    const blob = new Blob([jsonData], { type: 'application/json' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    const now = new Date();
    const timestamp = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(
      2,
      '0',
    )}-${String(now.getHours()).padStart(2, '0')}-${String(now.getMinutes()).padStart(2, '0')}-${String(now.getSeconds()).padStart(
      2,
      '0',
    )}`;
    link.setAttribute('href', url);
    link.setAttribute('download', `test-comparison-${timestamp}.json`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (comparing) {
    return <ProgressBar status="in-progress" label="Loading comparison..." value={currentAttempt * 20} />;
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
                  metric: 'Average Accuracy',
                  ...Object.fromEntries(
                    Object.entries(completeTestRuns).map(([testRunId, testRun]) => [
                      testRunId,
                      testRun.overallAccuracy !== null && testRun.overallAccuracy !== undefined
                        ? testRun.overallAccuracy.toFixed(3)
                        : 'N/A',
                    ]),
                  ),
                },
                {
                  metric: 'Average Weighted Overall Score',
                  ...Object.fromEntries(
                    Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                      if (testRun.weightedOverallScores && testRun.weightedOverallScores.length > 0) {
                        const avg =
                          testRun.weightedOverallScores.reduce((sum, score) => sum + score, 0) / testRun.weightedOverallScores.length;
                        return [testRunId, avg.toFixed(3)];
                      }
                      return [testRunId, 'N/A'];
                    }),
                  ),
                },
                {
                  metric: 'Average Confidence',
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

          {/* Average Accuracy Comparison */}
          <Container header={<Header variant="h3">Average Accuracy Comparison</Header>}>
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
                  items={[
                    ...Array.from(allAccuracyMetrics).map((metricKey) => ({
                      metric: metricKey.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase()),
                      ...Object.fromEntries(
                        Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                          const accuracyBreakdown = testRun.accuracyBreakdown || {};
                          const value = accuracyBreakdown[metricKey];
                          const displayValue = value !== null && value !== undefined ? value.toFixed(3) : '0.000';
                          return [testRunId, displayValue];
                        }),
                      ),
                    })),
                    {
                      metric: 'Weighted Overall Score',
                      ...Object.fromEntries(
                        Object.entries(completeTestRuns).map(([testRunId, testRun]) => {
                          if (testRun.weightedOverallScores && testRun.weightedOverallScores.length > 0) {
                            const avg =
                              testRun.weightedOverallScores.reduce((sum, score) => sum + score, 0) / testRun.weightedOverallScores.length;
                            return [testRunId, avg.toFixed(3)];
                          }
                          return [testRunId, 'N/A'];
                        }),
                      ),
                    },
                  ]}
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
          <Container header={<Header variant="h3">Cost Breakdown Comparison</Header>}>
            {(() => {
              const allCostItems = new Set();

              // Collect all unique cost items
              Object.values(completeTestRuns).forEach((testRun) => {
                if (testRun.costBreakdown) {
                  Object.entries(testRun.costBreakdown).forEach(([context, services]) => {
                    Object.keys(services).forEach((serviceUnit) => {
                      const lastUnderscoreIndex = serviceUnit.lastIndexOf('_');
                      const serviceApi = serviceUnit.substring(0, lastUnderscoreIndex);
                      const unit = serviceUnit.substring(lastUnderscoreIndex + 1);
                      const [service, api] = serviceApi.split('/');
                      allCostItems.add(`${context}|${service}/${api}|${unit}`);
                    });
                  });
                }
              });

              const tableItems = Array.from(allCostItems).map((itemKey) => {
                const [context, serviceApi, unit] = itemKey.split('|');
                const row = {
                  context,
                  serviceApi,
                  unit,
                };

                // Add cost for each test run
                Object.entries(completeTestRuns).forEach(([testRunId, testRun]) => {
                  const services = testRun.costBreakdown?.[context] || {};
                  const serviceKey = Object.keys(services).find((key) => {
                    const lastUnderscoreIndex = key.lastIndexOf('_');
                    const keyServiceApi = key.substring(0, lastUnderscoreIndex);
                    const [keyService, keyApi] = keyServiceApi.split('/');
                    return `${keyService}/${keyApi}` === serviceApi;
                  });

                  const details = services[serviceKey] || {};
                  const estimatedCost = details.estimated_cost || 0;
                  row[testRunId] = estimatedCost > 0 ? `$${estimatedCost.toFixed(4)}` : '$0.0000';
                });

                return row;
              });

              // Sort by context, then by service/api
              tableItems.sort((a, b) => {
                if (a.context !== b.context) return a.context.localeCompare(b.context);
                return a.serviceApi.localeCompare(b.serviceApi);
              });

              return tableItems.length > 0 ? (
                <Table
                  items={tableItems}
                  columnDefinitions={[
                    {
                      id: 'context',
                      header: 'Context',
                      cell: (item) => item.context,
                      width: 150,
                    },
                    {
                      id: 'serviceApi',
                      header: 'Service/Api',
                      cell: (item) => item.serviceApi,
                      width: 250,
                    },
                    {
                      id: 'unit',
                      header: 'Unit',
                      cell: (item) => item.unit,
                      width: 120,
                    },
                    ...Object.keys(completeTestRuns).map((testRunId) => ({
                      id: testRunId,
                      header: createTestRunHeader(testRunId),
                      cell: (item) => item[testRunId] || '$0.0000',
                      width: 120,
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
          <Container header={<Header variant="h3">Usage Breakdown Comparison</Header>}>
            {(() => {
              const allUsageItems = new Set();

              // Collect all unique usage items
              Object.values(completeTestRuns).forEach((testRun) => {
                if (testRun.costBreakdown) {
                  Object.entries(testRun.costBreakdown).forEach(([context, services]) => {
                    Object.keys(services).forEach((serviceUnit) => {
                      const lastUnderscoreIndex = serviceUnit.lastIndexOf('_');
                      const serviceApi = serviceUnit.substring(0, lastUnderscoreIndex);
                      const unit = serviceUnit.substring(lastUnderscoreIndex + 1);
                      const [service, api] = serviceApi.split('/');
                      allUsageItems.add(`${context}|${service}/${api}|${unit}`);
                    });
                  });
                }
              });

              const tableItems = Array.from(allUsageItems).map((itemKey) => {
                const [context, serviceApi, unit] = itemKey.split('|');
                const row = {
                  context,
                  serviceApi,
                  unit,
                };

                // Add usage value for each test run
                Object.entries(completeTestRuns).forEach(([testRunId, testRun]) => {
                  const services = testRun.costBreakdown?.[context] || {};
                  const serviceKey = Object.keys(services).find((key) => {
                    const lastUnderscoreIndex = key.lastIndexOf('_');
                    const keyServiceApi = key.substring(0, lastUnderscoreIndex);
                    const [keyService, keyApi] = keyServiceApi.split('/');
                    return `${keyService}/${keyApi}` === serviceApi;
                  });

                  const details = services[serviceKey] || {};
                  const value = details.value || 0;
                  row[testRunId] = value > 0 ? value.toLocaleString() : '0';
                });

                return row;
              });

              // Sort by context, then by service/api
              tableItems.sort((a, b) => {
                if (a.context !== b.context) return a.context.localeCompare(b.context);
                return a.serviceApi.localeCompare(b.serviceApi);
              });

              return tableItems.length > 0 ? (
                <Table
                  items={tableItems}
                  columnDefinitions={[
                    {
                      id: 'context',
                      header: 'Context',
                      cell: (item) => item.context,
                      width: 150,
                    },
                    {
                      id: 'serviceApi',
                      header: 'Service/Api',
                      cell: (item) => item.serviceApi,
                      width: 250,
                    },
                    {
                      id: 'unit',
                      header: 'Unit',
                      cell: (item) => item.unit,
                      width: 120,
                    },
                    ...Object.keys(completeTestRuns).map((testRunId) => ({
                      id: testRunId,
                      header: createTestRunHeader(testRunId),
                      cell: (item) => item[testRunId] || '0',
                      width: 120,
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
