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
  Modal,
  Textarea,
  FormField,
  BarChart,
  Select,
} from '@cloudscape-design/components';
import { generateClient } from 'aws-amplify/api';
import GET_TEST_RUN from '../../graphql/queries/getTestResults';
import START_TEST_RUN from '../../graphql/queries/startTestRun';
import LIST_INPUT_BUCKET_FILES from '../../graphql/queries/listInputBucketFiles';
import GET_TEST_SETS from '../../graphql/queries/getTestSets';
import TestStudioHeader from './TestStudioHeader';
import useAppContext from '../../contexts/app';

const client = generateClient();

/* eslint-disable react/prop-types */
const ComprehensiveBreakdown = ({ costBreakdown, accuracyBreakdown }) => {
  if (!costBreakdown && !accuracyBreakdown) {
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
        <Container header={<Header variant="h3">Estimated Cost</Header>}>
          <Table
            items={(() => {
              const costItems = [];
              let totalCost = 0;
              const contextTotals = {};

              // First pass: collect all items and calculate context totals
              Object.entries(costBreakdown).forEach(([context, services]) => {
                let contextSubtotal = 0;

                Object.entries(services).forEach(([serviceUnit, details]) => {
                  // Parse service_api_unit format
                  const parts = serviceUnit.split('_');
                  const service = parts[0];
                  const api = parts.slice(1, -1).join('/');
                  const unit = parts[parts.length - 1];

                  const cost = details.estimated_cost || 0;
                  contextSubtotal += cost;

                  costItems.push({
                    context,
                    serviceApi: `${service}/${api}`,
                    unit: details.unit || unit,
                    value: details.value || 'N/A',
                    unitCost: details.unit_cost ? `$${details.unit_cost}` : 'None',
                    estimatedCost: cost > 0 ? `$${cost.toFixed(4)}` : 'N/A',
                    sortOrder: 0, // Regular items
                  });
                });

                contextTotals[context] = contextSubtotal;
                totalCost += contextSubtotal;
              });

              // Sort items by context first, then by service/api
              costItems.sort((a, b) => {
                if (a.context !== b.context) {
                  return a.context.localeCompare(b.context);
                }
                return a.serviceApi.localeCompare(b.serviceApi);
              });

              // Second pass: insert subtotal rows after each context group
              const finalItems = [];
              let currentContext = null;

              costItems.forEach((item, index) => {
                // Add the regular item
                finalItems.push(item);

                // Check if this is the last item for this context
                const nextItem = costItems[index + 1];
                const isLastInContext = !nextItem || nextItem.context !== item.context;

                if (isLastInContext) {
                  // Add subtotal row for every context
                  finalItems.push({
                    context: '',
                    serviceApi: `${item.context} Subtotal: $${contextTotals[item.context].toFixed(4)}`,
                    unit: '',
                    value: '',
                    unitCost: '',
                    estimatedCost: '',
                    isSubtotal: true,
                    sortOrder: 1, // Subtotal items
                  });
                }
              });

              // Add total row
              if (totalCost > 0) {
                finalItems.push({
                  context: '',
                  serviceApi: `Total: $${totalCost.toFixed(4)}`,
                  unit: '',
                  value: '',
                  unitCost: '',
                  estimatedCost: '',
                  isTotal: true,
                  sortOrder: 2, // Total item
                });
              }

              return finalItems;
            })()}
            columnDefinitions={[
              {
                id: 'context',
                header: 'Context',
                cell: (item) => (item.isSubtotal || item.isTotal ? '' : item.context),
              },
              {
                id: 'serviceApi',
                header: 'Service/Api',
                cell: (item) => (
                  <span
                    style={{
                      fontWeight: item.isSubtotal || item.isTotal ? 'bold' : 'normal',
                      color: item.isTotal ? '#0073bb' : 'inherit',
                    }}
                  >
                    {item.serviceApi}
                  </span>
                ),
              },
              {
                id: 'unit',
                header: 'Unit',
                cell: (item) => (item.isSubtotal || item.isTotal ? '' : item.unit),
              },
              {
                id: 'value',
                header: 'Value',
                cell: (item) => (item.isSubtotal || item.isTotal ? '' : item.value),
              },
              {
                id: 'unitCost',
                header: 'Unit Cost',
                cell: (item) => (item.isSubtotal || item.isTotal ? '' : item.unitCost),
              },
              {
                id: 'estimatedCost',
                header: 'Estimated Cost',
                cell: (item) => (item.isSubtotal || item.isTotal ? '' : item.estimatedCost),
              },
            ]}
            variant="embedded"
          />
        </Container>
      )}
    </SpaceBetween>
  );
};

const TestResults = ({ testRunId, setSelectedTestRunId }) => {
  const { addTestRun } = useAppContext();
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reRunLoading, setReRunLoading] = useState(false);
  const [showReRunModal, setShowReRunModal] = useState(false);
  const [reRunContext, setReRunContext] = useState('');
  const [testSetFileCount, setTestSetFileCount] = useState(null);
  const [testSetStatus, setTestSetStatus] = useState(null);
  const [testSetFilePattern, setTestSetFilePattern] = useState(null);
  const [chartType, setChartType] = useState({ label: 'Bar Chart', value: 'bar' });

  const checkTestSetStatus = async () => {
    if (!results?.testSetId) return;

    try {
      const testSetsResult = await client.graphql({
        query: GET_TEST_SETS,
      });

      const testSets = testSetsResult.data.getTestSets || [];
      const testSet = testSets.find((ts) => ts.id === results.testSetId);

      if (testSet) {
        setTestSetStatus(testSet.status);
        setTestSetFileCount(testSet.fileCount);
        setTestSetFilePattern(testSet.filePattern);
      } else {
        setTestSetStatus('NOT_FOUND');
        setTestSetFileCount(0);
        setTestSetFilePattern(null);
      }
    } catch (err) {
      console.error('Failed to check test set status:', err);
      setTestSetStatus('ERROR');
      setTestSetFileCount(0);
    }
  };

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

  useEffect(() => {
    if (results?.testSetId) {
      checkTestSetStatus();
    }
  }, [results]);

  if (loading) return <ProgressBar status="in-progress" label="Loading test results..." />;
  if (error) return <Box>Error loading test results: {error}</Box>;
  if (!results) {
    const handleBackClick = () => {
      if (setSelectedTestRunId) {
        setSelectedTestRunId(null);
      } else {
        window.location.replace('#/test-studio?tab=executions');
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
  let accuracyBreakdown = null;

  try {
    if (results.costBreakdown) {
      costBreakdown = typeof results.costBreakdown === 'string' ? JSON.parse(results.costBreakdown) : results.costBreakdown;
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

  const handleReRun = async () => {
    console.log('=== handleReRun START ===');
    console.log('results.testSetId:', results?.testSetId);
    console.log('results.testSetName:', results?.testSetName);

    const testSetId = results?.testSetId;
    console.log('Using testSetId:', testSetId);

    if (!testSetId) {
      console.error('No testSetId found in results. Cannot re-run without testSetId.');
      return;
    }

    setReRunLoading(true);

    try {
      const input = {
        testSetId: testSetId,
        ...(reRunContext && { context: reRunContext }),
      };

      console.log('About to call GraphQL with input:', input);

      const result = await client.graphql({
        query: START_TEST_RUN,
        variables: { input },
      });

      console.log('GraphQL call completed, result:', result);

      if (result?.data?.startTestRun) {
        console.log('Success! Closing modal and redirecting...');
        const newTestRun = result.data.startTestRun;
        // Add to active test runs
        addTestRun(newTestRun.testRunId, newTestRun.testSetName, reRunContext, newTestRun.filesCount);
        setShowReRunModal(false);
        setReRunContext('');
        // Navigate to test executions tab
        window.location.hash = '#/test-studio?tab=executions';
      } else {
        console.error('No startTestRun data in result');
      }
    } catch (err) {
      console.error('GraphQL call failed:', err);
      if (err.errors) {
        err.errors.forEach((errorItem, index) => {
          console.error(`Error ${index}:`, errorItem.message);
        });
      }
    } finally {
      setReRunLoading(false);
    }
    console.log('=== handleReRun END ===');
  };

  const reRunButton = results?.testSetId ? (
    <Button
      onClick={() => {
        setShowReRunModal(true);
      }}
      iconName="arrow-right"
      disabled={!testSetFileCount || testSetFileCount === 0}
    >
      Re-Run
    </Button>
  ) : null;

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
      window.location.replace('#/test-studio?tab=executions');
    }
  };

  return (
    <Container
      header={
        <TestStudioHeader
          title={`Test Results: ${results.testRunId} (${results.testSetName})`}
          description={contextDescription}
          showPrintButton={true}
          additionalActions={[configButton, reRunButton].filter(Boolean)}
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
        <ColumnLayout columns={5} variant="text-grid">
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
          <Box>
            <Box variant="awsui-key-label">Duration</Box>
            <Box fontSize="heading-l">
              {results.createdAt && results.completedAt
                ? (() => {
                    const duration = new Date(results.completedAt) - new Date(results.createdAt);
                    const minutes = Math.floor(duration / 60000);
                    const seconds = Math.floor((duration % 60000) / 1000);
                    return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
                  })()
                : 'N/A'}
            </Box>
          </Box>
          <Box>
            <Box variant="awsui-key-label">Weighted Overall Scores</Box>
            <Box fontSize="heading-l">
              {results.weightedOverallScores && results.weightedOverallScores.length > 0
                ? (results.weightedOverallScores.reduce((sum, score) => sum + score, 0) / results.weightedOverallScores.length).toFixed(3)
                : 'N/A'}
            </Box>
          </Box>
        </ColumnLayout>

        {/* Weighted Overall Scores Distribution Chart */}
        {results.weightedOverallScores && results.weightedOverallScores.length > 1 && (
          <Container
            header={
              <Header
                variant="h3"
                actions={
                  <Select
                    selectedOption={chartType}
                    onChange={({ detail }) => setChartType(detail.selectedOption)}
                    options={[
                      { label: 'Bar Chart', value: 'bar' },
                      { label: 'Line Chart', value: 'line' },
                    ]}
                    placeholder="Select chart type"
                  />
                }
              >
                Weighted Overall Score Distribution ({results.testRunId})
              </Header>
            }
          >
            <BarChart
              title={`Distribution of Weighted Overall Scores (${results.testRunId})`}
              series={[
                {
                  title: 'Number of Documents',
                  type: chartType.value,
                  data: (() => {
                    // Create score range buckets
                    const buckets = {
                      '0.0-0.1': 0,
                      '0.1-0.2': 0,
                      '0.2-0.3': 0,
                      '0.3-0.4': 0,
                      '0.4-0.5': 0,
                      '0.5-0.6': 0,
                      '0.6-0.7': 0,
                      '0.7-0.8': 0,
                      '0.8-0.9': 0,
                      '0.9-1.0': 0,
                    };

                    // Count documents in each bucket
                    results.weightedOverallScores.forEach((score) => {
                      if (score < 0.1) buckets['0.0-0.1']++;
                      else if (score < 0.2) buckets['0.1-0.2']++;
                      else if (score < 0.3) buckets['0.2-0.3']++;
                      else if (score < 0.4) buckets['0.3-0.4']++;
                      else if (score < 0.5) buckets['0.4-0.5']++;
                      else if (score < 0.6) buckets['0.5-0.6']++;
                      else if (score < 0.7) buckets['0.6-0.7']++;
                      else if (score < 0.8) buckets['0.7-0.8']++;
                      else if (score < 0.9) buckets['0.8-0.9']++;
                      else buckets['0.9-1.0']++;
                    });

                    return Object.entries(buckets).map(([range, count]) => ({
                      x: range,
                      y: count,
                    }));
                  })(),
                },
              ]}
              xDomain={['0.0-0.1', '0.1-0.2', '0.2-0.3', '0.3-0.4', '0.4-0.5', '0.5-0.6', '0.6-0.7', '0.7-0.8', '0.8-0.9', '0.9-1.0']}
              yDomain={[0, Math.max(...results.weightedOverallScores.map(() => 1)) * results.weightedOverallScores.length]}
              xTitle="Weighted Overall Score Range"
              yTitle="Number of Documents"
              height={300}
              hideFilter
              hideLegend
              i18nStrings={{
                filterLabel: 'Filter displayed data',
                filterPlaceholder: 'Filter data',
                filterSelectedAriaLabel: 'selected',
                legendAriaLabel: 'Legend',
                chartAriaRoleDescription: 'bar chart',
                xTickFormatter: (value) => value,
                yTickFormatter: (value) => value.toString(),
              }}
            />
          </Container>
        )}

        {/* Breakdown Tables */}
        {(costBreakdown || accuracyBreakdown) && (
          <ComprehensiveBreakdown costBreakdown={costBreakdown} accuracyBreakdown={accuracyBreakdown} />
        )}
      </SpaceBetween>

      <Modal
        visible={showReRunModal}
        onDismiss={() => {
          setShowReRunModal(false);
          setReRunContext('');
        }}
        header="Re-Run Test"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button
                variant="link"
                onClick={() => {
                  setShowReRunModal(false);
                  setReRunContext('');
                }}
              >
                Cancel
              </Button>
              <Button variant="primary" onClick={handleReRun} loading={reRunLoading}>
                Re-Run Test
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <SpaceBetween size="m">
          <Box>
            <strong>Test Set:</strong> {results?.testSetName || 'N/A'}
            <br />
            <strong>Pattern:</strong> {testSetStatus === 'NOT_FOUND' ? 'Test set not found' : testSetFilePattern || 'Uploaded files'}
            <br />
            <strong>Files:</strong>{' '}
            {testSetStatus === 'NOT_FOUND' ? 'Test set deleted' : testSetFileCount !== null ? `${testSetFileCount} files` : 'Loading...'}
          </Box>
          <FormField label="Context" description="Optional context information for this test run">
            <Textarea
              value={reRunContext}
              onChange={({ detail }) => setReRunContext(detail.value)}
              placeholder="Enter context information..."
              rows={3}
            />
          </FormField>
        </SpaceBetween>
      </Modal>
    </Container>
  );
};

TestResults.propTypes = {
  testRunId: PropTypes.string.isRequired,
};

export default TestResults;
