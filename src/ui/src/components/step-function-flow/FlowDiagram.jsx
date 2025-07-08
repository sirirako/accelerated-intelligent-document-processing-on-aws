// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import React from 'react';
import PropTypes from 'prop-types';
import { Box, Badge } from '@awsui/components-react';
import './FlowDiagram.css';

const FlowDiagram = ({ steps, onStepClick, selectedStep, getStepIcon }) => {
  if (!steps || steps.length === 0) {
    return (
      <Box textAlign="center" padding="xl">
        <Box variant="p" color="text-status-inactive">
          No steps available
        </Box>
      </Box>
    );
  }

  // Filter out nested steps for the main flow diagram
  // We'll show them in a different way
  const mainSteps = steps.filter((step) => !step.isNested);

  const getStepStatus = (step) => {
    return step.status.toLowerCase();
  };

  const getProgressPercentage = (step) => {
    if (step.status === 'SUCCEEDED') return 100;
    if (step.status === 'FAILED') return 100;
    if (step.status === 'RUNNING') return 75; // Assume 75% for running steps
    return 0;
  };

  const getProgressBarStyle = (step) => {
    const width = `${getProgressPercentage(step)}%`;

    // Add specific styling for failed steps
    if (step.status === 'FAILED') {
      return {
        width,
        backgroundColor: '#dc3545', // Red color for failed steps
      };
    }

    return { width };
  };

  // Find Map states to show their nested steps
  const mapStates = steps.filter(
    (step) => step.name === 'ProcessSections' || step.type === 'Parallel' || step.name.includes('Map'),
  );

  return (
    <div className="flow-diagram">
      <div className="flow-container">
        {mainSteps.map((step, index) => {
          // Check if this is a Map state
          const isMapState = step.name === 'ProcessSections' || step.type === 'Parallel' || step.name.includes('Map');

          // Get nested steps for this Map state
          const nestedSteps = isMapState
            ? steps.filter(
                (s) => s.isNested && s.startDate >= step.startDate && (!step.stopDate || s.stopDate <= step.stopDate),
              )
            : [];

          // Check if this is a synthetic step for the complete flow
          const isCompleteFlowStep = step.isCompleteFlow === true;

          return (
            <React.Fragment key={`main-step-${step.name}-${step.type}`}>
              {/* Step Node */}
              <div
                className={`flow-step ${getStepStatus(step)} ${selectedStep?.name === step.name ? 'selected' : ''} ${
                  step.isSynthetic ? 'synthetic-step' : ''
                } ${isCompleteFlowStep ? 'complete-flow-step' : ''}`}
                onClick={() => onStepClick(step)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    onStepClick(step);
                  }
                }}
                role="button"
                tabIndex={0}
              >
                <div className="step-icon-container">
                  {getStepIcon(step.name, step.type, step.status)}
                  {step.status === 'RUNNING' && <div className="step-pulse-ring" />}
                </div>
                <div className="step-label">
                  <div className="step-name">
                    {step.name}
                    {step.isSynthetic && !isCompleteFlowStep && <Badge color="blue">Synthetic</Badge>}
                    {isCompleteFlowStep && <Badge color="purple">Complete Flow</Badge>}
                  </div>
                  <div className={`step-status-text status-text-${step.status.toLowerCase()}`}>{step.status}</div>
                  {step.error && (
                    <div className="step-error-indicator">
                      <span className="error-icon">⚠️</span>
                    </div>
                  )}

                  {/* Show indicator if this is a Map state with nested steps */}
                  {isMapState && nestedSteps.length > 0 && (
                    <div className="nested-steps-indicator">
                      <Badge color="green">Contains {nestedSteps.length} nested steps</Badge>
                    </div>
                  )}
                </div>
                <div className="step-progress">
                  <div className={`step-progress-bar ${step.status.toLowerCase()}`} style={getProgressBarStyle(step)} />
                </div>
              </div>

              {/* Flow Arrow */}
              {index < mainSteps.length - 1 && (
                <div className="flow-arrow">
                  <div className="arrow-line">
                    <div className="arrow-animation" />
                  </div>
                  <div className="arrow-head" />
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* Map State Nested Steps */}
      {mapStates.length > 0 && (
        <div className="map-state-nested-steps">
          {mapStates.map((mapState) => {
            // Get nested steps for this Map state
            const nestedSteps = steps.filter(
              (step) =>
                step.isNested &&
                step.startDate >= mapState.startDate &&
                (!mapState.stopDate || step.stopDate <= mapState.stopDate),
            );

            if (nestedSteps.length === 0) return null;

            return (
              <div key={`map-${mapState.name}`} className="nested-steps-container">
                <div className="nested-steps-header">
                  <h4>{mapState.name} Iterator Steps</h4>
                </div>
                <div className="nested-steps-flow">
                  {nestedSteps.map((step, stepIndex) => (
                    <React.Fragment key={`nested-${step.name}-${step.type}`}>
                      {/* Nested Step Node */}
                      <div
                        className={`flow-step nested-flow-step ${getStepStatus(step)} ${
                          selectedStep?.name === step.name ? 'selected' : ''
                        }`}
                        onClick={() => onStepClick(step)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            onStepClick(step);
                          }
                        }}
                        role="button"
                        tabIndex={0}
                      >
                        <div className="step-icon-container">{getStepIcon(step.name, step.type, step.status)}</div>
                        <div className="step-label">
                          <div className="step-name">{step.name}</div>
                          <div className={`step-status-text status-text-${step.status.toLowerCase()}`}>
                            {step.status}
                          </div>
                        </div>
                      </div>

                      {/* Flow Arrow for nested steps */}
                      {stepIndex < nestedSteps.length - 1 && (
                        <div className="flow-arrow nested-arrow">
                          <div className="arrow-line">
                            <div className="arrow-animation" />
                          </div>
                          <div className="arrow-head" />
                        </div>
                      )}
                    </React.Fragment>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Complete Flow Section */}
      <div className="flow-legend">
        <div className="legend-item">
          <div className="legend-icon succeeded" />
          <span>Completed</span>
        </div>
        <div className="legend-item">
          <div className="legend-icon running" />
          <span>Running</span>
        </div>
        <div className="legend-item">
          <div className="legend-icon failed" />
          <span>Failed</span>
        </div>
        <div className="legend-item">
          <div className="legend-icon pending" />
          <span>Pending</span>
        </div>
      </div>
    </div>
  );
};

FlowDiagram.propTypes = {
  steps: PropTypes.arrayOf(
    PropTypes.shape({
      name: PropTypes.string.isRequired,
      type: PropTypes.string.isRequired,
      status: PropTypes.string.isRequired,
      startDate: PropTypes.string,
      stopDate: PropTypes.string,
      error: PropTypes.string,
      isNested: PropTypes.bool,
      isSynthetic: PropTypes.bool,
      isCompleteFlow: PropTypes.bool,
    }),
  ),
  onStepClick: PropTypes.func.isRequired,
  selectedStep: PropTypes.shape({
    name: PropTypes.string,
  }),
  getStepIcon: PropTypes.func.isRequired,
};

FlowDiagram.defaultProps = {
  steps: [],
  selectedStep: null,
};

export default FlowDiagram;
