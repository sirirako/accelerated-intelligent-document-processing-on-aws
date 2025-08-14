// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React, { useState, useEffect, useRef } from 'react';
import PropTypes from 'prop-types';
import { API, Logger } from 'aws-amplify';
import { FormField, Textarea, Button, Grid, Box, SpaceBetween, ButtonDropdown, Select } from '@awsui/components-react';
import listAgentJobs from '../../graphql/queries/listAgentJobs';
import deleteAgentJob from '../../graphql/queries/deleteAgentJob';
import listAvailableAgents from '../../graphql/queries/listAvailableAgents';
import { useAnalyticsContext } from '../../contexts/analytics';

// Custom styles for expandable textarea
const textareaStyles = `
  .expandable-textarea {
    max-height: 250px;
    overflow-y: auto !important;
    resize: vertical;
  }
`;

const logger = new Logger('AnalyticsQueryInput');

const AnalyticsQueryInput = ({ onSubmit, isSubmitting, selectedResult }) => {
  const { analyticsState, updateAnalyticsState, resetAnalyticsState } = useAnalyticsContext();
  const { currentInputText } = analyticsState;

  const [queryHistory, setQueryHistory] = useState([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [selectedOption, setSelectedOption] = useState(null);
  const [isDeletingJob, setIsDeletingJob] = useState(false);
  const [availableAgents, setAvailableAgents] = useState([]);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [isLoadingAgents, setIsLoadingAgents] = useState(false);
  const lastFetchTimeRef = useRef(0);

  const fetchAvailableAgents = async () => {
    try {
      setIsLoadingAgents(true);
      const response = await API.graphql({
        query: listAvailableAgents,
      });

      const agents = response?.data?.listAvailableAgents || [];
      setAvailableAgents(agents);

      // Auto-select first agent if none selected
      if (agents.length > 0 && !selectedAgent) {
        setSelectedAgent({
          label: agents[0].agent_name,
          value: agents[0].agent_id,
          description: agents[0].agent_description,
        });
      }
    } catch (err) {
      logger.error('Error fetching available agents:', err);
      setAvailableAgents([]);
    } finally {
      setIsLoadingAgents(false);
    }
  };

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

      let response;
      try {
        response = await API.graphql({
          query: listAgentJobs,
          variables: { limit: 20 }, // Limit to most recent 20 queries
        });
      } catch (amplifyError) {
        // Amplify throws an exception when there are GraphQL errors, but the response might still contain valid data
        logger.warn('Amplify threw an exception due to GraphQL errors, checking for valid data:', amplifyError);

        // Check if the error object contains the actual response data
        if (amplifyError.data && amplifyError.data.listAgentJobs) {
          logger.info('Found valid data in the error response, proceeding with processing');
          response = {
            data: amplifyError.data,
            errors: amplifyError.errors || [],
          };
        } else {
          // If there's no data in the error, re-throw to be handled by outer catch
          throw amplifyError;
        }
      }

      // Handle GraphQL errors gracefully - log them but continue processing valid data
      if (response.errors && response.errors.length > 0) {
        logger.warn(`Received ${response.errors.length} GraphQL errors in listAgentJobs response:`, response.errors);
        logger.warn('Continuing to process valid data despite errors...');
      }

      // Get items array and filter out null values (corrupted items)
      const rawItems = response?.data?.listAgentJobs?.items || [];
      const nonNullJobs = rawItems.filter((job) => job !== null);

      logger.debug(`Raw response: ${rawItems.length} total items, ${nonNullJobs.length} non-null items`);
      logger.debug('Non-null jobs data:', nonNullJobs);

      // Filter out any jobs with invalid or missing required fields
      const validJobs = nonNullJobs.filter((job) => {
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

      logger.debug(`Filtered to ${validJobs.length} valid jobs`);

      // Sort by createdAt in descending order (newest first)
      // Use string comparison if date parsing fails
      const sortedJobs = [...validJobs].sort((a, b) => {
        try {
          // Try to parse dates and compare
          const dateA = a.createdAt ? new Date(a.createdAt) : new Date(0);
          const dateB = b.createdAt ? new Date(b.createdAt) : new Date(0);

          // Check if dates are valid
          if (Number.isNaN(dateA.getTime()) || Number.isNaN(dateB.getTime())) {
            // Fall back to string comparison if dates are invalid
            return (b.createdAt || '').localeCompare(a.createdAt || '');
          }

          return dateB.getTime() - dateA.getTime();
        } catch (e) {
          logger.warn('Error sorting jobs by date, using string comparison:', e);
          // Fall back to string comparison
          return (b.createdAt || '').localeCompare(a.createdAt || '');
        }
      });

      logger.debug('Final processed and sorted jobs:', sortedJobs);
      setQueryHistory(sortedJobs);

      // Log summary of what we processed
      if (response.errors && response.errors.length > 0) {
        logger.info(
          `Successfully processed ${sortedJobs.length} valid queries despite ${response.errors.length} GraphQL errors from corrupted items`,
        );
      } else {
        logger.info(`Successfully processed ${sortedJobs.length} queries with no errors`);
      }
    } catch (err) {
      logger.error('Error fetching query history:', err);
      // Only log as empty if it's a complete failure (network error, etc.)
      logger.error('Complete failure - setting empty history');
      setQueryHistory([]);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  // Fetch query history and agents when component mounts
  useEffect(() => {
    fetchQueryHistory(true);
    fetchAvailableAgents();
  }, []);

  // Update query input when a result is selected externally
  useEffect(() => {
    if (selectedResult) {
      updateAnalyticsState({ currentInputText: selectedResult.query });
      setSelectedOption(null); // Reset dropdown selection
    }
  }, [selectedResult, updateAnalyticsState]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (currentInputText.trim() && selectedAgent && !isSubmitting) {
      onSubmit(currentInputText, selectedAgent.value);
      setSelectedOption(null); // Reset dropdown selection after submission

      // Refresh the query history after a short delay to include the new query
      setTimeout(() => {
        fetchQueryHistory(true);
      }, 2000); // Wait 2 seconds to allow the backend to process the query
    }
  };

  const handleClearQuery = () => {
    // Clean up any existing subscription before resetting state
    if (analyticsState.subscription) {
      analyticsState.subscription.unsubscribe();
    }

    // Reset all analytics state to initial values
    resetAnalyticsState();
    // Also clear local component state
    setSelectedOption(null);
  };

  const handleDropdownItemClick = ({ detail }) => {
    // Prevent dropdown item selection if a delete operation is in progress
    if (isDeletingJob) {
      return;
    }

    const selectedJob = queryHistory.find((job) => job.jobId === detail.id);
    if (selectedJob) {
      updateAnalyticsState({ currentInputText: selectedJob.query });
      setSelectedOption({ value: selectedJob.jobId, label: selectedJob.query });

      // Submit the job to display its current status and results (if completed)
      // This will work for both completed jobs and in-progress jobs
      onSubmit(selectedJob.query, selectedAgent?.value, selectedJob.jobId);
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

  // Create dropdown items with delete functionality
  const createDropdownItems = () => {
    if (queryHistory.length === 0) {
      return [{ text: 'No previous queries found', disabled: true }];
    }

    return queryHistory.map((job) => {
      const displayText = job.query?.length > 50 ? `${job.query.substring(0, 50)}...` : job.query || 'No query';
      const dateText = formatDate(job.createdAt);

      return {
        id: job.jobId,
        text: (
          <div style={{ display: 'flex', alignItems: 'center', width: '100%', minHeight: '40px' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 'normal', marginBottom: '2px' }}>{displayText}</div>
              <div style={{ fontSize: '12px', color: '#5f6b7a' }}>
                {dateText} • {job.status === 'COMPLETED' ? 'Completed' : job.status || 'Unknown status'}
              </div>
            </div>
            <Button
              variant="icon"
              iconName="remove"
              onClick={async (e) => {
                e.preventDefault();
                e.stopPropagation();

                // Set flag to prevent dropdown item selection
                setIsDeletingJob(true);

                try {
                  await API.graphql({
                    query: deleteAgentJob,
                    variables: {
                      jobId: job.jobId,
                    },
                  });

                  logger.debug('Successfully deleted job:', job.jobId);

                  // Remove the deleted job from the local state
                  setQueryHistory((prev) => prev.filter((historyJob) => historyJob.jobId !== job.jobId));

                  // If the deleted job was currently selected, clear the selection
                  if (selectedOption && selectedOption.value === job.jobId) {
                    setSelectedOption(null);
                    updateAnalyticsState({ currentInputText: '' });
                  }
                } catch (err) {
                  logger.error('Error deleting job:', err);
                } finally {
                  // Reset the flag after a short delay to ensure event handling is complete
                  setTimeout(() => {
                    setIsDeletingJob(false);
                  }, 100);
                }
              }}
              ariaLabel={`Delete query: ${displayText}`}
              style={{
                opacity: 0.7,
                transition: 'opacity 0.2s',
                marginLeft: 'auto',
                flexShrink: 0,
              }}
              onMouseEnter={(e) => {
                e.target.style.opacity = 1;
              }}
              onMouseLeave={(e) => {
                e.target.style.opacity = 0.7;
              }}
            />
          </div>
        ),
        disabled: false,
      };
    });
  };

  return (
    <>
      <style>{textareaStyles}</style>
      <form onSubmit={handleSubmit}>
        <SpaceBetween size="s">
          <Grid gridDefinition={[{ colspan: { default: 12, xxs: 9 } }, { colspan: { default: 12, xxs: 3 } }]}>
            <SpaceBetween size="s">
              <FormField label="Select an agent">
                <Select
                  selectedOption={selectedAgent}
                  onChange={({ detail }) => setSelectedAgent(detail.selectedOption)}
                  options={availableAgents.map((agent) => ({
                    label: agent.agent_name,
                    value: agent.agent_id,
                    description: agent.agent_description,
                  }))}
                  placeholder="Choose an agent"
                  disabled={isSubmitting || isLoadingAgents}
                  loadingText="Loading agents..."
                  statusType={isLoadingAgents ? 'loading' : 'finished'}
                />
              </FormField>
              <FormField label="Enter your question for the agent">
                <Textarea
                  placeholder="How has the number of documents processed per day trended over the past three weeks?"
                  value={currentInputText}
                  onChange={({ detail }) => updateAnalyticsState({ currentInputText: detail.value })}
                  disabled={isSubmitting}
                  rows={3}
                  className="expandable-textarea"
                />
              </FormField>
            </SpaceBetween>
            <Box padding={{ top: 'xl' }}>
              {' '}
              {/* Add top padding to align with input box */}
              <SpaceBetween size="s">
                <Button
                  variant="primary"
                  type="submit"
                  disabled={!currentInputText.trim() || !selectedAgent || isSubmitting}
                  fullWidth
                >
                  {isSubmitting ? 'Submitting...' : 'Submit query'}
                </Button>
                <Button variant="normal" onClick={handleClearQuery} disabled={isSubmitting} fullWidth>
                  Clear query
                </Button>
              </SpaceBetween>
            </Box>
          </Grid>

          <FormField label="Previous queries">
            <ButtonDropdown
              items={createDropdownItems()}
              onItemClick={handleDropdownItemClick}
              onFocus={() => fetchQueryHistory()}
              loading={isLoadingHistory}
              disabled={isSubmitting}
            >
              {(() => {
                if (!selectedOption) return 'Select a previous query';
                if (selectedOption.label?.length > 40) {
                  return `${selectedOption.label.substring(0, 40)}...`;
                }
                return selectedOption.label || 'Selected query';
              })()}
            </ButtonDropdown>
          </FormField>
        </SpaceBetween>
      </form>
    </>
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
