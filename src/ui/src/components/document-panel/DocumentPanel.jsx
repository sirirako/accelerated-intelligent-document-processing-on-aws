// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

/* eslint-disable react/prop-types */
import React, { useState, useEffect } from 'react';
import {
  Box,
  ColumnLayout,
  Container,
  SpaceBetween,
  Link,
  Button,
  Header,
  Table,
  ExpandableSection,
  StatusIndicator,
} from '@awsui/components-react';
import { Logger } from 'aws-amplify';
import './DocumentPanel.css';
import DocumentViewers from '../document-viewers/DocumentViewers';
import SectionsPanel from '../sections-panel';
import PagesPanel from '../pages-panel';
import ChatPanel from '../chat-panel';
import useConfiguration from '../../hooks/use-configuration';
import { getSectionConfidenceAlerts, getDocumentConfidenceAlertCount } from '../common/confidence-alerts-utils';
// Uncomment the line below to enable debugging
// import { debugDocumentStructure } from '../common/debug-utils';

const logger = new Logger('DocumentPanel');

// Component to display detailed confidence alerts
const ConfidenceAlertsSection = ({ sections, mergedConfig }) => {
  // Uncomment the line below to enable debugging
  // debugDocumentStructure({ sections, mergedConfig });

  if (!sections || !Array.isArray(sections) || !mergedConfig) {
    return (
      <div>
        <StatusIndicator type="success">0 alerts</StatusIndicator>
        <Box fontSize="body-s" color="text-body-secondary" margin={{ top: 'xxxs' }}>
          No configuration available
        </Box>
      </div>
    );
  }

  const totalAlertCount = getDocumentConfidenceAlertCount(sections, mergedConfig);

  // Collect all confidence alerts from all sections for detailed display
  const allAlerts = [];
  sections.forEach((section, sectionIndex) => {
    const sectionAlerts = getSectionConfidenceAlerts(section, mergedConfig);
    sectionAlerts.forEach((alert) => {
      allAlerts.push({
        ...alert,
        sectionId: section.Id || `Section ${sectionIndex + 1}`,
        sectionClass: section.Class || 'Unknown',
      });
    });
  });

  if (totalAlertCount === 0) {
    return (
      <div>
        <StatusIndicator type="success">0 alerts</StatusIndicator>
        <Box fontSize="body-s" color="text-body-secondary" margin={{ top: 'xxxs' }}>
          All fields meet confidence requirements
        </Box>
      </div>
    );
  }

  return (
    <div>
      <StatusIndicator type="warning">
        {totalAlertCount} alert{totalAlertCount !== 1 ? 's' : ''}
      </StatusIndicator>
      <Box fontSize="body-s" color="text-body-secondary" margin={{ top: 'xxxs' }}>
        Low confidence fields detected
      </Box>
      <ExpandableSection
        headerText={`View ${totalAlertCount} field${totalAlertCount !== 1 ? 's' : ''} with low confidence`}
        variant="footer"
      >
        <SpaceBetween size="xs">
          {allAlerts.map((alert) => (
            <Box key={`${alert.sectionId}-${alert.fieldName}`} padding="xs" color="text-body-secondary">
              <Box fontSize="body-s">
                <strong>{alert.sectionId}</strong> - {alert.fieldName}
              </Box>
              <Box fontSize="body-s">
                Confidence: <span style={{ color: '#d13313' }}>{(alert.confidence * 100).toFixed(1)}%</span>
              </Box>
            </Box>
          ))}
        </SpaceBetween>
      </ExpandableSection>
    </div>
  );
};

// Helper function to parse serviceApi key into context and service
const parseServiceApiKey = (serviceApiKey) => {
  const parts = serviceApiKey.split('/');
  if (parts.length >= 3) {
    const context = parts[0];
    const serviceApi = parts.slice(1).join('/');
    return { context, serviceApi };
  }
  // Fallback for keys that don't follow the new format (less than 3 parts) - set context to ''
  return { context: '', serviceApi: serviceApiKey };
};

// Helper function to render HITL status without nested ternaries
const renderHitlStatus = (item) => {
  if (!item.hitlTriggered) {
    return 'N/A';
  }

  if (item.hitlCompleted || (item.hitlStatus && item.hitlStatus.toLowerCase() === 'completed')) {
    return 'A2I Review Completed';
  }

  if (item.hitlReviewURL) {
    return (
      <Link href={item.hitlReviewURL} external>
        A2I Review In Progress
      </Link>
    );
  }

  // If we have a status but no URL and not completed, show the status
  if (item.hitlStatus) {
    return item.hitlStatus === 'IN_PROGRESS' ? 'A2I Review In Progress' : item.hitlStatus;
  }

  return 'A2I Review Triggered';
};

// Helper function to format cost cells
const formatCostCell = (rowItem) => {
  if (rowItem.isTotal) {
    return <Box fontWeight="bold">{`${rowItem.note}: ${rowItem.cost}`}</Box>;
  }
  if (rowItem.isSubtotal) {
    return <Box fontWeight="bold" color="text-body-secondary">{`${rowItem.note}: ${rowItem.cost}`}</Box>;
  }
  return rowItem.cost;
};

// Component to display metering information in a table
const MeteringTable = ({ meteringData, preCalculatedTotals }) => {
  // Use configuration to get pricing data
  const { mergedConfig, loading } = useConfiguration();
  const [pricingData, setPricingData] = useState({});
  // We no longer use a default unit cost, showing "None" instead

  useEffect(() => {
    if (mergedConfig && mergedConfig.pricing) {
      // Convert pricing array to lookup object for easier access
      const pricingLookup = {};
      mergedConfig.pricing.forEach((item) => {
        if (item.name && item.units) {
          pricingLookup[item.name] = {};
          item.units.forEach((unitItem) => {
            if (unitItem.name && unitItem.price !== undefined) {
              // Ensure price is stored as a number
              pricingLookup[item.name][unitItem.name] = Number(unitItem.price);
            }
          });
        }
      });
      setPricingData(pricingLookup);
      logger.debug('Pricing data initialized:', pricingLookup);
    }
  }, [mergedConfig]);

  if (!meteringData) {
    return null;
  }

  if (loading) {
    return <Box>Loading pricing data...</Box>;
  }

  // Transform metering data into table rows with context parsing
  const rawTableItems = [];
  const contextTotals = {};
  let totalCost = 0;

  Object.entries(meteringData).forEach(([originalServiceApiKey, metrics]) => {
    const { context, serviceApi } = parseServiceApiKey(originalServiceApiKey);

    Object.entries(metrics).forEach(([unit, value]) => {
      const numericValue = Number(value);

      // Look up the unit price from the pricing data using the parsed serviceApi
      let unitPrice = null;
      let unitPriceDisplayValue = 'None';
      let cost = 0;
      if (pricingData[serviceApi] && pricingData[serviceApi][unit] !== undefined) {
        unitPrice = Number(pricingData[serviceApi][unit]);
        if (!Number.isNaN(unitPrice)) {
          unitPriceDisplayValue = `$${unitPrice}`;
          cost = numericValue * unitPrice;
          totalCost += cost;

          // Track context totals
          if (!contextTotals[context]) {
            contextTotals[context] = 0;
          }
          contextTotals[context] += cost;

          logger.debug(`Found price for ${serviceApi}/${unit}: ${unitPriceDisplayValue}`);
        } else {
          logger.warn(`Invalid price for ${serviceApi}/${unit}, using None`);
        }
      } else {
        logger.debug(`No price found for ${serviceApi}/${unit}, using None`);
      }

      rawTableItems.push({
        context,
        serviceApi,
        unit,
        value: String(numericValue),
        unitCost: unitPriceDisplayValue,
        cost: unitPrice !== null ? `$${cost.toFixed(4)}` : 'N/A',
        costValue: cost,
        isTotal: false,
        isSubtotal: false,
      });
    });
  });

  // Group items by context and add subtotals
  const tableItems = [];
  const contextGroups = {};

  // Group raw items by context
  rawTableItems.forEach((item) => {
    if (!contextGroups[item.context]) {
      contextGroups[item.context] = [];
    }
    contextGroups[item.context].push(item);
  });

  // Sort contexts in specific order: OCR, Classification, Extraction, Summarization
  const contextOrder = ['BDAProject', 'OCR', 'Classification', 'Extraction', 'Summarization'];
  const sortedContexts = Object.keys(contextGroups).sort((a, b) => {
    const aIndex = contextOrder.indexOf(a);
    const bIndex = contextOrder.indexOf(b);

    // If both contexts are in the predefined order, sort by their position
    if (aIndex !== -1 && bIndex !== -1) {
      return aIndex - bIndex;
    }

    // If only one context is in the predefined order, it comes first
    if (aIndex !== -1) return -1;
    if (bIndex !== -1) return 1;

    // If neither context is in the predefined order, sort alphabetically
    return a.localeCompare(b);
  });

  sortedContexts.forEach((context) => {
    // Add all items for this context
    tableItems.push(...contextGroups[context]);

    // Add subtotal row for this context
    const contextTotal = contextTotals[context] || 0;
    tableItems.push({
      context: '',
      serviceApi: '',
      unit: '',
      value: '',
      unitCost: '',
      cost: `$${contextTotal.toFixed(4)}`,
      costValue: contextTotal,
      isTotal: false,
      isSubtotal: true,
      note: `${context} Subtotal`,
    });
  });

  // Use preCalculatedTotals if provided, otherwise calculate locally
  const finalTotalCost = preCalculatedTotals ? preCalculatedTotals.totalCost : totalCost;

  // Add overall total row
  tableItems.push({
    context: '',
    serviceApi: '',
    unit: '',
    value: '',
    unitCost: '',
    cost: `$${finalTotalCost.toFixed(4)}`,
    costValue: finalTotalCost,
    isTotal: true,
    isSubtotal: false,
    note: 'Total',
  });

  return (
    <Table
      columnDefinitions={[
        {
          id: 'context',
          header: 'Context',
          cell: (rowItem) => rowItem.context,
        },
        {
          id: 'serviceApi',
          header: 'Service/Api',
          cell: (rowItem) => rowItem.serviceApi,
        },
        {
          id: 'unit',
          header: 'Unit',
          cell: (rowItem) => rowItem.unit,
        },
        {
          id: 'value',
          header: 'Value',
          cell: (rowItem) => rowItem.value,
        },
        {
          id: 'unitCost',
          header: 'Unit Cost',
          cell: (rowItem) => rowItem.unitCost,
        },
        {
          id: 'cost',
          header: 'Estimated Cost',
          cell: formatCostCell,
        },
      ]}
      items={tableItems}
      loadingText="Loading resources"
      sortingDisabled
      wrapLines
      stripedRows
      empty={
        <Box textAlign="center" color="inherit">
          <b>No metering data</b>
          <Box padding={{ bottom: 's' }} variant="p" color="inherit">
            No metering data is available for this document.
          </Box>
        </Box>
      }
    />
  );
};

// Helper function to calculate total costs using pricing data
const calculateTotalCosts = (meteringData, documentItem, pricingData) => {
  if (!meteringData) return { totalCost: 0, costPerPage: 0 };

  let totalCost = 0;

  if (pricingData) {
    Object.entries(meteringData).forEach(([originalServiceApiKey, metrics]) => {
      // Parse the serviceApi key to remove context prefix
      const { serviceApi } = parseServiceApiKey(originalServiceApiKey);

      Object.entries(metrics).forEach(([unit, value]) => {
        const numericValue = Number(value);
        if (pricingData[serviceApi] && pricingData[serviceApi][unit] !== undefined) {
          const unitPrice = Number(pricingData[serviceApi][unit]);
          if (!Number.isNaN(unitPrice)) {
            totalCost += numericValue * unitPrice;
          }
        }
      });
    });
  }

  const numPages = (documentItem && documentItem.pageCount) || 1;
  const costPerPage = totalCost / numPages;

  return { totalCost, costPerPage };
};

// Expandable section containing the metering table
const MeteringExpandableSection = ({ meteringData, documentItem }) => {
  const [expanded, setExpanded] = useState(false);
  const { mergedConfig } = useConfiguration();
  const [pricingData, setPricingData] = useState(null);

  // Convert pricing data to lookup format
  useEffect(() => {
    if (mergedConfig && mergedConfig.pricing) {
      const pricingLookup = {};
      mergedConfig.pricing.forEach((item) => {
        if (item.name && item.units) {
          pricingLookup[item.name] = {};
          item.units.forEach((unitItem) => {
            if (unitItem.name && unitItem.price !== undefined) {
              pricingLookup[item.name][unitItem.name] = Number(unitItem.price);
            }
          });
        }
      });
      setPricingData(pricingLookup);
    }
  }, [mergedConfig]);

  // Calculate the cost per page for the header
  const { totalCost, costPerPage } = calculateTotalCosts(meteringData, documentItem, pricingData);

  return (
    <Box margin={{ top: 'l', bottom: 'm' }}>
      <ExpandableSection
        variant="container"
        header={
          <Header variant="h3" description={`Estimated cost per page: $${costPerPage.toFixed(4)}`}>
            Estimated Cost
          </Header>
        }
        expanded={expanded}
        onChange={({ detail }) => setExpanded(detail.expanded)}
      >
        <div style={{ width: '100%' }}>
          <MeteringTable
            meteringData={meteringData}
            documentItem={documentItem}
            preCalculatedTotals={{ totalCost, costPerPage }}
          />
        </div>
      </ExpandableSection>
    </Box>
  );
};

const DocumentAttributes = ({ item }) => {
  return (
    <Container>
      <ColumnLayout columns={7} variant="text-grid">
        <SpaceBetween size="xs">
          <div>
            <Box margin={{ bottom: 'xxxs' }} color="text-label">
              <strong>Document ID</strong>
            </Box>
            <div>{item.objectKey}</div>
          </div>
        </SpaceBetween>

        <SpaceBetween size="xs">
          <div>
            <Box margin={{ bottom: 'xxxs' }} color="text-label">
              <strong>Status</strong>
            </Box>
            <div>{item.objectStatus}</div>
          </div>
        </SpaceBetween>

        <SpaceBetween size="xs">
          <div>
            <Box margin={{ bottom: 'xxxs' }} color="text-label">
              <strong>Submitted</strong>
            </Box>
            <div>{item.initialEventTime}</div>
          </div>
        </SpaceBetween>

        <SpaceBetween size="xs">
          <div>
            <Box margin={{ bottom: 'xxxs' }} color="text-label">
              <strong>Completed</strong>
            </Box>
            <div>{item.completionTime}</div>
          </div>
        </SpaceBetween>

        <SpaceBetween size="xs">
          <div>
            <Box margin={{ bottom: 'xxxs' }} color="text-label">
              <strong>Duration</strong>
            </Box>
            <div>{item.duration}</div>
          </div>
        </SpaceBetween>

        <SpaceBetween size="xs">
          <div>
            <Box margin={{ bottom: 'xxxs' }} color="text-label">
              <strong>Page Count</strong>
            </Box>
            <div>{item.pageCount || 0}</div>
          </div>
        </SpaceBetween>

        <SpaceBetween size="xs">
          <div>
            <Box margin={{ bottom: 'xxxs' }} color="text-label">
              <strong>Evaluation</strong>
            </Box>
            <div>{item.evaluationStatus || 'N/A'}</div>
          </div>
        </SpaceBetween>

        <SpaceBetween size="xs">
          <div>
            <Box margin={{ bottom: 'xxxs' }} color="text-label">
              <strong>HITL (A2I) Status</strong>
            </Box>
            <div>{renderHitlStatus(item)}</div>
          </div>
        </SpaceBetween>

        <SpaceBetween size="xs">
          <div>
            <Box margin={{ bottom: 'xxxs' }} color="text-label">
              <strong>Confidence Alerts</strong>
            </Box>
            <ConfidenceAlertsSection sections={item.sections} mergedConfig={item.mergedConfig} />
          </div>
        </SpaceBetween>

        <SpaceBetween size="xs">
          <div>
            <Box margin={{ bottom: 'xxxs' }} color="text-label">
              <strong>Summary</strong>
            </Box>
            <div>{item.summaryReportUri ? 'Available' : 'N/A'}</div>
          </div>
        </SpaceBetween>
      </ColumnLayout>
    </Container>
  );
};

export const DocumentPanel = ({ item, setToolsOpen, getDocumentDetailsFromIds, onDelete, onReprocess }) => {
  logger.debug('DocumentPanel item', item);

  // Fetch configuration for dynamic confidence threshold
  const { mergedConfig } = useConfiguration();

  // Create enhanced item with configuration
  const enhancedItem = {
    ...item,
    mergedConfig,
  };

  return (
    <SpaceBetween size="s">
      <Container
        header={
          <Header
            variant="h2"
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                {onReprocess && (
                  <Button iconName="arrow-right" variant="normal" onClick={onReprocess}>
                    Reprocess
                  </Button>
                )}
                {onDelete && (
                  <Button iconName="remove" variant="normal" onClick={onDelete}>
                    Delete
                  </Button>
                )}
              </SpaceBetween>
            }
          >
            Document Details
          </Header>
        }
      >
        <SpaceBetween size="l">
          <DocumentAttributes
            item={enhancedItem}
            setToolsOpen={setToolsOpen}
            getDocumentDetailsFromIds={getDocumentDetailsFromIds}
          />

          {item.metering && (
            <div>
              <MeteringExpandableSection meteringData={item.metering} documentItem={item} />
            </div>
          )}
        </SpaceBetween>
      </Container>
      <DocumentViewers
        objectKey={item.objectKey}
        evaluationReportUri={item.evaluationReportUri}
        summaryReportUri={item.summaryReportUri}
      />
      <SectionsPanel sections={item.sections} pages={item.pages} documentItem={item} mergedConfig={mergedConfig} />
      <PagesPanel pages={item.pages} />
      <ChatPanel objectKey={item.objectKey} />
    </SpaceBetween>
  );
};

export default DocumentPanel;
