// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React, { useState, useEffect } from 'react';
import { API, Logger } from 'aws-amplify';
import { Container, Header, SpaceBetween, Spinner, Box } from '@awsui/components-react';

import submitAnalyticsQuery from '../../graphql/queries/submitAnalyticsQuery';
import getAnalyticsJobStatus from '../../graphql/queries/getAnalyticsJobStatus';
import onAnalyticsJobComplete from '../../graphql/subscriptions/onAnalyticsJobComplete';

import AnalyticsQueryInput from './AnalyticsQueryInput';
import AnalyticsJobStatus from './AnalyticsJobStatus';
import AnalyticsResultDisplay from './AnalyticsResultDisplay';

const logger = new Logger('DocumentsAnalyticsLayout');

const DocumentsAnalyticsLayout = () => {
  const [queryText, setQueryText] = useState('');
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [jobResult, setJobResult] = useState(null);
  const [error, setError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [subscription, setSubscription] = useState(null);

  const subscribeToJobCompletion = (id) => {
    try {
      logger.debug('Subscribing to job completion for job ID:', id);
      const sub = API.graphql({
        query: onAnalyticsJobComplete,
        variables: { jobId: id },
      }).subscribe({
        next: ({ value }) => {
          // Log the entire subscription response
          logger.debug('Subscription response value:', JSON.stringify(value, null, 2));

          const job = value?.data?.onAnalyticsJobComplete;
          logger.debug('Extracted job data:', job);

          if (job) {
            setJobStatus(job.status);

            if (job.status === 'COMPLETED') {
              setJobResult(job.result);
            } else if (job.status === 'FAILED') {
              setError(job.error || 'Job processing failed');
            }
          } else {
            logger.error('Received null job data in subscription. Full response:', JSON.stringify(value, null, 2));
            setError(`Received invalid data from subscription. Check console logs for details.`);
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

  const handleSubmitQuery = async (query) => {
    try {
      setIsSubmitting(true);
      setQueryText(query);
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
      }, 5000); // Poll every 5 seconds
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
        <AnalyticsQueryInput onSubmit={handleSubmitQuery} isSubmitting={isSubmitting} />

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
