# JSON Schema Library Utilization Analysis

## Current State

### Backend (Python)
**Library Available:** `jsonschema` (Draft202012Validator)
**Currently Used In:**
- ✅ `src/lambda/update_configuration/index.py:88-135` - Validates extractionSchema on upload
- ✅ `lib/idp_common_pkg/idp_common/extraction/agentic_idp.py` - Some validation

**Schema Definitions Available:**
- ✅ `EXTRACTION_CLASS_SCHEMA` in `schema_definition.py`
- ✅ `EXTRACTION_SCHEMA_ARRAY` (referenced but need to verify)
- ✅ Comprehensive schema with AWS extensions defined

### Frontend (JavaScript)
**Library Available:** `ajv` + `ajv-formats`
**Currently Used In:**
- ✅ `src/ui/src/hooks/useSchemaValidation.js` - Custom validation logic
- ⚠️  Duplicates validation that could use AJV's built-in features

## Opportunities for Improvement

### HIGH PRIORITY: Backend Migration Validation

**File:** `lib/idp_common_pkg/idp_common/config_schema/migration.py`
**Issue:** NO validation after migration
**Risk:** Can produce invalid schemas that break downstream

**Current:**
```python
def migrate_legacy_to_schema(legacy_classes):
    # ... migration logic ...
    return _convert_classes_to_json_schema(migrated_classes)
    # NO VALIDATION!
```

**Proposed:**
```python
def migrate_legacy_to_schema(legacy_classes, validate=True):
    result = _convert_classes_to_json_schema(migrated_classes)
    
    if validate:
        from jsonschema import Draft202012Validator, ValidationError
        from .schema_definition import EXTRACTION_CLASS_SCHEMA
        
        validator = Draft202012Validator(EXTRACTION_CLASS_SCHEMA)
        try:
            if isinstance(result, list):
                for schema in result:
                    validator.validate(schema)
            else:
                validator.validate(result)
        except ValidationError as e:
            raise ValueError(f"Migration produced invalid schema: {e.message}")
    
    return result
```

**Impact:** Prevents invalid schemas from being created

---

### HIGH PRIORITY: Validate AWS Extensions

**File:** `lib/idp_common_pkg/idp_common/config_schema/migration.py:56-67`
**Issue:** No validation of AWS extension values
**Risk:** Invalid evaluation_method, confidence_threshold can be stored

**Current:**
```python
if "evaluation_method" in attr:
    schema_attr["x-aws-idp-evaluation-method"] = attr["evaluation_method"]
    # No validation!

if "confidence_threshold" in attr:
    threshold = attr["confidence_threshold"]
    # Weak string-to-float conversion
```

**Proposed:** Use schema definition to validate
```python
def _validate_aws_extensions(extensions: Dict[str, Any]) -> None:
    """Validate AWS IDP extensions against schema."""
    from jsonschema import Draft202012Validator, ValidationError
    
    # Extract AWS extension schema from EXTRACTION_CLASS_SCHEMA
    aws_extension_schema = {
        "type": "object",
        "properties": {
            "x-aws-idp-evaluation-method": {
                "type": "string",
                "enum": ["EXACT", "NUMERIC_EXACT", "FUZZY", "SEMANTIC"]
            },
            "x-aws-idp-confidence-threshold": {
                "type": "number",
                "minimum": 0,
                "maximum": 1
            }
        }
    }
    
    validator = Draft202012Validator(aws_extension_schema)
    try:
        validator.validate(extensions)
    except ValidationError as e:
        raise ValueError(f"Invalid AWS extension: {e.message}")
```

---

### MEDIUM PRIORITY: Frontend - Use AJV for All Validation

**File:** `src/ui/src/hooks/useSchemaValidation.js:67-133`
**Issue:** Manual validation logic duplicates what AJV can do

**Current:** Manual checks for minLength/maxLength, etc.
```javascript
if (attribute.type === 'string') {
  if (attribute.minLength !== undefined && attribute.maxLength !== undefined) {
    if (attribute.minLength > attribute.maxLength) {
      errors.push({ path: '/minLength', message: 'minLength cannot be greater than maxLength' });
    }
  }
}
```

**Proposed:** Define meta-schema and use AJV
```javascript
const ATTRIBUTE_META_SCHEMA = {
  type: 'object',
  properties: {
    type: { enum: ['string', 'number', 'integer', 'boolean', 'object', 'array', 'null'] },
    // AJV will validate all JSON Schema keywords automatically
  },
  // Add custom formats for AWS extensions
  if: { properties: { type: { const: 'string' } } },
  then: {
    properties: {
      minLength: { type: 'integer', minimum: 0 },
      maxLength: { type: 'integer', minimum: 0 }
    },
    // AJV can validate this relationship:
    if: { 
      required: ['minLength', 'maxLength']
    },
    then: {
      // Custom keyword or use ajv-keywords plugin
    }
  }
};

const validateAttribute = useCallback((attribute) => {
  const validate = ajv.compile(ATTRIBUTE_META_SCHEMA);
  const valid = validate(attribute);
  
  if (!valid) {
    return {
      valid: false,
      errors: validate.errors.map(err => ({
        path: err.instancePath,
        message: err.message
      }))
    };
  }
  
  return { valid: true, errors: [] };
}, [ajv]);
```

**Benefits:**
- Eliminate 70+ lines of manual validation
- Leverage AJV's optimized validation
- Automatically handle new JSON Schema keywords

---

### MEDIUM PRIORITY: Backend - Validate Configuration on Read

**File:** `lib/idp_common_pkg/idp_common/config/configuration_manager.py`
**Issue:** No validation when reading from DynamoDB

**Proposed:**
```python
def get_configuration(self, configuration_type: str, validate=True) -> Dict[str, Any]:
    """Get configuration with optional validation."""
    config = # ... fetch from DynamoDB ...
    
    if validate and 'classes' in config:
        from idp_common.config_schema import validate_extraction_schema
        try:
            validate_extraction_schema(config['classes'])
        except Exception as e:
            logger.error(f"Invalid config in DynamoDB: {e}")
            # Could return default or raise
    
    return config
```

---

### LOW PRIORITY: Frontend - Share Schema Definition

**Issue:** Schema definition duplicated between frontend and backend

**Current:**
- Backend: `lib/idp_common_pkg/idp_common/config_schema/schema_definition.py`
- Frontend: Partial schema in `useSchemaValidation.js`

**Proposed:**
- Generate JSON file from Python schema definition
- Import in both frontend and backend
- Single source of truth

---

## Implementation Priority

### Phase 1 (HIGH - Immediate)
1. ✅ Add validation to `migrate_legacy_to_schema()` 
2. ✅ Add AWS extension validation in migration
3. ✅ Validate after migration in configuration_resolver

### Phase 2 (MEDIUM - This Sprint)
4. ⚠️  Use AJV meta-schema in useSchemaValidation
5. ⚠️  Add validation on config read in ConfigurationManager

### Phase 3 (LOW - Future)
6. ⬜ Share schema definition between frontend/backend
7. ⬜ Add JSON Schema $ref resolution using library features

## Code Savings Estimate

- Backend validation: +50 lines (new code for safety)
- Frontend AJV improvements: -70 lines (eliminate manual validation)
- **Net:** -20 lines, +much better validation coverage
