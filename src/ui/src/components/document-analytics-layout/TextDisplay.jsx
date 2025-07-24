// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React from 'react';
import PropTypes from 'prop-types';
import { Box, Container, Header } from '@awsui/components-react';

const TextDisplay = ({ textData }) => {
  if (!textData || !textData.content) {
    return null;
  }

  return (
    <Container header={<Header variant="h3">Text Response</Header>}>
      <Box padding="m">
        <Box variant="p" fontSize="body-m" padding="s" backgroundColor="background-container-content">
          {textData.content}
        </Box>
      </Box>
    </Container>
  );
};

TextDisplay.propTypes = {
  textData: PropTypes.shape({
    content: PropTypes.string.isRequired,
    responseType: PropTypes.string,
  }),
};

TextDisplay.defaultProps = {
  textData: null,
};

export default TextDisplay;
