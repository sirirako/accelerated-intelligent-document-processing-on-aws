// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React, { useState } from 'react';
import { Container, Header, SpaceBetween, Button, ButtonDropdown } from '@awsui/components-react';

import AnalyticsResultDisplay from './AnalyticsResultDisplay';

// Sample data based on your JSON files
const samplePlotData = {
  responseType: 'plotData',
  data: {
    datasets: [
      {
        backgroundColor: 'rgba(54, 162, 235, 0.2)',
        borderColor: 'rgba(54, 162, 235, 1)',
        data: [1, 1, 1],
        borderWidth: 1,
        label: 'Documents Processed',
      },
    ],
    labels: ['Jul 17', 'Jul 18', 'Jul 21'],
  },
  options: {
    scales: {
      y: {
        beginAtZero: true,
        title: {
          display: true,
          text: 'Number of Documents',
        },
      },
    },
    responsive: true,
    title: {
      display: true,
      text: 'Daily Document Processing Count (Last Week)',
    },
    maintainAspectRatio: false,
  },
  type: 'bar',
};

const sampleTableData = {
  responseType: 'table',
  headers: [
    {
      id: 'processing_date',
      label: 'Processing Date',
      sortable: true,
    },
    {
      id: 'documents_processed',
      label: 'Documents Processed',
      sortable: true,
    },
  ],
  rows: [
    {
      id: '2025-07-17',
      data: {
        processing_date: '2025-07-17',
        documents_processed: 1,
      },
    },
    {
      id: '2025-07-18',
      data: {
        processing_date: '2025-07-18',
        documents_processed: 1,
      },
    },
    {
      id: '2025-07-21',
      data: {
        processing_date: '2025-07-21',
        documents_processed: 1,
      },
    },
  ],
};

const sampleTextData = {
  content: 'You have processed a total of 1 document.',
  responseType: 'text',
};

const TestAnalyticsDisplay = () => {
  const [currentResult, setCurrentResult] = useState(null);
  const [currentQuery, setCurrentQuery] = useState('');

  const testCases = [
    {
      id: 'plot',
      text: 'Test Plot Display',
      data: samplePlotData,
      query: 'Show me daily document processing count for the last week',
    },
    {
      id: 'table',
      text: 'Test Table Display',
      data: sampleTableData,
      query: 'Show me processing data in table format',
    },
    {
      id: 'text',
      text: 'Test Text Display',
      data: sampleTextData,
      query: 'How many documents have been processed?',
    },
  ];

  const handleTestCase = (testCase) => {
    setCurrentResult(testCase.data);
    setCurrentQuery(testCase.query);
  };

  return (
    <Container header={<Header variant="h1">Analytics Display Test</Header>}>
      <SpaceBetween size="l">
        <ButtonDropdown
          items={testCases.map((testCase) => ({
            id: testCase.id,
            text: testCase.text,
          }))}
          onItemClick={({ detail }) => {
            const testCase = testCases.find((tc) => tc.id === detail.id);
            if (testCase) {
              handleTestCase(testCase);
            }
          }}
        >
          Test Response Types
        </ButtonDropdown>

        <Button
          onClick={() => {
            setCurrentResult(null);
            setCurrentQuery('');
          }}
        >
          Clear Results
        </Button>

        {currentResult && <AnalyticsResultDisplay result={currentResult} query={currentQuery} />}
      </SpaceBetween>
    </Container>
  );
};

export default TestAnalyticsDisplay;
