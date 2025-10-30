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

const client = generateClient();

// Add print styles
const printStyles = `
  @media print {
    * {
      -webkit-print-color-adjust: exact !important;
      color-adjust: exact !important;
    }
    
    /* Hide sidebar and navigation elements */
    .awsui-app-layout-navigation,
    .awsui-side-navigation,
    .awsui-app-layout-tools,
    .awsui-breadcrumb-group,
    nav,
    aside,
    [data-testid="app-layout-navigation"],
    [data-testid="side-navigation"] {
      display: none !important;
    }
    
    /* Make main content take full width */
    .awsui-app-layout-main,
    .awsui-app-layout-content,
    main {
      margin: 0 !important;
      padding: 0 !important;
      width: 100% !important;
      max-width: 100% !important;
    }
    
    body {
      font-size: 12px !important;
      margin: 0 !important;
      padding: 0 !important;
    }
    
    .awsui-table-container,
    .awsui-table-wrapper,
    .awsui-table-content-wrapper {
      overflow: visible !important;
      max-height: none !important;
      height: auto !important;
    }
    
    .awsui-table {
      width: 100% !important;
      table-layout: fixed !important;
      border-collapse: collapse !important;
    }
    
    .awsui-table-cell,
    .awsui-table-header-cell {
      white-space: normal !important;
      word-wrap: break-word !important;
      overflow: visible !important;
      text-overflow: clip !important;
      padding: 4px !important;
      border: 1px solid #ccc !important;
    }
    
    .awsui-container {
      margin-bottom: 20px !important;
    }
    
    .awsui-table tbody tr {
      page-break-inside: avoid !important;
    }
    
    @page {
      size: A4 landscape;
      margin: 0.5in;
    }
  }
`;

// Inject styles
if (typeof document !== 'undefined') {
  const styleSheet = document.createElement('style');
  styleSheet.type = 'text/css';
  styleSheet.innerText = printStyles;
  document.head.appendChild(styleSheet);
}

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

const TestResults = ({ testRunId }) => {
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
  if (!results) return <Box>No test results found</Box>;

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
      costBreakdown =
        typeof results.costBreakdown === 'string' ? JSON.parse(results.costBreakdown) : results.costBreakdown;
    }
    if (results.usageBreakdown) {
      usageBreakdown =
        typeof results.usageBreakdown === 'string' ? JSON.parse(results.usageBreakdown) : results.usageBreakdown;
    }
    if (results.accuracyBreakdown) {
      accuracyBreakdown =
        typeof results.accuracyBreakdown === 'string'
          ? JSON.parse(results.accuracyBreakdown)
          : results.accuracyBreakdown;
    }
  } catch (e) {
    console.error('Error parsing breakdown data:', e);
  }

  const handlePrint = () => {
    // Force all tables to be fully visible before printing
    const tables = document.querySelectorAll('.awsui-table-container');
    const originalStyles = [];

    tables.forEach((table, index) => {
      originalStyles[index] = {
        overflow: table.style.overflow,
        maxHeight: table.style.maxHeight,
        height: table.style.height,
      };

      // eslint-disable-next-line no-param-reassign
      table.style.overflow = 'visible';
      // eslint-disable-next-line no-param-reassign
      table.style.maxHeight = 'none';
      // eslint-disable-next-line no-param-reassign
      table.style.height = 'auto';
    });

    // Add temporary print-specific styles
    const printStyleElement = document.createElement('style');
    printStyleElement.innerHTML = `
      @media print {
        .awsui-table-container * {
          overflow: visible !important;
          max-height: none !important;
          height: auto !important;
        }
        .awsui-table {
          table-layout: auto !important;
          width: 100% !important;
        }
        .awsui-table-cell {
          font-size: 10px !important;
          padding: 2px !important;
          word-break: break-word !important;
        }
      }
    `;
    document.head.appendChild(printStyleElement);

    setTimeout(() => {
      window.print();

      // Restore original styles after printing
      setTimeout(() => {
        tables.forEach((table, index) => {
          if (originalStyles[index]) {
            // eslint-disable-next-line no-param-reassign
            table.style.overflow = originalStyles[index].overflow;
            // eslint-disable-next-line no-param-reassign
            table.style.maxHeight = originalStyles[index].maxHeight;
            // eslint-disable-next-line no-param-reassign
            table.style.height = originalStyles[index].height;
          }
        });
        document.head.removeChild(printStyleElement);
      }, 1000);
    }, 100);
  };

  console.log('Parsed cost breakdown:', costBreakdown);
  console.log('Parsed usage breakdown:', usageBreakdown);

  return (
    <Container
      header={
        <Header
          variant="h2"
          actions={
            <Button onClick={handlePrint} iconName="print">
              Print
            </Button>
          }
        >
          Test Results: {results.testRunId} ({results.testSetName})
          {results.context && (
            <Box variant="p" color="text-body-secondary" margin={{ top: 'xs' }}>
              Context: {results.context}
            </Box>
          )}
        </Header>
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
              {results.totalCost !== null && results.totalCost !== undefined
                ? `$${results.totalCost.toFixed(4)}`
                : 'N/A'}
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
          <ComprehensiveBreakdown
            costBreakdown={costBreakdown}
            usageBreakdown={usageBreakdown}
            accuracyBreakdown={accuracyBreakdown}
          />
        )}
      </SpaceBetween>
    </Container>
  );
};

TestResults.propTypes = {
  testRunId: PropTypes.string.isRequired,
};

export default TestResults;
