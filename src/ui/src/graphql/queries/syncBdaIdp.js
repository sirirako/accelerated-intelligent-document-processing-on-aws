// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import gql from 'graphql-tag';

export default gql`
  mutation SyncBdaIdp($direction: String) {
    syncBdaIdp(direction: $direction) {
      success
      message
      processedClasses
      direction
      error {
        type
        message
      }
    }
  }
`;
