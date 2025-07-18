// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { FormField, Input, Button, Grid, Box } from '@awsui/components-react';

const AnalyticsQueryInput = ({ onSubmit, isSubmitting }) => {
  const [query, setQuery] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (query.trim() && !isSubmitting) {
      onSubmit(query);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <Grid gridDefinition={[{ colspan: { default: 12, xxs: 9 } }, { colspan: { default: 12, xxs: 3 } }]}>
        <FormField label="Enter your analytics query">
          <Input
            placeholder="e.g., Show me document processing volume over time"
            value={query}
            onChange={({ detail }) => setQuery(detail.value)}
            disabled={isSubmitting}
          />
        </FormField>
        <Box padding={{ top: 'xl' }}>
          {' '}
          {/* Add top padding to align with input box */}
          <Button variant="primary" type="submit" disabled={!query.trim() || isSubmitting} fullWidth>
            {isSubmitting ? 'Submitting...' : 'Submit query'}
          </Button>
        </Box>
      </Grid>
    </form>
  );
};

AnalyticsQueryInput.propTypes = {
  onSubmit: PropTypes.func.isRequired,
  isSubmitting: PropTypes.bool,
};

AnalyticsQueryInput.defaultProps = {
  isSubmitting: false,
};

export default AnalyticsQueryInput;
