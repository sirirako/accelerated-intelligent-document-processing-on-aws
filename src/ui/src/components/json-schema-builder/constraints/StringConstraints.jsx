import React from 'react';
import PropTypes from 'prop-types';
import { Header, FormField, Input, Select } from '@cloudscape-design/components';
import { FORMAT_OPTIONS, CONTENT_ENCODING_OPTIONS } from '../../../constants/schemaConstants';

const StringConstraints = ({ attribute, onUpdate }) => {
  if (attribute.type !== 'string') return null;

  return (
    <>
      <Header variant="h4">String Constraints</Header>

      <FormField label="Pattern (regex)" description="Regular expression pattern for validation">
        <Input
          value={attribute.pattern || ''}
          onChange={({ detail }) => onUpdate({ pattern: detail.value || undefined })}
          placeholder="e.g., ^\d{3}-\d{2}-\d{4}$"
        />
      </FormField>

      <FormField label="Format" description="Predefined format validation">
        <Select
          selectedOption={FORMAT_OPTIONS.find((opt) => opt.value === (attribute.format || '')) || FORMAT_OPTIONS[0]}
          onChange={({ detail }) => onUpdate({ format: detail.selectedOption.value || undefined })}
          options={FORMAT_OPTIONS}
        />
      </FormField>

      <FormField label="Min Length" description="Minimum string length">
        <Input
          type="number"
          value={attribute.minLength?.toString() || ''}
          onChange={({ detail }) => onUpdate({ minLength: detail.value ? parseInt(detail.value, 10) : undefined })}
          placeholder="e.g., 3"
        />
      </FormField>

      <FormField label="Max Length" description="Maximum string length">
        <Input
          type="number"
          value={attribute.maxLength?.toString() || ''}
          onChange={({ detail }) => onUpdate({ maxLength: detail.value ? parseInt(detail.value, 10) : undefined })}
          placeholder="e.g., 100"
        />
      </FormField>

      <FormField label="Content Media Type" description="MIME type for content (e.g., application/json)">
        <Input
          value={attribute.contentMediaType || ''}
          onChange={({ detail }) => onUpdate({ contentMediaType: detail.value || undefined })}
          placeholder="e.g., application/json, image/png"
        />
      </FormField>

      <FormField label="Content Encoding" description="Encoding format for string content">
        <Select
          selectedOption={
            CONTENT_ENCODING_OPTIONS.find((opt) => opt.value === (attribute.contentEncoding || '')) ||
            CONTENT_ENCODING_OPTIONS[0]
          }
          onChange={({ detail }) => onUpdate({ contentEncoding: detail.selectedOption.value || undefined })}
          options={CONTENT_ENCODING_OPTIONS}
        />
      </FormField>
    </>
  );
};

StringConstraints.propTypes = {
  attribute: PropTypes.shape({
    type: PropTypes.string,
    pattern: PropTypes.string,
    format: PropTypes.string,
    minLength: PropTypes.number,
    maxLength: PropTypes.number,
    contentMediaType: PropTypes.string,
    contentEncoding: PropTypes.string,
  }).isRequired,
  onUpdate: PropTypes.func.isRequired,
};

export default StringConstraints;
