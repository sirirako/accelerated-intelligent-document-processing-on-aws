import React from 'react';
import PropTypes from 'prop-types';
import { Header, FormField, Input, Checkbox } from '@cloudscape-design/components';

const ArrayConstraints = ({ attribute, onUpdate }) => {
  if (attribute.type !== 'array') return null;

  return (
    <>
      <Header variant="h4">Array Constraints</Header>

      <FormField label="Min Items" description="Minimum number of items in array">
        <Input
          type="number"
          value={attribute.minItems?.toString() || ''}
          onChange={({ detail }) => onUpdate({ minItems: detail.value ? parseInt(detail.value, 10) : undefined })}
          placeholder="e.g., 1 for non-empty"
        />
      </FormField>

      <FormField label="Max Items" description="Maximum number of items in array">
        <Input
          type="number"
          value={attribute.maxItems?.toString() || ''}
          onChange={({ detail }) => onUpdate({ maxItems: detail.value ? parseInt(detail.value, 10) : undefined })}
          placeholder="e.g., 10"
        />
      </FormField>

      <Checkbox
        checked={attribute.uniqueItems || false}
        onChange={({ detail }) => onUpdate({ uniqueItems: detail.checked || undefined })}
      >
        Unique Items (array elements must be unique)
      </Checkbox>

      <FormField 
        label="Min Contains" 
        description="Minimum number of items that must match the 'contains' schema. Used with the 'contains' keyword to validate that at least this many array items match a specific pattern."
      >
        <Input
          type="number"
          value={attribute.minContains?.toString() || ''}
          onChange={({ detail }) => onUpdate({ minContains: detail.value ? parseInt(detail.value, 10) : undefined })}
          placeholder="e.g., 2 (at least 2 matches)"
        />
      </FormField>

      <FormField 
        label="Max Contains" 
        description="Maximum number of items that can match the 'contains' schema. Used with the 'contains' keyword to limit how many array items match a specific pattern."
      >
        <Input
          type="number"
          value={attribute.maxContains?.toString() || ''}
          onChange={({ detail }) => onUpdate({ maxContains: detail.value ? parseInt(detail.value, 10) : undefined })}
          placeholder="e.g., 5 (at most 5 matches)"
        />
      </FormField>
    </>
  );
};

ArrayConstraints.propTypes = {
  attribute: PropTypes.shape({
    type: PropTypes.string,
    minItems: PropTypes.number,
    maxItems: PropTypes.number,
    uniqueItems: PropTypes.bool,
    minContains: PropTypes.number,
    maxContains: PropTypes.number,
  }).isRequired,
  onUpdate: PropTypes.func.isRequired,
};

export default ArrayConstraints;
