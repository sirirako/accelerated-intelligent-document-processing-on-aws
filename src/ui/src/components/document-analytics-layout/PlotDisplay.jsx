// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Box, Container, Header, Select, SpaceBetween } from '@awsui/components-react';
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
  // Chart type options for the dropdown
  const chartTypeOptions = [
    { label: 'Bar Chart', value: 'bar' },
    { label: 'Line Chart', value: 'line' },
    { label: 'Pie Chart', value: 'pie' },
    { label: 'Doughnut Chart', value: 'doughnut' },
  ];

  // State to track the current chart type, initialized with the type from JSON
  const [currentChartType, setCurrentChartType] = useState(null);
  const [selectedOption, setSelectedOption] = useState(null);

  // Initialize chart type when plotData changes
  useEffect(() => {
    if (plotData?.type) {
      const initialType = plotData.type.toLowerCase();
      setCurrentChartType(initialType);

      // Find the matching option for the Select component
      const matchingOption = chartTypeOptions.find((option) => option.value === initialType);
      setSelectedOption(matchingOption || chartTypeOptions[0]);
    }
  }, [plotData]);

  if (!plotData) {
    return null;
  }

  // Handle chart type change from dropdown
  const handleChartTypeChange = ({ detail }) => {
    setCurrentChartType(detail.selectedOption.value);
    setSelectedOption(detail.selectedOption);
  };

  // Prepare chart data with potential modifications for different chart types
  const prepareChartData = (originalData, chartType) => {
    const { datasets, labels } = originalData;

    // For pie and doughnut charts, we might need to aggregate data if there are multiple datasets
    if ((chartType === 'pie' || chartType === 'doughnut') && datasets.length > 1) {
      // Aggregate all datasets into a single dataset for pie/doughnut charts
      const aggregatedData = labels.map((_, index) =>
        datasets.reduce((sum, dataset) => sum + (dataset.data[index] || 0), 0),
      );

      return {
        labels,
        datasets: [
          {
            data: aggregatedData,
            backgroundColor: [
              'rgba(255, 99, 132, 0.8)',
              'rgba(54, 162, 235, 0.8)',
              'rgba(255, 205, 86, 0.8)',
              'rgba(75, 192, 192, 0.8)',
              'rgba(153, 102, 255, 0.8)',
              'rgba(255, 159, 64, 0.8)',
            ],
            borderColor: [
              'rgba(255, 99, 132, 1)',
              'rgba(54, 162, 235, 1)',
              'rgba(255, 205, 86, 1)',
              'rgba(75, 192, 192, 1)',
              'rgba(153, 102, 255, 1)',
              'rgba(255, 159, 64, 1)',
            ],
            borderWidth: 1,
            label: datasets.map((d) => d.label).join(' + ') || 'Combined Data',
          },
        ],
      };
    }

    return originalData;
  };

  // Prepare chart options with potential modifications for different chart types
  const prepareChartOptions = (originalOptions, chartType) => {
    const baseOptions = {
      responsive: true,
      maintainAspectRatio: false,
      ...originalOptions,
    };

    // For pie and doughnut charts, we typically don't need scales
    if (chartType === 'pie' || chartType === 'doughnut') {
      const { scales, ...optionsWithoutScales } = baseOptions;
      return {
        ...optionsWithoutScales,
        plugins: {
          ...baseOptions.plugins,
          legend: {
            position: 'right',
            ...baseOptions.plugins?.legend,
          },
        },
      };
    }

    return baseOptions;
  };

  const renderChart = () => {
    if (!currentChartType) return null;

    const { data, options } = plotData;
    const chartData = prepareChartData(data, currentChartType);
    const chartOptions = prepareChartOptions(options, currentChartType);

    const chartProps = {
      data: chartData,
      options: chartOptions,
    };

    switch (currentChartType) {
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
        <SpaceBetween direction="vertical" size="m">
          {/* Chart type selector */}
          <Box float="right">
            <Select
              selectedOption={selectedOption}
              onChange={handleChartTypeChange}
              options={chartTypeOptions}
              placeholder="Select chart type"
              expandToViewport
            />
          </Box>

          {/* Chart display */}
          <div style={{ height: '400px', width: '100%' }}>{renderChart()}</div>
        </SpaceBetween>
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
