import React from 'react';
import PropTypes from 'prop-types';
import { FormField, Textarea, Input } from '@cloudscape-design/components';
import { formatValueForInput, parseInputValue } from '../utils/schemaHelpers';

const MetadataFields = ({ attribute, onUpdate }) => {
  return (
    <>
      <FormField
        label="Description"
        description="Describe what information to extract and provide specific instructions for the LLM. Be clear about format, units, and any special handling needed."
      >
        <Textarea
          value={attribute.description || ''}
          onChange={({ detail }) => onUpdate({ description: detail.value || undefined })}
          rows={3}
          placeholder="e.g., The total amount due including tax, formatted as a decimal number"
        />
      </FormField>

      <FormField
        label="Examples"
        description="Provide example values to guide extraction. This helps the LLM understand the expected format and content. Enter comma-separated values or a JSON array."
      >
        <Textarea
          value={(() => {
            if (!attribute.examples) return '';
            if (!Array.isArray(attribute.examples)) return '';
            return attribute.examples.map((ex) => (typeof ex === 'object' ? JSON.stringify(ex) : ex)).join(', ');
          })()}
          onChange={({ detail }) => {
            if (!detail.value.trim()) {
              const updates = { ...attribute };
              delete updates.examples;
              onUpdate(updates);
              return;
            }
            try {
              const parsed = JSON.parse(`[${detail.value}]`);
              onUpdate({ examples: parsed });
            } catch {
              const examples = detail.value
                .split(',')
                .map((v) => v.trim())
                .filter((v) => v);
              onUpdate({ examples: examples.length > 0 ? examples : undefined });
            }
          }}
          rows={2}
          placeholder='e.g., "INV-2024-001", "PO-12345" or ["John Doe", "Jane Smith"]'
        />
      </FormField>

      <FormField
        label="Default Value"
        description="Fallback value to use if this field is not found or cannot be extracted from the document."
      >
        <Input
          value={formatValueForInput(attribute.default)}
          onChange={({ detail }) => {
            if (!detail.value) {
              const updates = { ...attribute };
              delete updates.default;
              onUpdate(updates);
              return;
            }
            const parsed = parseInputValue(detail.value, attribute.type);
            onUpdate({ default: parsed });
          }}
          placeholder="e.g., 0, N/A, or a JSON value"
        />
      </FormField>
    </>
  );
};

MetadataFields.propTypes = {
  attribute: PropTypes.shape({
    type: PropTypes.string,
    description: PropTypes.string,
    default: PropTypes.oneOfType([PropTypes.string, PropTypes.number, PropTypes.bool, PropTypes.object, PropTypes.array]),
    examples: PropTypes.arrayOf(
      PropTypes.oneOfType([PropTypes.string, PropTypes.number, PropTypes.bool, PropTypes.object, PropTypes.array]),
    ),
  }).isRequired,
  onUpdate: PropTypes.func.isRequired,
};

export default MetadataFields;
