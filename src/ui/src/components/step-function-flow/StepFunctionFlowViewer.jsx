// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { API, graphqlOperation, Logger } from 'aws-amplify';
import { Container, Header, SpaceBetween, Box, Alert, Spinner, Button, Modal } from '@awsui/components-react';
import { FaPlay, FaCheck, FaTimes, FaClock, FaRobot, FaFileAlt, FaEye, FaChartBar } from 'react-icons/fa';
import getStepFunctionExecution from '../../graphql/queries/getStepFunctionExecution';
import onStepFunctionExecutionUpdate from '../../graphql/subscriptions/onStepFunctionExecutionUpdate';
import FlowDiagram from './FlowDiagram';
import StepDetails from './StepDetails';
import './StepFunctionFlowViewer.css';

const logger = new Logger('StepFunctionFlowViewer');

const StepFunctionFlowViewer = ({ executionArn, visible, onDismiss }) => {
  const [selectedStep, setSelectedStep] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [subscription, setSubscription] = useState(null);
  const [isRealTime, setIsRealTime] = useState(false);
  const [refreshInterval] = useState(3000); // 3 seconds default (removed setter as it's not used)

  const fetchStepFunctionExecution = async () => {
    if (!executionArn || !visible) return;

    setLoading(true);
    setError(null);

    try {
      const result = await API.graphql(graphqlOperation(getStepFunctionExecution, { executionArn }));
      setData(result.data);
      logger.debug('Step Functions execution data:', result.data);
    } catch (err) {
      logger.error('Error fetching Step Functions execution:', err);
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  // Set up real-time subscription
  const setupSubscription = () => {
    if (!executionArn || subscription) return;

    try {
      const sub = API.graphql(graphqlOperation(onStepFunctionExecutionUpdate, { executionArn })).subscribe({
        next: ({ value }) => {
          logger.debug('Received Step Functions update:', value);
          if (value.data?.onStepFunctionExecutionUpdate) {
            setData({ getStepFunctionExecution: value.data.onStepFunctionExecutionUpdate });
            setIsRealTime(true);
            logger.info('Real-time update received for execution:', executionArn);
          }
        },
        error: (err) => {
          logger.warn('Subscription failed, falling back to polling:', err);
          setIsRealTime(false);
          // Continue with polling as fallback
        },
      });

      setSubscription(sub);
      // Don't set isRealTime=true until we actually receive data
      logger.debug('Step Functions subscription established (waiting for first update)');

      // Set a timeout to detect if subscription is not working
      setTimeout(() => {
        if (!isRealTime) {
          logger.warn('No real-time updates received, subscription may not be configured');
          setIsRealTime(false);
        }
      }, 10000); // Wait 10 seconds for first update
    } catch (err) {
      logger.error('Failed to establish subscription:', err);
      setIsRealTime(false);
    }
  };

  // Helper function to get status indicator
  const getStatusIndicator = () => {
    if (isRealTime) {
      return (
        <Box variant="small" color="text-status-success">
          🔴 Live Updates
        </Box>
      );
    }
    if (autoRefresh) {
      return (
        <Box variant="small" color="text-status-info">
          🔄 Auto-refresh ({refreshInterval / 1000}s)
        </Box>
      );
    }
    return (
      <Box variant="small" color="text-status-inactive">
        ⏸️ Manual refresh only
      </Box>
    );
  };

  // Initial fetch and subscription setup
  useEffect(() => {
    if (visible && executionArn) {
      fetchStepFunctionExecution();
      setupSubscription();
    }

    let intervalId;
    if (autoRefresh && visible && !isRealTime) {
      // Only use polling if subscription is not active
      intervalId = setInterval(fetchStepFunctionExecution, refreshInterval);
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
      if (subscription) {
        subscription.unsubscribe();
        setSubscription(null);
        setIsRealTime(false);
      }
    };
  }, [executionArn, visible, autoRefresh, isRealTime, refreshInterval]);

  useEffect(() => {
    if (data?.getStepFunctionExecution?.status === 'SUCCEEDED' || data?.getStepFunctionExecution?.status === 'FAILED') {
      setAutoRefresh(false);
    }
  }, [data]);

  const getStepIcon = (stepName, stepType, status) => {
    const iconProps = { size: 24, className: `step-icon step-icon-${status.toLowerCase()}` };

    if (stepName.toLowerCase().includes('upload') || stepName.toLowerCase().includes('input')) {
      return <FaFileAlt size={iconProps.size} className={iconProps.className} />;
    }
    if (stepName.toLowerCase().includes('bda') || stepName.toLowerCase().includes('bedrock')) {
      return <FaRobot size={iconProps.size} className={iconProps.className} />;
    }
    if (stepName.toLowerCase().includes('review') || stepName.toLowerCase().includes('hitl')) {
      return <FaEye size={iconProps.size} className={iconProps.className} />;
    }
    if (stepName.toLowerCase().includes('result') || stepName.toLowerCase().includes('process')) {
      return <FaChartBar size={iconProps.size} className={iconProps.className} />;
    }

    // Default icons based on status
    switch (status) {
      case 'SUCCEEDED':
        return <FaCheck size={iconProps.size} className={iconProps.className} />;
      case 'FAILED':
        return <FaTimes size={iconProps.size} className={iconProps.className} />;
      case 'RUNNING':
        return <FaClock size={iconProps.size} className={iconProps.className} />;
      default:
        return <FaPlay size={iconProps.size} className={iconProps.className} />;
    }
  };

  const formatDuration = (startDate, stopDate) => {
    if (!startDate) return 'N/A';
    const start = new Date(startDate);
    const end = stopDate ? new Date(stopDate) : new Date();
    const duration = Math.floor((end - start) / 1000);

    const minutes = Math.floor(duration / 60);
    const seconds = duration % 60;
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
  };

  if (loading) {
    return (
      <Modal visible={visible} onDismiss={onDismiss} header="Document Processing Flow" size="max">
        <Box textAlign="center" padding="xxl">
          <Spinner size="large" />
          <Box variant="p" margin={{ top: 'm' }}>
            Loading processing flow...
          </Box>
        </Box>
      </Modal>
    );
  }

  if (error) {
    return (
      <Modal visible={visible} onDismiss={onDismiss} header="Document Processing Flow" size="max">
        <Alert type="error" header="Error loading processing flow">
          {error.message}
        </Alert>
      </Modal>
    );
  }

  const execution = data?.getStepFunctionExecution;
  if (!execution) {
    return (
      <Modal visible={visible} onDismiss={onDismiss} header="Document Processing Flow" size="max">
        <Alert type="info" header="No processing flow found">
          No Step Functions execution found for this document.
        </Alert>
      </Modal>
    );
  }

  return (
    <Modal
      visible={visible}
      onDismiss={onDismiss}
      header={
        <Header
          variant="h2"
          actions={
            <SpaceBetween direction="horizontal" size="xs">
              {getStatusIndicator()}
              {!isRealTime && (
                <Button
                  variant={autoRefresh ? 'primary' : 'normal'}
                  onClick={() => setAutoRefresh(!autoRefresh)}
                  iconName={autoRefresh ? 'pause' : 'play'}
                >
                  {autoRefresh ? 'Pause' : 'Resume'} Auto-refresh
                </Button>
              )}
              <Button onClick={() => fetchStepFunctionExecution()} iconName="refresh" loading={loading}>
                Refresh
              </Button>
            </SpaceBetween>
          }
        >
          Document Processing Flow
        </Header>
      }
      size="max"
    >
      <SpaceBetween size="l">
        {/* Execution Overview */}
        <Container header={<Header variant="h3">Execution Overview</Header>}>
          <SpaceBetween direction="horizontal" size="l">
            <Box>
              <Box variant="awsui-key-label">Status</Box>
              <Box className={`execution-status execution-status-${execution.status.toLowerCase()}`}>
                {execution.status}
              </Box>
            </Box>
            <Box>
              <Box variant="awsui-key-label">Duration</Box>
              <Box>{formatDuration(execution.startDate, execution.stopDate)}</Box>
            </Box>
            <Box>
              <Box variant="awsui-key-label">Started</Box>
              <Box>{execution.startDate ? new Date(execution.startDate).toLocaleString() : 'N/A'}</Box>
            </Box>
            {execution.stopDate && (
              <Box>
                <Box variant="awsui-key-label">Completed</Box>
                <Box>{new Date(execution.stopDate).toLocaleString()}</Box>
              </Box>
            )}
          </SpaceBetween>
        </Container>

        {/* Flow Diagram */}
        <Container header={<Header variant="h3">Processing Flow</Header>}>
          <FlowDiagram
            steps={execution.steps || []}
            onStepClick={setSelectedStep}
            selectedStep={selectedStep}
            getStepIcon={getStepIcon}
          />
        </Container>

        {/* Step Details */}
        {selectedStep && (
          <Container header={<Header variant="h3">Step Details</Header>}>
            <StepDetails step={selectedStep} formatDuration={formatDuration} getStepIcon={getStepIcon} />
          </Container>
        )}

        {/* Steps Timeline */}
        <Container header={<Header variant="h3">Steps Timeline</Header>}>
          <div className="steps-timeline">
            {execution.steps?.map((step, index) => (
              <div
                key={step.name || index}
                className={`timeline-step ${step.status.toLowerCase()} ${
                  selectedStep?.name === step.name ? 'selected' : ''
                }`}
                onClick={() => setSelectedStep(step)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    setSelectedStep(step);
                  }
                }}
                role="button"
                tabIndex={0}
              >
                <div className="timeline-step-icon">{getStepIcon(step.name, step.type, step.status)}</div>
                <div className="timeline-step-content">
                  <div className="timeline-step-name">{step.name}</div>
                  <div className="timeline-step-meta">
                    <span className={`timeline-step-status status-${step.status.toLowerCase()}`}>{step.status}</span>
                    <span className="timeline-step-duration">{formatDuration(step.startDate, step.stopDate)}</span>
                  </div>
                  {step.error && (
                    <div className="timeline-step-error">
                      <strong>Error:</strong>{' '}
                      {step.error.length > 100 ? `${step.error.substring(0, 100)}...` : step.error}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Container>
      </SpaceBetween>
    </Modal>
  );
};

StepFunctionFlowViewer.propTypes = {
  executionArn: PropTypes.string.isRequired,
  visible: PropTypes.bool.isRequired,
  onDismiss: PropTypes.func.isRequired,
};

export default StepFunctionFlowViewer;
