// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState } from 'react';
import { Container, Header, SpaceBetween, Button, Box } from '@awsui/components-react';
import TestResults from '../test-results/TestResults';
import TestComparison from '../test-comparison/TestComparison';
import TestResultsList from '../test-results/TestResultsList';

const TestResultsAndComparison = () => {
  const [selectedTestRunId, setSelectedTestRunId] = useState(null);
  const [selectedTestRuns, setSelectedTestRuns] = useState([]);
  const [showComparison, setShowComparison] = useState(false);

  const handleTestRunSelect = (testRunId) => {
    console.log('Test run selected:', testRunId);

    if (selectedTestRuns.includes(testRunId)) {
      // Remove if already selected
      const newSelection = selectedTestRuns.filter((id) => id !== testRunId);
      setSelectedTestRuns(newSelection);
      if (newSelection.length === 0) {
        setShowComparison(false);
      }
    } else {
      // Add to selection
      const newSelection = [...selectedTestRuns, testRunId];
      setSelectedTestRuns(newSelection);
    }

    // Also set for detailed view
    setSelectedTestRunId(testRunId);
  };

  const handleCompare = () => {
    if (selectedTestRuns.length >= 2) {
      setShowComparison(true);
    }
  };

  const handleBackToList = () => {
    setSelectedTestRunId(null);
    setSelectedTestRuns([]);
    setShowComparison(false);
  };

  // Show detailed test results for a single test
  if (selectedTestRunId && !showComparison) {
    return (
      <Container
        header={
          <Header
            variant="h2"
            description="Detailed test results"
            actions={
              <Button variant="normal" onClick={handleBackToList}>
                Back to Test List
              </Button>
            }
          >
            Test Results: {selectedTestRunId}
          </Header>
        }
      >
        <TestResults testRunId={selectedTestRunId} />
      </Container>
    );
  }

  // Show comparison results
  if (showComparison && selectedTestRuns.length >= 2) {
    return (
      <Container
        header={
          <Header
            variant="h2"
            description="Comparing selected test runs"
            actions={
              <Button variant="normal" onClick={handleBackToList}>
                Back to Test List
              </Button>
            }
          >
            Test Comparison Results
          </Header>
        }
      >
        <TestComparison preSelectedTestRunIds={selectedTestRuns} />
      </Container>
    );
  }

  // Show test list with selection for comparison
  return (
    <Container>
      <SpaceBetween size="xs">
        {selectedTestRuns.length > 0 && (
          <Box>
            <strong>Selected for comparison:</strong>
            <ul>
              {selectedTestRuns.map((id) => (
                <li key={id}>
                  {id}{' '}
                  <Button variant="link" onClick={() => handleTestRunSelect(id)}>
                    Remove
                  </Button>
                </li>
              ))}
            </ul>
            {selectedTestRuns.length >= 2 && (
              <Button variant="primary" onClick={handleCompare}>
                Compare Selected Tests ({selectedTestRuns.length})
              </Button>
            )}
          </Box>
        )}

        <TestResultsList onSelectTestRun={handleTestRunSelect} />
      </SpaceBetween>
    </Container>
  );
};

export default TestResultsAndComparison;
