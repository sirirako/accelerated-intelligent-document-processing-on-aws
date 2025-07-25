// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import React, { useEffect, useRef } from 'react';
import PropTypes from 'prop-types';
import { Container, Header, Box, Spinner, SpaceBetween } from '@awsui/components-react';

const AgentMessagesDisplay = ({ agentMessages, isProcessing }) => {
  const messagesEndRef = useRef(null);

  // Split assistant messages that contain both text and tool use
  const splitAssistantMessage = (message) => {
    const { content } = message;

    // If content is a string, check if it contains tool use JSON
    if (typeof content === 'string') {
      // Look for tool use patterns in the string
      const toolUseRegex = /\{"toolUse":\{[^}]+\}\}/g;
      const matches = content.match(toolUseRegex);

      if (matches && matches.length > 0) {
        const messages = [];
        let remainingContent = content;

        matches.forEach((match) => {
          // Split the content at the tool use
          const parts = remainingContent.split(match);

          // Add text part if it exists and has meaningful content
          if (parts[0] && parts[0].trim()) {
            messages.push({
              ...message,
              content: parts[0].trim(),
            });
          }

          // Parse and add tool use message
          try {
            const toolUse = JSON.parse(match);
            const toolName = toolUse.toolUse?.name || 'unknown';
            messages.push({
              ...message,
              role: 'tool',
              content: `Tool request initiated for tool: ${toolName}`,
              tool_name: toolName,
              timestamp: message.timestamp,
            });
          } catch (error) {
            // If parsing fails, include the raw JSON as assistant message
            messages.push({
              ...message,
              content: match,
            });
          }

          remainingContent = parts[1] || '';
        });

        // Add any remaining content
        if (remainingContent && remainingContent.trim()) {
          messages.push({
            ...message,
            content: remainingContent.trim(),
          });
        }

        return messages.length > 0 ? messages : [message];
      }
    }

    // If content is an array, process each item
    if (Array.isArray(content)) {
      const messages = [];
      let textParts = [];

      content.forEach((item) => {
        if (typeof item === 'string') {
          textParts.push(item);
        } else if (item && typeof item === 'object' && item.text) {
          textParts.push(item.text);
        } else if (item && typeof item === 'object' && item.toolUse) {
          // Add text content if we have any
          if (textParts.length > 0) {
            const textContent = textParts.join('\n').trim();
            if (textContent) {
              messages.push({
                ...message,
                content: textContent,
              });
            }
            textParts = [];
          }

          // Add tool use message
          const toolName = item.toolUse?.name || 'unknown';
          messages.push({
            ...message,
            role: 'tool',
            content: `${toolName}`,
            tool_name: toolName,
            timestamp: message.timestamp,
          });
        }
      });

      // Add any remaining text content
      if (textParts.length > 0) {
        const textContent = textParts.join('\n').trim();
        if (textContent) {
          messages.push({
            ...message,
            content: textContent,
          });
        }
      }

      return messages.length > 0 ? messages : [message];
    }

    // For other content types, return as-is
    return [message];
  };

  // Parse agent messages from JSON string and split combined messages
  const parseMessages = (messagesString) => {
    if (!messagesString) return [];

    try {
      const parsed = JSON.parse(messagesString);
      const rawMessages = Array.isArray(parsed) ? parsed : [];

      // Process messages to split assistant messages that contain tool use
      const processedMessages = [];

      rawMessages.forEach((message) => {
        // Skip messages with empty or invalid content
        if (
          !message.content ||
          (Array.isArray(message.content) && message.content.length === 0) ||
          (typeof message.content === 'string' && !message.content.trim())
        ) {
          return;
        }

        if (message.role === 'assistant' && message.content) {
          const splitMessages = splitAssistantMessage(message);
          processedMessages.push(...splitMessages);
        } else {
          processedMessages.push(message);
        }
      });

      return processedMessages;
    } catch (error) {
      return [];
    }
  };

  const messages = parseMessages(agentMessages);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isProcessing]);

  // Format timestamp for display
  const formatTimestamp = (timestamp) => {
    if (!timestamp) return '';
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString();
    } catch (error) {
      return timestamp;
    }
  };

  // Get role display name and styling
  const getRoleInfo = (role) => {
    switch (role) {
      case 'user':
        return { display: 'User', color: '#0073bb', icon: '👤' };
      case 'assistant':
        return { display: 'Assistant', color: '#037f0c', icon: '🤖' };
      case 'tool':
        return { display: 'Tool', color: '#8b5a00', icon: '🔧' };
      default:
        return { display: role || 'Unknown', color: '#666', icon: '❓' };
    }
  };

  // Extract text content from message content (handles both string and object formats)
  const extractTextContent = (content) => {
    if (!content) return '<No content>';

    // If content is a string, return it directly
    if (typeof content === 'string') {
      return content;
    }

    // If content is an array, extract text from each item
    if (Array.isArray(content)) {
      const textParts = [];

      content.forEach((item) => {
        if (typeof item === 'string') {
          textParts.push(item);
        } else if (item && typeof item === 'object' && item.text) {
          textParts.push(item.text);
        } else if (item && typeof item === 'object' && !item.toolUse) {
          // For other objects that aren't toolUse, stringify them
          textParts.push(JSON.stringify(item));
        }
        // Skip toolUse objects as they're handled separately
      });

      const result = textParts.join('\n').trim();
      return result || '<No text content>';
    }

    // If content is an object with a text property, extract it
    if (typeof content === 'object' && content.text) {
      return content.text;
    }

    // For any other object, stringify it
    if (typeof content === 'object') {
      return JSON.stringify(content, null, 2);
    }

    return String(content);
  };

  // Render individual message
  const renderMessage = (message, index) => {
    const roleInfo = getRoleInfo(message.role);
    const timestamp = formatTimestamp(message.timestamp);
    let textContent = extractTextContent(message.content);

    // For tool messages, if we have a tool_name, show it more prominently
    if (message.role === 'tool' && message.tool_name) {
      // If the content is just a generic success message, show the tool name instead
      if (
        textContent === "Tool completed with status 'success'." ||
        textContent.includes('Tool completed with status')
      ) {
        textContent = `Tool request initiated for tool: ${message.tool_name}`;
      }
    }

    // Create a unique key for this message
    const messageKey = `${message.role}-${message.sequence_number}-${index}-${message.timestamp}`;

    return (
      <Box key={messageKey} padding={{ vertical: 'xs', horizontal: 's' }}>
        <div
          style={{
            borderLeft: `3px solid ${roleInfo.color}`,
            paddingLeft: '8px',
            marginBottom: '4px',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              marginBottom: '2px',
              fontSize: '13px',
              fontWeight: 'bold',
              color: roleInfo.color,
            }}
          >
            <span style={{ marginRight: '4px' }}>{roleInfo.icon}</span>
            <span>{roleInfo.display}</span>
            {timestamp && (
              <span
                style={{
                  marginLeft: '8px',
                  fontSize: '11px',
                  color: '#666',
                  fontWeight: 'normal',
                }}
              >
                {timestamp}
              </span>
            )}
            {message.tool_name && (
              <span
                style={{
                  marginLeft: '6px',
                  fontSize: '11px',
                  backgroundColor: '#f0f0f0',
                  padding: '1px 4px',
                  borderRadius: '2px',
                  fontWeight: 'normal',
                }}
              >
                {message.tool_name}
              </span>
            )}
          </div>
          <div
            style={{
              fontSize: '13px',
              lineHeight: '1.3',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {textContent}
          </div>
        </div>
      </Box>
    );
  };

  if (!messages.length && !isProcessing) {
    return null;
  }

  return (
    <Container
      header={
        <Header variant="h3" description="Real-time agent conversation">
          Agent Thought Process
        </Header>
      }
    >
      <div
        style={{
          backgroundColor: '#fafafa',
          border: '1px solid #e0e0e0',
          borderRadius: '4px',
          height: '300px',
          overflowY: 'auto',
          fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace',
          padding: '4px',
        }}
      >
        <SpaceBetween size="none">
          {messages.length > 0 ? (
            messages.map((message, index) => renderMessage(message, index))
          ) : (
            <Box textAlign="center" padding="s" color="text-body-secondary">
              <em>Waiting for agent to start...</em>
            </Box>
          )}

          {isProcessing && (
            <Box padding={{ vertical: 'xs', horizontal: 's' }} textAlign="center">
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#666',
                  fontSize: '12px',
                }}
              >
                <Spinner size="normal" />
                <span style={{ marginLeft: '6px' }}>Agent is thinking...</span>
              </div>
            </Box>
          )}

          {/* Invisible element to scroll to */}
          <div ref={messagesEndRef} />
        </SpaceBetween>
      </div>
    </Container>
  );
};

AgentMessagesDisplay.propTypes = {
  agentMessages: PropTypes.string,
  isProcessing: PropTypes.bool,
};

AgentMessagesDisplay.defaultProps = {
  agentMessages: null,
  isProcessing: false,
};

export default AgentMessagesDisplay;
