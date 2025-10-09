// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Container, Table, Button, Header, SpaceBetween, ButtonDropdown, Modal } from '@awsui/components-react';
import { API, graphqlOperation } from 'aws-amplify';
import GET_TEST_RUNS from '../../graphql/queries/getTestRuns';
import TestResults from './TestResults';
import TestComparison from '../test-comparison/TestComparison';

const TIME_PERIOD_OPTIONS = [
  { id: 'refresh-2h', hours: 2, text: '2 hrs' },
  { id: 'refresh-4h', hours: 4, text: '4 hrs' },
  { id: 'refresh-8h', hours: 8, text: '8 hrs' },
  { id: 'refresh-1d', hours: 24, text: '1 day' },
  { id: 'refresh-2d', hours: 48, text: '2 days' },
  { id: 'refresh-1w', hours: 168, text: '1 week' },
  { id: 'refresh-2w', hours: 336, text: '2 weeks' },
  { id: 'refresh-1m', hours: 720, text: '30 days' },
].map((option) => ({ ...option, text: option.text })); // Ensure text is the display text

const TestRunIdCell = ({ item, onSelect }) => (
  <Button variant="link" onClick={() => onSelect(item.testRunId)}>
    {item.testRunId}
  </Button>
);

TestRunIdCell.propTypes = {
  item: PropTypes.shape({
    testRunId: PropTypes.string.isRequired,
  }).isRequired,
  onSelect: PropTypes.func.isRequired,
};

const TestResultsList = () => {
  const [selectedTestRunId, setSelectedTestRunId] = useState(null);
  const [testRuns, setTestRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedItems, setSelectedItems] = useState([]);
  const [timePeriodHours, setTimePeriodHours] = useState(2);
  const [isComparisonModalVisible, setIsComparisonModalVisible] = useState(false);
  const [selectedTestRunIds, setSelectedTestRunIds] = useState([]);

  const getTestRunIdCell = (item) => <TestRunIdCell item={item} onSelect={setSelectedTestRunId} />;

  const fetchTestRuns = async () => {
    try {
      setLoading(true);
      console.log('Fetching test runs with timePeriodHours:', timePeriodHours);
      const result = await API.graphql(graphqlOperation(GET_TEST_RUNS, { timePeriodHours }));
      setTestRuns(result.data.getTestRuns || []);
      setError(null);
    } catch (err) {
      const errorMessage =
        err.errors?.length > 0 ? err.errors.map((e) => e.message).join('; ') : 'Failed to load test runs';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTestRuns();
  }, [timePeriodHours]);

  const downloadToExcel = () => {
    // Convert test runs data to CSV format
    const headers = [
      'Test Run ID',
      'Test Set',
      'Status',
      'Files Count',
      'Overall Accuracy',
      'Average Confidence',
      'Total Cost',
      'Created At',
      'Completed At',
    ];
    const csvData = testRuns.map((run) => [
      run.testRunId,
      run.testSetName || '',
      run.status,
      run.filesCount || 0,
      run.overallAccuracy ? `${run.overallAccuracy}%` : '',
      run.averageConfidence ? `${run.averageConfidence}%` : '',
      run.totalCost ? `$${run.totalCost}` : '',
      run.createdAt || '',
      run.completedAt || '',
    ]);

    const csvContent = [headers, ...csvData].map((row) => row.map((field) => `"${field}"`).join(',')).join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `test-results-${new Date().toISOString().split('T')[0]}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleRefresh = () => {
    fetchTestRuns();
  };

  const handleCompare = () => {
    if (selectedItems.length > 1) {
      const testRunIds = selectedItems.map((item) => item.testRunId);
      setSelectedTestRunIds(testRunIds);
      setIsComparisonModalVisible(true);
    }
  };

  if (selectedTestRunId) {
    return (
      <div>
        <Button variant="link" onClick={() => setSelectedTestRunId(null)} iconName="arrow-left">
          Back to Test Runs
        </Button>
        <TestResults testRunId={selectedTestRunId} />
      </div>
    );
  }

  if (loading) return <div>Loading test runs...</div>;
  if (error) return <div>Error loading test runs: {error}</div>;

  return (
    <Container
      header={
        <Header
          variant="h2"
          actions={
            <SpaceBetween direction="horizontal" size="xs">
              <ButtonDropdown
                loading={loading}
                onItemClick={({ detail }) => {
                  const selectedOption = TIME_PERIOD_OPTIONS.find((opt) => opt.id === detail.id);
                  if (selectedOption) {
                    setTimePeriodHours(selectedOption.hours);
                  }
                }}
                items={TIME_PERIOD_OPTIONS}
              >
                {`Load: ${TIME_PERIOD_OPTIONS.find((opt) => opt.hours === timePeriodHours)?.text || '2 hrs'}`}
              </ButtonDropdown>
              <Button iconName="refresh" variant="normal" loading={loading} onClick={handleRefresh} />
              <Button iconName="download" variant="normal" loading={loading} onClick={downloadToExcel} />
              {selectedItems.length > 1 && (
                <Button iconName="compare" variant="normal" onClick={handleCompare}>
                  Test Comparison
                </Button>
              )}
            </SpaceBetween>
          }
        >
          Test Results
        </Header>
      }
    >
      <Table
        items={testRuns}
        columnDefinitions={[
          {
            id: 'testRunId',
            header: 'Test Run ID',
            cell: getTestRunIdCell,
          },
          {
            id: 'testSetName',
            header: 'Test Set Name',
            cell: (item) => item.testSetName,
          },
          {
            id: 'status',
            header: 'Status',
            cell: (item) => item.status,
          },
          {
            id: 'filesCount',
            header: 'Files Count',
            cell: (item) => item.filesCount,
          },
          {
            id: 'createdAt',
            header: 'Created At',
            cell: (item) => new Date(item.createdAt).toLocaleString(),
          },
        ]}
        selectionType="multi"
        selectedItems={selectedItems}
        onSelectionChange={({ detail }) => setSelectedItems(detail.selectedItems)}
        empty="No test runs found"
        loading={loading}
      />

      <Modal
        visible={isComparisonModalVisible}
        onDismiss={() => {
          setIsComparisonModalVisible(false);
          setSelectedTestRunIds([]);
          setSelectedItems([]);
        }}
        size="large"
        header="Test Comparison"
      >
        <TestComparison preSelectedTestRunIds={selectedTestRunIds} />
      </Modal>
    </Container>
  );
};

TestResultsList.propTypes = {};

TestResultsList.defaultProps = {};

export default TestResultsList;
