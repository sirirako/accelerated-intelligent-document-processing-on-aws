// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState } from 'react';
import PropTypes from 'prop-types';
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
} from '@awsui/components-react';

// Cell renderers moved outside component to avoid nested component warnings
const FilePatternCell = ({ item }) => <code>{item.filePattern}</code>;
FilePatternCell.propTypes = {
  item: PropTypes.shape({
    filePattern: PropTypes.string.isRequired,
  }).isRequired,
};

const FileCountCell = ({ item }) => <Badge color="blue">{item.fileCount} files</Badge>;
FileCountCell.propTypes = {
  item: PropTypes.shape({
    fileCount: PropTypes.number.isRequired,
  }).isRequired,
};

const CreatedAtCell = ({ item }) => new Date(item.createdAt).toLocaleDateString();
CreatedAtCell.propTypes = {
  item: PropTypes.shape({
    createdAt: PropTypes.string.isRequired,
  }).isRequired,
};

const TestSets = () => {
  const [testSets, setTestSets] = useState([]);
  const [selectedItems, setSelectedItems] = useState([]);
  const [showAddModal, setShowAddModal] = useState(false);
  const [newTestSetName, setNewTestSetName] = useState('');
  const [filePattern, setFilePattern] = useState('');
  const [matchingFiles, setMatchingFiles] = useState([]);
  const [fileCount, setFileCount] = useState(0);
  const [showFilesModal, setShowFilesModal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleCheckFiles = async () => {
    if (!filePattern.trim()) return;

    setLoading(true);
    try {
      // TODO: Replace with actual API call to list files from InputBucket
      // Simulated file matching for now
      const mockFiles = ['lending_package_001.pdf', 'lending_package_002.pdf', 'lending_package_003.pdf'].filter(
        (file) => {
          const pattern = filePattern.replace(/\*/g, '.*');
          return new RegExp(pattern, 'i').test(file);
        },
      );

      setMatchingFiles(mockFiles);
      setFileCount(mockFiles.length);
      setShowFilesModal(true);
    } catch (err) {
      setError('Failed to check files');
    } finally {
      setLoading(false);
    }
  };

  const handleAddTestSet = () => {
    if (!newTestSetName.trim() || !filePattern.trim()) {
      setError('Both test set name and file pattern are required');
      return;
    }

    const newTestSet = {
      id: Date.now().toString(),
      name: newTestSetName.trim(),
      filePattern: filePattern.trim(),
      fileCount,
      createdAt: new Date().toISOString(),
    };

    setTestSets([...testSets, newTestSet]);
    setNewTestSetName('');
    setFilePattern('');
    setFileCount(0);
    setShowAddModal(false);
    setError('');
  };

  const handleDeleteTestSets = () => {
    const selectedIds = selectedItems.map((item) => item.id);
    setTestSets(testSets.filter((testSet) => !selectedIds.includes(testSet.id)));
    setSelectedItems([]);
  };

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
      cell: FilePatternCell,
    },
    {
      id: 'fileCount',
      header: 'Files',
      cell: FileCountCell,
    },
    {
      id: 'createdAt',
      header: 'Created',
      cell: CreatedAtCell,
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
              <Button disabled={selectedItems.length === 0} onClick={handleDeleteTestSets}>
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
      <Table
        columnDefinitions={columnDefinitions}
        items={testSets}
        selectedItems={selectedItems}
        onSelectionChange={({ detail }) => setSelectedItems(detail.selectedItems)}
        selectionType="multi"
        empty={
          <Box textAlign="center" color="inherit">
            <b>No test sets</b>
            <Box padding={{ bottom: 's' }} variant="p" color="inherit">
              No test sets to display.
            </Box>
            <Button onClick={() => setShowAddModal(true)}>Add Test Set</Button>
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
              <Button variant="primary" onClick={handleAddTestSet}>
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
                placeholder="lending_package*.pdf"
              />
              <Button disabled={!filePattern.trim()} loading={loading} onClick={handleCheckFiles}>
                Check Files
              </Button>
            </SpaceBetween>
          </FormField>

          {fileCount > 0 && (
            <Box>
              <Badge color="green">{fileCount} matching files found</Badge>
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
    </Container>
  );
};

export default TestSets;
