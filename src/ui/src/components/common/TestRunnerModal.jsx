// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { Modal, Box, SpaceBetween, Button, FormField, Input, Alert } from '@awsui/components-react';
import TestRunnerStatus from '../test-results/TestRunnerStatus';

const TestRunnerModal = ({ visible, onDismiss, onRunTest, loading }) => {
  const [testSetName, setTestSetName] = useState('');
  const [filePattern, setFilePattern] = useState('');
  const [error, setError] = useState('');
  const [currentTestRunId, setCurrentTestRunId] = useState(null);
  const [testStarted, setTestStarted] = useState(false);
  const [testCompleted, setTestCompleted] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);

  const handleRunTest = async () => {
    if (!testSetName.trim() || !filePattern.trim()) {
      setError('Both test set name and file pattern are required');
      return;
    }

    try {
      const result = await onRunTest({ testSetName: testSetName.trim(), filePattern: filePattern.trim() });

      if (!result || !result.testRunId) {
        setError('Failed to start test run - no test ID returned');
        return;
      }

      setCurrentTestRunId(result.testRunId);
      setTestStarted(true);
      setError('');
    } catch (err) {
      let errorMessage = 'Failed to start test run';

      if (err.errors && err.errors.length > 0) {
        errorMessage = err.errors.map((e) => e.message).join('; ');
      }

      setError(errorMessage);
    }
  };

  const handleDismiss = () => {
    // Reset state when modal is dismissed
    setTestSetName('');
    setFilePattern('');
    setError('');
    setCurrentTestRunId(null);
    setTestStarted(false);
    setTestCompleted(false);
    setIsMinimized(false);
    onDismiss();
  };

  const handleTestComplete = () => {
    setTestCompleted(true);
    // Auto-close modal after 3 seconds when test completes
    setTimeout(() => {
      handleDismiss();
    }, 3000);
  };

  const handleMinimize = () => {
    setIsMinimized(true);
  };

  const handleRestore = () => {
    setIsMinimized(false);
  };

  // Show minimized state
  if (isMinimized && testStarted) {
    return (
      <div
        style={{
          position: 'fixed',
          bottom: '20px',
          right: '20px',
          backgroundColor: '#232f3e',
          color: 'white',
          padding: '12px 16px',
          borderRadius: '8px',
          boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
          zIndex: 1000,
          cursor: 'pointer',
        }}
        onClick={handleRestore}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            handleRestore();
          }
        }}
        role="button"
        tabIndex={0}
      >
        <div style={{ fontSize: '14px', fontWeight: 'bold' }}>Test Running: {currentTestRunId}</div>
        <div style={{ fontSize: '12px', opacity: 0.8 }}>Click to restore</div>
      </div>
    );
  }

  return (
    <Modal
      onDismiss={testCompleted ? handleDismiss : undefined} // Only allow dismiss when completed
      visible={visible && !isMinimized}
      closeAriaLabel="Close modal"
      size="medium"
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            {!testStarted && (
              <Button variant="link" onClick={handleDismiss}>
                Cancel
              </Button>
            )}
            {testStarted && !testCompleted && (
              <Button variant="normal" onClick={handleMinimize}>
                Minimize
              </Button>
            )}
            {!testCompleted && !testStarted && (
              <Button variant="primary" onClick={handleRunTest} loading={loading}>
                Run Test
              </Button>
            )}
          </SpaceBetween>
        </Box>
      }
      header={testStarted ? `Test Running: ${currentTestRunId}` : 'Run Test Set'}
    >
      <SpaceBetween direction="vertical" size="l">
        {error && (
          <Alert type="error" dismissible onDismiss={() => setError('')}>
            {error}
          </Alert>
        )}

        {!testStarted ? (
          <>
            <FormField label="Test Set Name" description="A descriptive name for this test set">
              <Input
                value={testSetName}
                onChange={({ detail }) => setTestSetName(detail.value)}
                placeholder="e.g., lending-package-v1"
              />
            </FormField>

            <FormField label="File Pattern" description="Pattern to match files in the input bucket (e.g., 'prefix.*')">
              <Input
                value={filePattern}
                onChange={({ detail }) => setFilePattern(detail.value)}
                placeholder="lending_package*.pdf"
              />
            </FormField>
          </>
        ) : (
          currentTestRunId && <TestRunnerStatus testRunId={currentTestRunId} onComplete={handleTestComplete} />
        )}
      </SpaceBetween>
    </Modal>
  );
};

TestRunnerModal.propTypes = {
  visible: PropTypes.bool.isRequired,
  onDismiss: PropTypes.func.isRequired,
  onRunTest: PropTypes.func.isRequired,
  loading: PropTypes.bool.isRequired,
};

export default TestRunnerModal;
