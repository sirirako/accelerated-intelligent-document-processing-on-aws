import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { Box, SpaceBetween, Header, Button, Badge, Icon, Container } from '@cloudscape-design/components';
import { DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors } from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

const getTypeColor = (type) => {
  switch (type) {
    case 'string':
      return 'blue';
    case 'number':
      return 'green';
    case 'boolean':
      return 'grey';
    case 'object':
      return 'red';
    case 'array':
      return 'purple';
    default:
      return 'grey';
  }
};

const SortableAttributeItem = ({ id, name, attribute, isSelected, isRequired, onSelect, onRemove }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({
    id,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const hasNestedProperties =
    attribute.type === 'object' && attribute.properties && Object.keys(attribute.properties).length > 0;
  const hasArrayItems = attribute.type === 'array' && attribute.items;
  const hasComposition = attribute.oneOf || attribute.anyOf || attribute.allOf;
  const hasConditional = attribute.if;
  const isExpandable = hasNestedProperties || hasArrayItems || hasComposition || hasConditional;

  const getBadges = () => {
    const badges = [];
    badges.push(
      <Badge key="type" color={getTypeColor(attribute.type)}>
        {attribute.type || 'any'}
      </Badge>,
    );

    if (isRequired) {
      badges.push(
        <Badge key="required" color="red">
          required
        </Badge>,
      );
    }
    if (attribute.readOnly) {
      badges.push(<Badge key="readonly">read-only</Badge>);
    }
    if (attribute.writeOnly) {
      badges.push(<Badge key="writeonly">write-only</Badge>);
    }
    if (attribute.deprecated) {
      badges.push(<Badge key="deprecated">deprecated</Badge>);
    }
    if (attribute.const !== undefined) {
      badges.push(
        <Badge key="const" color="blue">
          const
        </Badge>,
      );
    }
    if (attribute.enum) {
      badges.push(
        <Badge key="enum" color="blue">
          enum
        </Badge>,
      );
    }
    if (hasComposition) {
      let compositionType = 'allOf';
      if (attribute.oneOf) {
        compositionType = 'oneOf';
      } else if (attribute.anyOf) {
        compositionType = 'anyOf';
      }
      badges.push(
        <Badge key="composition" color="purple">
          {compositionType}
        </Badge>,
      );
    }
    if (hasConditional) {
      badges.push(
        <Badge key="conditional" color="purple">
          if/then
        </Badge>,
      );
    }

    return badges;
  };

  const renderNestedContent = () => {
    if (hasNestedProperties) {
      return (
        <Box padding={{ left: 'l' }}>
          <SpaceBetween size="xs">
            {Object.entries(attribute.properties).map(([propName, propValue]) => (
              <Box key={propName} padding="xs" style={{ borderLeft: '2px solid #ddd' }}>
                <div style={{ fontSize: '12px' }}>
                  <strong>{propName}</strong>: <Badge color={getTypeColor(propValue.type)}>{propValue.type}</Badge>
                  {propValue.description && (
                    <div style={{ color: '#666', marginTop: '2px' }}>{propValue.description}</div>
                  )}
                </div>
              </Box>
            ))}
          </SpaceBetween>
        </Box>
      );
    }

    if (hasArrayItems) {
      return (
        <Box padding={{ left: 'l' }}>
          <div style={{ fontSize: '12px', borderLeft: '2px solid #ddd', paddingLeft: '8px' }}>
            <strong>Items:</strong>{' '}
            {attribute.items.$ref && <Badge>{attribute.items.$ref.replace('#/$defs/', '')}</Badge>}
            {!attribute.items.$ref && <Badge color={getTypeColor(attribute.items.type)}>{attribute.items.type}</Badge>}
          </div>
        </Box>
      );
    }

    if (hasComposition) {
      let compositionKey = 'allOf';
      if (attribute.oneOf) {
        compositionKey = 'oneOf';
      } else if (attribute.anyOf) {
        compositionKey = 'anyOf';
      }
      const schemas = attribute[compositionKey];
      return (
        <Box padding={{ left: 'l' }}>
          <div style={{ fontSize: '12px', borderLeft: '2px solid #ddd', paddingLeft: '8px' }}>
            <strong>{compositionKey}:</strong> {schemas.length} schemas
          </div>
        </Box>
      );
    }

    if (hasConditional) {
      return (
        <Box padding={{ left: 'l' }}>
          <div style={{ fontSize: '12px', borderLeft: '2px solid #ddd', paddingLeft: '8px' }}>
            <strong>Conditional:</strong> if/then{attribute.else ? '/else' : ''}
          </div>
        </Box>
      );
    }

    return null;
  };

  return (
    <div
      ref={setNodeRef}
      style={{
        ...style,
        marginBottom: '8px',
      }}
    >
      <Container
        disableContentPaddings={false}
      >
        <div
          onClick={() => onSelect(name)}
          onKeyPress={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              onSelect(name);
            }
          }}
          role="button"
          tabIndex={0}
          style={{
            cursor: 'pointer',
            borderLeft: isSelected ? '4px solid #0972d3' : '4px solid transparent',
            paddingLeft: '8px',
            backgroundColor: isSelected ? '#f0f8ff' : 'transparent',
          }}
        >
          <SpaceBetween size="xs">
            <Box>
              <SpaceBetween direction="horizontal" size="xs">
                <span style={{ cursor: 'grab', display: 'flex', alignItems: 'center' }} {...attributes} {...listeners}>
                  <Icon name="drag-indicator" />
                </span>
                {isExpandable && (
                  <Icon
                    name={isExpanded ? 'caret-down-filled' : 'caret-right-filled'}
                    onClick={(e) => {
                      e.stopPropagation();
                      setIsExpanded(!isExpanded);
                    }}
                  />
                )}
                <Box fontWeight="bold">{name}</Box>
                <SpaceBetween direction="horizontal" size="xs">
                  {getBadges()}
                </SpaceBetween>
                <Box float="right">
                  <SpaceBetween direction="horizontal" size="xs">
                    <Button
                      variant="icon"
                      iconName="edit"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelect(name);
                      }}
                      ariaLabel={`Edit ${name}`}
                    />
                    <Button
                      variant="icon"
                      iconName="close"
                      onClick={(e) => {
                        e.stopPropagation();
                        onRemove(name);
                      }}
                      ariaLabel={`Remove ${name}`}
                    />
                  </SpaceBetween>
                </Box>
              </SpaceBetween>
            </Box>
            {attribute.description && (
              <Box fontSize="body-s" color="text-body-secondary">
                {attribute.description}
              </Box>
            )}
            {isExpanded && isExpandable && renderNestedContent()}
          </SpaceBetween>
        </div>
      </Container>
    </div>
  );
};

SortableAttributeItem.propTypes = {
  id: PropTypes.string.isRequired,
  name: PropTypes.string.isRequired,
  attribute: PropTypes.shape({
    type: PropTypes.string,
    description: PropTypes.string,
    'x-aws-idp-attribute-type': PropTypes.string,
  }).isRequired,
  isSelected: PropTypes.bool.isRequired,
  isRequired: PropTypes.bool.isRequired,
  onSelect: PropTypes.func.isRequired,
  onRemove: PropTypes.func.isRequired,
};

// Memoize SortableAttributeItem to prevent re-renders of unselected items
const MemoizedSortableAttributeItem = React.memo(SortableAttributeItem);

const SchemaCanvas = ({ selectedClass, selectedAttributeId, onSelectAttribute, onRemoveAttribute, onReorder }) => {
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  if (!selectedClass) {
    return (
      <Box textAlign="center" padding="xxl">
        <Header variant="h3">No Class Selected</Header>
        <p>Select or create a class to start defining attributes</p>
      </Box>
    );
  }

  const attributes = Object.entries(selectedClass.attributes.properties || {});
  const attributeIds = attributes.map(([attributeName]) => attributeName);
  const requiredAttributes = selectedClass.attributes.required || [];

  const handleDragEnd = (event) => {
    const { active, over } = event;

    if (!over || !active) return;

    if (active.id !== over.id) {
      const oldIndex = attributeIds.indexOf(active.id);
      const newIndex = attributeIds.indexOf(over.id);
      onReorder(oldIndex, newIndex);
    }
  };

  return (
    <Box>
      <Header variant="h3" description="Click an attribute or use the edit icon to view and modify its properties">
        Attributes ({attributes.length})
      </Header>
      <SpaceBetween size="s">
        {attributes.length === 0 ? (
          <Box textAlign="center" padding="l" color="text-body-secondary">
            No attributes defined. Click &quot;Add Attribute&quot; to get started.
          </Box>
        ) : (
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <SortableContext items={attributeIds} strategy={verticalListSortingStrategy}>
              {attributes.map(([attributeName, attribute]) => (
                <MemoizedSortableAttributeItem
                  key={attributeName}
                  id={attributeName}
                  name={attributeName}
                  attribute={attribute}
                  isSelected={selectedAttributeId === attributeName}
                  isRequired={requiredAttributes.includes(attributeName)}
                  onSelect={onSelectAttribute}
                  onRemove={onRemoveAttribute}
                />
              ))}
            </SortableContext>
          </DndContext>
        )}
      </SpaceBetween>
    </Box>
  );
};

SchemaCanvas.propTypes = {
  selectedClass: PropTypes.shape({
    attributes: PropTypes.shape({
      properties: PropTypes.shape({}),
    }),
  }),
  selectedAttributeId: PropTypes.string,
  onSelectAttribute: PropTypes.func.isRequired,
  onRemoveAttribute: PropTypes.func.isRequired,
  onReorder: PropTypes.func.isRequired,
};

SchemaCanvas.defaultProps = {
  selectedClass: null,
  selectedAttributeId: null,
};

// Memoize the component to prevent re-renders when props haven't changed
export default React.memo(SchemaCanvas);
