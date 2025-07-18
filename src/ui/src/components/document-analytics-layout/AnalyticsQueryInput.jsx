// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React, { useState, useEffect, useRef } from 'react';
import PropTypes from 'prop-types';
import { API, Logger } from 'aws-amplify';
import { FormField, Input, Button, Grid, Box, Select, SpaceBetween } from '@awsui/components-react';
import listAnalyticsJobs from '../../graphql/queries/listAnalyticsJobs';

const logger = new Logger('AnalyticsQueryInput');

const AnalyticsQueryInput = ({ onSubmit, isSubmitting, selectedResult }) => {
  const [query, setQuery] = useState('');
  const [queryHistory, setQueryHistory] = useState([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [selectedOption, setSelectedOption] = useState(null);
  const lastFetchTimeRef = useRef(0);

  const fetchQueryHistory = async (force = false) => {
    // Don't fetch if we're already loading
    if (isLoadingHistory) return;

    // Don't fetch too frequently unless forced
    const now = Date.now();
    if (!force && now - lastFetchTimeRef.current < 5000) {
      // 5 second cooldown
      logger.debug('Skipping fetch due to cooldown');
      return;
    }

    try {
      setIsLoadingHistory(true);
      lastFetchTimeRef.current = now;

      const response = await API.graphql({
        query: listAnalyticsJobs,
        variables: { limit: 20 }, // Limit to most recent 20 queries
      });

      // Check if there are errors but we still got some data
      if (response.errors) {
        logger.warn('Received errors in listAnalyticsJobs response:', response.errors);
        // Continue processing if we have data despite errors
      }

      // Get items array and filter out null values
      const jobs = (response?.data?.listAnalyticsJobs?.items || []).filter((job) => job !== null);

      logger.debug('Raw jobs data:', jobs);

      // Filter out any jobs with invalid or missing required fields
      const validJobs = jobs.filter((job) => {
        try {
          // Check if job has required fields
          if (!job || !job.jobId || !job.query || !job.status) {
            logger.warn('Filtering out job with missing required fields:', job);
            return false;
          }

          // We'll keep jobs even with invalid dates - we'll handle them in the sort and display
          return true;
        } catch (e) {
          logger.warn(`Filtering out job with error: ${job?.jobId || 'unknown'}`, e);
          return false;
        }
      });

      // Sort by createdAt in descending order (newest first)
      // Use string comparison if date parsing fails
      const sortedJobs = [...validJobs].sort((a, b) => {
        try {
          // Try to parse dates and compare
          const dateA = a.createdAt ? new Date(a.createdAt) : new Date(0);
          const dateB = b.createdAt ? new Date(b.createdAt) : new Date(0);

          // Check if dates are valid
          if (!Number.isNaN(dateA.getTime()) && !Number.isNaN(dateB.getTime())) {
            return dateB - dateA;
          }

          // Fallback to string comparison
          return (b.createdAt || '').localeCompare(a.createdAt || '');
        } catch (e) {
          logger.warn('Error sorting jobs by date:', e);
          // Fallback to string comparison of jobId as last resort
          return (b.jobId || '').localeCompare(a.jobId || '');
        }
      });

      setQueryHistory(sortedJobs);
      logger.debug('Query history loaded:', sortedJobs.length);
    } catch (err) {
      logger.error('Error fetching query history:', err);
      // Continue with empty history rather than breaking the component
      setQueryHistory([]);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  // Fetch query history when component mounts
  useEffect(() => {
    fetchQueryHistory(true);
  }, []);

  // Update query input when a result is selected externally
  useEffect(() => {
    if (selectedResult) {
      setQuery(selectedResult.query);
      setSelectedOption(null); // Reset dropdown selection
    }
  }, [selectedResult]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (query.trim() && !isSubmitting) {
      onSubmit(query);
      setSelectedOption(null); // Reset dropdown selection after submission

      // Refresh the query history after a short delay to include the new query
      setTimeout(() => {
        fetchQueryHistory(true);
      }, 2000); // Wait 2 seconds to allow the backend to process the query
    }
  };

  const handleHistorySelection = ({ detail }) => {
    if (detail.selectedOption) {
      const selectedJob = queryHistory.find((job) => job.jobId === detail.selectedOption.value);
      if (selectedJob) {
        setQuery(selectedJob.query);
        setSelectedOption(detail.selectedOption);

        // If the job is completed, also submit the result to display it
        if (selectedJob.status === 'COMPLETED') {
          onSubmit(selectedJob.query, selectedJob.jobId);
        }
      }
    }
  };

  // Handle dropdown open event
  const handleDropdownOpen = (event) => {
    if (event.detail.open) {
      // Dropdown is being opened, fetch fresh data
      fetchQueryHistory();
    }
  };

  // Format date for display in dropdown
  const formatDate = (dateString) => {
    try {
      const date = new Date(dateString);
      // Check if date is valid
      if (Number.isNaN(date.getTime())) {
        return 'Unknown date';
      }
      return date.toLocaleString();
    } catch (e) {
      logger.warn(`Error formatting date: ${dateString}`, e);
      return 'Unknown date';
    }
  };

  // Create options for the dropdown
  const historyOptions = queryHistory
    .map((job) => {
      try {
        return {
          label: `${
            job.query?.length > 50 ? `${job.query.substring(0, 50)}...` : job.query || 'No query'
          } (${formatDate(job.createdAt)})`,
          value: job.jobId,
          description: job.status === 'COMPLETED' ? 'Completed' : job.status || 'Unknown status',
        };
      } catch (e) {
        logger.warn(`Error creating history option for job: ${job?.jobId}`, e);
        return {
          label: `Query ${job?.jobId || 'unknown'}`,
          value: job?.jobId || 'unknown',
          description: 'Error displaying query details',
        };
      }
    })
    .filter((option) => option.value !== 'unknown'); // Filter out any invalid options

  return (
    <form onSubmit={handleSubmit}>
      <SpaceBetween size="s">
        <FormField label="Previous queries">
          <Select
            placeholder="Select a previous query"
            options={historyOptions}
            selectedOption={selectedOption}
            onChange={handleHistorySelection}
            onFocus={() => fetchQueryHistory()}
            expandToViewport
            loadingText="Loading query history..."
            statusType={isLoadingHistory ? 'loading' : 'finished'}
            empty="No previous queries found"
            disabled={isSubmitting}
            onExpandableItemClick={handleDropdownOpen}
          />
        </FormField>

        <Grid gridDefinition={[{ colspan: { default: 12, xxs: 9 } }, { colspan: { default: 12, xxs: 3 } }]}>
          <FormField label="Enter your analytics query">
            <Input
              placeholder="e.g., Show me document processing volume over time"
              value={query}
              onChange={({ detail }) => setQuery(detail.value)}
              disabled={isSubmitting}
            />
          </FormField>
          <Box padding={{ top: 'xl' }}>
            {' '}
            {/* Add top padding to align with input box */}
            <Button variant="primary" type="submit" disabled={!query.trim() || isSubmitting} fullWidth>
              {isSubmitting ? 'Submitting...' : 'Submit query'}
            </Button>
          </Box>
        </Grid>
      </SpaceBetween>
    </form>
  );
};

AnalyticsQueryInput.propTypes = {
  onSubmit: PropTypes.func.isRequired,
  isSubmitting: PropTypes.bool,
  selectedResult: PropTypes.shape({
    query: PropTypes.string,
    jobId: PropTypes.string,
  }),
};

AnalyticsQueryInput.defaultProps = {
  isSubmitting: false,
  selectedResult: null,
};

export default AnalyticsQueryInput;
