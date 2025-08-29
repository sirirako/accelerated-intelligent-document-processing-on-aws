# GenAI IDP Accelerator - Active Context

## Current Task Focus

**Feature Implementation**: Custom Prompt Generator Lambda Functions for Patterns 2 & 3

**Task Status**: ✅ **COMPLETED** - Successfully implemented custom business logic integration for extraction prompts

## Feature Overview

Added capability for users to plug in custom Lambda functions to customize system and task prompts used in extraction inferences for Pattern 2 and Pattern 3. This enables customers to implement their own business logic while leveraging the existing IDP infrastructure.

## Implementation Summary

### Core Changes Made

#### 1. ExtractionService Enhancements (`lib/idp_common_pkg/idp_common/extraction/service.py`)
- **Added Lambda invocation method**: `_invoke_custom_prompt_lambda()` with comprehensive error handling
- **Integrated Lambda workflow**: Modified `process_document_section()` to check for and use custom Lambda
- **Fail-fast error handling**: Lambda failures cause extraction to fail with detailed error messages
- **Comprehensive logging**: Added detailed logging for Lambda invocations and errors
- **Backward compatibility**: Default prompt logic preserved when no Lambda is configured

#### 2. CloudFormation Template Updates
**Pattern 2 (`patterns/pattern-2/template.yaml`):**
- Added IAM permission for ExtractionFunction to invoke Lambda functions with `GENAIIDP-*` naming
- Added configuration schema for `custom_prompt_lambda_arn` field with validation pattern

**Pattern 3 (`patterns/pattern-3/template.yaml`):**
- Added identical IAM permission for ExtractionFunction  
- Added identical configuration schema for UI integration

#### 3. Documentation and Examples
- **Example Lambda Function**: Created comprehensive example showing multiple use cases
- **Complete Documentation**: Detailed README with architecture, examples, and best practices
- **Integration Guide**: Step-by-step deployment and configuration instructions

### Key Technical Details

**Lambda Interface:**
```json
// Input to custom Lambda
{
  "config": {}, // Complete configuration object
  "prompt_placeholders": {
    "DOCUMENT_TEXT": "...",
    "DOCUMENT_CLASS": "...", 
    "ATTRIBUTE_NAMES_AND_DESCRIPTIONS": "..."
  },
  "default_task_prompt_content": [...], // Fully resolved default content
  "serialized_document": {} // Complete Document object
}

// Required output from Lambda  
{
  "system_prompt": "custom system prompt",
  "task_prompt_content": [...] // Custom content array
}
```

**IAM Permission Pattern:**
```yaml
- Effect: Allow
  Action: lambda:InvokeFunction
  Resource: !Sub "arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:GENAIIDP-*"
  Condition:
    StringLike:
      "lambda:FunctionName": "GENAIIDP-*"
```

**Configuration Schema Addition:**
```yaml
custom_prompt_lambda_arn:
  type: string
  description: "(Optional) ARN of Lambda function to generate custom extraction prompts..."
  pattern: "^(|arn:aws:lambda:[^:]+:[^:]+:function:GENAIIDP-.*)$"
```

## Business Value

### Extensibility Benefits
- **Custom Business Logic**: Customers can implement domain-specific processing rules
- **External Integration**: Lambda can query databases, APIs, or other systems for context
- **Conditional Processing**: Different prompts based on document content or metadata
- **Regulatory Compliance**: Apply industry-specific prompt requirements
- **Multi-Tenancy**: Customer-specific prompt customization in shared environments

### Use Case Examples
- **Financial Services**: Regulatory compliance prompts, multi-currency handling
- **Healthcare**: HIPAA-compliant prompts, medical terminology enhancement
- **Legal**: Jurisdiction-specific processing, contract type specialization
- **Insurance**: Policy-specific extraction, claims processing customization

## Security and Compliance

### Security Features
- **Scoped IAM permissions**: Only functions with `GENAIIDP-*` naming can be invoked
- **Fail-safe operation**: Lambda failures cause extraction to fail (no silent errors)
- **Audit trail**: Comprehensive logging of all Lambda invocations
- **Input validation**: Lambda response structure is validated

### Naming Convention Enforcement
- **Required prefix**: `GENAIIDP-*` enforced via IAM condition
- **Pattern validation**: CloudFormation schema validates ARN format
- **Security boundary**: Prevents invocation of arbitrary Lambda functions

## Next Steps (Future Enhancements)
1. **Pattern 1 Support**: Extend to BDA-based Pattern 1 if requested
2. **Classification Customization**: Similar Lambda support for classification prompts
3. **Assessment Customization**: Custom Lambda for assessment prompts
4. **Prompt Caching**: Implement response caching for identical inputs
5. **Async Processing**: Support for asynchronous Lambda invocations

## Implementation Files Modified
- `lib/idp_common_pkg/idp_common/extraction/service.py` - Core Lambda integration
- `patterns/pattern-2/template.yaml` - IAM permissions and schema
- `patterns/pattern-3/template.yaml` - IAM permissions and schema  
- `examples/custom-prompt-lambda/` - Documentation and example code

## Testing Validation
- ✅ Python syntax validation passed
- ✅ CloudFormation template structure validated
- ✅ Example Lambda function created with comprehensive use cases
- ✅ Documentation created with deployment guide

This feature is production-ready and maintains full backward compatibility while providing powerful extensibility for customer-specific requirements.
