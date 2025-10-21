export const TYPE_OPTIONS = [
  { label: 'String', value: 'string' },
  { label: 'Number', value: 'number' },
  { label: 'Integer', value: 'integer' },
  { label: 'Boolean', value: 'boolean' },
  { label: 'Object', value: 'object' },
  { label: 'Array', value: 'array' },
  { label: 'Null', value: 'null' },
];

export const ATTRIBUTE_TYPE_OPTIONS = [
  { label: 'Simple', value: 'simple', description: 'Single value field' },
  { label: 'Group', value: 'group', description: 'Nested object with properties' },
  { label: 'List', value: 'list', description: 'Array of items' },
];

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

export const CONTENT_ENCODING_OPTIONS = [
  { label: 'None', value: '' },
  { label: 'Base64', value: 'base64' },
  { label: '7bit', value: '7bit' },
  { label: '8bit', value: '8bit' },
  { label: 'Binary', value: 'binary' },
  { label: 'Quoted-Printable', value: 'quoted-printable' },
];

export const EVALUATION_METHOD_OPTIONS = [
  { label: 'Exact', value: 'EXACT' },
  { label: 'Numeric Exact', value: 'NUMERIC_EXACT' },
  { label: 'Fuzzy', value: 'FUZZY' },
  { label: 'Semantic', value: 'SEMANTIC' },
];

export const TYPE_COLORS = {
  string: 'blue',
  number: 'green',
  integer: 'green',
  boolean: 'grey',
  object: 'red',
  array: 'purple',
  null: 'grey',
};
