// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import {
  Table,
  Button,
  SpaceBetween,
  ButtonDropdown,
  Modal,
  Pagination,
  Box,
  TextFilter,
  Flashbar,
} from '@awsui/components-react';
import { useCollection } from '@awsui/collection-hooks';
import { API, graphqlOperation } from 'aws-amplify';
import GET_TEST_RUNS from '../../graphql/queries/getTestRuns';
import DELETE_TESTS from '../../graphql/mutations/deleteTests';
import TestResults from './TestResults';
import TestComparison from '../test-comparison/TestComparison';
import DeleteDocumentModal from '../common/DeleteDocumentModal';
import { paginationLabels } from '../common/labels';
import { TableHeader } from '../common/table';

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
  const [successMessage, setSuccessMessage] = useState(null);
  const [selectedItems, setSelectedItems] = useState([]);
  const [timePeriodHours, setTimePeriodHours] = useState(2);
  const [isComparisonModalVisible, setIsComparisonModalVisible] = useState(false);
  const [selectedTestRunIds, setSelectedTestRunIds] = useState([]);
  const [isDeleteModalVisible, setIsDeleteModalVisible] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [pageSize, setPageSize] = useState(10);

  // Use collection hook for pagination, filtering, and sorting
  const { items, collectionProps, paginationProps, filterProps } = useCollection(testRuns, {
    filtering: {
      empty: 'No test runs found',
      noMatch: 'No test runs match the filter',
    },
    pagination: { pageSize },
    sorting: { defaultState: { sortingColumn: { sortingField: 'createdAt' }, isDescending: true } },
    selection: {
      keepSelection: false,
      trackBy: 'testRunId',
    },
  });

  const handleTestRunSelect = (testRunId) => {
    setSelectedTestRunId(testRunId);
  };

  const getTestRunIdCell = (item) => <TestRunIdCell item={item} onSelect={handleTestRunSelect} />;

  const fetchTestRuns = async () => {
    try {
      setLoading(true);
      console.log('Fetching test runs with timePeriodHours:', timePeriodHours);
      const result = await API.graphql(graphqlOperation(GET_TEST_RUNS, { timePeriodHours }));
      console.log('Raw GraphQL result:', result);
      console.log('getTestRuns data:', result.data.getTestRuns);
      console.log('Number of test runs returned:', result.data.getTestRuns?.length || 0);
      setTestRuns(result.data.getTestRuns || []);
      setError(null);
    } catch (err) {
      console.error('Error fetching test runs:', err);
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
    const headers = ['Test Run ID', 'Test Set', 'Status', 'Files Count', 'Created At', 'Completed At'];
    const csvData = testRuns.map((run) => [
      run.testRunId,
      run.testSetName || '',
      run.status,
      run.filesCount || 0,
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

  const confirmDelete = async () => {
    try {
      setDeleteLoading(true);
      const testRunIds = selectedItems.map((item) => item.testRunId);
      console.log('Attempting to delete test runs:', testRunIds);

      const result = await API.graphql(graphqlOperation(DELETE_TESTS, { testRunIds }));
      console.log('Delete result:', result);

      const count = selectedItems.length;
      setSuccessMessage(`Successfully deleted ${count} test run${count > 1 ? 's' : ''}`);
      setSelectedItems([]);
      setIsDeleteModalVisible(false);
      fetchTestRuns(); // Refresh the list

      // Clear success message after 5 seconds
      setTimeout(() => setSuccessMessage(null), 5000);

      return result.data.deleteTests;
    } catch (err) {
      console.error('Error deleting test runs:', err);
      console.error('Error details:', err.errors);
      return false;
    } finally {
      setDeleteLoading(false);
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
    <SpaceBetween size="s">
      {successMessage && (
        <Flashbar
          items={[
            {
              type: 'success',
              content: successMessage,
              dismissible: true,
              onDismiss: () => setSuccessMessage(null),
            },
          ]}
        />
      )}
      <TableHeader
        title={`Test Results (${testRuns.length})`}
        actionButtons={
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
            <Button
              iconName="remove"
              variant="normal"
              onClick={() => setIsDeleteModalVisible(true)}
              disabled={selectedItems.length === 0}
              loading={deleteLoading}
            />
            {selectedItems.length > 1 && (
              <Button iconName="compare" variant="normal" onClick={handleCompare}>
                Test Comparison
              </Button>
            )}
          </SpaceBetween>
        }
      />
      <Table
        items={items}
        selectedItems={selectedItems}
        onSelectionChange={({ detail }) => setSelectedItems(detail.selectedItems)}
        sortingColumn={collectionProps.sortingColumn}
        sortingDescending={collectionProps.sortingDescending}
        onSortingChange={collectionProps.onSortingChange}
        columnDefinitions={[
          {
            id: 'testRunId',
            header: 'Test Run ID',
            cell: getTestRunIdCell,
            sortingField: 'testRunId',
          },
          {
            id: 'testSetName',
            header: 'Test Set Name',
            cell: (item) => item.testSetName,
            sortingField: 'testSetName',
          },
          {
            id: 'status',
            header: 'Status',
            cell: (item) => item.status,
            sortingField: 'status',
          },
          {
            id: 'filesCount',
            header: 'Files Count',
            cell: (item) => item.filesCount,
            sortingField: 'filesCount',
          },
          {
            id: 'createdAt',
            header: 'Created At',
            cell: (item) => new Date(item.createdAt).toLocaleString(),
            sortingField: 'createdAt',
          },
        ]}
        selectionType="multi"
        filter={
          <TextFilter
            filteringText={filterProps.filteringText}
            onChange={filterProps.onChange}
            filteringAriaLabel="Filter test runs"
            filteringPlaceholder="Find test runs"
          />
        }
        empty={
          <Box textAlign="center" color="inherit">
            <b>No test runs found</b>
            <Box variant="p" color="inherit">
              No test runs available for the selected time period.
            </Box>
          </Box>
        }
        loading={loading}
        stickyHeader
        pagination={
          <Pagination
            currentPageIndex={paginationProps.currentPageIndex}
            pagesCount={paginationProps.pagesCount}
            onChange={paginationProps.onChange}
            ariaLabels={paginationLabels}
          />
        }
        preferences={
          <Button
            variant="icon"
            iconName="settings"
            ariaLabel="Page size settings"
            onClick={() => {
              if (pageSize === 10) setPageSize(20);
              else if (pageSize === 20) setPageSize(50);
              else setPageSize(10);
            }}
          />
        }
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
        <TestComparison preSelectedTestRunIds={selectedTestRunIds} onTestRunSelect={setSelectedTestRunId} />
      </Modal>

      <DeleteDocumentModal
        visible={isDeleteModalVisible}
        onDismiss={() => setIsDeleteModalVisible(false)}
        onConfirm={confirmDelete}
        selectedItems={selectedItems}
        itemType="test run"
      />
    </SpaceBetween>
  );
};

TestResultsList.propTypes = {};

TestResultsList.defaultProps = {
  onSelectTestRun: null,
};

export default TestResultsList;
