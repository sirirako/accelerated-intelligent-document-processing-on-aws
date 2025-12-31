# JSON Serialization Fix - DynamicModel Error

## Issue

The evaluation function failed in Lambda with the error:
```
TypeError: Object of type DynamicModel is not JSON serializable
```

## Root Cause

When Stickler creates Pydantic models dynamically, nested object comparisons can result in Pydantic model instances within the `expected` and `actual` fields of AttributeEvaluationResult. When these are serialized to JSON for storage in S3, the default JSON serializer cannot handle Pydantic model objects.

The error occurred at line 1645 in `service.py` when trying to write evaluation results to S3:
```python
s3.write_content(
    content=result_dict,  # Contains nested Pydantic models
    bucket=output_bucket,
    key=output_key,
    content_type="application/json",
)
```

## Solution

Applied a two-part fix:

### 1. Enhanced `_convert_numpy_types()` Function

Added handling for Pydantic models to recursively serialize them:

```python
def _convert_numpy_types(obj: Any) -> Any:
    """
    Recursively convert numpy types and Pydantic models to Python native types.
    """
    import numpy as np

    if isinstance(obj, np.bool_):
        return bool(obj)
    # ... numpy handling ...
    elif hasattr(obj, "model_dump"):
        # Handle Pydantic v2 models (including DynamicModel from Stickler)
        return _convert_numpy_types(obj.model_dump())
    elif hasattr(obj, "dict"):
        # Handle Pydantic v1 models
        return _convert_numpy_types(obj.dict())
    else:
        return obj
```

### 2. Updated `model_dump()` Calls with `mode='python'`

Changed Pydantic model serialization to use `mode='python'` for complete nested serialization:

```python
# Before:
expected_dict = expected_instance.model_dump()

# After:
expected_dict = expected_instance.model_dump(mode='python')
```

The `mode='python'` parameter ensures Pydantic recursively serializes all nested models to plain Python dictionaries, preventing any Pydantic model objects from remaining in the structure.

## Files Modified

1. **lib/idp_common_pkg/idp_common/evaluation/service.py**
   - Enhanced `_convert_numpy_types()` to handle Pydantic models
   - Updated `_transform_stickler_result()` to use `model_dump(mode='python')`

## Testing

Created `test_serialization_fix.py` to verify the fix:

```bash
python test_serialization_fix.py
```

**Test Results**: ✅ ALL TESTS PASSED

The test verifies:
1. `model_dump(mode='python')` properly serializes nested Pydantic models
2. JSON serialization works without DynamicModel errors
3. `_convert_numpy_types()` handles Pydantic models recursively
4. Full evaluation result structures serialize successfully

## Impact

- ✅ Fixes Lambda evaluation function failures
- ✅ Ensures all nested Pydantic models are properly serialized
- ✅ No breaking changes to API or data structures
- ✅ Backward compatible with existing code

## Deployment

After deploying this fix, the evaluation function should:
1. Successfully serialize evaluation results to JSON
2. Store results in S3 without errors
3. Generate both JSON and Markdown reports
4. Complete document evaluation workflows

## Related

This fix is part of the sticker-eval v0.1.4 integration that adds field comparison details. The enhanced features include nested object comparisons, which surfaced this serialization issue that needed to be addressed.