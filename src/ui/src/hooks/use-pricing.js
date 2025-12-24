// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { useState, useEffect } from 'react';
import { generateClient } from 'aws-amplify/api';
import { ConsoleLogger } from 'aws-amplify/utils';
import getPricingQuery from '../graphql/queries/getPricing';
import updatePricingMutation from '../graphql/queries/updatePricing';
import restoreDefaultPricingMutation from '../graphql/queries/restoreDefaultPricing';

const client = generateClient();
const logger = new ConsoleLogger('usePricing');

const usePricing = () => {
  const [pricing, setPricing] = useState(null);
  const [defaultPricing, setDefaultPricing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  const fetchPricing = async (silent = false) => {
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      logger.debug('Fetching pricing...');
      const result = await client.graphql({ query: getPricingQuery });
      logger.debug('API response:', result);

      const response = result.data.getPricing;

      if (!response.success) {
        const errorMsg = response.error?.message || 'Failed to load pricing';
        throw new Error(errorMsg);
      }

      // pricing comes as AWSJSON (a JSON string) - parse it
      let pricingData = response.pricing;
      if (typeof pricingData === 'string') {
        pricingData = JSON.parse(pricingData);
      }

      // defaultPricing also comes as AWSJSON - parse it
      let defaultPricingData = response.defaultPricing;
      if (typeof defaultPricingData === 'string') {
        defaultPricingData = JSON.parse(defaultPricingData);
      }

      // The new pricing data structure is { pricing: [{ name: "service/api", units: [{ name, price }] }] }
      // Just pass through the data directly - no restructuring needed
      logger.debug('Parsed pricing:', pricingData);
      logger.debug('Parsed default pricing:', defaultPricingData);
      setPricing(pricingData);
      setDefaultPricing(defaultPricingData);
    } catch (err) {
      logger.error('Error fetching pricing', err);
      setError(`Failed to load pricing: ${err.message}`);
    } finally {
      if (silent) {
        setRefreshing(false);
      } else {
        setLoading(false);
      }
    }
  };

  const updatePricing = async (newPricing) => {
    setError(null);
    try {
      logger.debug('Updating pricing with:', newPricing);

      // Send the entire pricing object as AWSJSON (stringify if not already a string)
      const pricingConfig = typeof newPricing === 'string' ? newPricing : JSON.stringify(newPricing);

      logger.debug('Sending pricingConfig:', pricingConfig);

      const result = await client.graphql({
        query: updatePricingMutation,
        variables: { pricingConfig },
      });

      const response = result.data.updatePricing;

      if (!response.success) {
        const errorMsg = response.error?.message || 'Failed to update pricing';
        throw new Error(errorMsg);
      }

      // Refetch silently to ensure backend and frontend are in sync
      await fetchPricing(true);

      return true;
    } catch (err) {
      logger.error('Error updating pricing', err);
      setError(`Failed to update pricing: ${err.message}`);
      return false;
    }
  };

  const restoreDefaultPricing = async () => {
    setError(null);
    try {
      logger.debug('Restoring default pricing...');

      const result = await client.graphql({
        query: restoreDefaultPricingMutation,
      });

      const response = result.data.restoreDefaultPricing;

      if (!response.success) {
        const errorMsg = response.error?.message || 'Failed to restore default pricing';
        throw new Error(errorMsg);
      }

      // Refetch to get the restored defaults
      await fetchPricing(true);

      return true;
    } catch (err) {
      logger.error('Error restoring default pricing', err);
      setError(`Failed to restore default pricing: ${err.message}`);
      return false;
    }
  };

  useEffect(() => {
    fetchPricing();
  }, []);

  return {
    pricing,
    defaultPricing,
    loading,
    refreshing,
    error,
    fetchPricing,
    updatePricing,
    restoreDefaultPricing,
  };
};

export default usePricing;
