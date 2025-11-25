// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState } from 'react';
import {
  Container,
  Header,
  SpaceBetween,
  Button,
  ButtonDropdown,
  Table,
  Box,
  Modal,
  FormField,
  Input,
  Alert,
  Badge,
  ExpandableSection,
} from '@cloudscape-design/components';
import { generateClient } from 'aws-amplify/api';
import ADD_TEST_SET from '../../graphql/queries/addTestSet';
import ADD_TEST_SET_FROM_UPLOAD from '../../graphql/queries/addTestSetFromUpload';
import DELETE_TEST_SETS from '../../graphql/queries/deleteTestSets';
import GET_TEST_SETS from '../../graphql/queries/getTestSets';
import LIST_INPUT_BUCKET_FILES from '../../graphql/queries/listInputBucketFiles';
import VALIDATE_TEST_FILE_NAME from '../../graphql/queries/checkTestSetFiles';

const client = generateClient();

// Constants
const MAX_ZIP_SIZE_BYTES = 1073741824; // 1 GB

const TestSets = () => {
  const [testSets, setTestSets] = useState([]);
  const [selectedItems, setSelectedItems] = useState([]);
  const [showAddPatternModal, setShowAddPatternModal] = useState(false);
  const [showAddUploadModal, setShowAddUploadModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [newTestSetName, setNewTestSetName] = useState('');
  const [filePattern, setFilePattern] = useState('');
  const [zipFile, setZipFile] = useState(null);
  const [matchingFiles, setMatchingFiles] = useState([]);
  const [fileCount, setFileCount] = useState(0);
  const [showFilesModal, setShowFilesModal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const [warningMessage, setWarningMessage] = useState('');
  const [confirmReplacement, setConfirmReplacement] = useState(false);

  const loadTestSets = async () => {
    try {
      console.log('TestSets: Loading test sets...');
      const result = await client.graphql({ query: GET_TEST_SETS });
      console.log('TestSets: GraphQL result:', result);
      const backendTestSets = result.data.getTestSets || [];

      // Upsert: merge backend data with existing UI state, deduplicating by id
      setTestSets((prevTestSets) => {
        const merged = [...prevTestSets];

        backendTestSets.forEach((backendTestSet) => {
          const existingIndex = merged.findIndex((ts) => ts.id === backendTestSet.id);
          if (existingIndex >= 0) {
            // Update existing with fresh backend data
            merged[existingIndex] = backendTestSet;
          } else {
            // Add new test set from backend
            merged.push(backendTestSet);
          }
        });

        // Keep active test sets even if missing from backend (during processing)
        const backendIds = new Set(backendTestSets.map((ts) => ts.id));
        return merged.filter((ts) => backendIds.has(ts.id) || (ts.status !== 'COMPLETED' && ts.status !== 'FAILED'));
      });
    } catch (err) {
      console.error('TestSets: Failed to load test sets:', err);
      setError(`Failed to load test sets: ${err.message || 'Unknown error'}`);
    }
  };

  React.useEffect(() => {
    loadTestSets();
  }, []);

  // Simple polling for active test sets
  React.useEffect(() => {
    const hasActiveTestSets = testSets.some((testSet) => testSet.status !== 'COMPLETED' && testSet.status !== 'FAILED');

    if (!hasActiveTestSets) {
      console.log('No active test sets, no polling needed');
      return;
    }

    console.log('Starting polling for active test sets');
    const interval = setInterval(() => {
      console.log('Polling refresh...');
      loadTestSets();
    }, 3000);

    return () => {
      console.log('Cleaning up polling');
      clearInterval(interval);
    };
  }, [testSets]);

  // Separate discovery polling for new test sets (less frequent)
  React.useEffect(() => {
    console.log('Starting discovery polling for new test sets');
    const discoveryInterval = setInterval(() => {
      console.log('Discovery polling...');
      loadTestSets();
    }, 30000); // Every 30 seconds

    return () => {
      console.log('Cleaning up discovery polling');
      clearInterval(discoveryInterval);
    };
  }, []); // No dependencies - always runs

  // Cleanup polling on unmount
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

  const validateTestSetName = (name) => {
    const validPattern = /^[a-zA-Z0-9 _-]+$/;
    return validPattern.test(name);
  };

  const handleAddTestSet = async () => {
    if (!newTestSetName.trim() || !filePattern.trim()) {
      setError('Both test set name and file pattern are required');
      return;
    }

    // 1. UI validation using existing validateTestSetName
    if (!validateTestSetName(newTestSetName.trim())) {
      setError('Test set name can only contain letters, numbers, spaces, underscores, and dashes');
      return;
    }

    // 2. Backend validation using VALIDATE_TEST_FILE_NAME
    try {
      const validationResult = await client.graphql({
        query: VALIDATE_TEST_FILE_NAME,
        variables: { fileName: newTestSetName.trim() },
      });

      const validation = validationResult.data.validateTestFileName;
      if (validation && validation.exists) {
        if (!confirmReplacement) {
          setWarningMessage(
            `Test set ID "${validation.testSetId}" already exists and will be replaced. Click "Add Test Set" again to confirm.`,
          );
          setConfirmReplacement(true);
          return;
        }
        setWarningMessage('');
      } else {
        setWarningMessage('');
        setConfirmReplacement(false);
      }
    } catch (err) {
      setError(`Failed to validate test set name: ${err.message}`);
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
        // Immediate UI update for responsive feedback
        setTestSets((prev) => [...prev, newTestSet]);
        setNewTestSetName('');
        setFilePattern('');
        setFileCount(0);
        setShowAddPatternModal(false);
        setError('');
        setWarningMessage('');
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

  const handleAddUploadTestSet = async () => {
    if (!newTestSetName.trim()) {
      setError('Test set name is required');
      return;
    }

    if (!validateTestSetName(newTestSetName.trim())) {
      setError('Test set name can only contain letters, numbers, spaces, underscores, and dashes');
      return;
    }

    try {
      const validationResult = await client.graphql({
        query: VALIDATE_TEST_FILE_NAME,
        variables: { fileName: newTestSetName.trim() },
      });

      const validation = validationResult.data.validateTestFileName;
      if (validation && validation.exists) {
        if (!confirmReplacement) {
          setWarningMessage(
            `Test set ID "${validation.testSetId}" already exists and will be replaced. Click "Create Test Set" again to confirm.`,
          );
          setConfirmReplacement(true);
          return;
        }
        setWarningMessage('');
      } else {
        setWarningMessage('');
        setConfirmReplacement(false);
      }
    } catch (err) {
      setError(`Failed to validate test set name: ${err.message}`);
      return;
    }

    if (!zipFile) {
      setError('Zip file is required');
      return;
    }

    setLoading(true);
    try {
      const result = await client.graphql({
        query: ADD_TEST_SET_FROM_UPLOAD,
        variables: {
          input: {
            fileName: zipFile.name,
            fileSize: zipFile.size,
          },
        },
      });

      const response = result.data.addTestSetFromUpload;

      if (!response || !response.presignedUrl) {
        throw new Error('Failed to get upload URL from server');
      }

      const presignedPostData = JSON.parse(response.presignedUrl);
      const formData = new FormData();

      Object.entries(presignedPostData.fields).forEach(([key, value]) => {
        formData.append(key, value);
      });
      formData.append('file', zipFile);

      const uploadResponse = await fetch(presignedPostData.url, {
        method: 'POST',
        body: formData,
      });

      if (!uploadResponse.ok) {
        throw new Error(`Upload failed: ${uploadResponse.status} ${uploadResponse.statusText}`);
      }

      const newTestSet = {
        id: response.testSetId,
        name: newTestSetName.trim(),
        status: 'QUEUED',
        fileCount: null,
        createdAt: new Date().toISOString(),
        filePattern: null,
      };

      // Immediate UI update for responsive feedback
      setTestSets((prev) => [...prev, newTestSet]);

      setSuccessMessage(`Test set "${newTestSetName}" created successfully. Zip file is being processed.`);
      setError('');
      setShowAddUploadModal(false);
      setNewTestSetName('');
      setZipFile(null);
    } catch (err) {
      setError(`Failed to create test set: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    setError('');
    setWarningMessage('');
    setSuccessMessage('');
    try {
      const result = await client.graphql({ query: GET_TEST_SETS });
      setTestSets(result.data.getTestSets || []);
    } catch (err) {
      setError(`Failed to refresh test sets: ${err.message}`);
    } finally {
      setRefreshing(false);
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

  const filteredTestSets = testSets.filter((item) => item != null).sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
  console.log('Filtered testSets for Table:', filteredTestSets);

  const columnDefinitions = [
    {
      id: 'name',
      header: 'Test Set Name',
      cell: (item) => item.name,
      sortingField: 'name',
    },
    {
      id: 'id',
      header: 'Test Set ID',
      cell: (item) => item.id,
      sortingField: 'id',
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
      id: 'status',
      header: 'Status',
      cell: (item) => {
        const status = item.status || '-';

        if (status === 'FAILED' && item.error) {
          const truncatedError = item.error.length > 15 ? `${item.error.substring(0, 15)}...` : item.error;

          return (
            <div>
              <div style={{ color: '#d13212', fontWeight: 'bold' }}>FAILED</div>
              <div
                style={{
                  fontSize: '0.9em',
                  color: '#666',
                  marginTop: '2px',
                  cursor: 'help',
                  maxWidth: '200px',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
                title={item.error}
              >
                {truncatedError}
              </div>
            </div>
          );
        }

        return status;
      },
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
              <Button iconName="refresh" loading={refreshing} onClick={handleRefresh}>
                Refresh
              </Button>
              <Button iconName="remove" disabled={selectedItems.length === 0 || loading} onClick={() => setShowDeleteModal(true)} />
              <ButtonDropdown
                variant="primary"
                items={[
                  { id: 'pattern', text: 'Existing Files' },
                  { id: 'upload', text: 'New Upload' },
                ]}
                onItemClick={({ detail }) => {
                  if (detail.id === 'pattern') {
                    setShowAddPatternModal(true);
                  } else if (detail.id === 'upload') {
                    setShowAddUploadModal(true);
                  }
                }}
              >
                Add Test Set
              </ButtonDropdown>
            </SpaceBetween>
          }
        >
          Test Sets ({filteredTestSets.length})
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
        visible={showAddPatternModal}
        onDismiss={() => {
          setShowAddPatternModal(false);
          setConfirmReplacement(false);
          setWarningMessage('');
        }}
        header="Add Test Set from Pattern"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button
                variant="link"
                onClick={() => {
                  setShowAddPatternModal(false);
                  setConfirmReplacement(false);
                  setWarningMessage('');
                }}
              >
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
          {warningMessage && <Alert type="warning">{warningMessage}</Alert>}

          <FormField label="Test Set Name">
            <Input
              value={newTestSetName}
              onChange={({ detail }) => {
                setNewTestSetName(detail.value);
                setConfirmReplacement(false);
                setWarningMessage('');
              }}
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
        visible={showAddUploadModal}
        onDismiss={() => {
          setShowAddUploadModal(false);
          setConfirmReplacement(false);
          setWarningMessage('');
          setError('');
          setZipFile(null);
        }}
        header="Add Test Set from Upload"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button
                variant="link"
                onClick={() => {
                  setShowAddUploadModal(false);
                  setConfirmReplacement(false);
                  setWarningMessage('');
                  setError('');
                  setZipFile(null);
                }}
              >
                Cancel
              </Button>
              <Button variant="primary" loading={loading} onClick={handleAddUploadTestSet} disabled={!zipFile}>
                Upload and Create Test Set
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <SpaceBetween size="m">
          {error && <Alert type="error">{error}</Alert>}
          {warningMessage && <Alert type="warning">{warningMessage}</Alert>}

          <FormField label="Test Set Zip File" description="Select a zip file containing your test set structure">
            <ExpandableSection headerText="View required file structure" variant="footer">
              <Box margin={{ bottom: 's' }}>
                <pre
                  style={{
                    backgroundColor: '#f8f9fa',
                    padding: '12px',
                    borderRadius: '4px',
                    fontSize: '12px',
                    overflow: 'auto',
                  }}
                >
                  {`my-test-set.zip
└── my-test-set/
    ├── input/
    │   ├── document1.pdf
    │   └── document2.pdf
    └── baseline/
        ├── document1.pdf/
        │   └── [ground truth files]
        └── document2.pdf/
            └── [ground truth files]`}
                </pre>
              </Box>
              <Alert type="info">Each input file must have a corresponding baseline folder with the same name.</Alert>
            </ExpandableSection>
            <input
              type="file"
              accept=".zip"
              onChange={async (e) => {
                const file = e.target.files[0];
                if (file) {
                  // Check file size
                  if (file.size > MAX_ZIP_SIZE_BYTES) {
                    setError(`Zip file size (${(file.size / 1024 / 1024 / 1024).toFixed(2)} GB) exceeds maximum limit of 1 GB`);
                    setZipFile(null);
                    setNewTestSetName('');
                    return;
                  }

                  // Extract test set name from zip filename (remove .zip extension)
                  const fileName = file.name.replace(/\.zip$/i, '');

                  // Validate the filename
                  if (!validateTestSetName(fileName)) {
                    setError('Zip filename can only contain letters, numbers, spaces, underscores, and dashes');
                    setZipFile(null);
                    setNewTestSetName('');
                    return;
                  }

                  // Check if test set already exists
                  try {
                    const validationResult = await client.graphql({
                      query: VALIDATE_TEST_FILE_NAME,
                      variables: { fileName },
                    });

                    const validation = validationResult.data.validateTestFileName;
                    if (validation && validation.exists) {
                      setWarningMessage(`Test set ID "${validation.testSetId}" already exists and will be replaced.`);
                    } else {
                      setWarningMessage('');
                    }
                  } catch (err) {
                    setError(`Failed to validate test set name: ${err.message}`);
                    setZipFile(null);
                    setNewTestSetName('');
                    return;
                  }

                  setZipFile(file);
                  setNewTestSetName(fileName);
                  setError('');
                } else {
                  setZipFile(null);
                  setNewTestSetName('');
                  setWarningMessage('');
                }
              }}
              style={{ width: '100%', padding: '8px' }}
            />
            {zipFile && (
              <Box margin={{ top: 'xs' }}>
                <Badge color="blue">Test Set Name: {newTestSetName}</Badge>
              </Box>
            )}
          </FormField>
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
                <strong>{item.name}</strong>
                {item.filePattern && ` (${item.filePattern})`}
              </li>
            ))}
          </ul>
        </Box>
      </Modal>
    </Container>
  );
};

export default TestSets;
