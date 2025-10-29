import React from 'react';
import PropTypes from 'prop-types';
import { Header, FormField, Input, TokenGroup, Button, SpaceBetween } from '@cloudscape-design/components';
import { formatValueForInput, parseInputValue } from '../utils/schemaHelpers';

const ValueConstraints = ({ attribute, onUpdate }) => {
  return (
    <>
      <Header variant="h4">Value Constraints</Header>

      <FormField label="Const (Single Constant Value)" description="Field must be exactly this value">
        <Input
          value={formatValueForInput(attribute.const)}
          onChange={({ detail }) => {
            if (!detail.value) {
              const updates = { ...attribute };
              delete updates.const;
              onUpdate(updates);
              return;
            }
            const parsed = parseInputValue(detail.value, attribute.type);
            onUpdate({ const: parsed });
          }}
          placeholder='e.g., "active", 42, or JSON value'
          disabled={attribute.enum && attribute.enum.length > 0}
        />
      </FormField>

      <FormField
        label="Enum Values (Multiple Allowed Values)"
        description="Comma-separated list of allowed values (mutually exclusive with const)"
      >
        {attribute.enum && attribute.enum.length > 0 ? (
          <SpaceBetween size="xs">
            <TokenGroup
              items={attribute.enum.map((val) => ({
                label: typeof val === 'object' ? JSON.stringify(val) : String(val),
                dismissLabel: `Remove ${val}`,
              }))}
              onDismiss={({ detail: { itemIndex } }) => {
                const newEnum = [...(attribute.enum || [])];
                newEnum.splice(itemIndex, 1);
                onUpdate({ enum: newEnum.length > 0 ? newEnum : undefined });
              }}
            />
            <Button
              variant="link"
              onClick={() => {
                const updates = { ...attribute };
                delete updates.enum;
                onUpdate(updates);
              }}
            >
              Clear all enum values
            </Button>
          </SpaceBetween>
        ) : (
          <Input
            placeholder="value1, value2, value3"
            defaultValue=""
            onBlur={(e) => {
              const value = e.target.value.trim();
              if (value) {
                try {
                  const parsed = JSON.parse(`[${value}]`);
                  onUpdate({ enum: parsed });
                } catch {
                  const enumValues = value
                    .split(',')
                    .map((v) => v.trim())
                    .filter((v) => v);
                  onUpdate({ enum: enumValues.length > 0 ? enumValues : undefined });
                }
              }
            }}
            disabled={attribute.const !== undefined}
          />
        )}
      </FormField>
    </>
  );
};

ValueConstraints.propTypes = {
  attribute: PropTypes.shape({
    type: PropTypes.string,
    const: PropTypes.oneOfType([PropTypes.string, PropTypes.number, PropTypes.bool, PropTypes.object, PropTypes.array]),
    enum: PropTypes.arrayOf(PropTypes.oneOfType([PropTypes.string, PropTypes.number, PropTypes.bool, PropTypes.object, PropTypes.array])),
  }).isRequired,
  onUpdate: PropTypes.func.isRequired,
};

export default ValueConstraints;
