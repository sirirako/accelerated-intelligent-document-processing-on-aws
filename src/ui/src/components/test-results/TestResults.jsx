// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Container, Header, SpaceBetween, Box, ColumnLayout, ProgressBar, Badge, Alert } from '@awsui/components-react';
import { API, graphqlOperation } from 'aws-amplify';
import GET_TEST_RUN from '../../graphql/queries/getTestResults';

const CostBreakdown = ({ costBreakdown }) => {
  if (!costBreakdown || Object.keys(costBreakdown).length === 0) {
    return <Box>No cost data available</Box>;
  }

  const formatLabel = (key) => {
    return key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase());
  };

  return (
    <SpaceBetween direction="vertical" size="xs">
      {costBreakdown.test_total_cost && (
        <Box>
          <strong>Test Cost:</strong> ${costBreakdown.test_total_cost}
        </Box>
      )}
      {costBreakdown.baseline_total_cost && (
        <Box>
          <strong>Baseline Cost:</strong> ${costBreakdown.baseline_total_cost}
        </Box>
      )}
      {/* Render all similarity metrics dynamically */}
      {Object.entries(costBreakdown)
        .filter(([, value]) => typeof value === 'number')
        .filter(([key]) => key.includes('_similarity'))
        .map(([key, value]) => (
          <Box key={key}>
            <strong>{formatLabel(key.replace('_similarity', ''))}:</strong>
            <Badge color={value >= 0 ? 'green' : 'red'}>
              {value > 0 ? '+' : ''}
              {value}%
            </Badge>
          </Box>
        ))}
    </SpaceBetween>
  );
};

const UsageBreakdown = ({ usageBreakdown }) => {
  if (!usageBreakdown || Object.keys(usageBreakdown).length === 0) {
    return <Box>No usage data available</Box>;
  }

  const formatLabel = (key) => {
    return key
      .replace(/_usage_similarity$/, '')
      .replace(/\//g, ' ')
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (l) => l.toUpperCase());
  };

  return (
    <SpaceBetween direction="vertical" size="xs">
      {Object.entries(usageBreakdown)
        .filter(([, value]) => typeof value === 'number')
        .map(([key, value]) => (
          <Box key={key}>
            <strong>{formatLabel(key)}:</strong>
            <Badge color={value >= 0 ? 'green' : 'red'}>
              {value > 0 ? '+' : ''}
              {value}%
            </Badge>
          </Box>
        ))}
    </SpaceBetween>
  );
};

CostBreakdown.propTypes = {
  costBreakdown: PropTypes.objectOf(PropTypes.oneOfType([PropTypes.number, PropTypes.string])),
};

CostBreakdown.defaultProps = {
  costBreakdown: null,
};

UsageBreakdown.propTypes = {
  usageBreakdown: PropTypes.objectOf(PropTypes.number),
};

UsageBreakdown.defaultProps = {
  usageBreakdown: null,
};

const TestResults = ({ testRunId }) => {
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchResults = async () => {
      try {
        const result = await API.graphql(graphqlOperation(GET_TEST_RUN, { testRunId }));
        setResults(result.data.getTestRun);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    const interval = setInterval(fetchResults, 10000);
    fetchResults();

    return () => clearInterval(interval);
  }, [testRunId]);

  if (loading) return <ProgressBar status="in-progress" label="Loading test results..." />;
  if (error) return <Box>Error loading test results: {error}</Box>;
  if (!results) return <Box>No test results found</Box>;

  const getStatusColor = (status) => {
    if (status === 'COMPLETE') return 'green';
    if (status === 'RUNNING') return 'blue';
    return 'red';
  };

  const hasAccuracyData = results.overallAccuracy !== null && results.overallAccuracy !== undefined;

  return (
    <Container header={<Header variant="h2">Test Results: {testRunId}</Header>}>
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
          <Alert type="success" header="Baseline Comparison">
            Results compared against ground truth baselines for accuracy calculation
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
            <Box variant="awsui-key-label">Overall Accuracy</Box>
            <Box fontSize="display-l">{hasAccuracyData ? `${results.overallAccuracy}%` : 'N/A'}</Box>
            {hasAccuracyData && <Box variant="small">vs baseline ground truth</Box>}
          </Box>
          <Box>
            <Box variant="awsui-key-label">Average Confidence</Box>
            <Box fontSize="display-l">{results.averageConfidence ? `${results.averageConfidence}%` : 'N/A'}</Box>
          </Box>
          <Box>
            <Box variant="awsui-key-label">Total Cost</Box>
            <Box fontSize="display-l">{results.totalCost ? `$${results.totalCost}` : 'N/A'}</Box>
          </Box>
        </ColumnLayout>

        {/* Cost Breakdown */}
        {results.costBreakdown && (
          <Box>
            <Header variant="h3">Cost Comparison</Header>
            <CostBreakdown costBreakdown={results.costBreakdown} />
          </Box>
        )}

        {/* Usage Breakdown */}
        {results.usageBreakdown && (
          <Box>
            <Header variant="h3">Usage Comparison</Header>
            <UsageBreakdown usageBreakdown={results.usageBreakdown} />
          </Box>
        )}

        {/* Accuracy Details */}
        {hasAccuracyData && (
          <Box>
            <Header variant="h3">Accuracy Analysis</Header>
            <SpaceBetween direction="vertical" size="s">
              <Box>
                <strong>Comparison Method:</strong> Section-level classification matching against baseline
              </Box>
              <Box>
                <strong>Ground Truth Source:</strong> Baseline files from evaluation bucket
              </Box>
              <Box>
                <strong>Accuracy Calculation:</strong> Matching sections / Total sections × 100%
              </Box>
            </SpaceBetween>
          </Box>
        )}

        {/* Processing Status for Running Tests */}
        {results.status === 'RUNNING' && (
          <Box>
            <Header variant="h3">Processing Status</Header>
            <ProgressBar
              value={results.filesCount > 0 ? Math.round((results.completedFiles / results.filesCount) * 100) : 0}
              label={`${results.completedFiles}/${results.filesCount} files completed`}
              status="in-progress"
            />
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
