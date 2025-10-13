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
} from '@awsui/components-react';
import { API, graphqlOperation } from 'aws-amplify';
import GET_TEST_RUN from '../../graphql/queries/getTestResults';

/* eslint-disable react/prop-types */
const ComprehensiveBreakdown = ({ baseline, test }) => {
  if (!baseline || !test) {
    return <Box>No comparison data available</Box>;
  }

  const usageItems = [];

  // Usage breakdown - aggregate tokens
  if (baseline.usage && test.usage) {
    // Aggregate token usage by type
    const aggregateTokens = (usage) => {
      const tokens = { inputTokens: 0, outputTokens: 0, totalTokens: 0 };
      Object.keys(usage).forEach((key) => {
        if (key.includes('bedrock') && usage[key]) {
          tokens.inputTokens += usage[key].inputTokens || 0;
          tokens.outputTokens += usage[key].outputTokens || 0;
          tokens.totalTokens += usage[key].totalTokens || 0;
        }
      });
      return tokens;
    };

    const baselineTokens = aggregateTokens(baseline.usage);
    const testTokens = aggregateTokens(test.usage);

    // Add token metrics
    ['inputTokens', 'outputTokens', 'totalTokens'].forEach((tokenType) => {
      const baselineValue = baselineTokens[tokenType];
      const testValue = testTokens[tokenType];

      if (baselineValue > 0 || testValue > 0) {
        const metricName = tokenType.replace(/([A-Z])/g, ' $1').replace(/^./, (str) => str.toUpperCase());

        let changeDisplay;
        if (baselineValue === 0) {
          changeDisplay = (
            <>
              New <span style={{ color: 'red' }}>↑</span>
            </>
          );
        } else if (testValue === 0) {
          changeDisplay = (
            <>
              Removed <span style={{ color: 'green' }}>↓</span>
            </>
          );
        } else {
          const changeValue = (((testValue - baselineValue) / baselineValue) * 100).toFixed(2);
          changeDisplay = (
            <>
              {Math.abs(changeValue)}%
              {parseFloat(changeValue) !== 0 && (
                <span style={{ color: parseFloat(changeValue) > 0 ? 'red' : 'green' }}>
                  {parseFloat(changeValue) > 0 ? ' ↑' : ' ↓'}
                </span>
              )}
            </>
          );
        }

        usageItems.push({
          metric: metricName,
          baseline: baselineValue.toString(),
          test: testValue.toString(),
          change: changeDisplay,
        });
      }
    });

    // Add other non-token metrics
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

              let changeDisplay;
              if (baselineValue === 0) {
                changeDisplay = (
                  <>
                    New <span style={{ color: 'red' }}>↑</span>
                  </>
                );
              } else if (testValue === 0) {
                changeDisplay = (
                  <>
                    Removed <span style={{ color: 'green' }}>↓</span>
                  </>
                );
              } else {
                const changeValue = (((testValue - baselineValue) / baselineValue) * 100).toFixed(2);
                changeDisplay = (
                  <>
                    {Math.abs(changeValue)}%
                    {parseFloat(changeValue) !== 0 && (
                      <span style={{ color: parseFloat(changeValue) > 0 ? 'red' : 'green' }}>
                        {parseFloat(changeValue) > 0 ? ' ↑' : ' ↓'}
                      </span>
                    )}
                  </>
                );
              }

              usageItems.push({
                metric: metricName,
                baseline: baselineValue.toString(),
                test: testValue.toString(),
                change: changeDisplay,
              });
            }
          });
        }
      }
    });
  }

  const columnDefinitions = [
    { id: 'metric', header: 'Metric', cell: (item) => item.metric },
    { id: 'baseline', header: 'Baseline', cell: (item) => item.baseline },
    { id: 'test', header: 'Test', cell: (item) => item.test },
    { id: 'change', header: 'Relative Change', cell: (item) => item.change },
  ];

  return (
    <SpaceBetween direction="vertical" size="m">
      {usageItems.length > 0 && <Table columnDefinitions={columnDefinitions} items={usageItems} variant="embedded" />}
    </SpaceBetween>
  );
};

const AccuracyBreakdown = ({ baseline, test }) => {
  if (!baseline?.accuracy || !test?.accuracy) {
    return <Box>No accuracy data available</Box>;
  }

  const items = [];
  const metrics = ['precision', 'recall', 'f1_score', 'accuracy'];

  metrics.forEach((metric) => {
    const baselineValue = baseline.accuracy[metric];
    const testValue = test.accuracy[metric];

    if (baselineValue !== undefined && testValue !== undefined) {
      const difference = testValue - baselineValue;

      items.push({
        metric: metric.charAt(0).toUpperCase() + metric.slice(1).replace('_', ' '),
        baseline: `${(baselineValue * 100).toFixed(2)}%`,
        test: `${(testValue * 100).toFixed(2)}%`,
        change: (
          <>
            {Math.abs(difference * 100).toFixed(2)}
            {difference !== 0 && (
              <span style={{ color: difference >= 0 ? 'green' : 'red' }}>{difference >= 0 ? ' ↑' : ' ↓'}</span>
            )}
          </>
        ),
      });
    }
  });

  return (
    <Table
      columnDefinitions={[
        { id: 'metric', header: 'Metric', cell: (item) => item.metric },
        { id: 'baseline', header: 'Baseline', cell: (item) => item.baseline },
        { id: 'test', header: 'Test', cell: (item) => item.test },
        { id: 'change', header: 'Change', cell: (item) => item.change },
      ]}
      items={items}
      variant="embedded"
    />
  );
};

const TestResults = ({ testRunId }) => {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Helper function to render percentage changes with appropriate arrows and colors
  const renderPercentageChange = (value, type) => {
    if (value === null || value === undefined) return 'N/A';

    const roundedValue = Math.abs(value).toFixed(2);
    if (parseFloat(roundedValue) === 0) {
      return `${roundedValue}%`;
    }

    const isIncrease = value > 0;
    let arrow;
    let arrowColor;

    if (type === 'accuracy' || type === 'confidence') {
      // For accuracy and confidence: increase is good (green up), decrease is bad (red down)
      arrow = isIncrease ? ' ↑' : ' ↓';
      arrowColor = isIncrease ? 'green' : 'red';
    } else {
      // For cost and usage: increase is bad (red up), decrease is good (green down)
      arrow = isIncrease ? ' ↑' : ' ↓';
      arrowColor = isIncrease ? 'red' : 'green';
    }

    return (
      <>
        {roundedValue}%<span style={{ color: arrowColor }}>{arrow}</span>
      </>
    );
  };

  useEffect(() => {
    const fetchResults = async () => {
      try {
        const result = await API.graphql(graphqlOperation(GET_TEST_RUN, { testRunId }));
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
  if (!results) return <Box>No test results found</Box>;

  const getStatusColor = (status) => {
    if (status === 'COMPLETE') return 'green';
    if (status === 'RUNNING') return 'blue';
    return 'red';
  };

  const hasAccuracyData = results.accuracySimilarity !== null && results.accuracySimilarity !== undefined;

  let baseline = null;
  let test = null;

  try {
    if (results.baseline) {
      baseline = typeof results.baseline === 'string' ? JSON.parse(results.baseline) : results.baseline;
      // Check if it's double-encoded
      if (typeof baseline === 'string') {
        baseline = JSON.parse(baseline);
      }
    }
    if (results.test) {
      test = typeof results.test === 'string' ? JSON.parse(results.test) : results.test;
      // Check if it's double-encoded
      if (typeof test === 'string') {
        test = JSON.parse(test);
      }
    }
  } catch (e) {
    console.error('Error parsing baseline/test:', e);
  }

  console.log('Parsed baseline:', baseline);
  console.log('Parsed test:', test);

  if (baseline?.usage) {
    console.log('Baseline usage keys:', Object.keys(baseline.usage));
    console.log('Baseline usage data:', baseline.usage);
  }

  if (test?.usage) {
    console.log('Test usage keys:', Object.keys(test.usage));
    console.log('Test usage data:', test.usage);
  }

  const confidenceChange =
    baseline &&
    baseline.confidence &&
    baseline.confidence.average_confidence &&
    test &&
    test.confidence &&
    test.confidence.average_confidence
      ? (
          ((test.confidence.average_confidence - baseline.confidence.average_confidence) /
            baseline.confidence.average_confidence) *
          100
        ).toFixed(2)
      : null;

  return (
    <Container>
      <SpaceBetween direction="vertical" size="l">
        {/* Overall Status */}
        <Box>
          <Badge color={getStatusColor(results.status)}>{results.status}</Badge>
          <Box margin={{ left: 's' }} display="inline">
            {results.completedFiles}/{results.filesCount} files processed
          </Box>
        </Box>

        {/* Baseline Comparison Alert */}
        {hasAccuracyData && (
          <Alert type="success" header="Test vs Baseline Comparison">
            Test results compared against baseline ground truth data for accuracy and cost analysis
          </Alert>
        )}

        {!hasAccuracyData && results.status === 'COMPLETE' && (
          <Alert type="warning" header="No Baseline Comparison">
            No baseline files found for comparison. Use &quot;Use as baseline&quot; on processed documents to create
            ground truth data.
          </Alert>
        )}

        {/* Key Metrics */}
        <ColumnLayout columns={3} variant="text-grid">
          <Box>
            <Box variant="awsui-key-label">Cost (Baseline → Test)</Box>
            <Box fontSize="heading-l">
              {baseline?.cost?.total_cost && test?.cost?.total_cost
                ? `$${baseline.cost.total_cost.toFixed(4)} → $${test.cost.total_cost.toFixed(4)}`
                : 'N/A'}
            </Box>
            <Box fontSize="body-s">
              {baseline?.cost?.total_cost && test?.cost?.total_cost
                ? renderPercentageChange(
                    ((test.cost.total_cost - baseline.cost.total_cost) / baseline.cost.total_cost) * 100,
                    'cost',
                  )
                : ''}
            </Box>
          </Box>
          <Box>
            <Box variant="awsui-key-label">Confidence (Baseline → Test)</Box>
            <Box fontSize="heading-l">
              {baseline?.confidence?.average_confidence && test?.confidence?.average_confidence
                ? `${(baseline.confidence.average_confidence * 100).toFixed(1)}% → ${(
                    test.confidence.average_confidence * 100
                  ).toFixed(1)}%`
                : 'N/A'}
            </Box>
            <Box fontSize="body-s">
              {confidenceChange ? (
                <>
                  {Math.abs(parseFloat(confidenceChange)).toFixed(2)}
                  {parseFloat(confidenceChange) !== 0 && (
                    <span style={{ color: parseFloat(confidenceChange) > 0 ? 'green' : 'red' }}>
                      {parseFloat(confidenceChange) > 0 ? ' ↑' : ' ↓'}
                    </span>
                  )}
                </>
              ) : (
                renderPercentageChange(results.confidenceSimilarity, 'confidence')
              )}
            </Box>
          </Box>
          <Box>
            <Box variant="awsui-key-label">Accuracy (Baseline → Test)</Box>
            <Box fontSize="heading-l">
              {baseline?.accuracy?.accuracy && test?.accuracy?.accuracy
                ? `${(baseline.accuracy.accuracy * 100).toFixed(1)}% → ${(test.accuracy.accuracy * 100).toFixed(1)}%`
                : 'N/A'}
            </Box>
            <Box fontSize="body-s">
              {baseline?.accuracy?.accuracy && test?.accuracy?.accuracy ? (
                <>
                  {Math.abs((test.accuracy.accuracy - baseline.accuracy.accuracy) * 100).toFixed(2)}
                  {test.accuracy.accuracy - baseline.accuracy.accuracy !== 0 && (
                    <span style={{ color: test.accuracy.accuracy - baseline.accuracy.accuracy > 0 ? 'green' : 'red' }}>
                      {test.accuracy.accuracy - baseline.accuracy.accuracy > 0 ? ' ↑' : ' ↓'}
                    </span>
                  )}
                </>
              ) : (
                ''
              )}
            </Box>
          </Box>
        </ColumnLayout>

        {/* Models Used */}
        {baseline && test && (
          <Box>
            <Header variant="h3">Models Used</Header>
            <Table
              columnDefinitions={[
                { id: 'context', header: 'Context', cell: (item) => item.context },
                { id: 'baseline', header: 'Baseline', cell: (item) => item.baseline },
                { id: 'test', header: 'Test', cell: (item) => item.test },
              ]}
              items={(() => {
                const contextMap = new Map();

                // Process baseline usage
                if (baseline.usage) {
                  Object.keys(baseline.usage).forEach((key) => {
                    if (key.includes('bedrock')) {
                      const parts = key.split('/');
                      const context = `${parts[0]} - ${parts[1]}`;
                      const modelPart = parts[2];
                      const modelName = modelPart
                        ? modelPart
                            .replace(/^us\./, '')
                            .replace(/:0.*$/, '')
                            .replace(/\./g, ' ')
                            .replace(/\b\w/g, (l) => l.toUpperCase())
                        : 'N/A';

                      if (!contextMap.has(context)) {
                        contextMap.set(context, { context, baseline: 'N/A', test: 'N/A' });
                      }
                      contextMap.get(context).baseline = modelName;
                    }
                  });
                }

                // Process test usage
                if (test.usage) {
                  Object.keys(test.usage).forEach((key) => {
                    if (key.includes('bedrock')) {
                      const parts = key.split('/');
                      const context = `${parts[0]} - ${parts[1]}`;
                      const modelPart = parts[2];
                      const modelName = modelPart
                        ? modelPart
                            .replace(/^us\./, '')
                            .replace(/:0.*$/, '')
                            .replace(/\./g, ' ')
                            .replace(/\b\w/g, (l) => l.toUpperCase())
                        : 'N/A';

                      if (!contextMap.has(context)) {
                        contextMap.set(context, { context, baseline: 'N/A', test: 'N/A' });
                      }
                      contextMap.get(context).test = modelName;
                    }
                  });
                }

                return Array.from(contextMap.values());
              })()}
              variant="embedded"
            />
          </Box>
        )}

        {/* Cost Breakdown */}
        {baseline && test && (
          <Box>
            <Header variant="h3">Cost Breakdown</Header>
            <Table
              columnDefinitions={[
                { id: 'service', header: 'Service', cell: (item) => item.service },
                { id: 'baseline', header: 'Baseline', cell: (item) => item.baseline },
                { id: 'test', header: 'Test', cell: (item) => item.test },
                { id: 'change', header: 'Relative Change', cell: (item) => item.change },
              ]}
              items={(() => {
                const costItems = [];
                console.log('Baseline cost object:', baseline.cost);
                console.log('Test cost object:', test.cost);
                console.log('Baseline cost keys:', Object.keys(baseline.cost));
                console.log('Test cost keys:', Object.keys(test.cost));

                if (baseline.cost && test.cost) {
                  // Get all unique service keys from both baseline and test
                  const allCostKeys = new Set([
                    ...Object.keys(baseline.cost).filter((key) => key !== 'total_cost'),
                    ...Object.keys(test.cost).filter((key) => key !== 'total_cost'),
                  ]);
                  console.log('Cost service keys:', Array.from(allCostKeys));

                  allCostKeys.forEach((service) => {
                    const baselineServiceCost = baseline.cost[service];
                    const testServiceCost = test.cost[service];

                    console.log(`${service} baseline structure:`, baselineServiceCost);
                    console.log(`${service} test structure:`, testServiceCost);
                    if (baselineServiceCost) console.log(`${service} baseline keys:`, Object.keys(baselineServiceCost));
                    if (testServiceCost) console.log(`${service} test keys:`, Object.keys(testServiceCost));

                    // Sum all cost values within the service object (similar to usage aggregation)
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
                    console.log(`Service ${service}:`, {
                      baselineValue,
                      testValue,
                      baselineServiceCost,
                      testServiceCost,
                    });

                    if (baselineValue > 0 || testValue > 0) {
                      let changeDisplay;
                      if (baselineValue === 0) {
                        changeDisplay = (
                          <>
                            New <span style={{ color: 'red' }}>↑</span>
                          </>
                        );
                      } else if (testValue === 0) {
                        changeDisplay = (
                          <>
                            Removed <span style={{ color: 'green' }}>↓</span>
                          </>
                        );
                      } else {
                        const changeValue = (((testValue - baselineValue) / baselineValue) * 100).toFixed(2);
                        changeDisplay = (
                          <>
                            {Math.abs(changeValue)}%
                            {parseFloat(changeValue) !== 0 && (
                              <span style={{ color: parseFloat(changeValue) > 0 ? 'red' : 'green' }}>
                                {parseFloat(changeValue) > 0 ? ' ↑' : ' ↓'}
                              </span>
                            )}
                          </>
                        );
                      }

                      costItems.push({
                        service,
                        baseline: `$${baselineValue.toFixed(4)}`,
                        test: `$${testValue.toFixed(4)}`,
                        change: changeDisplay,
                      });
                    }
                  });
                }
                console.log('Final cost items:', costItems);
                return costItems;
              })()}
              variant="embedded"
            />
          </Box>
        )}

        {/* Usage Breakdown */}
        {baseline && test && (
          <Box>
            <Header variant="h3">Usage Breakdown</Header>
            <ComprehensiveBreakdown baseline={baseline} test={test} />
          </Box>
        )}

        {/* Accuracy Breakdown */}
        {baseline && test && (
          <Box>
            <Header variant="h3">Accuracy Breakdown</Header>
            <AccuracyBreakdown baseline={baseline} test={test} />
          </Box>
        )}
      </SpaceBetween>
    </Container>
  );
};

TestResults.propTypes = {
  testRunId: PropTypes.string.isRequired,
};

export default TestResults;
