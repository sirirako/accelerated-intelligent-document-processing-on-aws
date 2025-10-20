# Test Studio

The Test Studio provides a comprehensive interface for managing test sets, running tests, and analyzing results directly from the web UI. This system enables users to create reusable test sets, execute document processing tests, and compare performance metrics across multiple test runs.

## Overview

The Test Studio consists of three main sections:
1. **Test Sets**: Create and manage reusable collections of test documents
2. **Test Runner**: Execute tests with live status monitoring
3. **Test Results**: View and compare test run outcomes

The system supports real-time monitoring, prevents concurrent test execution, and maintains test state across navigation.

## Architecture

### Backend Components

#### TestRunner Lambda
- **Purpose**: Executes test runs with configurable parameters
- **Location**: `src/lambda/test_runner/index.py`
- **Functionality**:
  - Processes documents from test sets
  - Applies configurable test parameters
  - Manages test execution lifecycle
  - Provides status updates and progress tracking

#### TestResultsResolver Lambda
- **Purpose**: Handles GraphQL queries for test results and comparisons
- **Location**: `src/lambda/test_results_resolver/index.py`
- **Functionality**:
  - Retrieves test run data and status
  - Performs configuration comparison logic
  - Aggregates cost and usage metrics
  - Provides service-level breakdowns

### GraphQL Schema
- **Location**: `src/api/schema.graphql`
- **Queries Added**:
  - `getTestSets`: List available test sets
  - `getTestRuns`: List test runs with filtering
  - `getTestRun`: Get detailed test run data
  - `compareTestRuns`: Compare multiple test runs
  - `startTestRun`: Initiate new test execution
  - `getTestRunStatus`: Real-time status monitoring

### Frontend Components

#### Test Studio Layout
- **Location**: `src/ui/src/components/test-studio-layout/TestStudioLayout.jsx`
- **Purpose**: Main container with tab navigation and global test state management
- **Features**:
  - Three-tab interface (Sets, Runner, Results)
  - Global test state persistence across navigation
  - Live test status display when tests are running
  - URL-based tab navigation

#### Test Sets
- **Location**: `src/ui/src/components/test-studio-layout/TestSets.jsx`
- **Purpose**: Manage collections of test documents
- **Features**:
  - Create new test sets with file patterns
  - View existing test sets with file counts
  - Edit and delete test sets
  - File pattern validation

#### Test Runner
- **Location**: `src/ui/src/components/test-studio-layout/TestRunner.jsx`
- **Purpose**: Execute tests with selected test sets
- **Features**:
  - Test set selection dropdown
  - Single test execution (prevents concurrent runs)
  - Disabled state when test is already running
  - Warning alerts for concurrent test attempts
  - Live status integration

#### Test Results and Comparison
- **Location**: `src/ui/src/components/test-studio-layout/TestResultsAndComparison.jsx`
- **Purpose**: View and compare test run outcomes
- **Features**:
  - Test run listing with filtering
  - Multi-select for comparison
  - Detailed metrics and cost analysis
  - Export capabilities

## Test Studio Interface Guide

### Accessing Test Studio
1. **Main Navigation**: Click "Test Studio" in the main navigation menu
2. **Direct URL**: Navigate to `/#/test-studio` with optional `?tab=` parameter

### Test Sets Tab

#### Creating Test Sets
1. Click "Create Test Set" button
2. Enter test set name and description
3. Define file pattern (e.g., `*.pdf`, `invoice_*.pdf`)
4. Save test set for reuse

#### Managing Test Sets
- **View**: List shows name, pattern, and file count
- **Edit**: Modify existing test set properties
- **Delete**: Remove test sets no longer needed
- **File Count**: Automatically calculated based on pattern

### Test Runner Tab

#### Running Tests
1. **Select Test Set**: Choose from dropdown of available test sets
2. **Run Test**: Click "Run Test" button to start execution
3. **Monitor Progress**: Live status appears at top of Test Studio
4. **Wait for Completion**: Button remains disabled until test finishes

#### Test Execution States
- **Ready**: Button enabled, no test running
- **Running**: Button disabled, warning message displayed
- **Completed**: Button re-enabled, status cleared

#### Concurrent Test Prevention
- **Single Test Limit**: Only one test can run at a time
- **Disabled Button**: "Run Test" button disabled when test is active
- **Warning Message**: Alert explains why button is disabled
- **Global State**: Test state persists across tab navigation

### Test Results Tab

#### Viewing Results
- **Test Run List**: Shows recent test executions
- **Status Indicators**: Running, completed, failed states
- **Detailed View**: Click test run for comprehensive metrics
- **Time Filtering**: Filter by time periods

#### Comparing Results
- **Multi-Select**: Choose multiple test runs for comparison
- **Side-by-Side**: Compare metrics, costs, and configurations
- **Export Options**: Download results for external analysis

### Live Status Monitoring

#### Global Test State
- **Persistent State**: Test status maintained across navigation
- **Live Updates**: Real-time progress monitoring
- **Status Display**: Shows current test run ID and progress
- **Auto-Refresh**: Status updates without manual refresh

#### Navigation Behavior
- **State Persistence**: Test state survives tab switching
- **Return to Studio**: Status visible when returning to Test Studio
- **Cross-Tab Awareness**: All tabs aware of running test state

## Key Features

### Test Set Management
- **Reusable Collections**: Create test sets for repeated use
- **Pattern-Based**: Use file patterns to define document sets
- **Dynamic Counts**: Automatic file count calculation
- **Validation**: Pattern validation and error handling

### Single Test Execution
- **Concurrency Prevention**: Only one test runs at a time
- **State Management**: Global test state across navigation
- **User Feedback**: Clear indication of test status
- **Button States**: Disabled/enabled based on test activity

### Live Status Monitoring
- **Real-Time Updates**: Live progress tracking
- **Persistent Display**: Status visible across tab navigation
- **Automatic Cleanup**: Status cleared on test completion
- **Error Handling**: Failed test state management

### Enhanced Navigation
- **Tab-Based Interface**: Three distinct functional areas
- **URL Integration**: Bookmarkable tab states
- **Breadcrumb Support**: Clear navigation hierarchy
- **Responsive Design**: Works across device sizes

## User Workflows

### Creating and Running a Test
1. **Navigate to Test Studio** → Sets tab
2. **Create Test Set**: Define name, description, and file pattern
3. **Switch to Runner Tab**: Select the new test set
4. **Execute Test**: Click "Run Test" and monitor progress
5. **View Results**: Switch to Results tab when complete

### Managing Multiple Test Sets
1. **Create Multiple Sets**: Different patterns for different document types
2. **Organize by Purpose**: Separate sets for different test scenarios
3. **Reuse Sets**: Run same test set multiple times
4. **Compare Results**: Use Results tab to compare outcomes

### Monitoring Long-Running Tests
1. **Start Test**: Begin execution in Runner tab
2. **Navigate Away**: Switch to other parts of application
3. **Return to Studio**: Test status still visible
4. **Check Progress**: Live updates show current state

## Technical Implementation

### State Management
- **Global Context**: Test state in App.jsx context
- **Persistence**: State survives component unmounting
- **Synchronization**: All components use same state source
- **Cleanup**: Automatic state reset on completion

### Component Architecture
```
TestStudioLayout (Container)
├── TestSets (Tab 1)
├── TestRunner (Tab 2)
└── TestResultsAndComparison (Tab 3)
```

### Data Flow
```
User Action → TestRunner → GraphQL Mutation → Lambda → Status Update → UI Refresh
```

### Error Handling
- **Validation**: Input validation with user feedback
- **Network Errors**: Graceful handling of API failures
- **State Recovery**: Robust state management
- **User Guidance**: Clear error messages and guidance

## Configuration

### Test Set Patterns
- **Wildcards**: Use `*` for pattern matching
- **Extensions**: Filter by file type (`.pdf`, `.jpg`)
- **Prefixes**: Match filename prefixes
- **Complex Patterns**: Combine multiple criteria

### Navigation Settings
- **Default Tab**: Sets tab as entry point
- **URL Parameters**: `?tab=runner` for direct navigation
- **History Support**: Browser back/forward navigation

## Performance Considerations

### Frontend Optimization
- **Component Cleanup**: Proper useEffect cleanup
- **State Efficiency**: Minimal re-renders
- **Memory Management**: Prevent memory leaks
- **Responsive Updates**: Efficient status polling

### Backend Integration
- **GraphQL Efficiency**: Optimized queries
- **Real-Time Updates**: Efficient polling strategy
- **Error Recovery**: Robust error handling
- **Resource Management**: Proper cleanup

## Troubleshooting

### Common Issues

#### Test Won't Start
- **Check Test Set**: Ensure test set has matching files
- **Verify Selection**: Confirm test set is selected
- **Check Status**: Ensure no other test is running
- **Review Logs**: Check browser console for errors

#### Status Not Updating
- **Network Issues**: Check internet connectivity
- **GraphQL Errors**: Review network tab in browser
- **Component State**: Verify component mounting
- **Polling Issues**: Check status update frequency

#### Navigation Problems
- **URL Parameters**: Verify tab parameter format
- **Browser History**: Check back/forward navigation
- **Component Mounting**: Ensure proper component lifecycle
- **State Persistence**: Verify global state management

### Debugging

#### Frontend Debugging
- **React DevTools**: Inspect component state
- **Browser Console**: Check for JavaScript errors
- **Network Tab**: Monitor GraphQL requests
- **Component Lifecycle**: Verify mounting/unmounting

#### Backend Debugging
- **CloudWatch Logs**: Review Lambda execution logs
- **GraphQL Responses**: Check API response format
- **Database Queries**: Verify data retrieval
- **Error Handling**: Review error propagation

## Future Enhancements

### Planned Features
- **Batch Test Sets**: Multiple test set execution
- **Scheduled Tests**: Automated test execution
- **Advanced Patterns**: More complex file matching
- **Test Templates**: Reusable test configurations

### UI Improvements
- **Progress Visualization**: Enhanced progress indicators
- **Bulk Operations**: Multi-test set management
- **Advanced Filtering**: Better result filtering
- **Export Options**: More export formats

## Related Documentation

- [Architecture](./architecture.md) - Overall system architecture
- [Configuration](./configuration.md) - System configuration options
- [Monitoring](./monitoring.md) - Monitoring and logging capabilities
- [Evaluation Framework](./evaluation.md) - Accuracy assessment system
