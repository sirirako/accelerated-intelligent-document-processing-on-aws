// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React from 'react';
import PropTypes from 'prop-types';
import { Box, Container, Header } from '@awsui/components-react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Title,
  Tooltip,
  Legend,
  ArcElement,
  Filler,
} from 'chart.js';
import { Bar, Line, Pie, Doughnut } from 'react-chartjs-2';

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Title,
  Tooltip,
  Legend,
  ArcElement,
  Filler,
);

const PlotDisplay = ({ plotData }) => {
  if (!plotData) {
    return null;
  }

  const renderChart = () => {
    const { type, data, options } = plotData;

    const chartProps = {
      data,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        ...options,
      },
    };

    switch (type?.toLowerCase()) {
      case 'bar':
        return <Bar data={chartProps.data} options={chartProps.options} />;
      case 'line':
        return <Line data={chartProps.data} options={chartProps.options} />;
      case 'pie':
        return <Pie data={chartProps.data} options={chartProps.options} />;
      case 'doughnut':
        return <Doughnut data={chartProps.data} options={chartProps.options} />;
      default:
        return <Bar data={chartProps.data} options={chartProps.options} />; // Default to bar chart
    }
  };

  return (
    <Container header={<Header variant="h3">{plotData.options?.title?.text || 'Chart'}</Header>}>
      <Box padding="m">
        <div style={{ height: '400px', width: '100%' }}>{renderChart()}</div>
      </Box>
    </Container>
  );
};

PlotDisplay.propTypes = {
  plotData: PropTypes.shape({
    type: PropTypes.string,
    data: PropTypes.shape({
      datasets: PropTypes.arrayOf(PropTypes.shape({})),
      labels: PropTypes.arrayOf(PropTypes.string),
    }),
    options: PropTypes.shape({
      title: PropTypes.shape({
        text: PropTypes.string,
      }),
    }),
  }),
};

PlotDisplay.defaultProps = {
  plotData: null,
};

export default PlotDisplay;
