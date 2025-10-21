import React from 'react';
import PropTypes from 'prop-types';
import { Header, FormField, Input, Textarea, Checkbox } from '@cloudscape-design/components';
import { formatValueForInput, parseInputValue } from '../utils/schemaHelpers';

const MetadataFields = ({ attribute, onUpdate }) => {
  return (
    <>
      <Header variant="h4">Metadata</Header>

      <FormField label="Title" description="Human-readable title for this attribute">
        <Input
          value={attribute.title || ''}
          onChange={({ detail }) => onUpdate({ title: detail.value || undefined })}
          placeholder="e.g., Invoice Number"
        />
      </FormField>

      <FormField label="Description" description="Detailed description of this attribute">
        <Textarea
          value={attribute.description || ''}
          onChange={({ detail }) => onUpdate({ description: detail.value || undefined })}
          rows={3}
          placeholder="Describe what this field represents and how it should be extracted"
        />
      </FormField>

      <FormField label="Comment" description="Internal comment for developers (not for end users)">
        <Textarea
          value={attribute.$comment || ''}
          onChange={({ detail }) => onUpdate({ $comment: detail.value || undefined })}
          rows={2}
          placeholder="Notes for developers maintaining this schema"
        />
      </FormField>

      <FormField label="Default Value" description="Default value if attribute is not present">
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
          placeholder="e.g., 0, '', or JSON value"
        />
      </FormField>

      <FormField
        label="Examples"
        description="Example values (comma-separated for simple types, JSON array for complex)"
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
          placeholder='e.g., "value1", "value2" or valid JSON array'
        />
      </FormField>

      <Checkbox
        checked={attribute.readOnly || false}
        onChange={({ detail }) => onUpdate({ readOnly: detail.checked || undefined })}
      >
        Read Only (for response schemas, not user input)
      </Checkbox>

      <Checkbox
        checked={attribute.writeOnly || false}
        onChange={({ detail }) => onUpdate({ writeOnly: detail.checked || undefined })}
      >
        Write Only (for request schemas, not returned in responses)
      </Checkbox>

      <Checkbox
        checked={attribute.deprecated || false}
        onChange={({ detail }) => onUpdate({ deprecated: detail.checked || undefined })}
      >
        Deprecated (mark this field as deprecated)
      </Checkbox>
    </>
  );
};

MetadataFields.propTypes = {
  attribute: PropTypes.shape({
    type: PropTypes.string,
    title: PropTypes.string,
    description: PropTypes.string,
    $comment: PropTypes.string,
    default: PropTypes.oneOfType([
      PropTypes.string,
      PropTypes.number,
      PropTypes.bool,
      PropTypes.object,
      PropTypes.array,
    ]),
    examples: PropTypes.arrayOf(
      PropTypes.oneOfType([PropTypes.string, PropTypes.number, PropTypes.bool, PropTypes.object, PropTypes.array]),
    ),
    readOnly: PropTypes.bool,
    writeOnly: PropTypes.bool,
    deprecated: PropTypes.bool,
  }).isRequired,
  onUpdate: PropTypes.func.isRequired,
};

export default MetadataFields;
