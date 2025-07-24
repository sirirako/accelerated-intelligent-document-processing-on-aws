// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React, { useState, useEffect } from 'react';
import { API, Logger } from 'aws-amplify';
import { Container, Header, SpaceBetween, Spinner, Box, Button } from '@awsui/components-react';

import submitAnalyticsQuery from '../../graphql/queries/submitAnalyticsQuery';
import getAnalyticsJobStatus from '../../graphql/queries/getAnalyticsJobStatus';
import onAnalyticsJobComplete from '../../graphql/subscriptions/onAnalyticsJobComplete';

import AnalyticsQueryInput from './AnalyticsQueryInput';
import AnalyticsJobStatus from './AnalyticsJobStatus';
import AnalyticsResultDisplay from './AnalyticsResultDisplay';

const logger = new Logger('DocumentsAnalyticsLayout');

// Sample data for testing
const sampleResponses = {
  plot: {
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
  },
  table: {
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
  },
  text: {
    content: 'You have processed a total of 1 document.',
    responseType: 'text',
  },
};

const DocumentsAnalyticsLayout = () => {
  const [queryText, setQueryText] = useState('');
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [jobResult, setJobResult] = useState(null);
  const [error, setError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [subscription, setSubscription] = useState(null);
  const [selectedHistoryItem] = useState(null);
  const [testMode, setTestMode] = useState(false);

  const subscribeToJobCompletion = (id) => {
    try {
      logger.debug('Subscribing to job completion for job ID:', id);
      const sub = API.graphql({
        query: onAnalyticsJobComplete,
        variables: { jobId: id },
      }).subscribe({
        next: async ({ value }) => {
          // Log the entire subscription response
          logger.debug('Subscription response value:', JSON.stringify(value, null, 2));

          const jobCompleted = value?.data?.onAnalyticsJobComplete;
          logger.debug('Job completion notification:', jobCompleted);

          if (jobCompleted) {
            // Job completed, now fetch the actual job details
            try {
              logger.debug('Fetching job details after completion notification');
              const jobResponse = await API.graphql({
                query: getAnalyticsJobStatus,
                variables: { jobId: id },
              });

              const job = jobResponse?.data?.getAnalyticsJobStatus;
              logger.debug('Fetched job details:', job);

              if (job) {
                setJobStatus(job.status);

                if (job.status === 'COMPLETED') {
                  setJobResult(job.result);
                } else if (job.status === 'FAILED') {
                  setError(job.error || 'Job processing failed');
                }
              } else {
                logger.error('Failed to fetch job details after completion notification');
                setError('Failed to fetch job details after completion');
              }
            } catch (fetchError) {
              logger.error('Error fetching job details:', fetchError);
              setError(`Failed to fetch job details: ${fetchError.message || 'Unknown error'}`);
            }
          } else {
            logger.error('Received invalid completion notification. Full response:', JSON.stringify(value, null, 2));
            setError(`Received invalid completion notification. Check console logs for details.`);
          }
        },
        error: (err) => {
          logger.error('Subscription error:', err);
          logger.error('Error details:', JSON.stringify(err, null, 2));
          setError(`Subscription error: ${err.message || 'Unknown error'}`);
        },
      });

      setSubscription(sub);
      return sub;
    } catch (err) {
      logger.error('Error setting up subscription:', err);
      setError(`Failed to set up job status subscription: ${err.message || 'Unknown error'}`);
      return null;
    }
  };

  // Clean up subscription when component unmounts or when jobId changes
  useEffect(() => {
    return () => {
      if (subscription) {
        logger.debug('Cleaning up subscription');
        subscription.unsubscribe();
      }
    };
  }, [subscription]);

  const handleSubmitQuery = async (query, existingJobId = null) => {
    try {
      setQueryText(query);

      // If an existing job ID is provided, fetch that job's result instead of creating a new job
      if (existingJobId) {
        logger.debug('Using existing job:', existingJobId);
        setJobId(existingJobId);

        // Fetch the job status and result
        const response = await API.graphql({
          query: getAnalyticsJobStatus,
          variables: { jobId: existingJobId },
        });

        const job = response?.data?.getAnalyticsJobStatus;
        if (job) {
          setJobStatus(job.status);
          if (job.status === 'COMPLETED') {
            setJobResult(job.result);
          } else if (job.status === 'FAILED') {
            setError(job.error || 'Job processing failed');
          } else {
            // If job is still processing, subscribe to updates
            subscribeToJobCompletion(existingJobId);
          }
        }
        return;
      }

      // Otherwise, create a new job
      setIsSubmitting(true);
      setJobResult(null);
      setError(null);

      // Clean up previous subscription if exists
      if (subscription) {
        subscription.unsubscribe();
      }

      logger.debug('Submitting analytics query:', query);
      const response = await API.graphql({
        query: submitAnalyticsQuery,
        variables: { query },
      });

      const job = response?.data?.submitAnalyticsQuery;
      logger.debug('Job created:', job);

      if (!job) {
        throw new Error('Failed to create analytics job - received null response');
      }

      setJobId(job.jobId);
      setJobStatus(job.status);

      // Subscribe to job completion
      subscribeToJobCompletion(job.jobId);
    } catch (err) {
      logger.error('Error submitting query:', err);
      setError(err.message || 'Failed to submit query');
      setJobStatus('FAILED');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTestResponse = (responseType) => {
    const testQueries = {
      plot: 'Show me daily document processing count for the last week',
      table: 'Show me processing data in table format',
      text: 'How many documents have been processed?',
    };

    setQueryText(testQueries[responseType]);
    setJobResult(sampleResponses[responseType]);
    setJobStatus('COMPLETED');
    setJobId(`test-${responseType}-${Date.now()}`);
    setError(null);
  };

  // Poll for job status as a fallback in case subscription fails
  useEffect(() => {
    let intervalId;

    if (jobId && jobStatus && (jobStatus === 'PENDING' || jobStatus === 'PROCESSING')) {
      intervalId = setInterval(async () => {
        try {
          logger.debug('Polling job status for job ID:', jobId);
          const response = await API.graphql({
            query: getAnalyticsJobStatus,
            variables: { jobId },
          });

          const job = response?.data?.getAnalyticsJobStatus;
          logger.debug('Polled job status:', job);

          if (job && job.status !== jobStatus) {
            setJobStatus(job.status);

            if (job.status === 'COMPLETED') {
              setJobResult(job.result);
              clearInterval(intervalId);
            } else if (job.status === 'FAILED') {
              setError(job.error || 'Job processing failed');
              clearInterval(intervalId);
            }
          }
        } catch (err) {
          logger.error('Error polling job status:', err);
          // Don't set error here to avoid overriding subscription errors
        }
      }, 30000); // Poll every 30 seconds
    }

    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [jobId, jobStatus]);

  return (
    <Container header={<Header variant="h1">Document Analytics</Header>}>
      <SpaceBetween size="l">
        <Box>
          <SpaceBetween size="s" direction="horizontal">
            <Button variant="link" onClick={() => setTestMode(!testMode)}>
              {testMode ? 'Hide' : 'Show'} Test Mode
            </Button>
          </SpaceBetween>
        </Box>

        {testMode && (
          <Container header={<Header variant="h2">Test Response Types</Header>}>
            <SpaceBetween size="m">
              <Box>Use these buttons to test the different response display types:</Box>
              <SpaceBetween size="s" direction="horizontal">
                <Button onClick={() => handleTestResponse('plot')}>Test Plot Response</Button>
                <Button onClick={() => handleTestResponse('table')}>Test Table Response</Button>
                <Button onClick={() => handleTestResponse('text')}>Test Text Response</Button>
                <Button
                  onClick={() => {
                    setJobResult(null);
                    setQueryText('');
                    setJobStatus(null);
                    setJobId(null);
                    setError(null);
                  }}
                >
                  Clear Results
                </Button>
              </SpaceBetween>
            </SpaceBetween>
          </Container>
        )}

        <AnalyticsQueryInput
          onSubmit={handleSubmitQuery}
          isSubmitting={isSubmitting}
          selectedResult={selectedHistoryItem}
        />

        {isSubmitting && (
          <Box textAlign="center" padding={{ vertical: 'l' }}>
            <Spinner size="large" />
            <Box padding={{ top: 's' }}>Submitting your query...</Box>
          </Box>
        )}

        <AnalyticsJobStatus jobId={jobId} status={jobStatus} error={error} />

        {jobStatus === 'PROCESSING' && (
          <Box textAlign="center" padding={{ vertical: 'l' }}>
            <Spinner size="large" />
            <Box padding={{ top: 's' }}>Processing your query...</Box>
          </Box>
        )}

        {jobResult && <AnalyticsResultDisplay result={jobResult} query={queryText} />}
      </SpaceBetween>
    </Container>
  );
};

export default DocumentsAnalyticsLayout;
