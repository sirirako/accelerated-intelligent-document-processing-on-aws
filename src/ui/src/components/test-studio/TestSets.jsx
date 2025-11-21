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
} from '@cloudscape-design/components';
import { generateClient } from 'aws-amplify/api';
import ADD_TEST_SET from '../../graphql/queries/addTestSet';
import ADD_TEST_SET_FROM_UPLOAD from '../../graphql/queries/addTestSetFromUpload';
import DELETE_TEST_SETS from '../../graphql/queries/deleteTestSets';
import GET_TEST_SETS from '../../graphql/queries/getTestSets';
import LIST_INPUT_BUCKET_FILES from '../../graphql/queries/listInputBucketFiles';

const client = generateClient();

const TestSets = () => {
  const [testSets, setTestSets] = useState([]);
  const [selectedItems, setSelectedItems] = useState([]);
  const [showAddPatternModal, setShowAddPatternModal] = useState(false);
  const [showAddUploadModal, setShowAddUploadModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [newTestSetName, setNewTestSetName] = useState('');
  const [filePattern, setFilePattern] = useState('');
  const [inputFiles, setInputFiles] = useState([]);
  const [baselineFiles, setBaselineFiles] = useState([]);
  const [matchingFiles, setMatchingFiles] = useState([]);
  const [fileCount, setFileCount] = useState(0);
  const [showFilesModal, setShowFilesModal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const [warningMessage, setWarningMessage] = useState('');
  const [confirmReplacement, setConfirmReplacement] = useState(false);
  const [pollingInterval, setPollingInterval] = useState(null);

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

  // Auto-refresh polling until all test sets are completed or failed
  React.useEffect(() => {
    const hasActiveTestSets = testSets.some((testSet) => testSet.status !== 'COMPLETED' && testSet.status !== 'FAILED');

    console.log('Polling check:', {
      hasActiveTestSets,
      pollingActive: !!pollingInterval,
      testSetsCount: testSets.length,
      testSets: testSets.map((t) => ({ name: t.name, status: t.status })),
    });

    // Clear existing interval first
    if (pollingInterval) {
      clearInterval(pollingInterval);
      setPollingInterval(null);
    }

    // Start new interval if needed
    if (hasActiveTestSets) {
      console.log('Starting polling...');
      const interval = setInterval(() => {
        console.log('Polling refresh...');
        loadTestSets();
      }, 2000);
      setPollingInterval(interval);
    }

    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
    };
  }, [testSets]);

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

  const validateFilePairing = () => {
    if (inputFiles.length === 0 || baselineFiles.length === 0) {
      return { isValid: false, errors: ['Both input files and baseline files are required'] };
    }

    if (inputFiles.length !== baselineFiles.length) {
      return { isValid: false, errors: ['Number of input files must match number of baseline files'] };
    }

    const inputNames = inputFiles.map((f) => f.name);
    const baselineNames = baselineFiles.map((f) => f.name);
    const errors = [];

    // Check each input file has corresponding baseline zip
    const missingBaselines = inputNames.filter((name) => !baselineNames.includes(`${name}.zip`));

    if (missingBaselines.length > 0) {
      errors.push(`Missing baseline files: ${missingBaselines.map((name) => `${name}.zip`).join(', ')}`);
    }

    // Check for extra baseline files
    const expectedBaselines = inputNames.map((name) => `${name}.zip`);
    const extraBaselines = baselineNames.filter((name) => !expectedBaselines.includes(name));

    if (extraBaselines.length > 0) {
      errors.push(`Unexpected baseline files: ${extraBaselines.join(', ')}`);
    }

    // Check baseline files are zip files
    const nonZipBaselines = baselineFiles.filter((f) => !f.name.endsWith('.zip'));
    if (nonZipBaselines.length > 0) {
      errors.push(`Baseline files must be zip files: ${nonZipBaselines.map((f) => f.name).join(', ')}`);
    }

    return { isValid: errors.length === 0, errors };
  };

  const validateTestSetName = (name) => {
    const validPattern = /^[a-zA-Z0-9 _-]+$/;
    return validPattern.test(name);
  };

  const checkTestSetNameToday = (name) => {
    const today = new Date().toISOString().split('T')[0].replace(/-/g, ''); // YYYYMMDD
    const expectedId = `${name.replace(/ /g, '-')}_${today}`;
    return testSets.some((testSet) => testSet.id === expectedId);
  };

  const handleAddTestSet = async () => {
    if (!newTestSetName.trim() || !filePattern.trim()) {
      setError('Both test set name and file pattern are required');
      return;
    }

    if (!validateTestSetName(newTestSetName.trim())) {
      setError('Test set name can only contain letters, numbers, spaces, underscores, and dashes');
      return;
    }

    if (checkTestSetNameToday(newTestSetName.trim())) {
      if (!confirmReplacement) {
        setWarningMessage(
          `Test set "${newTestSetName.trim()}" already exists for today and will be replaced. Click "Add Test Set" again to confirm.`,
        );
        setConfirmReplacement(true);
        return; // Stop here and let user confirm
      }
      // User has confirmed, proceed with replacement
      setWarningMessage('');
    } else {
      setWarningMessage('');
      setConfirmReplacement(false);
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
        setShowAddPatternModal(false);
        setError('');
        setWarningMessage('');
        setSuccessMessage(`Successfully created test set "${newTestSet.name}"`);
        setTimeout(() => setSuccessMessage(''), 3000);
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

    if (checkTestSetNameToday(newTestSetName.trim())) {
      if (!confirmReplacement) {
        setWarningMessage(
          `Test set "${newTestSetName.trim()}" already exists for today and will be replaced. Click "Create Test Set" again to confirm.`,
        );
        setConfirmReplacement(true);
        return; // Stop here and let user confirm
      }
      // User has confirmed, proceed with replacement
      setWarningMessage('');
    } else {
      setWarningMessage('');
      setConfirmReplacement(false);
    }

    // Validate file pairing
    const validation = validateFilePairing();
    if (!validation.isValid) {
      setError(validation.errors.join('. '));
      return;
    }

    // Check for .zip files in input files
    const zipInputFiles = inputFiles.filter((file) => file.name.toLowerCase().endsWith('.zip'));
    if (zipInputFiles.length > 0) {
      setError(`Input files cannot be ZIP files: ${zipInputFiles.map((f) => f.name).join(', ')}`);
      return;
    }

    setLoading(true);
    try {
      // Prepare file info for GraphQL mutation
      const inputFileInfos = inputFiles.map((file) => ({
        fileName: file.name,
        fileSize: file.size,
        contentType: file.type,
      }));

      const baselineFileInfos = baselineFiles.map((file) => ({
        fileName: file.name,
        fileSize: file.size,
        contentType: 'application/zip', // Force standard ZIP content type
      }));

      // Call GraphQL mutation to get presigned URLs
      const result = await client.graphql({
        query: ADD_TEST_SET_FROM_UPLOAD,
        variables: {
          input: {
            name: newTestSetName.trim(),
            inputFiles: inputFileInfos,
            baselineFiles: baselineFileInfos,
          },
        },
      });

      const response = result.data.addTestSetFromUpload;

      // Check if response is null (GraphQL error)
      if (!response) {
        console.error('GraphQL mutation returned null response:', result);
        throw new Error('Failed to create test set - server returned null response');
      }

      // Check if required fields exist
      if (!response.inputUploadUrls || !response.baselineUploadUrls) {
        console.error('Missing upload URLs in response:', response);
        throw new Error('Failed to get upload URLs from server');
      }

      // Upload files using presigned URLs
      const uploadPromises = [];

      // Upload input files
      response.inputUploadUrls.forEach((urlInfo, index) => {
        const file = inputFiles[index];

        // Parse the presigned post data
        const presignedPostData = JSON.parse(urlInfo.presignedUrl);

        const formData = new FormData();

        // Add all required fields from presigned URL
        Object.entries(presignedPostData.fields).forEach(([key, value]) => {
          formData.append(key, value);
        });

        // Add the file last
        formData.append('file', file);

        const uploadPromise = fetch(presignedPostData.url, {
          method: 'POST',
          body: formData,
        })
          .then(async (uploadResponse) => {
            if (!uploadResponse.ok) {
              const responseText = await uploadResponse.text();
              console.error(`Upload response body:`, responseText);
              throw new Error(`Upload failed for ${file.name}: ${uploadResponse.status} ${uploadResponse.statusText}`);
            }
            return uploadResponse;
          })
          .catch((uploadError) => {
            console.error(`Error uploading input file ${file.name}:`, uploadError);
            throw uploadError;
          });

        uploadPromises.push(uploadPromise);
      });

      // Upload baseline files
      response.baselineUploadUrls.forEach((urlInfo, index) => {
        const file = baselineFiles[index];

        // Parse the presigned post data
        const presignedPostData = JSON.parse(urlInfo.presignedUrl);

        const formData = new FormData();

        // Add all required fields from presigned URL
        Object.entries(presignedPostData.fields).forEach(([key, value]) => {
          formData.append(key, value);
        });

        // Add the file last
        formData.append('file', file);

        const uploadPromise = fetch(presignedPostData.url, {
          method: 'POST',
          body: formData,
        })
          .then(async (uploadResponse) => {
            if (!uploadResponse.ok) {
              const responseText = await uploadResponse.text();
              console.error(`S3 Error for ${file.name} (${uploadResponse.status}):`, responseText);
              throw new Error(`Upload failed for ${file.name}: ${uploadResponse.status} ${uploadResponse.statusText}`);
            }
            return uploadResponse;
          })
          .catch((uploadError) => {
            console.error(`Error uploading baseline file ${file.name}:`, uploadError);
            throw uploadError;
          });

        uploadPromises.push(uploadPromise);
      });

      // Wait for all uploads to complete
      await Promise.all(uploadPromises);

      setSuccessMessage(`Test set "${newTestSetName}" created successfully. Files are being processed.`);
      setTimeout(() => setSuccessMessage(''), 3000);
      setShowAddUploadModal(false);
      setNewTestSetName('');
      setInputFiles([]);
      setBaselineFiles([]);
    } catch (err) {
      setError(`Failed to create upload test set: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    setError('');
    setWarningMessage('');
    try {
      const result = await client.graphql({ query: GET_TEST_SETS });
      setTestSets(result.data.getTestSets || []);
      setSuccessMessage('Test sets refreshed');
      setTimeout(() => setSuccessMessage(''), 3000);
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
      setTimeout(() => setSuccessMessage(''), 3000);
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
      cell: (item) => item.status || '-',
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
              <Button disabled={selectedItems.length === 0 || loading} onClick={() => setShowDeleteModal(true)}>
                Delete
              </Button>
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
          setInputFiles([]);
          setBaselineFiles([]);
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
                  setInputFiles([]);
                  setBaselineFiles([]);
                }}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                loading={loading}
                onClick={handleAddUploadTestSet}
                disabled={inputFiles.length === 0 || baselineFiles.length === 0}
              >
                Upload and Create Test Set
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
              placeholder="e.g., manual-upload-set-v1"
            />
          </FormField>

          <FormField label="Input Files" description="Select multiple input files (PDF, images, etc.)">
            <input
              type="file"
              multiple
              onChange={(e) => setInputFiles(Array.from(e.target.files))}
              style={{ width: '100%', padding: '8px' }}
            />
            {inputFiles.length > 0 && (
              <Box margin={{ top: 'xs' }}>
                <Badge color="blue">{inputFiles.length} input files selected</Badge>
              </Box>
            )}
          </FormField>

          <FormField label="Baseline Files" description="Select corresponding baseline zip files (filename.ext.zip)">
            <input
              type="file"
              multiple
              accept=".zip"
              onChange={(e) => setBaselineFiles(Array.from(e.target.files))}
              style={{ width: '100%', padding: '8px' }}
            />
            {baselineFiles.length > 0 && (
              <Box margin={{ top: 'xs' }}>
                <Badge color="green">{baselineFiles.length} baseline files selected</Badge>
              </Box>
            )}
          </FormField>

          {inputFiles.length > 0 && baselineFiles.length > 0 && (
            <Box>
              <Alert type={inputFiles.length === baselineFiles.length ? 'success' : 'warning'}>
                {inputFiles.length === baselineFiles.length
                  ? `Ready to upload ${inputFiles.length} file pairs`
                  : `File count mismatch: ${inputFiles.length} input files, ${baselineFiles.length} baseline files`}
              </Alert>
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
