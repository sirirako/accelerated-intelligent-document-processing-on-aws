// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React from 'react';
import { StatusIndicator } from '@cloudscape-design/components';

/**
 * Render HITL status consistently across all components
 * @param {Object} item - Document item with HITL fields
 * @returns {string|JSX.Element} - Rendered HITL status
 */
export const renderHitlStatus = (item) => {
  if (!item.hitlTriggered) {
    return <StatusIndicator type="stopped">N/A</StatusIndicator>;
  }

  // Check for failed status
  if (item.hitlStatus && item.hitlStatus.toLowerCase() === 'failed') {
    return <StatusIndicator type="error">Review Failed</StatusIndicator>;
  }

  // Check for skipped status
  if (item.hitlStatus && item.hitlStatus.toLowerCase() === 'skipped') {
    return <StatusIndicator type="stopped">Review Skipped</StatusIndicator>;
  }

  // Check for completed status
  if (item.hitlCompleted || (item.hitlStatus && item.hitlStatus.toLowerCase() === 'completed')) {
    return <StatusIndicator type="success">Review Completed</StatusIndicator>;
  }

  // Check for in-progress status
  if (item.hitlStatus && item.hitlStatus.toLowerCase() === 'inprogress') {
    return <StatusIndicator type="in-progress">Review In Progress</StatusIndicator>;
  }

  // HITL triggered but not completed - pending review
  return <StatusIndicator type="pending">Pending Review</StatusIndicator>;
};

export default renderHitlStatus;
