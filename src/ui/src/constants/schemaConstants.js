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
// AWS IDP Evaluation Extensions (Stickler-based Baseline Accuracy)
// ============================================================================
/** Evaluation method for baseline comparison */
export const X_AWS_IDP_EVALUATION_METHOD = 'x-aws-idp-evaluation-method';

/** Evaluation threshold for baseline match (0.0 to 1.0) */
export const X_AWS_IDP_EVALUATION_THRESHOLD = 'x-aws-idp-evaluation-threshold';

/** Evaluation weight for field importance (business criticality) */
export const X_AWS_IDP_EVALUATION_WEIGHT = 'x-aws-idp-evaluation-weight';

/** Overall match threshold for document-level evaluation (0.0 to 1.0) */
export const X_AWS_IDP_EVALUATION_MATCH_THRESHOLD = 'x-aws-idp-evaluation-match-threshold';

/** Evaluation model name (optional, defaults to document type name) */
export const X_AWS_IDP_EVALUATION_MODEL_NAME = 'x-aws-idp-evaluation-model-name';

// Valid evaluation methods
export const EVALUATION_METHOD_EXACT = 'EXACT';
export const EVALUATION_METHOD_NUMERIC_EXACT = 'NUMERIC_EXACT';
export const EVALUATION_METHOD_FUZZY = 'FUZZY';
export const EVALUATION_METHOD_LEVENSHTEIN = 'LEVENSHTEIN';
export const EVALUATION_METHOD_SEMANTIC = 'SEMANTIC';
export const EVALUATION_METHOD_LLM = 'LLM';
export const EVALUATION_METHOD_HUNGARIAN = 'HUNGARIAN';

export const VALID_EVALUATION_METHODS = [
  EVALUATION_METHOD_EXACT,
  EVALUATION_METHOD_NUMERIC_EXACT,
  EVALUATION_METHOD_FUZZY,
  EVALUATION_METHOD_LEVENSHTEIN,
  EVALUATION_METHOD_SEMANTIC,
  EVALUATION_METHOD_LLM,
  EVALUATION_METHOD_HUNGARIAN,
];

// UI-friendly evaluation method options with descriptions and validation metadata
export const EVALUATION_METHOD_OPTIONS = [
  {
    label: 'Exact',
    value: EVALUATION_METHOD_EXACT,
    description: 'Character-by-character match after normalization',
    validFor: [TYPE_STRING, TYPE_NUMBER, TYPE_INTEGER, TYPE_BOOLEAN],
  },
  {
    label: 'Numeric Exact',
    value: EVALUATION_METHOD_NUMERIC_EXACT,
    description: 'Numeric comparison (currency/format normalized)',
    validFor: [TYPE_NUMBER, TYPE_INTEGER, TYPE_STRING],
  },
  {
    label: 'Fuzzy',
    value: EVALUATION_METHOD_FUZZY,
    description: 'Allows minor formatting variations',
    validFor: [TYPE_STRING],
  },
  {
    label: 'Levenshtein',
    value: EVALUATION_METHOD_LEVENSHTEIN,
    description: 'String distance-based matching',
    validFor: [TYPE_STRING],
  },
  {
    label: 'Semantic',
    value: EVALUATION_METHOD_SEMANTIC,
    description: 'Embedding-based meaning comparison',
    validFor: [TYPE_STRING, TYPE_OBJECT],
  },
  {
    label: 'LLM',
    value: EVALUATION_METHOD_LLM,
    description: 'AI-powered functional equivalence',
    validFor: [TYPE_STRING, TYPE_OBJECT],
  },
  {
    label: 'Hungarian',
    value: EVALUATION_METHOD_HUNGARIAN,
    description: 'Optimal matching for arrays of objects (List[Object] only)',
    validFor: [TYPE_ARRAY],
    requiresStructuredItems: true, // Only for arrays with object items
  },
];

// Default threshold values per evaluation method (for regular fields)
// Only methods that use similarity thresholds have defaults here
export const EVALUATION_THRESHOLD_DEFAULTS = {
  [EVALUATION_METHOD_FUZZY]: 0.85,
  [EVALUATION_METHOD_LEVENSHTEIN]: 0.8,
  [EVALUATION_METHOD_SEMANTIC]: 0.7,
  // No defaults for EXACT (binary), NUMERIC_EXACT (uses tolerance), LLM (binary)
};

// Default match_threshold values per evaluation method (for structured arrays)
// Note: Only HUNGARIAN uses match_threshold. LLM evaluates arrays semantically without match_threshold.
export const EVALUATION_MATCH_THRESHOLD_DEFAULTS = {
  [EVALUATION_METHOD_HUNGARIAN]: 0.8,
};

// Methods that require threshold configuration (for non-array fields)
// Only methods that use similarity-based scoring require thresholds
export const METHODS_REQUIRING_THRESHOLD = [
  EVALUATION_METHOD_FUZZY,
  EVALUATION_METHOD_LEVENSHTEIN,
  EVALUATION_METHOD_SEMANTIC,
  // EXACT, NUMERIC_EXACT, and LLM do not use thresholds
];

// Methods that require match_threshold configuration (for structured arrays)
// Note: Only HUNGARIAN uses match_threshold for item-by-item optimal matching.
// LLM evaluates arrays semantically as a whole and does not use match_threshold.
export const METHODS_REQUIRING_MATCH_THRESHOLD = [EVALUATION_METHOD_HUNGARIAN];

// ============================================================================
// AWS IDP Assessment Extensions (Extraction Confidence Alerts)
// ============================================================================
/** Confidence threshold for extraction quality alerts (0.0 to 1.0) */
export const X_AWS_IDP_CONFIDENCE_THRESHOLD = 'x-aws-idp-confidence-threshold';

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
