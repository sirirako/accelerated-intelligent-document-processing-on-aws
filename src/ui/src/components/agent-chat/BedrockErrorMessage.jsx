// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { Alert, Box, Button, ExpandableSection, SpaceBetween, StatusIndicator } from '@cloudscape-design/components';

const BedrockErrorMessage = ({ errorInfo, onRetry, className = '' }) => {
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false);

  // Map error types to appropriate alert types and status indicators
  const getErrorDisplayInfo = (errorType) => {
    switch (errorType) {
      case 'service_unavailable':
        return {
          alertType: 'warning',
          statusType: 'warning',
          icon: 'warning',
          title: 'Service Temporarily Unavailable',
        };
      case 'rate_limit':
      case 'model_throttling':
      case 'too_many_requests':
        return {
          alertType: 'warning',
          statusType: 'warning',
          icon: 'warning',
          title: 'Rate Limit Exceeded',
        };
      case 'quota_exceeded':
        return {
          alertType: 'error',
          statusType: 'error',
          icon: 'error',
          title: 'Usage Quota Exceeded',
        };
      case 'validation_error':
        return {
          alertType: 'error',
          statusType: 'error',
          icon: 'error',
          title: 'Request Validation Error',
        };
      case 'access_denied':
        return {
          alertType: 'error',
          statusType: 'error',
          icon: 'error',
          title: 'Access Denied',
        };
      case 'model_unavailable':
        return {
          alertType: 'warning',
          statusType: 'warning',
          icon: 'warning',
          title: 'AI Model Unavailable',
        };
      case 'timeout':
        return {
          alertType: 'warning',
          statusType: 'warning',
          icon: 'warning',
          title: 'Request Timeout',
        };
      default:
        return {
          alertType: 'error',
          statusType: 'error',
          icon: 'error',
          title: 'Service Error',
        };
    }
  };

  const displayInfo = getErrorDisplayInfo(errorInfo.errorType);

  // Format retry delay for display
  const formatRetryDelay = (seconds) => {
    if (!seconds) return null;

    if (seconds < 60) {
      return `${seconds} seconds`;
    } else if (seconds < 3600) {
      const minutes = Math.floor(seconds / 60);
      return `${minutes} minute${minutes > 1 ? 's' : ''}`;
    } else {
      const hours = Math.floor(seconds / 3600);
      return `${hours} hour${hours > 1 ? 's' : ''}`;
    }
  };

  const retryDelayText = formatRetryDelay(errorInfo.retryDelaySeconds);

  return (
    <div className={`bedrock-error-message ${className}`}>
      <Alert
        type={displayInfo.alertType}
        header={
          <SpaceBetween direction="horizontal" size="xs" alignItems="center">
            <StatusIndicator type={displayInfo.statusType}>{displayInfo.title}</StatusIndicator>
            {errorInfo.retryAttempts > 0 && (
              <Box fontSize="body-s" color="text-status-inactive">
                (After {errorInfo.retryAttempts} retry attempt{errorInfo.retryAttempts > 1 ? 's' : ''})
              </Box>
            )}
          </SpaceBetween>
        }
        action={
          errorInfo.retryRecommended &&
          onRetry && (
            <Button variant="primary" onClick={onRetry} iconName="refresh">
              Try Again
              {retryDelayText && ` (wait ${retryDelayText})`}
            </Button>
          )
        }
      >
        <SpaceBetween size="m">
          {/* Main error message */}
          <Box>{errorInfo.message}</Box>

          {/* Action recommendations */}
          {errorInfo.actionRecommendations && errorInfo.actionRecommendations.length > 0 && (
            <Box>
              <Box fontWeight="bold" fontSize="body-s" color="text-label">
                What you can do:
              </Box>
              <ul style={{ margin: '8px 0', paddingLeft: '20px' }}>
                {errorInfo.actionRecommendations.map((recommendation) => (
                  <li key={recommendation} style={{ marginBottom: '4px' }}>
                    <Box fontSize="body-s">{recommendation}</Box>
                  </li>
                ))}
              </ul>
            </Box>
          )}

          {/* Retry information */}
          {errorInfo.retryRecommended && retryDelayText && (
            <Box>
              <StatusIndicator type="info">Recommended wait time: {retryDelayText}</StatusIndicator>
            </Box>
          )}

          {/* Technical details (expandable) */}
          {errorInfo.technicalDetails && (
            <ExpandableSection
              headerText="Technical Details"
              variant="footer"
              expanded={showTechnicalDetails}
              onChange={({ detail }) => setShowTechnicalDetails(detail.expanded)}
            >
              <Box padding="s" backgroundColor="background-container-content" fontSize="body-s" fontFamily="monospace">
                <Box color="text-body-secondary">Error Type: {errorInfo.errorType}</Box>
                <Box color="text-body-secondary" margin={{ top: 'xs' }}>
                  Details: {errorInfo.technicalDetails}
                </Box>
                {errorInfo.retryAttempts > 0 && (
                  <Box color="text-body-secondary" margin={{ top: 'xs' }}>
                    Retry Attempts: {errorInfo.retryAttempts}
                  </Box>
                )}
              </Box>
            </ExpandableSection>
          )}
        </SpaceBetween>
      </Alert>
    </div>
  );
};

BedrockErrorMessage.propTypes = {
  errorInfo: PropTypes.shape({
    errorType: PropTypes.string.isRequired,
    message: PropTypes.string.isRequired,
    technicalDetails: PropTypes.string,
    retryRecommended: PropTypes.bool,
    retryDelaySeconds: PropTypes.number,
    actionRecommendations: PropTypes.arrayOf(PropTypes.string),
    isTransient: PropTypes.bool,
    retryAttempts: PropTypes.number,
  }).isRequired,
  onRetry: PropTypes.func,
  className: PropTypes.string,
};

export default BedrockErrorMessage;
