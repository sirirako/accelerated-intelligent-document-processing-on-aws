import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import {
  Box,
  SpaceBetween,
  Header,
  FormField,
  Input,
  Select,
  Textarea,
  TokenGroup,
  Checkbox,
  Button,
  Toggle,
  Alert,
} from '@cloudscape-design/components';
import SchemaCompositionEditor from './SchemaCompositionEditor';
import SchemaConditionalEditor from './SchemaConditionalEditor';
import StringConstraints from './constraints/StringConstraints';
import NumberConstraints from './constraints/NumberConstraints';
import ArrayConstraints from './constraints/ArrayConstraints';
import ObjectConstraints from './constraints/ObjectConstraints';
import MetadataFields from './constraints/MetadataFields';
import ValueConstraints from './constraints/ValueConstraints';
import {
  TYPE_OPTIONS,
  EVALUATION_METHOD_OPTIONS,
  X_AWS_IDP_DOCUMENT_TYPE,
  X_AWS_IDP_EVALUATION_METHOD,
  X_AWS_IDP_CONFIDENCE_THRESHOLD,
} from '../../constants/schemaConstants';

const SchemaInspector = ({
  selectedClass,
  selectedAttribute,
  selectedAttributeName,
  onUpdate,
  onUpdateClass,
  onRenameAttribute,
  availableClasses,
  isRequired,
  onToggleRequired,
}) => {
  // Show class-level settings when class is selected but no attribute is selected
  if (selectedClass && (!selectedAttribute || !selectedAttributeName)) {
    return (
      <Box>
        <Header variant="h3">Class Inspector: {selectedClass.name}</Header>
        <SpaceBetween size="m">
          <FormField
            label="Document Type"
            description="Document types become top-level schemas. Shared classes are reusable definitions."
          >
            <Toggle
              checked={selectedClass[X_AWS_IDP_DOCUMENT_TYPE] || false}
              onChange={({ detail }) => onUpdateClass({ [X_AWS_IDP_DOCUMENT_TYPE]: detail.checked })}
            >
              {selectedClass[X_AWS_IDP_DOCUMENT_TYPE] ? 'This is a document type' : 'This is a shared class'}
            </Toggle>
          </FormField>

          {selectedClass[X_AWS_IDP_DOCUMENT_TYPE] ? (
            <Alert type="info">
              <strong>Document Type</strong>
              <br />
              This class will be exported as a standalone JSON schema. Each document type schema will only include $defs
              for classes it actually references, keeping schemas minimal and focused.
            </Alert>
          ) : (
            <Alert type="info">
              <strong>Shared Class</strong>
              <br />
              This class is available to be referenced by document types and other classes. It will only appear in the
              $defs section of schemas that reference it.
            </Alert>
          )}

          <FormField label="Class Description" description="Describe the purpose of this class">
            <Textarea
              value={selectedClass.description || ''}
              onChange={({ detail }) => onUpdateClass({ description: detail.value || undefined })}
              rows={3}
              placeholder="Describe what this class represents"
            />
          </FormField>
        </SpaceBetween>
      </Box>
    );
  }

  if (!selectedAttribute || !selectedAttributeName) {
    return (
      <Box textAlign="center" padding="xxl">
        <Header variant="h3">No Selection</Header>
        <p>Select a class or attribute from the canvas to edit its properties</p>
      </Box>
    );
  }

  const [attributeLabel, setAttributeLabel] = useState(selectedAttributeName || '');

  useEffect(() => {
    setAttributeLabel(selectedAttributeName || '');
  }, [selectedAttributeName]);

  const handleRenameSubmit = () => {
    const trimmed = attributeLabel.trim();
    if (!trimmed || trimmed === selectedAttributeName) {
      setAttributeLabel(selectedAttributeName || '');
      return;
    }

    if (onRenameAttribute && !onRenameAttribute(trimmed)) {
      setAttributeLabel(selectedAttributeName || '');
    }
  };

  return (
    <Box>
      <Header variant="h3">Property Inspector: {selectedAttributeName}</Header>
      <SpaceBetween size="m">
        <FormField label="Attribute Name">
          <Input
            value={attributeLabel}
            onChange={({ detail }) => setAttributeLabel(detail.value)}
            onBlur={handleRenameSubmit}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                handleRenameSubmit();
              }
            }}
          />
        </FormField>

        <Checkbox checked={isRequired} onChange={({ detail }) => onToggleRequired(detail.checked)}>
          Required field
        </Checkbox>

        <FormField label="Type" description="JSON Schema type for this attribute">
          <Select
            selectedOption={TYPE_OPTIONS.find((opt) => opt.value === selectedAttribute.type) || null}
            onChange={({ detail }) => onUpdate({ type: detail.selectedOption.value })}
            options={TYPE_OPTIONS}
          />
        </FormField>

        {selectedAttribute.type === 'object' && availableClasses && availableClasses.length > 0 && (
          <>
            <FormField
              label="Reference Existing Class (Optional)"
              description="Link to a reusable class definition instead of defining properties inline"
            >
              <Select
                selectedOption={
                  selectedAttribute.$ref
                    ? {
                        label: selectedAttribute.$ref.replace('#/$defs/', ''),
                        value: selectedAttribute.$ref,
                      }
                    : null
                }
                onChange={({ detail }) => {
                  if (detail.selectedOption.value) {
                    const updates = { ...selectedAttribute, $ref: detail.selectedOption.value };
                    delete updates.properties;
                    delete updates.required;
                    delete updates.minProperties;
                    delete updates.maxProperties;
                    delete updates.additionalProperties;
                    onUpdate(updates);
                  } else {
                    const updates = { ...selectedAttribute, $ref: undefined };
                    onUpdate(updates);
                  }
                }}
                options={[
                  { label: 'None (inline properties)', value: '' },
                  ...availableClasses.map((cls) => ({
                    label: cls.name,
                    value: `#/$defs/${cls.name}`,
                  })),
                ]}
                placeholder="Select a class to reference"
              />
            </FormField>

            {!selectedAttribute.$ref && <ObjectConstraints attribute={selectedAttribute} onUpdate={onUpdate} />}
          </>
        )}

        {selectedAttribute.type === 'array' && availableClasses && availableClasses.length > 0 && (
          <>
            <FormField label="Array Item Type" description="Define what each item in the array should be">
              <Select
                selectedOption={
                  selectedAttribute.items?.$ref
                    ? {
                        label: selectedAttribute.items.$ref.replace('#/$defs/', ''),
                        value: selectedAttribute.items.$ref,
                      }
                    : {
                        label: `Simple (${selectedAttribute.items?.type || 'string'})`,
                        value: 'simple',
                      }
                }
                onChange={({ detail }) => {
                  if (detail.selectedOption.value === 'simple') {
                    onUpdate({ items: { type: 'string' } });
                  } else {
                    onUpdate({ items: { $ref: detail.selectedOption.value } });
                  }
                }}
                options={[
                  { label: 'Simple (string)', value: 'simple' },
                  ...availableClasses.map((cls) => ({
                    label: `Class: ${cls.name}`,
                    value: `#/$defs/${cls.name}`,
                  })),
                ]}
              />
            </FormField>

            <ArrayConstraints attribute={selectedAttribute} onUpdate={onUpdate} />
          </>
        )}

        <Header variant="h4">Metadata</Header>

        <MetadataFields attribute={selectedAttribute} onUpdate={onUpdate} />

        <StringConstraints attribute={selectedAttribute} onUpdate={onUpdate} />

        <NumberConstraints attribute={selectedAttribute} onUpdate={onUpdate} />

        <ValueConstraints attribute={selectedAttribute} onUpdate={onUpdate} />

        <SchemaCompositionEditor
          selectedAttribute={selectedAttribute}
          availableClasses={availableClasses}
          onUpdate={onUpdate}
        />

        <SchemaConditionalEditor
          selectedAttribute={selectedAttribute}
          availableClasses={availableClasses}
          onUpdate={onUpdate}
        />

        <Header variant="h4">AWS IDP Extensions</Header>

        <FormField label="Evaluation Method">
          <Select
            selectedOption={
              EVALUATION_METHOD_OPTIONS.find((opt) => opt.value === selectedAttribute[X_AWS_IDP_EVALUATION_METHOD]) ||
              null
            }
            onChange={({ detail }) =>
              onUpdate({
                [X_AWS_IDP_EVALUATION_METHOD]: detail.selectedOption.value,
              })
            }
            options={EVALUATION_METHOD_OPTIONS}
            placeholder="Select evaluation method"
          />
        </FormField>

        <FormField label="Confidence Threshold" description="Minimum confidence score (0-1)">
          <Input
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={selectedAttribute[X_AWS_IDP_CONFIDENCE_THRESHOLD]?.toString() || ''}
            onChange={({ detail }) =>
              onUpdate({
                [X_AWS_IDP_CONFIDENCE_THRESHOLD]: detail.value ? parseFloat(detail.value) : undefined,
              })
            }
          />
        </FormField>
      </SpaceBetween>
    </Box>
  );
};

// Memoize the component to prevent re-renders when props haven't changed
export default React.memo(SchemaInspector);

SchemaInspector.propTypes = {
  selectedClass: PropTypes.shape({
    name: PropTypes.string,
    description: PropTypes.string,
    X_AWS_IDP_DOCUMENT_TYPE: PropTypes.bool,
  }),
  selectedAttribute: PropTypes.shape({}),
  selectedAttributeName: PropTypes.string,
  onUpdate: PropTypes.func.isRequired,
  onUpdateClass: PropTypes.func,
  availableClasses: PropTypes.arrayOf(
    PropTypes.shape({
      name: PropTypes.string,
    }),
  ),
  isRequired: PropTypes.bool,
  onToggleRequired: PropTypes.func,
  onRenameAttribute: PropTypes.func,
};

SchemaInspector.defaultProps = {
  selectedClass: null,
  selectedAttribute: null,
  selectedAttributeName: null,
  availableClasses: [],
  isRequired: false,
  onToggleRequired: () => {},
  onRenameAttribute: () => true,
  onUpdateClass: () => {},
};
