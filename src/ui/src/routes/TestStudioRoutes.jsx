// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React from 'react';
import { Route, Switch, useRouteMatch } from 'react-router-dom';
import { Logger } from 'aws-amplify';

import TestStudioLayout from '../components/test-studio-layout/TestStudioLayout';
import GenAIIDPTopNavigation from '../components/genai-idp-top-navigation';

const logger = new Logger('TestStudioRoutes');

const TestStudioRoutes = () => {
  const { path } = useRouteMatch();
  logger.info('path ', path);

  return (
    <Switch>
      <Route path={path}>
        <div>
          <GenAIIDPTopNavigation />
          <TestStudioLayout />
        </div>
      </Route>
    </Switch>
  );
};

export default TestStudioRoutes;
