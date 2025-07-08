import React, { useState, useEffect, useRef } from 'react';
import PropTypes from 'prop-types';
import { API, graphqlOperation, Logger } from 'aws-amplify';
import { Container, Header, SpaceBetween, Box, Alert, Spinner, Button, Modal, Badge } from '@awsui/components-react';
import {
  FaPlay,
  FaCheck,
  FaTimes,
  FaClock,
  FaRobot,
  FaFileAlt,
  FaEye,
  FaChartBar,
  FaMap,
  FaList,
} from 'react-icons/fa';
import getStepFunctionExecution from '../../graphql/queries/getStepFunctionExecution';
import FlowDiagram from './FlowDiagram';
import StepDetails from './StepDetails';
import './StepFunctionFlowViewer.css';

const logger = new Logger('StepFunctionFlowViewer');

const StepFunctionFlowViewer = ({ executionArn, visible, onDismiss }) => {
  const [selectedStep, setSelectedStep] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(false);
  const [lastRefreshTime, setLastRefreshTime] = useState(null);
  const autoRefreshIntervalRef = useRef(null);
  const AUTO_REFRESH_INTERVAL = 10000; // 10 seconds
  const [enhancedSteps, setEnhancedSteps] = useState([]);

  // Function to enhance Step Function steps for better visualization
  const enhanceStepFunctionSteps = (steps) => {
    if (!steps || !Array.isArray(steps)) return [];

    // Create a copy of the steps array
    const processedSteps = [...steps];

    // Find Map states
    const mapStates = steps.filter((step) => step.name.includes('ProcessSections') || step.type === 'Parallel');

    // Check if we have the complete flow or need to add synthetic steps
    const hasProcessResultsStep = steps.some((step) => step.name === 'ProcessResultsStep');
    const hasSummarizationChoice = steps.some((step) => step.name === 'SummarizationChoice');
    const hasSummarizationStep = steps.some((step) => step.name === 'SummarizationStep');
    const hasWorkflowComplete = steps.some((step) => step.name === 'WorkflowComplete');

    // If we're missing steps after the Map state, add synthetic steps for the complete flow
    if (
      mapStates.length > 0 &&
      (!hasProcessResultsStep || !hasSummarizationChoice || !hasSummarizationStep || !hasWorkflowComplete)
    ) {
      // Find the last step in the current flow
      const lastStep = [...steps].sort((a, b) => {
        if (!a.stopDate) return 1;
        if (!b.stopDate) return -1;
        return new Date(b.stopDate) - new Date(a.stopDate);
      })[0];

      // Add synthetic steps for the complete flow
      if (!hasProcessResultsStep) {
        processedSteps.push({
          name: 'ProcessResultsStep',
          type: 'Task',
          status: lastStep.status === 'SUCCEEDED' ? 'SUCCEEDED' : 'PENDING',
          startDate: lastStep.stopDate,
          stopDate:
            lastStep.status === 'SUCCEEDED'
              ? new Date(new Date(lastStep.stopDate).getTime() + 1000).toISOString()
              : null,
          input: null,
          output: null,
          error: null,
          isSynthetic: true,
          isCompleteFlow: true,
        });
      }

      if (!hasSummarizationChoice) {
        const prevStep = hasProcessResultsStep
          ? steps.find((step) => step.name === 'ProcessResultsStep')
          : processedSteps.find((step) => step.name === 'ProcessResultsStep');

        processedSteps.push({
          name: 'SummarizationChoice',
          type: 'Choice',
          status: prevStep && prevStep.status === 'SUCCEEDED' ? 'SUCCEEDED' : 'PENDING',
          startDate: prevStep ? prevStep.stopDate : lastStep.stopDate,
          stopDate:
            prevStep && prevStep.status === 'SUCCEEDED'
              ? new Date(new Date(prevStep.stopDate).getTime() + 1000).toISOString()
              : null,
          input: null,
          output: null,
          error: null,
          isSynthetic: true,
          isCompleteFlow: true,
        });
      }

      if (!hasSummarizationStep) {
        const prevStep = hasSummarizationChoice
          ? steps.find((step) => step.name === 'SummarizationChoice')
          : processedSteps.find((step) => step.name === 'SummarizationChoice');

        processedSteps.push({
          name: 'SummarizationStep',
          type: 'Task',
          status: prevStep && prevStep.status === 'SUCCEEDED' ? 'SUCCEEDED' : 'PENDING',
          startDate: prevStep ? prevStep.stopDate : lastStep.stopDate,
          stopDate:
            prevStep && prevStep.status === 'SUCCEEDED'
              ? new Date(new Date(prevStep.stopDate).getTime() + 1000).toISOString()
              : null,
          input: null,
          output: null,
          error: null,
          isSynthetic: true,
          isCompleteFlow: true,
        });
      }

      if (!hasWorkflowComplete) {
        const prevStep = hasSummarizationStep
          ? steps.find((step) => step.name === 'SummarizationStep')
          : processedSteps.find((step) => step.name === 'SummarizationStep');

        processedSteps.push({
          name: 'WorkflowComplete',
          type: 'Pass',
          status: prevStep && prevStep.status === 'SUCCEEDED' ? 'SUCCEEDED' : 'PENDING',
          startDate: prevStep ? prevStep.stopDate : lastStep.stopDate,
          stopDate:
            prevStep && prevStep.status === 'SUCCEEDED'
              ? new Date(new Date(prevStep.stopDate).getTime() + 1000).toISOString()
              : null,
          input: null,
          output: null,
          error: null,
          isSynthetic: true,
          isCompleteFlow: true,
        });
      }
    }

    // For each Map state, add synthetic steps to represent the nested workflow
    mapStates.forEach((mapState) => {
      // Find the index of the Map state
      const mapStateIndex = processedSteps.findIndex((step) => step.name === mapState.name);

      // Create a synthetic step to represent the Map state completion
      const syntheticStep = {
        name: `${mapState.name} (Completed)`,
        type: 'MapComplete',
        status: mapState.status,
        startDate: mapState.startDate,
        stopDate: mapState.stopDate,
        input: null,
        output: null,
        error: null,
        isSynthetic: true,
      };

      // Insert the synthetic step after the Map state
      if (mapStateIndex > -1 && mapStateIndex < processedSteps.length) {
        processedSteps.splice(mapStateIndex + 1, 0, syntheticStep);
      }
    });

    // Add synthetic steps for the nested workflow in the Map state
    const finalSteps = [];

    processedSteps.forEach((step) => {
      // Add the step to the processed steps
      finalSteps.push(step);

      // If this is a Map state, add synthetic steps for the nested workflow
      if (step.name === 'ProcessSections') {
        // Add synthetic steps for the nested workflow
        finalSteps.push({
          name: 'ExtractionStep (Iterator)',
          type: 'Task',
          status: step.status,
          startDate: step.startDate,
          stopDate: step.stopDate,
          input: null,
          output: null,
          error: null,
          isSynthetic: true,
          isNested: true,
        });

        finalSteps.push({
          name: 'AssessmentChoice (Iterator)',
          type: 'Choice',
          status: step.status,
          startDate: step.startDate,
          stopDate: step.stopDate,
          input: null,
          output: null,
          error: null,
          isSynthetic: true,
          isNested: true,
        });

        finalSteps.push({
          name: 'AssessmentStep (Iterator)',
          type: 'Task',
          status: step.status,
          startDate: step.startDate,
          stopDate: step.stopDate,
          input: null,
          output: null,
          error: null,
          isSynthetic: true,
          isNested: true,
        });

        finalSteps.push({
          name: 'SectionComplete (Iterator)',
          type: 'Pass',
          status: step.status,
          startDate: step.startDate,
          stopDate: step.stopDate,
          input: null,
          output: null,
          error: null,
          isSynthetic: true,
          isNested: true,
        });
      }
    });

    // Sort steps by start date to ensure correct order
    return finalSteps.sort((a, b) => {
      if (!a.startDate) return 1;
      if (!b.startDate) return -1;
      return new Date(a.startDate) - new Date(b.startDate);
    });
  };

  const fetchStepFunctionExecution = async () => {
    if (!executionArn || !visible) return;

    setLoading(true);
    setError(null);

    try {
      const result = await API.graphql(graphqlOperation(getStepFunctionExecution, { executionArn }));
      setData(result.data);
      setLastRefreshTime(new Date());
      logger.debug('Step Functions execution data:', result.data);

      // Process the steps to enhance Map state visualization
      if (result.data?.getStepFunctionExecution?.steps) {
        const processedSteps = enhanceStepFunctionSteps(result.data.getStepFunctionExecution.steps);
        setEnhancedSteps(processedSteps);
      }
    } catch (err) {
      logger.error('Error fetching Step Functions execution:', err);
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  // Set up auto-refresh functionality
  const setupAutoRefresh = () => {
    if (autoRefreshEnabled) {
      // Clear any existing interval
      if (autoRefreshIntervalRef.current) {
        clearInterval(autoRefreshIntervalRef.current);
      }

      // Set up new interval
      autoRefreshIntervalRef.current = setInterval(() => {
        logger.debug('Auto-refreshing Step Functions execution data');
        fetchStepFunctionExecution();
      }, AUTO_REFRESH_INTERVAL);

      logger.info('Auto-refresh enabled for execution:', executionArn);
    } else if (autoRefreshIntervalRef.current) {
      // Disable auto-refresh by clearing the interval
      clearInterval(autoRefreshIntervalRef.current);
      autoRefreshIntervalRef.current = null;
      logger.info('Auto-refresh disabled for execution:', executionArn);
    }
  };

  // Toggle auto-refresh
  const toggleAutoRefresh = () => {
    const newState = !autoRefreshEnabled;
    setAutoRefreshEnabled(newState);
  };

  // Helper function to get status indicator
  const getStatusIndicator = () => {
    if (autoRefreshEnabled) {
      return (
        <Box variant="small" color="text-status-success">
          🔄 Auto-Refresh On
        </Box>
      );
    }
    return (
      <Box variant="small" color="text-status-inactive">
        ⏸️ Auto-Refresh Off
      </Box>
    );
  };

  // Initial fetch and auto-refresh setup
  useEffect(() => {
    if (visible && executionArn) {
      fetchStepFunctionExecution();
      setupAutoRefresh();
    }

    return () => {
      // Clean up interval on unmount
      if (autoRefreshIntervalRef.current) {
        clearInterval(autoRefreshIntervalRef.current);
        autoRefreshIntervalRef.current = null;
      }
    };
  }, [executionArn, visible, autoRefreshEnabled]);

  // Update auto-refresh when the toggle changes
  useEffect(() => {
    setupAutoRefresh();
  }, [autoRefreshEnabled]);

  // Disable auto-refresh when execution completes
  useEffect(() => {
    const execution = data?.getStepFunctionExecution;
    if (
      execution &&
      (execution.status === 'SUCCEEDED' || execution.status === 'FAILED' || execution.status === 'ABORTED')
    ) {
      // If execution is complete, disable auto-refresh
      if (autoRefreshEnabled) {
        logger.info('Execution complete, disabling auto-refresh');
        setAutoRefreshEnabled(false);
      }
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
    if (stepName.toLowerCase().includes('map') || stepName.toLowerCase().includes('sections')) {
      return <FaMap size={iconProps.size} className={iconProps.className} />;
    }
    if (stepName.toLowerCase().includes('iterator')) {
      return <FaList size={iconProps.size} className={iconProps.className} />;
    }
    if (stepName.toLowerCase().includes('ocr')) {
      return <FaFileAlt size={iconProps.size} className={iconProps.className} />;
    }
    if (stepName.toLowerCase().includes('classification')) {
      return <FaRobot size={iconProps.size} className={iconProps.className} />;
    }
    if (stepName.toLowerCase().includes('extraction')) {
      return <FaRobot size={iconProps.size} className={iconProps.className} />;
    }
    if (stepName.toLowerCase().includes('assessment')) {
      return <FaEye size={iconProps.size} className={iconProps.className} />;
    }
    if (stepName.toLowerCase().includes('summarization')) {
      return <FaChartBar size={iconProps.size} className={iconProps.className} />;
    }
    if (stepName.toLowerCase().includes('workflow')) {
      return <FaCheck size={iconProps.size} className={iconProps.className} />;
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
              <Button
                variant={autoRefreshEnabled ? 'primary' : 'normal'}
                onClick={toggleAutoRefresh}
                iconName={autoRefreshEnabled ? 'refresh' : 'settings'}
              >
                {autoRefreshEnabled ? 'Disable' : 'Enable'} Auto-Refresh
              </Button>
              <Button onClick={() => fetchStepFunctionExecution()} iconName="refresh" loading={loading}>
                Refresh Now
              </Button>
              {lastRefreshTime && (
                <Box variant="small" color="text-body-secondary">
                  Last updated: {lastRefreshTime.toLocaleTimeString()}
                </Box>
              )}
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
            steps={enhancedSteps.length > 0 ? enhancedSteps : execution.steps || []}
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
            {(enhancedSteps.length > 0 ? enhancedSteps : execution.steps)?.map((step) => (
              <div
                key={`timeline-${step.name}-${step.type}-${step.status}`}
                className={`timeline-step ${step.status.toLowerCase()} ${
                  selectedStep?.name === step.name ? 'selected' : ''
                } ${step.isNested ? 'nested-step' : ''}`}
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
                  <div className="timeline-step-name">
                    {step.name}
                    {step.isSynthetic && <Badge color="blue">Synthetic</Badge>}
                    {step.isNested && <Badge color="green">Nested</Badge>}
                  </div>
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
