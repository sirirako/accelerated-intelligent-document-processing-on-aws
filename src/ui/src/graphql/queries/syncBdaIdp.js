// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import gql from 'graphql-tag';

export default gql`
  mutation SyncBdaIdp($versionName: String) {
    syncBdaIdp(versionName: $versionName) {
      success
      message
      processedClasses
      error {
        type
        message
      }
    }
  }
`;
