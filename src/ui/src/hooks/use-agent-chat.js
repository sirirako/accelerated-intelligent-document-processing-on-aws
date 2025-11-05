// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState, useRef } from 'react';
import { generateClient } from 'aws-amplify/api';
import { ConsoleLogger } from 'aws-amplify/utils';
import { v4 as uuidv4 } from 'uuid';

import { SEND_AGENT_MESSAGE, ON_AGENT_MESSAGE_UPDATE } from '../graphql/queries/agentChatQueries';
import { GET_AGENT_CHAT_MESSAGES } from '../graphql/queries/agentChatSessionQueries';

const logger = new ConsoleLogger('useAgentChat');
const client = generateClient();

const useAgentChat = (config = {}) => {
  // Default configuration for backward compatibility
  const defaultConfig = {
    agentType: 'idp-help',
    mutation: SEND_AGENT_MESSAGE,
    subscription: ON_AGENT_MESSAGE_UPDATE,
    method: 'chat',
  };

  const agentConfig = { ...defaultConfig, ...config };

  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [waitingForResponse, setWaitingForResponse] = useState(false);
  const [error, setError] = useState(null);
  const [sessionId, setSessionId] = useState(uuidv4());
  const sentMessagesRef = useRef(new Set());

  // Parse JSON from message content and extract responseType
  const parseResponseData = (content) => {
    try {
      // Look for JSON objects containing responseType with proper bracket matching
      const findJsonWithResponseType = (text) => {
        const startIndex = text.indexOf('"responseType"');
        if (startIndex === -1) return null;

        // Find the opening brace before responseType
        let openBraceIndex = -1;
        for (let i = startIndex; i >= 0; i -= 1) {
          if (text[i] === '{') {
            openBraceIndex = i;
            break;
          }
        }

        if (openBraceIndex === -1) return null;

        // Find the matching closing brace
        let braceCount = 0;
        let closeBraceIndex = -1;

        for (let j = openBraceIndex; j < text.length; j += 1) {
          if (text[j] === '{') {
            braceCount += 1;
          } else if (text[j] === '}') {
            braceCount -= 1;
            if (braceCount === 0) {
              closeBraceIndex = j;
              break;
            }
          }
        }

        if (closeBraceIndex === -1) return null;

        return text.substring(openBraceIndex, closeBraceIndex + 1);
      };

      const jsonStr = findJsonWithResponseType(content);

      if (jsonStr) {
        const parsed = JSON.parse(jsonStr);

        if (parsed.responseType) {
          // Remove the JSON from the original content to get text content
          const textContent = content.replace(jsonStr, '').trim();

          let processedData;

          if (parsed.responseType === 'plotData') {
            // Format plotData to match PlotDisplay component expectations
            processedData = {
              data: parsed.data || parsed,
              options: parsed.options || {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                  title: {
                    display: true,
                    text: parsed.title || 'Chart',
                  },
                },
              },
              type: parsed.type || 'line',
            };
          } else {
            // For other types (table, etc.), use data as-is
            processedData = parsed.data || parsed.tableData || parsed.plotData || parsed;
          }

          return {
            responseType: parsed.responseType,
            data: processedData,
            textContent,
          };
        }
      }

      return null;
    } catch (parseError) {
      console.warn('Failed to parse response data:', parseError);
      return null;
    }
  };

  // Handle streaming messages with proper phase management
  const handleStreamingMessage = (newMessage) => {
  

    setMessages((prevMessages) => {
      const isFinalMessage = !newMessage.isProcessing;

      if (isFinalMessage) {
        setWaitingForResponse(false);

        // Parse the final message content for responseType
        const parsedData = parseResponseData(newMessage.content);

        // Update existing messages as not processing and apply parsed data if available
        return prevMessages.map((msg) => {
          if (msg.role === 'assistant' && msg.isProcessing && msg.sessionId === newMessage.sessionId) {
            const updatedMsg = { ...msg, isProcessing: false };

            // If we have parsed data, update the message with structured data
            if (parsedData) {
              updatedMsg.parsedData = parsedData;
              updatedMsg.content = parsedData.textContent || msg.content;
            }

            return updatedMsg;
          }
          return msg;
        });
      }

      // Check if this message contains structured data start marker
      const hasStructuredDataStart = newMessage.content.includes('"type": "structured_data_start"');

      // Check if this message contains subagent markers
      const hasSubagentStart = newMessage.content.includes('"type": "subagent_start"');
      const hasSubagentEnd = newMessage.content.includes('"type": "subagent_end"');

      if (hasStructuredDataStart) {
        // This message contains structured_data_start - mark message to stop displaying content
        try {
          const structuredDataRegex = /\{[^{}]*"type":\s*"structured_data_start"[^{}]*\}/;
          const structuredDataMatch = newMessage.content.match(structuredDataRegex);

          if (structuredDataMatch) {
            const structuredDataInfo = JSON.parse(structuredDataMatch[0]);

            // Find or create the streaming message to mark it
            const streamingIndex = prevMessages.findIndex(
              (msg) =>
                msg.role === 'assistant' && msg.isProcessing && msg.sessionId === newMessage.sessionId && msg.messageType !== 'tool_use',
            );

            const updatedMessages = [...prevMessages];

            if (streamingIndex >= 0) {
              // Mark existing message
              updatedMessages[streamingIndex] = {
                ...updatedMessages[streamingIndex],
                awaitingStructuredData: true,
                structuredDataType: structuredDataInfo.responseType,
              };
            } else {
              // Create new message marked to await structured data
              const newMsg = {
                role: 'assistant',
                content: '',
                messageType: 'text',
                toolUseData: null,
                isProcessing: true,
                sessionId: newMessage.sessionId,
                timestamp: newMessage.timestamp,
                id: `${newMessage.timestamp}-structured`,
                awaitingStructuredData: true,
                structuredDataType: structuredDataInfo.responseType,
              };
              updatedMessages.push(newMsg);
            }

            return updatedMessages;
          }
        } catch (e) {
          console.warn('Failed to parse structured_data_start JSON:', e);
        }
      }

      if (hasSubagentStart) {
        // This message contains subagent_start - parse it and create tool use message
        try {
          const startRegex = /\{[^{}]*"type":\s*"subagent_start"[^{}]*\}/;
          const startMatch = newMessage.content.match(startRegex);

          if (startMatch) {
            const startData = JSON.parse(startMatch[0]);

            // Find the last regular message to finalize it
            const lastRegularIndex = prevMessages.findIndex(
              (msg) =>
                msg.role === 'assistant' && msg.isProcessing && msg.sessionId === newMessage.sessionId && msg.messageType !== 'tool_use',
            );

            const updatedMessages = [...prevMessages];

            if (lastRegularIndex >= 0) {
              // Finalize the last regular message
              updatedMessages[lastRegularIndex] = {
                ...updatedMessages[lastRegularIndex],
                isProcessing: false,
              };
            }

            // Create new tool use message
            const toolUseMessage = {
              role: 'assistant',
              content: '',
              messageType: 'tool_use',
              toolUseData: {
                ...startData,
                toolContent: '',
              },
              isProcessing: true,
              sessionId: newMessage.sessionId,
              timestamp: newMessage.timestamp,
              id: `${newMessage.timestamp}-tool`,
            };

            return [...updatedMessages, toolUseMessage];
          }
        } catch (e) {
          console.warn('Failed to parse subagent_start JSON:', e);
        }
      } else if (hasSubagentEnd) {
        // This message contains subagent_end - finalize tool use and potentially create new message
        const updatedMessages = [...prevMessages];

        // Find the current tool use message
        const toolUseIndex = updatedMessages.findIndex(
          (msg) => msg.role === 'assistant' && msg.isProcessing && msg.sessionId === newMessage.sessionId && msg.messageType === 'tool_use',
        );

        if (toolUseIndex >= 0) {
          // Mark tool use as complete (don't add the subagent_end JSON to content)
          updatedMessages[toolUseIndex] = {
            ...updatedMessages[toolUseIndex],
            isProcessing: false,
            timestamp: newMessage.timestamp,
          };

          // Extract any content after the subagent_end JSON
          const endRegex = /\{[^{}]*"type":\s*"subagent_end"[^{}]*\}/;
          const contentAfterEnd = newMessage.content.replace(endRegex, '').trim();

          // If there's content after subagent_end, create a new streaming message
          if (contentAfterEnd) {
            const postToolMessage = {
              role: 'assistant',
              content: contentAfterEnd,
              messageType: 'text',
              toolUseData: null,
              isProcessing: true,
              sessionId: newMessage.sessionId,
              timestamp: newMessage.timestamp,
              id: `${newMessage.timestamp}-post-tool`,
            };

            return [...updatedMessages, postToolMessage];
          }

          return updatedMessages;
        }
      }

      // Find existing streaming message for this session
      const existingStreamingIndex = prevMessages.findIndex(
        (msg) => msg.role === 'assistant' && msg.isProcessing && msg.sessionId === newMessage.sessionId,
      );

      if (existingStreamingIndex >= 0) {
        const updatedMessages = [...prevMessages];
        const existingMessage = updatedMessages[existingStreamingIndex];

        if (existingMessage.messageType === 'tool_use') {
          // Stream content into tool use area
          const updatedToolUseData = {
            ...existingMessage.toolUseData,
            toolContent: (existingMessage.toolUseData?.toolContent || '') + newMessage.content,
          };

          updatedMessages[existingStreamingIndex] = {
            ...existingMessage,
            toolUseData: updatedToolUseData,
            timestamp: newMessage.timestamp,
          };

          return updatedMessages;
        }
        if (existingMessage.awaitingStructuredData) {
          // Don't accumulate content when awaiting structured data
          // Just update timestamp to keep message alive
          updatedMessages[existingStreamingIndex] = {
            ...existingMessage,
            timestamp: newMessage.timestamp,
          };

          return updatedMessages;
        }
        // Regular content streaming
        updatedMessages[existingStreamingIndex] = {
          ...existingMessage,
          content: existingMessage.content + newMessage.content,
          timestamp: newMessage.timestamp,
        };

        return updatedMessages;
      }

      // No existing streaming message, create new one
      return [
        ...prevMessages,
        {
          role: newMessage.role,
          content: newMessage.content,
          messageType: 'text',
          toolUseData: null,
          isProcessing: newMessage.isProcessing,
          sessionId: newMessage.sessionId,
          timestamp: newMessage.timestamp,
          id: newMessage.timestamp,
        },
      ];
    });
  };

  const addMessage = (newMessage) => {
    if (newMessage.role === 'assistant') {
      handleStreamingMessage(newMessage);
      return;
    }

    // For user messages, check if we already have this content in our sent messages
    // to avoid duplicates when the subscription echoes back our locally added message
    const messageKey = `${newMessage.sessionId}:${newMessage.content}`;

    if (sentMessagesRef.current.has(messageKey)) {
      return;
    }

    setMessages((prevMessages) => [
      ...prevMessages,
      {
        ...newMessage,
        id: newMessage.timestamp,
      },
    ]);
  };

  // Subscribe to chat message updates
  useEffect(() => {
    logger.info('Setting up GraphQL subscription for session:', sessionId);
    logger.info('Using agent config:', agentConfig);

    const subscription = client
      .graphql({
        query: agentConfig.subscription,
        variables: { sessionId },
      })
      .subscribe({
        next: ({ data }) => {
          const chatMessage = data?.onAgentChatMessageUpdate;

          if (chatMessage) {
            addMessage(chatMessage);
          } else {
            console.log('No chat message in subscription data:', data);
          }
        },
        error: (err) => {
          logger.error('Subscription error:', err);
          setError('Connection to chat service lost. Please refresh the page.');
        },
      });

    return () => {
      if (subscription) {
        subscription.unsubscribe();
      }
    };
  }, [sessionId, agentConfig.subscription]);

  // Send a chat message
  const sendMessage = async (prompt, options = {}) => {
    if (!prompt.trim()) return undefined;

    setIsLoading(true);
    setWaitingForResponse(true);
    setError(null);

    const messageKey = `${sessionId}:${prompt}`;
    sentMessagesRef.current.add(messageKey);

    const userMessage = {
      role: 'user',
      content: prompt,
      messageType: 'text',
      toolUseData: null,
      isProcessing: false,
      sessionId,
      timestamp: Date.now(),
      id: `user-${Date.now()}`,
    };

    setMessages((prevMessages) => [...prevMessages, userMessage]);

    try {
      const response = await client.graphql({
        query: agentConfig.mutation,
        variables: {
          prompt,
          sessionId,
          method: agentConfig.method,
          enableCodeIntelligence: options.enableCodeIntelligence,
        },
      });

      return response;
    } catch (err) {
      setError('Failed to send message. Please try again.');
      logger.error('Chat error:', err);
      setWaitingForResponse(false);
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  // Cancel waiting for response
  const cancelResponse = () => {
    setWaitingForResponse(false);
    logger.info('Response cancelled by user');
  };

  // Clear error
  const clearError = () => {
    setError(null);
  };

  const clearChat = () => {
    setMessages([]);
    setSessionId(uuidv4());
    setWaitingForResponse(false);
    setIsLoading(false);
    setError(null);
    sentMessagesRef.current = new Set();
  };

  // Load a previous chat session
  const loadChatSession = async (targetSessionId, existingMessages = null) => {
    try {
      setIsLoading(true);
      setError(null);

      // If messages are already provided (from dropdown), use them
      let messagesToLoad = existingMessages;

      // Otherwise, fetch messages from the server
      if (!messagesToLoad) {
        const response = await client.graphql({
          query: GET_AGENT_CHAT_MESSAGES,
          variables: { sessionId: targetSessionId },
        });
        messagesToLoad = response?.data?.getChatMessages || [];
      }

      // Convert messages to the format expected by the UI
      const formattedMessages = messagesToLoad.map((msg, index) => ({
        role: msg.role,
        content: msg.content,
        messageType: 'text',
        toolUseData: null,
        isProcessing: false, // Historical messages are never processing
        sessionId: msg.sessionId,
        timestamp: msg.timestamp,
        id: `${msg.timestamp}-${index}`,
      }));

      // Update state with loaded session
      setMessages(formattedMessages);
      setSessionId(targetSessionId);
      setWaitingForResponse(false);
      sentMessagesRef.current = new Set();

      logger.info(`Loaded chat session ${targetSessionId} with ${formattedMessages.length} messages`);
    } catch (err) {
      setError('Failed to load chat session. Please try again.');
      logger.error('Error loading chat session:', err);
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  return {
    messages,
    isLoading,
    waitingForResponse,
    error,
    sessionId,
    sendMessage,
    cancelResponse,
    clearError,
    clearChat,
    loadChatSession,
    agentConfig, // Expose config for debugging
  };
};

export default useAgentChat;
