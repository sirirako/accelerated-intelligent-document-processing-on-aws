# Test Execution Management

The Test Execution Management system provides a comprehensive interface for running, monitoring, and comparing document processing test runs directly from the web UI. This system enables users to evaluate different configurations, compare performance metrics, and analyze cost implications across multiple test executions.

## Overview

The system consists of backend Lambda functions for test execution and result processing, along with frontend components for user interaction and data visualization. It supports real-time monitoring, detailed comparisons, and export capabilities.

## Architecture

### Backend Components

#### TestRunner Lambda
- **Purpose**: Executes test runs with configurable parameters
- **Location**: `src/lambda/test_runner/index.py`
- **Functionality**:
  - Processes selected documents from the document list
  - Applies configurable test parameters
  - Manages test execution lifecycle
  - Provides status updates and progress tracking

#### TestResultsResolver Lambda
- **Purpose**: Handles GraphQL queries for test results and comparisons
- **Location**: `src/lambda/test_results_resolver/index.py`
- **Functionality**:
  - Retrieves test run data and status
  - Performs configuration comparison logic (Custom vs Default)
  - Aggregates cost and usage metrics
  - Provides service-level breakdowns
  - Supports parallel processing for performance

### GraphQL Schema
- **Location**: `src/api/schema.graphql`
- **Queries Added**:
  - `getTestRuns`: List test runs with filtering
  - `getTestRun`: Get detailed test run data
  - `compareTestRuns`: Compare multiple test runs
  - `startTestRun`: Initiate new test execution
  - `getTestRunStatus`: Real-time status monitoring

### Frontend Components

#### TestResultsList
- **Location**: `src/ui/src/components/test-results/TestResultsList.jsx`
- **Purpose**: Main interface for browsing and managing test runs
- **Features**:
  - Time period filtering (2hrs, 24hrs, 7days, 30days)
  - Multi-select functionality for comparison
  - Excel export capability
  - Real-time status updates
  - Pagination and sorting

#### TestResults
- **Location**: `src/ui/src/components/test-results/TestResults.jsx`
- **Purpose**: Detailed view for individual test runs
- **Features**:
  - Comprehensive metrics display
  - Cost and usage breakdown
  - 10-second live polling for running tests
  - Model usage analysis
  - Accuracy and confidence metrics

#### TestComparison
- **Location**: `src/ui/src/components/test-comparison/TestComparison.jsx`
- **Purpose**: Side-by-side comparison of multiple test runs
- **Features**:
  - Performance metrics comparison
  - Configuration differences analysis
  - Service Cost Breakdown with colored arrows
  - Service Usage Breakdown with detailed metrics
  - Transposed table format (metrics as rows, test runs as columns)

#### TestRunnerModal
- **Location**: `src/ui/src/components/common/TestRunnerModal.jsx`
- **Purpose**: Interface for initiating new test runs
- **Features**:
  - Document selection from current list
  - Configuration parameter input
  - Test run naming and description
  - Validation and error handling

## UI Interaction Guide

### Accessing Test Results
1. **From Document List**: Click the "Test Results" button in the top navigation
2. **Direct Navigation**: Use the main navigation menu to access Test Results section

### TestResultsList Interface

#### Time Period Filtering
- **Filter Options**: 2hrs, 24hrs, 7days, 30days dropdown
- **Auto-refresh**: List updates automatically when filter changes
- **Default View**: Shows last 24 hours of test runs

#### Test Run Selection
- **Single Selection**: Click on test run row to view details
- **Multi-Selection**: Use checkboxes to select multiple test runs
- **Select All**: Header checkbox selects/deselects all visible test runs
- **Selection Counter**: Shows "X selected" when multiple runs chosen

#### Action Buttons
- **Compare Selected**: Appears when 2+ test runs selected
- **Export to Excel**: Downloads filtered test run data
- **Run New Test**: Opens TestRunnerModal for new test execution
- **Refresh**: Manual refresh button for latest data

#### Status Indicators
- **Running**: Blue progress indicator with live updates
- **Complete**: Green checkmark with completion time
- **Failed**: Red error indicator with failure reason
- **Pending**: Gray clock icon for queued tests

### TestResults Detail View

#### Navigation
- **Breadcrumb**: Shows path back to TestResultsList
- **Test Run ID**: Clickable header linking to comparison view
- **Back Button**: Returns to previous list view

#### Live Updates
- **Auto-polling**: Updates every 10 seconds for running tests
- **Status Changes**: Real-time progress and completion updates
- **Visual Indicators**: Loading spinners during updates

#### Data Sections
- **Key Metrics**: Cost, accuracy, confidence at the top
- **Performance Metrics**: Detailed breakdown tables
- **Cost Breakdown**: Service-level cost analysis
- **Usage Breakdown**: Token and resource usage
- **Models Used**: AI models and configurations
- **Accuracy Breakdown**: Precision, recall, F1 scores

### TestComparison Interface

#### Header Navigation
- **Test Run Headers**: Clickable test run IDs link to detail views
- **Comparison Title**: Shows number of test runs being compared
- **Back to List**: Returns to TestResultsList

#### Comparison Tables
- **Transposed Format**: Metrics as rows, test runs as columns
- **Performance Metrics**: Accuracy, confidence, file counts
- **Accuracy Breakdown**: Precision, recall, F1 comparisons
- **Cost Breakdown**: Total and service-level costs
- **Usage Breakdown**: Token usage and API calls
- **Configuration Differences**: Only shows differing settings

#### Service Breakdowns
- **Service Cost Breakdown**: 
  - Format: `$baseline → $test (change%)`
  - Colored arrows: Red ↑ increases, Green ↓ decreases
  - No arrows for 0% changes
- **Service Usage Breakdown**:
  - Format: `baseline → test (change%)`
  - Lambda requests/duration, BDA pages
  - Colored percentage changes

#### Visual Elements
- **Colored Arrows**: Only arrow symbols colored, not percentages
- **Hover Effects**: Interactive elements highlight on hover
- **Responsive Layout**: Adapts to different screen sizes

### TestRunnerModal

#### Document Selection
- **Pre-selected**: Shows currently selected documents from Document List
- **Document Count**: Displays number of documents to process
- **Selection Summary**: Brief overview of selected files

#### Configuration Options
- **Test Name**: Required field for test identification
- **Description**: Optional field for test notes
- **Configuration Parameters**: Dropdown for processing options
- **Validation**: Real-time validation with error messages

#### Execution Controls
- **Start Test**: Initiates test run with selected parameters
- **Cancel**: Closes modal without starting test
- **Progress Feedback**: Shows submission status and errors

### Keyboard Shortcuts
- **Escape**: Close modals and return to previous view
- **Enter**: Submit forms and confirm actions
- **Space**: Toggle checkboxes in selection lists
- **Tab**: Navigate through interactive elements

### Mobile Responsiveness
- **Responsive Tables**: Horizontal scrolling on small screens
- **Touch Interactions**: Optimized for touch devices
- **Simplified Navigation**: Condensed menus for mobile
- **Readable Text**: Appropriate font sizes for mobile viewing

### Error Handling
- **Network Errors**: Clear messages for connectivity issues
- **Validation Errors**: Inline error messages with guidance
- **Loading States**: Spinners and progress indicators
- **Empty States**: Helpful messages when no data available

### Accessibility Features
- **Keyboard Navigation**: Full keyboard accessibility
- **Screen Reader Support**: Proper ARIA labels and descriptions
- **High Contrast**: Readable colors and contrast ratios
- **Focus Indicators**: Clear focus states for interactive elements

## Key Features

### Enhanced Test Comparison

#### Service Cost Breakdown
- Shows cost comparison at the service level (Bedrock, Lambda, BDA)
- Format: `$baseline → $test (change%)`
- Colored arrows: Red ↑ for increases, Green ↓ for decreases
- Aggregates nested cost objects automatically

#### Service Usage Breakdown
- Displays usage metrics for non-Bedrock services
- Format: `baseline → test (change%)`
- Includes Lambda requests/duration, BDA pages, etc.
- Matches TestResults.jsx format exactly

#### Visual Indicators
- **Colored Arrows**: Only arrow symbols are colored, not percentages
- **Zero Changes**: No arrows displayed for 0% changes
- **Consistent Formatting**: All sections use baseline → test (change%) format

#### Transposed Tables
- **Metrics as Rows**: Better readability for comparison
- **Test Runs as Columns**: Easy side-by-side analysis
- **Clickable Headers**: Test run IDs link to detailed views

### Configuration Comparison
- **Custom vs Default Logic**: Properly identifies configuration differences
- **Flattened Display**: Dot notation for nested configuration paths
- **Meaningful Differences**: Only shows settings that actually differ

### Real-Time Monitoring
- **Live Updates**: 10-second polling for running tests
- **Status Tracking**: Progress indicators and completion status
- **Error Handling**: Comprehensive error states and user feedback

## User Workflows

### Starting a Test Run
1. Navigate to Document List
2. Select documents for testing
3. Click "Test Results" → "Run New Test"
4. Configure test parameters in TestRunnerModal
5. Submit test run
6. Monitor progress in TestResultsList

### Viewing Test Results
1. Access TestResultsList from Document List
2. Filter by time period if needed
3. Click on test run ID for detailed view
4. Review metrics, costs, and accuracy data
5. Export to Excel if needed

### Comparing Test Runs
1. In TestResultsList, select 2+ test runs
2. Click "Compare Selected"
3. Review side-by-side comparison in TestComparison
4. Analyze performance metrics, configuration differences
5. Examine Service Cost and Usage Breakdowns
6. Use colored arrows to identify improvements/regressions

## Data Flow

### Test Execution
```
User → TestRunnerModal → TestRunner Lambda → Document Processing → Results Storage
```

### Result Retrieval
```
UI Component → GraphQL Query → TestResultsResolver Lambda → DynamoDB/S3 → Formatted Response
```

### Comparison Processing
```
TestComparison → compareTestRuns Query → Parallel Data Fetching → Configuration Analysis → Service Breakdowns
```

## Configuration

### Time Period Filters
- **2 hours**: Recent test runs for immediate feedback
- **24 hours**: Daily testing cycles
- **7 days**: Weekly analysis and trends
- **30 days**: Monthly reporting and historical analysis

### Export Options
- **Excel Format**: Comprehensive data export for external analysis
- **Filtered Data**: Respects current time period and selection filters
- **Formatted Output**: Human-readable format with proper headers

## Performance Considerations

### Backend Optimization
- **Parallel Processing**: ThreadPoolExecutor for concurrent operations
- **Efficient Queries**: Optimized DynamoDB and S3 access patterns
- **Caching**: Appropriate caching strategies for frequently accessed data

### Frontend Optimization
- **Component Cleanup**: Proper useEffect cleanup to prevent memory leaks
- **Conditional Rendering**: Efficient re-rendering based on state changes
- **Debounced Updates**: Prevents excessive API calls during user interaction

## Error Handling

### Backend Errors
- Comprehensive logging for debugging
- Graceful degradation for partial failures
- Timeout handling for long-running operations

### Frontend Errors
- User-friendly error messages
- Loading states during operations
- Fallback UI for missing data

## Testing

### Unit Tests
- **Location**: `lib/idp_common_pkg/tests/unit/`
- **Coverage**: All new functionality with proper mocking
- **Validation**: 449 tests passing, 7 skipped

### Integration Testing
- End-to-end workflow validation
- GraphQL query testing
- Component interaction testing

## Troubleshooting

### Common Issues

#### Test Run Not Starting
- Check document selection in TestRunnerModal
- Verify configuration parameters
- Review CloudWatch logs for TestRunner Lambda

#### Comparison Data Missing
- Ensure test runs have completed successfully
- Check TestResultsResolver Lambda logs
- Verify GraphQL query parameters

#### UI Performance Issues
- Check browser console for JavaScript errors
- Verify network connectivity for GraphQL queries
- Monitor component re-rendering patterns

### Debugging

#### Backend Debugging
- CloudWatch logs for Lambda functions
- DynamoDB query performance metrics
- S3 access patterns and timing

#### Frontend Debugging
- Browser developer tools
- React DevTools for component state
- Network tab for GraphQL query analysis

## Future Enhancements

### Planned Features
- Batch test execution for multiple document sets
- Advanced filtering and search capabilities
- Custom metric definitions and calculations
- Integration with external reporting systems

### Performance Improvements
- Enhanced caching strategies
- Optimized data aggregation
- Improved UI responsiveness

## Related Documentation

- [Architecture](./architecture.md) - Overall system architecture
- [Configuration](./configuration.md) - System configuration options
- [Monitoring](./monitoring.md) - Monitoring and logging capabilities
- [Evaluation Framework](./evaluation.md) - Accuracy assessment system
