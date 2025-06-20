// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { HttpRequest } from '@aws-sdk/protocol-http';
import { S3RequestPresigner } from '@aws-sdk/s3-request-presigner';
import { parseUrl } from '@aws-sdk/url-parser';
import { Sha256 } from '@aws-crypto/sha256-browser';
import { formatUrl } from '@aws-sdk/util-format-url';
import { Logger } from 'aws-amplify';

const logger = new Logger('generate-s3-presigned-url');

const parseS3Url = (s3Url) => {
  if (!s3Url || typeof s3Url !== 'string' || !s3Url.startsWith('s3://')) {
    return null;
  }

  const withoutProtocol = s3Url.slice(5); // Remove 's3://'
  const firstSlashIndex = withoutProtocol.indexOf('/');

  if (firstSlashIndex === -1) {
    return {
      bucket: withoutProtocol,
      key: '',
    };
  }

  const bucket = withoutProtocol.slice(0, firstSlashIndex);
  const key = withoutProtocol.slice(firstSlashIndex + 1);

  if (!bucket) {
    return null;
  }

  return { bucket, key };
};

const generateS3PresignedUrl = async (url, credentials) => {
  // If it's already a special URL (like detailType), return as is
  if (url.includes('detailType')) {
    return url;
  }

  try {
    logger.debug('Generating presigned URL for:', url);

    let bucketName;
    let key;

    if (url.startsWith('s3://')) {
      const parsed = parseS3Url(url);

      if (!parsed) throw new Error('Invalid S3 URL format');

      bucketName = parsed.bucket;
      key = parsed.key;
    } else {
      // Handle existing HTTPS URLs
      const urlObj = new URL(url);
      [bucketName] = urlObj.hostname.split('.');
      key = urlObj.pathname.substring(1); // Remove leading slash
    }

    // Extract region from env
    const region = process.env.REACT_APP_AWS_REGION;

    // Construct the canonical S3 URL
    const newUrl = `https://${bucketName}.s3.${region}.amazonaws.com/${key}`;

    // Parse the URL for the presigner
    const s3ObjectUrl = parseUrl(newUrl);
    logger.debug('Canonical URL:', newUrl);

    // Create presigner instance
    const presigner = new S3RequestPresigner({
      credentials,
      region,
      sha256: Sha256,
    });

    // Generate presigned URL
    const presignedResponse = await presigner.presign(new HttpRequest(s3ObjectUrl));
    const presignedUrl = formatUrl(presignedResponse);

    return presignedUrl;
  } catch (error) {
    throw new Error(`Failed to generate presigned URL: ${error.message}`);
  }
};

export default generateS3PresignedUrl;
