// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React from 'react';
import { HelpPanel, Icon } from '@awsui/components-react';

const ToolsPanel = () => {
  return (
    <HelpPanel
      header={<h2>Document Analytics</h2>}
      footer={
        <div>
          <h3>
            Learn more <Icon name="external" />
          </h3>
          <ul>
            <li>
              <a href="https://gitlab.aws.dev/genaiic-reusable-assets/engagement-artifacts/genaiic-idp-accelerator/-/blob/main/README.md">
                GenAI IDP Accelerator Documentation
              </a>
            </li>
          </ul>
        </div>
      }
    >
      <div>
        <p>
          Use the Document Analytics feature to query your document processing data using natural language and receive
          interactive visualizations and insights.
        </p>
        <h3>How to use</h3>
        <ol>
          <li>Enter your query in the text box</li>
          <li>Click the Submit button</li>
          <li>Wait for the query to process</li>
          <li>View the results in the visualization area</li>
        </ol>
        <h3>Example queries</h3>
        <ul>
          <li>Show me document processing volume over time</li>
          <li>What are the most common document types?</li>
          <li>What is the average processing time per document?</li>
        </ul>
      </div>
    </HelpPanel>
  );
};

export default ToolsPanel;
