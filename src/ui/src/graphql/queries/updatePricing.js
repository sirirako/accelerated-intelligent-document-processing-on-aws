// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import gql from 'graphql-tag';

export default gql`
  mutation UpdatePricing($pricingConfig: AWSJSON!) {
    updatePricing(pricingConfig: $pricingConfig) {
      success
      message
      error {
        type
        message
      }
    }
  }
`;
