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
- **Purpose**: Initiates test runs and queues file processing jobs
- **Location**: `src/lambda/test_runner/index.py`
- **Functionality**:
  - Validates test sets and finds matching files
  - Stores initial test run metadata with QUEUED status
  - Sends SQS message to trigger asynchronous file processing
  - Returns immediately to prevent AppSync timeout issues
  - Optimized for fast response (< 30 seconds)

#### TestFileCopier Lambda
- **Purpose**: Handles asynchronous file copying and processing initiation
- **Location**: `src/lambda/test_file_copier/index.py`
- **Functionality**:
  - Processes SQS messages from TestRunner
  - Updates test run status to PROCESSING
  - Copies baseline files for evaluation comparison
  - Copies input files to trigger document processing pipeline
  - Handles errors and updates status to FAILED if needed
  - Uses high concurrency for fast file operations

#### SQS Integration
- **TestFileCopyQueue**: Main queue for file copying jobs
- **TestFileCopyQueueDLQ**: Dead letter queue for failed operations
- **Message Format**: Contains test run ID, file pattern, bucket names, and tracking table
- **Benefits**: Reliable async processing, automatic retries, prevents AppSync timeouts

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

The Test Studio is now consolidated into a single `test-studio` directory containing all related components:

#### Test Studio Layout
- **Location**: `src/ui/src/components/test-studio/TestStudioLayout.jsx`
- **Purpose**: Main container with tab navigation and global test state management
- **Features**:
  - Three-tab interface (Sets, Runner, Results)
  - Global test state persistence across navigation
  - Live test status display when tests are running
  - URL-based tab navigation

#### Test Sets
- **Location**: `src/ui/src/components/test-studio/TestSets.jsx`
- **Purpose**: Manage collections of test documents
- **Features**:
  - Create new test sets with file patterns
  - View existing test sets with file counts
  - Edit and delete test sets
  - File pattern validation

#### Test Runner
- **Location**: `src/ui/src/components/test-studio/TestRunner.jsx`
- **Purpose**: Execute tests with selected test sets
- **Features**:
  - Test set selection dropdown
  - Single test execution (prevents concurrent runs)
  - Disabled state when test is already running
  - Warning alerts for concurrent test attempts
  - Live status integration

#### Test Results List
- **Location**: `src/ui/src/components/test-studio/TestResultsList.jsx`
- **Purpose**: Unified interface for viewing, comparing, and managing test results
- **Features**:
  - Test run listing with filtering and pagination
  - Multi-select for comparison
  - Navigation to detailed test results view
  - Delete functionality for test runs
  - Export capabilities
  - Integrated comparison modal

#### Test Results Detail
- **Location**: `src/ui/src/components/test-studio/TestResults.jsx`
- **Purpose**: Detailed view of individual test run results
- **Features**:
  - Comprehensive metrics and cost analysis
  - File-level breakdown
  - Error analysis and reporting
  - Performance metrics

#### Test Comparison
- **Location**: `src/ui/src/components/test-studio/TestComparison.jsx`
- **Purpose**: Side-by-side comparison of multiple test runs
- **Features**:
  - Configuration comparison
  - Performance metrics comparison
  - Cost analysis comparison
  - Visual difference highlighting

#### Test Runner Status
- **Location**: `src/ui/src/components/test-studio/TestRunnerStatus.jsx`
- **Purpose**: Real-time test execution monitoring
- **Features**:
  - Live progress tracking
  - Status updates across navigation
  - Completion notifications
  - Error state handling

#### Delete Test Modal
- **Location**: `src/ui/src/components/test-studio/DeleteTestModal.jsx`
- **Purpose**: Reusable confirmation modal for test-related deletions
- **Features**:
  - Supports both test runs and test sets
  - Displays item details for confirmation
  - Loading states during deletion
  - Proper error handling

## Component Consolidation

The Test Studio has been streamlined by consolidating related components:

### Previous Structure
```
components/
├── test-studio-layout/
├── test-results/
└── test-comparison/
```

### Current Structure
```
components/
└── test-studio/
    ├── TestStudioLayout.jsx
    ├── TestSets.jsx
    ├── TestRunner.jsx
    ├── TestResultsList.jsx
    ├── TestResults.jsx
    ├── TestComparison.jsx
    ├── TestRunnerStatus.jsx
    ├── DeleteTestModal.jsx
    └── index.js
```

### Merged Components
- **TestResultsAndComparison** → **TestResultsList**: The wrapper component was merged into TestResultsList since it provided duplicate functionality for navigation and comparison that TestResultsList already handled.

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
- **Delete**: Remove test sets no longer needed using DeleteTestModal
- **File Count**: Automatically calculated based on pattern

### Test Runner Tab

#### Running Tests
1. **Select Test Set**: Choose from dropdown of available test sets
2. **Run Test**: Click "Run Test" button to start execution
3. **Monitor Progress**: Live status appears at top of Test Studio via TestRunnerStatus
4. **Wait for Completion**: Button remains disabled until test finishes

#### Test Execution States
- **Ready**: Button enabled, no test running
- **QUEUED**: Test run created, file copying jobs queued in SQS
- **RUNNING**: Files being copied and documents being processed
- **COMPLETED**: Test finished successfully, button re-enabled
- **FAILED**: Test encountered errors during processing

#### Concurrent Test Prevention
- **Single Test Limit**: Only one test can run at a time
- **Disabled Button**: "Run Test" button disabled when test is active
- **Warning Message**: Alert explains why button is disabled
- **Global State**: Test state persists across tab navigation

### Test Results Tab

#### Unified Results Interface
The Results tab now provides a single, integrated interface that handles:

#### Viewing Results
- **Test Run List**: Shows recent test executions with truncated IDs and hover tooltips
- **Status Indicators**: Running, completed, failed states
- **Detailed View**: Click test run for comprehensive metrics via TestResults component
- **Time Filtering**: Filter by time periods
- **Pagination**: Configurable page sizes for large result sets

#### Comparing Results
- **Multi-Select**: Choose multiple test runs for comparison
- **Comparison Modal**: Integrated TestComparison component in modal
- **Side-by-Side**: Compare metrics, costs, and configurations
- **Export Options**: Download results for external analysis

#### Managing Results
- **Delete Functionality**: Remove test runs using DeleteTestModal
- **Bulk Operations**: Select multiple test runs for deletion
- **Confirmation**: Clear confirmation dialogs showing test run details

### Live Status Monitoring

#### Global Test State
- **Persistent State**: Test status maintained across navigation via TestRunnerStatus
- **Live Updates**: Real-time progress monitoring
- **Status Display**: Shows current test run ID and progress
- **Auto-Refresh**: Status updates without manual refresh

#### Navigation Behavior
- **State Persistence**: Test state survives tab switching
- **Return to Studio**: Status visible when returning to Test Studio
- **Cross-Tab Awareness**: All tabs aware of running test state

## Key Features

### Consolidated Architecture
- **Single Directory**: All test-related components in one location
- **Reduced Complexity**: Eliminated duplicate wrapper components
- **Improved Maintainability**: Cleaner import paths and dependencies
- **Reusable Components**: Shared components like DeleteTestModal

### Enhanced User Experience
- **Truncated IDs**: Test run IDs displayed as shortened versions with full ID on hover
- **Consistent Modals**: Unified delete confirmation across test sets and test runs
- **Integrated Navigation**: Seamless flow between list, detail, and comparison views
- **Responsive Design**: Proper text truncation and column sizing

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
- **Real-Time Updates**: Live progress tracking via TestRunnerStatus
- **Persistent Display**: Status visible across tab navigation
- **Automatic Cleanup**: Status cleared on test completion
- **Error Handling**: Failed test state management

## User Workflows

### Creating and Running a Test
1. **Navigate to Test Studio** → Sets tab
2. **Create Test Set**: Define name, description, and file pattern
3. **Switch to Runner Tab**: Select the new test set
4. **Execute Test**: Click "Run Test" and monitor progress
5. **View Results**: Switch to Results tab when complete

### Managing Test Results
1. **View Results List**: Browse recent test runs with truncated IDs
2. **Select for Comparison**: Multi-select test runs for analysis
3. **Compare Results**: Use integrated comparison modal
4. **Delete Old Results**: Clean up using bulk delete functionality
5. **Export Data**: Download results for external analysis

### Monitoring Long-Running Tests
1. **Start Test**: Begin execution in Runner tab
2. **Navigate Away**: Switch to other parts of application
3. **Return to Studio**: Test status still visible via TestRunnerStatus
4. **Check Progress**: Live updates show current state

## Technical Implementation

### Component Architecture
```
TestStudioLayout (Container)
├── TestSets (Tab 1)
├── TestRunner (Tab 2) + TestRunnerStatus
└── TestResultsList (Tab 3)
    ├── TestResults (Detail View)
    ├── TestComparison (Comparison Modal)
    └── DeleteTestModal (Confirmation)
```

### State Management
- **Global Context**: Test state in App.jsx context
- **Persistence**: State survives component unmounting
- **Synchronization**: All components use same state source
- **Cleanup**: Automatic state reset on completion

### Data Flow
```
User Action → TestRunner → SQS Message → TestFileCopier → File Operations → Status Updates → UI Refresh
```

### Status Flow
```
QUEUED (TestRunner) → RUNNING (TestFileCopier) → COMPLETED/FAILED (Document Processing)
```

### SQS Message Format
```json
{
  "testRunId": "test-set-1-20231107-162647",
  "filePattern": "lending*",
  "inputBucket": "input-bucket-name",
  "baselineBucket": "baseline-bucket-name", 
  "trackingTable": "tracking-table-name"
}
```

### Import Structure
All components now use local imports within the test-studio directory:
```javascript
// Before consolidation
import TestResults from '../test-results/TestResults';
import TestComparison from '../test-comparison/TestComparison';

// After consolidation
import TestResults from './TestResults';
import TestComparison from './TestComparison';
```

## Performance Considerations

### Frontend Optimization
- **Reduced Bundle Size**: Consolidated components reduce import overhead
- **Component Cleanup**: Proper useEffect cleanup
- **State Efficiency**: Minimal re-renders
- **Memory Management**: Prevent memory leaks
- **Responsive Updates**: Efficient status polling

### UI Performance
- **Text Truncation**: CSS-based truncation for long test run IDs
- **Table Optimization**: Proper column sizing and wrapping prevention
- **Modal Efficiency**: Lazy loading of comparison components
- **Pagination**: Configurable page sizes for large datasets

## Troubleshooting

### Common Issues

#### Component Import Errors
- **Check Paths**: Verify import paths after consolidation
- **Missing Components**: Ensure all components moved to test-studio directory
- **Index Exports**: Verify index.js exports are updated

#### Test Run Display Issues
- **Truncated IDs**: Hover over shortened IDs to see full test run ID
- **Wrapping Text**: Check table wrapLines={false} setting
- **Column Width**: Adjust column widths for proper display

#### Navigation Problems
- **Tab Navigation**: Verify TestStudioLayout tab routing
- **Modal State**: Check modal visibility state management
- **Back Navigation**: Ensure proper state cleanup on navigation

## Related Documentation

- [Architecture](./architecture.md) - Overall system architecture
- [Configuration](./configuration.md) - System configuration options
- [Monitoring](./monitoring.md) - Monitoring and logging capabilities
- [Evaluation Framework](./evaluation.md) - Accuracy assessment system
