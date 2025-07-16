# Natural Language Analytics Feature Implementation Plan

## Overview
This document outlines the implementation plan for adding a natural language analytics feature to the GenAI IDP Accelerator. This feature will allow users to query document processing analytics using natural language and receive interactive visualizations and insights.

## Architecture

### Components
1. **Frontend**: New React component for analytics interface
2. **GraphQL API**: Extended schema with new query and subscription types
3. **Request Handler Lambda**: Fast Lambda to create analytics jobs
4. **Analytics Processor Lambda**: Long-running Lambda to process analytics queries
5. **DynamoDB Table**: For tracking analytics job status
6. **AI Agent**: Powered by the Strands package to interpret queries and generate responses
7. **Data Source**: Amazon Athena for querying the reporting database

### Asynchronous Processing Pattern
Due to AppSync's 30-second timeout limitation and the potentially long-running nature of analytics queries, we'll implement an asynchronous processing pattern:

1. User submits query through the UI
2. Request Handler Lambda creates a job record and returns a job ID
3. Analytics Processor Lambda is invoked asynchronously to handle the actual processing
4. Frontend polls for job status or uses GraphQL subscription
5. When complete, results are stored in DynamoDB and delivered to the frontend

This approach serves as a reference architecture for future agentic developments in the IDP accelerator where processes may take longer than 30 seconds to complete.

### Data Flow
1. User enters natural language query in the UI
2. Query is sent to AppSync GraphQL API
3. AppSync invokes the Request Handler Lambda
4. Request Handler Lambda:
   - Creates a job record in DynamoDB with status "PENDING"
   - Invokes the Analytics Processor Lambda asynchronously
   - Returns job ID to the frontend
5. Analytics Processor Lambda:
   - Updates job status to "PROCESSING"
   - Uses Strands to interpret the query and generate Athena SQL
   - Executes the query against the reporting database
   - Formats results as interactive visualization data
   - Updates job record with results and status "COMPLETED"
   - Publishes update to AppSync to trigger subscription
6. Frontend receives completion notification and renders visualization

## Data Formats



### Response Types
1. **Text**: Simple text responses for questions with scalar answers
2. **Table**: Structured data for tabular results
3. **PlotData**: JSON structure containing data series, labels, and visualization parameters

## Code Modifications

### Files to Create
1. **Lambda Functions**:
   - `/src/lambda/analytics_request_handler/` (Fast Lambda for job creation)
   - `/src/lambda/analytics_processor/` (Long-running Lambda for query processing)
2. **GraphQL Schema Extension**: Update to `/src/api/schema.graphql`
3. **DynamoDB Table**: New table for analytics job tracking
4. **Frontend Components**:
   - `/src/ui/src/components/analytics-panel/*`

### Files to Modify
1. **CloudFormation Template**: Add new Lambda functions, DynamoDB table, and AppSync resources
2. **Navigation Component**: Add analytics tab
3. **Route Configuration**: Add route for analytics page
4. **GraphQL Queries and Subscriptions**: Add new definitions

## Dependencies
- **Strands**: AI agent framework for query interpretation and visualization generation
- **React Charting Library**: For frontend visualization (Recharts, Plotly.js, or similar)
- **AWS SDK**: For Athena, Bedrock, and DynamoDB integration

## Implementation Phases
1. **Backend Infrastructure**:
   - Create DynamoDB table for job tracking
   - Implement Request Handler Lambda
   - Implement Analytics Processor Lambda
   - Add AppSync resolvers and schema extensions

2. **AI Agent Development**:
   - Integrate Strands package
   - Implement query interpretation (prompt engineering etc)
   - Build Athena query generation
   - Create visualization data formatters

3. **Frontend Development**:
   - Create analytics UI components
   - Implement job status tracking
   - Add visualization rendering
   - Add navigation and routing

4. **Testing & Refinement**:
   - Test with various query types and complexities
   - Optimize performance
   - Refine visualization options

## Security Considerations
- Lambda functions will require appropriate IAM permissions for Athena, Bedrock, DynamoDB, and S3
- Maintain existing authentication through Cognito
- Scope Athena permissions to only the reporting database
- Implement job ownership validation to prevent unauthorized access to job results

## User Experience
- Provide immediate feedback when queries are submitted
- Show job status and estimated completion time
- Include query suggestions and examples
- Support visualization customization where appropriate
- Maintain responsive design for all device types