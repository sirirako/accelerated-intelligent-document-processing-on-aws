// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Container, Header, SpaceBetween, Table, Box } from '@awsui/components-react';
import { API, graphqlOperation } from 'aws-amplify';
import COMPARE_TEST_RUNS from '../../graphql/queries/compareTestRuns';

const TestComparison = ({ preSelectedTestRunIds = [] }) => {
  const [comparisonData, setComparisonData] = useState(null);
  const [comparing, setComparing] = useState(false);

  useEffect(() => {
    const fetchComparison = async () => {
      if (preSelectedTestRunIds.length >= 2) {
        setComparing(true);
        try {
          const result = await API.graphql(
            graphqlOperation(COMPARE_TEST_RUNS, {
              testRunIds: preSelectedTestRunIds,
            }),
          );
          setComparisonData(result.data.compareTestRuns);
        } catch (error) {
          const errorMessage =
            error.errors?.length > 0 ? error.errors.map((e) => e.message).join('; ') : 'Error comparing test runs';
          console.error('Error comparing test runs:', errorMessage);
        } finally {
          setComparing(false);
        }
      }
    };

    fetchComparison();
  }, [preSelectedTestRunIds]);

  if (comparing) {
    return <Box>Loading comparison...</Box>;
  }

  if (!comparisonData) {
    return <Box>No comparison data available</Box>;
  }

  return (
    <Container header={<Header variant="h2">Compare Test Runs</Header>}>
      <SpaceBetween direction="vertical" size="l">
        {/* Comparison Results */}
        {comparisonData && (
          <SpaceBetween direction="vertical" size="l">
            {/* Metrics Comparison */}
            <Box>
              <Header variant="h3">Performance Comparison</Header>
              <Table
                items={comparisonData.metrics}
                columnDefinitions={[
                  { id: 'metric', header: 'Metric', cell: (item) => item.metric },
                  ...preSelectedTestRunIds.map((runId) => ({
                    id: runId,
                    header: runId,
                    cell: (item) => item.values[runId] || 'N/A',
                  })),
                ]}
              />
            </Box>

            {/* Config Differences */}
            <Box>
              <Header variant="h3">Configuration Differences</Header>
              <Table
                items={comparisonData.configDifferences}
                columnDefinitions={[
                  { id: 'setting', header: 'Setting', cell: (item) => item.setting },
                  ...preSelectedTestRunIds.map((runId) => ({
                    id: runId,
                    header: runId,
                    cell: (item) => item.values[runId] || 'N/A',
                  })),
                ]}
              />
            </Box>

            {/* Cost Analysis */}
            <Box>
              <Header variant="h3">Cost Analysis</Header>
              <Table
                items={comparisonData.costs}
                columnDefinitions={[
                  { id: 'component', header: 'Cost Component', cell: (item) => item.component },
                  ...preSelectedTestRunIds.map((runId) => ({
                    id: runId,
                    header: runId,
                    cell: (item) => `$${item.values[runId] || '0'}`,
                  })),
                ]}
              />
            </Box>
          </SpaceBetween>
        )}
      </SpaceBetween>
    </Container>
  );
};

TestComparison.propTypes = {
  preSelectedTestRunIds: PropTypes.arrayOf(PropTypes.string),
};

TestComparison.defaultProps = {
  preSelectedTestRunIds: [],
};

export default TestComparison;
