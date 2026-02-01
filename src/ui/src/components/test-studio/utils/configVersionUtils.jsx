// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React from 'react';
import { Link, Box } from '@cloudscape-design/components';

/**
 * Format config version with clickable link and truncated description
 * @param {string} configVersion - The version ID (e.g., 'v21')
 * @param {Array} versions - Array of version objects with versionId and description
 * @param {number} maxDescLength - Maximum description length before truncation (default: 10)
 * @returns {JSX.Element|string} Formatted config version with link or 'N/A'
 */
export const formatConfigVersionLink = (configVersion, versions, maxDescLength = 10) => {
  if (!configVersion) return 'N/A';

  const versionId = configVersion;
  const versionFromList = versions.find((v) => v.versionId === versionId);

  if (versionFromList?.description) {
    const truncatedDesc =
      versionFromList.description.length > maxDescLength
        ? `${versionFromList.description.substring(0, maxDescLength)}...`
        : versionFromList.description;
    return (
      <Link
        href={`#/documents/config?version=${versionId}`}
        title={`${versionId} (${versionFromList.description}) - Click to view configuration`}
      >
        {`${versionId} (${truncatedDesc})`}
      </Link>
    );
  }

  return <Link href={`#/documents/config?version=${versionId}`}>{versionId}</Link>;
};

/**
 * Format config version for text export (CSV, etc.) with full description
 * @param {string} configVersion - The version ID (e.g., 'v21')
 * @param {Array} versions - Array of version objects with versionId and description
 * @returns {string} Formatted config version text or 'N/A'
 */
export const formatConfigVersionText = (configVersion, versions) => {
  if (!configVersion) return 'N/A';

  const versionId = configVersion;
  const versionFromList = versions.find((v) => v.versionId === versionId);

  return versionFromList?.description ? `${versionId} (${versionFromList.description})` : versionId;
};
