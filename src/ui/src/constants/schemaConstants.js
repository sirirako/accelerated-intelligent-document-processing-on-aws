/**
 * JSON Schema and AWS IDP Extension Constants
 *
 * These constants match the backend lib/idp_common_pkg/idp_common/config/schema_constants.py
 * to ensure consistency between frontend and backend when building and processing document schemas.
 *
 * @see lib/idp_common_pkg/idp_common/config/schema_constants.py
 */

// ============================================================================
// JSON Schema Standard Fields
// ============================================================================
export const SCHEMA_FIELD = '$schema';
export const ID_FIELD = '$id';
export const DEFS_FIELD = '$defs';
export const REF_FIELD = '$ref';

// ============================================================================
// JSON Schema Standard Property Names
// ============================================================================
export const SCHEMA_TYPE = 'type';
export const SCHEMA_PROPERTIES = 'properties';
export const SCHEMA_ITEMS = 'items';
export const SCHEMA_REQUIRED = 'required';
export const SCHEMA_DESCRIPTION = 'description';
export const SCHEMA_EXAMPLES = 'examples';

// ============================================================================
// JSON Schema Type Values
// ============================================================================
export const TYPE_OBJECT = 'object';
export const TYPE_ARRAY = 'array';
export const TYPE_STRING = 'string';
export const TYPE_NUMBER = 'number';
export const TYPE_INTEGER = 'integer';
export const TYPE_BOOLEAN = 'boolean';
export const TYPE_NULL = 'null';

// UI-friendly type options for dropdowns
export const TYPE_OPTIONS = [
  { label: 'String', value: TYPE_STRING },
  { label: 'Number', value: TYPE_NUMBER },
  { label: 'Integer', value: TYPE_INTEGER },
  { label: 'Boolean', value: TYPE_BOOLEAN },
  { label: 'Object', value: TYPE_OBJECT },
  { label: 'Array', value: TYPE_ARRAY },
  { label: 'Null', value: TYPE_NULL },
];

// Type colors for UI visualization
export const TYPE_COLORS = {
  [TYPE_STRING]: 'blue',
  [TYPE_NUMBER]: 'green',
  [TYPE_INTEGER]: 'green',
  [TYPE_BOOLEAN]: 'grey',
  [TYPE_OBJECT]: 'red',
  [TYPE_ARRAY]: 'purple',
  [TYPE_NULL]: 'grey',
};

// ============================================================================
// AWS IDP Document Type Extensions
// ============================================================================
/** Marks a schema as a document type (top-level class) */
export const X_AWS_IDP_DOCUMENT_TYPE = 'x-aws-idp-document-type';

/** Classification metadata for document type */
export const X_AWS_IDP_CLASSIFICATION = 'x-aws-idp-classification';

/** Regex patterns for classification optimization */
export const X_AWS_IDP_DOCUMENT_NAME_REGEX = 'x-aws-idp-document-name-regex';
export const X_AWS_IDP_PAGE_CONTENT_REGEX = 'x-aws-idp-document-page-content-regex';

// ============================================================================
// AWS IDP List-Specific Extensions
// ============================================================================
/** Description for list items */
export const X_AWS_IDP_LIST_ITEM_DESCRIPTION = 'x-aws-idp-list-item-description';

/** Original attribute name (preserved from legacy format) */
export const X_AWS_IDP_ORIGINAL_NAME = 'x-aws-idp-original-name';

// ============================================================================
// AWS IDP Evaluation Extensions
// ============================================================================
/** Evaluation method for attribute comparison */
export const X_AWS_IDP_EVALUATION_METHOD = 'x-aws-idp-evaluation-method';

// Valid evaluation methods
export const EVALUATION_METHOD_EXACT = 'EXACT';
export const EVALUATION_METHOD_NUMERIC_EXACT = 'NUMERIC_EXACT';
export const EVALUATION_METHOD_FUZZY = 'FUZZY';
export const EVALUATION_METHOD_SEMANTIC = 'SEMANTIC';
export const EVALUATION_METHOD_LLM = 'LLM';

export const VALID_EVALUATION_METHODS = [
  EVALUATION_METHOD_EXACT,
  EVALUATION_METHOD_NUMERIC_EXACT,
  EVALUATION_METHOD_FUZZY,
  EVALUATION_METHOD_SEMANTIC,
  EVALUATION_METHOD_LLM,
];

// UI-friendly evaluation method options
export const EVALUATION_METHOD_OPTIONS = [
  { label: 'Exact', value: EVALUATION_METHOD_EXACT },
  { label: 'Numeric Exact', value: EVALUATION_METHOD_NUMERIC_EXACT },
  { label: 'Fuzzy', value: EVALUATION_METHOD_FUZZY },
  { label: 'Semantic', value: EVALUATION_METHOD_SEMANTIC },
  { label: 'LLM', value: EVALUATION_METHOD_LLM },
];

/** Confidence threshold for evaluation (0.0 to 1.0) */
export const X_AWS_IDP_CONFIDENCE_THRESHOLD = 'x-aws-idp-confidence-threshold';

/** Hungarian algorithm comparator for list matching */
export const X_AWS_IDP_HUNGARIAN_COMPARATOR = 'x-aws-idp-hungarian-comparator';

// ============================================================================
// AWS IDP Prompt Extensions
// ============================================================================
/** Custom prompt override for attribute extraction */
export const X_AWS_IDP_PROMPT_OVERRIDE = 'x-aws-idp-prompt-override';

/** Maximum length for prompt overrides */
export const MAX_PROMPT_OVERRIDE_LENGTH = 10000;

// ============================================================================
// AWS IDP Example Extensions
// ============================================================================
/** Extensions for few-shot example support */
export const X_AWS_IDP_EXAMPLES = 'x-aws-idp-examples';
export const X_AWS_IDP_CLASS_PROMPT = 'x-aws-idp-class-prompt';
export const X_AWS_IDP_ATTRIBUTES_PROMPT = 'x-aws-idp-attributes-prompt';
export const X_AWS_IDP_IMAGE_PATH = 'x-aws-idp-image-path';

// ============================================================================
// Legacy Format Field Names (for migration reference)
// ============================================================================
export const LEGACY_ATTRIBUTES = 'attributes';
export const LEGACY_NAME = 'name';
export const LEGACY_DESCRIPTION = 'description';
export const LEGACY_ATTRIBUTE_TYPE = 'attributeType';
export const LEGACY_GROUP_ATTRIBUTES = 'groupAttributes';
export const LEGACY_LIST_ITEM_TEMPLATE = 'listItemTemplate';
export const LEGACY_ITEM_ATTRIBUTES = 'itemAttributes';
export const LEGACY_ITEM_DESCRIPTION = 'itemDescription';

// Legacy attribute type values (deprecated - use JSON Schema types instead)
export const ATTRIBUTE_TYPE_SIMPLE = 'simple';
export const ATTRIBUTE_TYPE_GROUP = 'group';
export const ATTRIBUTE_TYPE_LIST = 'list';

// UI-friendly legacy attribute options (for migration UI)
export const ATTRIBUTE_TYPE_OPTIONS = [
  { label: 'Simple', value: ATTRIBUTE_TYPE_SIMPLE, description: 'Single value field' },
  { label: 'Group', value: ATTRIBUTE_TYPE_GROUP, description: 'Nested object with properties' },
  { label: 'List', value: ATTRIBUTE_TYPE_LIST, description: 'Array of items' },
];

// ============================================================================
// JSON Schema Format Options
// ============================================================================
export const FORMAT_OPTIONS = [
  { label: 'None', value: '' },
  { label: 'Date', value: 'date' },
  { label: 'Time', value: 'time' },
  { label: 'Date-Time', value: 'date-time' },
  { label: 'Duration', value: 'duration' },
  { label: 'Email', value: 'email' },
  { label: 'IDN Email', value: 'idn-email' },
  { label: 'Hostname', value: 'hostname' },
  { label: 'IDN Hostname', value: 'idn-hostname' },
  { label: 'IPv4', value: 'ipv4' },
  { label: 'IPv6', value: 'ipv6' },
  { label: 'URI', value: 'uri' },
  { label: 'URI Reference', value: 'uri-reference' },
  { label: 'IRI', value: 'iri' },
  { label: 'IRI Reference', value: 'iri-reference' },
  { label: 'URI Template', value: 'uri-template' },
  { label: 'JSON Pointer', value: 'json-pointer' },
  { label: 'Relative JSON Pointer', value: 'relative-json-pointer' },
  { label: 'Regex', value: 'regex' },
  { label: 'UUID', value: 'uuid' },
];

// ============================================================================
// Content Encoding Options
// ============================================================================
export const CONTENT_ENCODING_OPTIONS = [
  { label: 'None', value: '' },
  { label: 'Base64', value: 'base64' },
  { label: '7bit', value: '7bit' },
  { label: '8bit', value: '8bit' },
  { label: 'Binary', value: 'binary' },
  { label: 'Quoted-Printable', value: 'quoted-printable' },
];

// ============================================================================
// Default Values
// ============================================================================
/** Default JSON Schema version */
export const DEFAULT_SCHEMA_VERSION = 'https://json-schema.org/draft/2020-12/schema';

/** Default confidence threshold */
export const DEFAULT_CONFIDENCE_THRESHOLD = 0.9;
