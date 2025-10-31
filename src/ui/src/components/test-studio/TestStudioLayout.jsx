// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState, useEffect } from 'react';
import { AppLayout, ContentLayout, Header, SpaceBetween } from '@cloudscape-design/components';
import { useLocation } from 'react-router-dom';

import Navigation from '../genaiidp-layout/navigation';
import TestSets from './TestSets';
import TestRunner from './TestRunner';
import TestResultsList from './TestResultsList';
import TestComparison from './TestComparison';
import { appLayoutLabels } from '../common/labels';
import useAppContext from '../../contexts/app';

const TestStudioLayout = () => {
  const { navigationOpen, setNavigationOpen, currentTestRunId, setCurrentTestRunId, testStarted, setTestStarted } =
    useAppContext();
  const location = useLocation();
  const [activeTabId, setActiveTabId] = useState('sets');
  const [timePeriodHours, setTimePeriodHours] = useState(2);
  const [selectedTestItems, setSelectedTestItems] = useState([]);

  // Handle URL tab parameter
  useEffect(() => {
    const urlParams = new URLSearchParams(location.search);
    const tab = urlParams.get('tab');
    if (tab && ['sets', 'runner', 'results', 'comparison'].includes(tab)) {
      setActiveTabId(tab);
    }
  }, [location.search]);

  const handleTestStart = (testRunId) => {
    setCurrentTestRunId(testRunId);
    setTestStarted(true);
  };

  const handleTestComplete = () => {
    setTestStarted(false);
    setCurrentTestRunId(null);
  };

  const renderContent = () => {
    switch (activeTabId) {
      case 'sets':
        return <TestSets />;
      case 'runner':
        return (
          <TestRunner
            onTestStart={handleTestStart}
            onTestComplete={handleTestComplete}
            currentTestRunId={currentTestRunId}
            testStarted={testStarted}
          />
        );
      case 'results':
        return (
          <TestResultsList
            timePeriodHours={timePeriodHours}
            setTimePeriodHours={setTimePeriodHours}
            selectedItems={selectedTestItems}
            setSelectedItems={setSelectedTestItems}
          />
        );
      case 'comparison': {
        const urlParams = new URLSearchParams(location.search);
        const testIds = urlParams.get('testIds');
        const testRunIds = testIds ? testIds.split(',') : [];
        return <TestComparison preSelectedTestRunIds={testRunIds} />;
      }
      default:
        return <TestSets />;
    }
  };

  return (
    <AppLayout
      ariaLabels={appLayoutLabels}
      navigation={<Navigation />}
      navigationOpen={navigationOpen}
      onNavigationChange={({ detail }) => setNavigationOpen(detail.open)}
      content={
        <ContentLayout
          header={
            <Header variant="h1" description="Run tests, view results, and compare test outcomes">
              Test Studio
            </Header>
          }
        >
          <SpaceBetween size="l">{renderContent()}</SpaceBetween>
        </ContentLayout>
      }
    />
  );
};

export default TestStudioLayout;
