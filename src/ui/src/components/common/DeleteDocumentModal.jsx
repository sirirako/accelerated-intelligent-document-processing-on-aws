// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React from 'react';
import PropTypes from 'prop-types';
import { Modal, Box, SpaceBetween, Button } from '@awsui/components-react';

const DeleteDocumentModal = ({ visible, onDismiss, onConfirm, selectedItems, itemType = 'document' }) => {
  const itemCount = selectedItems.length;
  const isMultiple = itemCount > 1;
  const itemTypePlural = itemType === 'document' ? 'documents' : `${itemType}s`;

  const getItemKey = (item) => item.objectKey || item.testRunId || item.id;
  const getItemName = (item) => {
    if (itemType === 'test run') {
      return item.testRunId;
    }
    return item.name || item.objectKey || item.testRunId || item.id;
  };

  return (
    <Modal
      visible={visible}
      onDismiss={onDismiss}
      header={`Delete ${isMultiple ? itemTypePlural : itemType}`}
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={onDismiss}>
              Cancel
            </Button>
            <Button variant="primary" onClick={onConfirm}>
              Delete
            </Button>
          </SpaceBetween>
        </Box>
      }
    >
      <p>
        Are you sure you want to delete {isMultiple ? `these ${itemCount} ${itemTypePlural}` : `this ${itemType}`}? This
        action cannot be undone.
      </p>
      {isMultiple && (
        <ul>
          {selectedItems.map((item) => (
            <li key={getItemKey(item)}>{getItemName(item)}</li>
          ))}
        </ul>
      )}
    </Modal>
  );
};

DeleteDocumentModal.propTypes = {
  visible: PropTypes.bool.isRequired,
  onDismiss: PropTypes.func.isRequired,
  onConfirm: PropTypes.func.isRequired,
  selectedItems: PropTypes.arrayOf(
    PropTypes.shape({
      objectKey: PropTypes.string,
      testRunId: PropTypes.string,
      name: PropTypes.string,
      id: PropTypes.string,
    }),
  ).isRequired,
  itemType: PropTypes.string,
};

DeleteDocumentModal.defaultProps = {
  itemType: 'document',
};

export default DeleteDocumentModal;
