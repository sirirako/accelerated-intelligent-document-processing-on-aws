# Active Context

## Current Work Focus
Centralized Pricing Configuration System - COMPLETED

## Recent Changes

### Pricing Configuration System Implementation (COMPLETED)

Implemented a full centralized pricing configuration system that mirrors the existing Configuration UI pattern:

#### Backend Changes:
1. **Constants** (`lib/idp_common_pkg/idp_common/config/constants.py`):
   - Added `CONFIG_TYPE_DEFAULT_PRICING = "DefaultPricing"` 
   - Added `CONFIG_TYPE_CUSTOM_PRICING = "CustomPricing"`

2. **ConfigurationManager** (`lib/idp_common_pkg/idp_common/config/configuration_manager.py`):
   - Added `get_merged_pricing()` - returns DefaultPricing merged with CustomPricing deltas
   - Added `save_custom_pricing(pricing_config)` - saves user overrides to CustomPricing
   - Added `delete_custom_pricing()` - deletes CustomPricing (for restore to defaults)

3. **update_configuration Lambda** (`src/lambda/update_configuration/index.py`):
   - Changed to store pricing as "DefaultPricing" instead of "Pricing" at deployment time

4. **configuration_resolver Lambda** (`src/lambda/configuration_resolver/index.py`):
   - Updated `handle_get_pricing()` to return both `pricing` (merged) and `defaultPricing`
   - `handle_update_pricing()` saves to CustomPricing (deltas only)
   - `handle_restore_default_pricing()` deletes CustomPricing

5. **GraphQL Schema** (`src/api/schema.graphql`):
   - Added `defaultPricing: AWSJSON` field to PricingResponse type

#### Frontend Changes:
1. **GraphQL Queries**:
   - `getPricing.js` - Updated to request `defaultPricing` field
   - `restoreDefaultPricing.js` - NEW mutation for restore functionality

2. **use-pricing.js Hook**:
   - Added `defaultPricing` state
   - Added `restoreDefaultPricing()` function
   - Returns both `pricing` and `defaultPricing` for UI diff/restore features

3. **PricingLayout.jsx** - Enhanced to match Configuration UI features:
   - **Form/JSON/YAML Views** - Already existed
   - **Import/Export** - Already existed
   - **Changed field highlighting** - NEW: Shows "Modified" indicator with blue StatusIndicator
   - **Restore default per field** - NEW: Popover with default value and "Reset to default" button
   - **Restore All Defaults button** - NEW: Confirmation modal, disabled when no customizations

## Design Pattern

The pricing system follows the same DefaultPricing/CustomPricing pattern as configuration:
- **DefaultPricing**: Full baseline stored at deployment time from `config_library/pricing.yaml`
- **CustomPricing**: Only stores user overrides (deltas from default)
- **Reset to default**: Simply DELETE CustomPricing record (no copy needed)
- **Reading**: Backend merges DefaultPricing + CustomPricing and returns both for UI

## Key Files Modified
- `lib/idp_common_pkg/idp_common/config/constants.py`
- `lib/idp_common_pkg/idp_common/config/configuration_manager.py`
- `src/lambda/update_configuration/index.py`
- `src/lambda/configuration_resolver/index.py`
- `src/api/schema.graphql`
- `src/ui/src/graphql/queries/getPricing.js`
- `src/ui/src/graphql/queries/restoreDefaultPricing.js` (NEW)
- `src/ui/src/hooks/use-pricing.js`
- `src/ui/src/components/pricing-layout/PricingLayout.jsx`

## UI Features Comparison

| Feature | Configuration UI | Pricing UI |
|---------|-----------------|------------|
| Form View | ✅ | ✅ |
| JSON View | ✅ | ✅ |
| YAML View | ✅ | ✅ |
| Import | ✅ | ✅ |
| Export | ✅ | ✅ |
| Changed field highlighting | ✅ | ✅ |
| Restore default per field | ✅ | ✅ |
| Restore All Defaults | ✅ | ✅ |
| Save as Default | ✅ | N/A (not needed for pricing) |
| Config Library | ✅ | N/A (not applicable) |

## Next Steps
- None - Implementation complete
- Ready for testing in deployed environment