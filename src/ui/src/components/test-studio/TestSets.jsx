// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState } from 'react';
import {
  Container,
  Header,
  SpaceBetween,
  Button,
  Table,
  Box,
  Modal,
  FormField,
  Input,
  Alert,
  Badge,
} from '@cloudscape-design/components';
import { generateClient } from 'aws-amplify/api';
import ADD_TEST_SET from '../../graphql/queries/addTestSet';
import DELETE_TEST_SETS from '../../graphql/queries/deleteTestSets';
import GET_TEST_SETS from '../../graphql/queries/getTestSets';
import LIST_INPUT_BUCKET_FILES from '../../graphql/queries/listInputBucketFiles';

const client = generateClient();

const TestSets = () => {
  const [testSets, setTestSets] = useState([]);
  const [selectedItems, setSelectedItems] = useState([]);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [newTestSetName, setNewTestSetName] = useState('');
  const [filePattern, setFilePattern] = useState('');
  const [matchingFiles, setMatchingFiles] = useState([]);
  const [fileCount, setFileCount] = useState(0);
  const [showFilesModal, setShowFilesModal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const loadTestSets = async () => {
    try {
      console.log('TestSets: Loading test sets...');
      const result = await client.graphql({ query: GET_TEST_SETS });
      console.log('TestSets: GraphQL result:', result);
      setTestSets(result.data.getTestSets || []);
    } catch (err) {
      console.error('TestSets: Failed to load test sets:', err);
      setError(`Failed to load test sets: ${err.message || 'Unknown error'}`);
    }
  };

  React.useEffect(() => {
    loadTestSets();
  }, []);

  const handleCheckFiles = async () => {
    if (!filePattern.trim()) return;

    setLoading(true);
    try {
      const result = await client.graphql({
        query: LIST_INPUT_BUCKET_FILES,
        variables: { filePattern: filePattern.trim() },
      });

      const files = result.data.listInputBucketFiles || [];
      setMatchingFiles(files);
      setFileCount(files.length);
      setShowFilesModal(true);
    } catch (err) {
      setError(`Failed to check files: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleAddTestSet = async () => {
    if (!newTestSetName.trim() || !filePattern.trim()) {
      setError('Both test set name and file pattern are required');
      return;
    }

    setLoading(true);
    try {
      const result = await client.graphql({
        query: ADD_TEST_SET,
        variables: {
          name: newTestSetName.trim(),
          filePattern: filePattern.trim(),
          fileCount,
        },
      });

      console.log('GraphQL result:', result);
      const newTestSet = result.data.addTestSet;
      console.log('New test set data:', newTestSet);

      if (newTestSet) {
        const updatedTestSets = [...testSets, newTestSet];
        console.log('Updating testSets from', testSets.length, 'to', updatedTestSets.length);
        console.log('New test set added:', newTestSet);
        setTestSets(updatedTestSets);
        setNewTestSetName('');
        setFilePattern('');
        setFileCount(0);
        setShowAddModal(false);
        setError('');
        setSuccessMessage(`Successfully created test set "${newTestSet.name}"`);
      } else {
        setError('Failed to create test set - no data returned');
      }
    } catch (err) {
      setError(`Failed to add test set: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteTestSets = async () => {
    const testSetIds = selectedItems.map((item) => item.id);
    const deleteCount = testSetIds.length;

    setLoading(true);
    try {
      await client.graphql({
        query: DELETE_TEST_SETS,
        variables: { testSetIds },
      });
      setTestSets(testSets.filter((testSet) => !testSetIds.includes(testSet.id)));
      setSelectedItems([]);
      setSuccessMessage(`Successfully deleted ${deleteCount} test set${deleteCount > 1 ? 's' : ''}`);
      setError('');
    } catch (err) {
      setError(`Failed to delete test sets: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const filteredTestSets = testSets.filter((item) => item != null);
  console.log('Filtered testSets for Table:', filteredTestSets);

  const columnDefinitions = [
    {
      id: 'name',
      header: 'Test Set Name',
      cell: (item) => item.name,
      sortingField: 'name',
    },
    {
      id: 'filePattern',
      header: 'File Pattern',
      cell: (item) => item.filePattern,
    },
    {
      id: 'fileCount',
      header: 'Files',
      cell: (item) => item.fileCount,
    },
    {
      id: 'createdAt',
      header: 'Created',
      cell: (item) => new Date(item.createdAt).toLocaleDateString(),
      sortingField: 'createdAt',
    },
  ];

  return (
    <Container
      header={
        <Header
          variant="h2"
          description="Manage test sets for document processing"
          actions={
            <SpaceBetween direction="horizontal" size="xs">
              <Button disabled={selectedItems.length === 0 || loading} onClick={() => setShowDeleteModal(true)}>
                Delete
              </Button>
              <Button variant="primary" onClick={() => setShowAddModal(true)}>
                Add Test Set
              </Button>
            </SpaceBetween>
          }
        >
          Test Sets
        </Header>
      }
    >
      {error && (
        <Alert type="error" dismissible onDismiss={() => setError('')}>
          {error}
        </Alert>
      )}

      {successMessage && (
        <Alert type="success" dismissible onDismiss={() => setSuccessMessage('')}>
          {successMessage}
        </Alert>
      )}

      <Table
        columnDefinitions={columnDefinitions}
        items={filteredTestSets}
        selectedItems={selectedItems}
        onSelectionChange={({ detail }) => setSelectedItems(detail.selectedItems)}
        selectionType="multi"
        empty={
          <Box textAlign="center" color="inherit">
            <b>No test sets</b>
            <Box padding={{ bottom: 's' }} variant="p" color="inherit">
              No test sets to display.
            </Box>
          </Box>
        }
      />

      <Modal
        visible={showAddModal}
        onDismiss={() => setShowAddModal(false)}
        header="Add New Test Set"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setShowAddModal(false)}>
                Cancel
              </Button>
              <Button variant="primary" loading={loading} onClick={handleAddTestSet} disabled={fileCount === 0}>
                Add Test Set
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <SpaceBetween size="m">
          {error && <Alert type="error">{error}</Alert>}

          <FormField label="Test Set Name">
            <Input
              value={newTestSetName}
              onChange={({ detail }) => setNewTestSetName(detail.value)}
              placeholder="e.g., lending-package-v1"
            />
          </FormField>

          <FormField label="File Pattern" description="Pattern to match files (use * for wildcards)">
            <SpaceBetween direction="horizontal" size="xs">
              <Input
                value={filePattern}
                onChange={({ detail }) => {
                  setFilePattern(detail.value);
                  setFileCount(0);
                }}
                placeholder="prefix/*"
              />
              <Button disabled={!filePattern.trim()} loading={loading} onClick={handleCheckFiles}>
                Check Files
              </Button>
            </SpaceBetween>
          </FormField>

          {fileCount > 0 && (
            <Box>
              <Badge color="green">
                {fileCount} {fileCount === 1 ? 'file' : 'files'} found
              </Badge>
            </Box>
          )}
        </SpaceBetween>
      </Modal>

      <Modal
        visible={showFilesModal}
        onDismiss={() => setShowFilesModal(false)}
        header={`Matching Files (${matchingFiles.length})`}
        footer={
          <Box float="right">
            <Button onClick={() => setShowFilesModal(false)}>Close</Button>
          </Box>
        }
      >
        <Box>
          {matchingFiles.length > 0 ? (
            <ul>
              {matchingFiles.map((file) => (
                <li key={file}>{file}</li>
              ))}
            </ul>
          ) : (
            <Box textAlign="center">No matching files found</Box>
          )}
        </Box>
      </Modal>

      <Modal
        visible={showDeleteModal}
        onDismiss={() => setShowDeleteModal(false)}
        header="Confirm Delete"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setShowDeleteModal(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                loading={loading}
                onClick={() => {
                  handleDeleteTestSets();
                  setShowDeleteModal(false);
                }}
              >
                Delete
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <Box>
          <div>Are you sure you want to delete the following test set{selectedItems.length > 1 ? 's' : ''}?</div>
          <ul style={{ marginTop: '10px' }}>
            {selectedItems.map((item) => (
              <li key={item.id}>
                <strong>{item.name}</strong> ({item.filePattern})
              </li>
            ))}
          </ul>
        </Box>
      </Modal>
    </Container>
  );
};

export default TestSets;
