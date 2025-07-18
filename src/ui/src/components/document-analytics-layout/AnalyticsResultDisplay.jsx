// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React from 'react';
import PropTypes from 'prop-types';
import { Box, Container, Header, SpaceBetween, Alert } from '@awsui/components-react';
import { Logger } from 'aws-amplify';

const logger = new Logger('AnalyticsResultDisplay');

const AnalyticsResultDisplay = ({ result, query }) => {
  if (!result) {
    return null;
  }

  const { responseType, content, plotData, tableData, dashboardData } = result;

  // Helper function to safely parse JSON strings
  const safeJsonParse = (jsonString, fallback = null) => {
    if (typeof jsonString !== 'string') {
      return jsonString; // Already an object, return as is
    }

    try {
      return JSON.parse(jsonString);
    } catch (error) {
      logger.warn('Failed to parse JSON string:', error);
      return fallback;
    }
  };

  const renderContent = () => {
    if (content) {
      return (
        <Box padding="m">
          <pre>{content}</pre>
        </Box>
      );
    }
    return null;
  };

  const renderPlotData = () => {
    if (plotData && plotData.length > 0) {
      return (
        <Box padding="m">
          <Header variant="h3">Plot Data</Header>
          {plotData.map((plot, i) => {
            // Parse the plot data if it's a string
            const parsedPlot = safeJsonParse(plot, { error: 'Invalid plot data format' });

            // Use a more stable key if available in the plot data
            const plotKey = parsedPlot.id || parsedPlot.title || `plot-${i}`;

            return <pre key={plotKey}>{JSON.stringify(parsedPlot, null, 2)}</pre>;
          })}
        </Box>
      );
    }
    return null;
  };

  const renderTableData = () => {
    if (tableData && tableData.length > 0) {
      return (
        <Box padding="m">
          <Header variant="h3">Table Data</Header>
          {tableData.map((table, i) => {
            // Parse the table data if it's a string
            const parsedTable = safeJsonParse(table, { error: 'Invalid table data format' });

            // Use a more stable key if available in the table data
            const tableKey = parsedTable.id || parsedTable.title || `table-${i}`;

            return <pre key={tableKey}>{JSON.stringify(parsedTable, null, 2)}</pre>;
          })}
        </Box>
      );
    }
    return null;
  };

  const renderDashboardData = () => {
    if (dashboardData) {
      // Parse the dashboard data if it's a string
      const parsedDashboard = safeJsonParse(dashboardData, { error: 'Invalid dashboard data format' });

      return (
        <Box padding="m">
          <Header variant="h3">Dashboard Data</Header>
          {/* For now, just display the JSON. In the future, this would be a dashboard component */}
          <pre>{JSON.stringify(parsedDashboard, null, 2)}</pre>
        </Box>
      );
    }
    return null;
  };

  return (
    <Container
      header={
        <Header variant="h2">
          Results for: <i>{query}</i>
        </Header>
      }
    >
      <SpaceBetween size="m">
        <Alert type="info">
          Response type: <strong>{responseType}</strong>
        </Alert>
        {renderContent()}
        {renderPlotData()}
        {renderTableData()}
        {renderDashboardData()}
      </SpaceBetween>
    </Container>
  );
};

AnalyticsResultDisplay.propTypes = {
  result: PropTypes.shape({
    responseType: PropTypes.string,
    content: PropTypes.string,
    plotData: PropTypes.arrayOf(
      PropTypes.oneOfType([
        PropTypes.string, // For JSON strings
        PropTypes.object, // For parsed objects
      ]),
    ),
    tableData: PropTypes.arrayOf(
      PropTypes.oneOfType([
        PropTypes.string, // For JSON strings
        PropTypes.object, // For parsed objects
      ]),
    ),
    dashboardData: PropTypes.oneOfType([
      PropTypes.string, // For JSON strings
      PropTypes.object, // For parsed objects
    ]),
  }),
  query: PropTypes.string,
};

AnalyticsResultDisplay.defaultProps = {
  result: null,
  query: '',
};

export default AnalyticsResultDisplay;
