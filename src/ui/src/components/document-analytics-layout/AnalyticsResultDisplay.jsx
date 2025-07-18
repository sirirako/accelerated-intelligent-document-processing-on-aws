// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React from 'react';
import PropTypes from 'prop-types';
import { Box, Container, Header, SpaceBetween, Alert } from '@awsui/components-react';

const AnalyticsResultDisplay = ({ result, query }) => {
  if (!result) {
    return null;
  }

  const { responseType, content, plotData, tableData, dashboardData } = result;

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
            // Use a more stable key if available in the plot data
            const plotKey = plot.id || plot.title || `plot-${i}`;
            return <pre key={plotKey}>{JSON.stringify(plot, null, 2)}</pre>;
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
            // Use a more stable key if available in the table data
            const tableKey = table.id || table.title || `table-${i}`;
            return <pre key={tableKey}>{JSON.stringify(table, null, 2)}</pre>;
          })}
        </Box>
      );
    }
    return null;
  };

  const renderDashboardData = () => {
    if (dashboardData) {
      return (
        <Box padding="m">
          <Header variant="h3">Dashboard Data</Header>
          {/* For now, just display the JSON. In the future, this would be a dashboard component */}
          <pre>{JSON.stringify(dashboardData, null, 2)}</pre>
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
    plotData: PropTypes.arrayOf(PropTypes.shape({})),
    tableData: PropTypes.arrayOf(PropTypes.shape({})),
    dashboardData: PropTypes.shape({}),
  }),
  query: PropTypes.string,
};

AnalyticsResultDisplay.defaultProps = {
  result: null,
  query: '',
};

export default AnalyticsResultDisplay;
