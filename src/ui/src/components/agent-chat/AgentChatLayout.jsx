// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import React, { useState, useRef, useMemo, useEffect } from 'react';
import PropTypes from 'prop-types';
import {
  Container,
  Alert,
  Box,
  Header,
  Spinner,
  PromptInput,
  SpaceBetween,
  ExpandableSection,
  Button,
  Checkbox,
} from '@cloudscape-design/components';
import { SupportPromptGroup, LoadingBar } from '@cloudscape-design/chat-components';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import useAgentChat from '../../hooks/use-agent-chat';
import useAppContext from '../../contexts/app';
import PlotDisplay from '../document-agents-layout/PlotDisplay';
import TableDisplay from '../document-agents-layout/TableDisplay';
import './AgentChatLayout.css';

const AgentChatLayout = ({
  title = 'AI Assistant',
  placeholder = 'Ask me anything about documents, errors, or IDP code base',
  agentConfig = {},
  className = '',
  showHeader = true,
  customStyles = {},
}) => {
  const [inputValue, setInputValue] = useState('');
  const [expandedSections, setExpandedSections] = useState(new Set());
  const [welcomeAnimated, setWelcomeAnimated] = useState(false);
  const [lastMessageCount, setLastMessageCount] = useState(0);
  const [enableCodeIntelligence, setEnableCodeIntelligence] = useState(true);
  const chatMessagesRef = useRef(null);
  const { messages, isLoading, waitingForResponse, error, sendMessage, clearError, clearChat } = useAgentChat(agentConfig);
  const { user } = useAppContext();

  const userInitial = useMemo(() => {
    if (!user?.username) return 'U';
    return user.username.charAt(0).toUpperCase();
  }, [user]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setWelcomeAnimated(true);
    }, 100);

    return () => clearTimeout(timer);
  }, []);

  // Listen for sample query insertion events from the tools panel
  useEffect(() => {
    const handleSampleQueryInsert = (event) => {
      const { query } = event.detail;
      setInputValue(query);
    };

    window.addEventListener('insertSampleQuery', handleSampleQueryInsert);

    return () => {
      window.removeEventListener('insertSampleQuery', handleSampleQueryInsert);
    };
  }, []);

  // Track new messages and scroll to new assistant messages (but not while streaming)
  useEffect(() => {
    if (messages.length > lastMessageCount) {
      const newMessages = messages.slice(lastMessageCount);

      const newAssistantMessage = newMessages.find((msg) => msg.role === 'assistant' && msg.isProcessing === true);

      if (newAssistantMessage) {
        setTimeout(() => {
          if (chatMessagesRef.current) {
            const assistantMessages = chatMessagesRef.current.querySelectorAll('.assistant-message');
            if (assistantMessages.length > 0) {
              const lastAssistantMessage = assistantMessages[assistantMessages.length - 1];
              lastAssistantMessage.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
          }
        }, 100);
      }

      setLastMessageCount(messages.length);
    }
  }, [messages, lastMessageCount]);

  const handlePromptSubmit = async () => {
    const prompt = inputValue;
    if (!prompt.trim()) return;

    setInputValue('');
    try {
      await sendMessage(prompt, { enableCodeIntelligence });
      // Scroll to the latest user message after sending
      setTimeout(() => {
        if (chatMessagesRef.current) {
          const userMessages = chatMessagesRef.current.querySelectorAll('.user-message');
          if (userMessages.length > 0) {
            const lastUserMessage = userMessages[userMessages.length - 1];
            lastUserMessage.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }
        }
      }, 100); // Small delay to ensure the message is rendered
    } catch (err) {
      console.error('Failed to send message:', err);
    }
  };

  const handleInputChange = (event) => {
    setInputValue(event.detail.value);
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handlePromptSubmit();
    }
  };

  // Handle expandable section state changes
  const handleExpandedChange = (messageId, expanded) => {
    setExpandedSections((prev) => {
      const newSet = new Set(prev);
      if (expanded) {
        newSet.add(messageId);
      } else {
        newSet.delete(messageId);
      }
      return newSet;
    });
  };

  // Hardcoded sample prompts from different agents
  const supportPrompts = [
    {
      id: 'GeneralAgent',
      prompt: 'What capabilities do you have?',
    },
    {
      id: 'AnalyticsAgent',
      prompt: 'Can you make a table of the documents uploaded in the last three days?',
    },
    {
      id: 'CodeIntelligenceAgent',
      prompt: 'Explain how the document classification pipeline works in the IDP accelerator',
    },
    {
      id: 'ErrorAnalyzerAgent',
      prompt: 'Analyze recent errors in document processing',
    },
  ];

  const renderedMessages = useMemo(() => {
    return messages.map((message) => {
      let contentText = '';
      if (typeof message.content === 'string') {
        contentText = message.content;
      } else if (Array.isArray(message.content) && message.content[0]) {
        const content = message.content[0];
        if (content?.error) {
          contentText = `Error: ${content.error}`;
        } else {
          contentText = content?.text || '';
        }
      }

      const isUser = message.role === 'user';

      return (
        <div
          key={`${message.role}-${message.timestamp}`}
          className={`chat-message-wrapper ${isUser ? 'user-message' : 'assistant-message'}`}
        >
          <div className="message-container">
            {isUser && (
              <div className="message-avatar">
                <div className="avatar-circle">{userInitial}</div>
              </div>
            )}
            <div className="message-content">
              {(() => {
                if (message.messageType === 'tool_use' && message.toolUseData) {
                  return (
                    <div className="tool-usage-container">
                      <ExpandableSection
                        headerText={
                          <>
                            <div style={{ display: 'flex' }} title="Click to expand for more information">
                              {message.toolUseData.agent_name} &nbsp; {message.isProcessing && <Spinner />}{' '}
                            </div>
                          </>
                        }
                        variant="footer"
                        expanded={expandedSections.has(message.id)}
                        onChange={({ detail }) => handleExpandedChange(message.id, detail.expanded)}
                      >
                        {message.toolUseData.toolContent && (
                          <Box margin={{ top: 'xs' }}>
                            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
                              {message.toolUseData.toolContent}
                            </ReactMarkdown>
                          </Box>
                        )}
                      </ExpandableSection>
                    </div>
                  );
                }

                if (message.parsedData) {
                  return (
                    <SpaceBetween size="m">
                      {message.parsedData.textContent && (
                        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
                          {message.parsedData.textContent}
                        </ReactMarkdown>
                      )}

                      {message.parsedData.responseType === 'plotData' && <PlotDisplay plotData={message.parsedData.data} />}

                      {message.parsedData.responseType === 'table' && <TableDisplay tableData={message.parsedData.data} />}
                    </SpaceBetween>
                  );
                }

                return (
                  <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
                    {contentText}
                  </ReactMarkdown>
                );
              })()}
            </div>
          </div>
        </div>
      );
    });
  }, [messages, user, expandedSections]);

  const chatContent = (
    <div className="chat-container">
      <div className="chat-content">
        {error && (
          <Alert type="error" dismissible onDismiss={clearError}>
            {error}
          </Alert>
        )}

        <div ref={chatMessagesRef} className="chat-messages">
          {messages.length === 0 ? (
            <div className={`welcome-text ${welcomeAnimated ? 'animate-in' : ''}`}>
              <h2>
                Welcome to <span>Agent Companion Chat</span>
              </h2>
            </div>
          ) : (
            <>
              {renderedMessages}
              {waitingForResponse && <LoadingBar variant="gen-ai-masked" />}
            </>
          )}
        </div>
      </div>

      <div className="prompt-input-container">
        <SpaceBetween direction="vertical" size="m">
          {messages.length === 0 && (
            <SpaceBetween direction="horizontal" size="s" alignItems="center">
              <Box flex="1">
                <SupportPromptGroup
                  alignment="horizontal"
                  items={supportPrompts.map((item) => ({
                    text: item.prompt,
                    id: item.id,
                  }))}
                  onItemClick={async ({ detail }) => {
                    const selectedPrompt = supportPrompts.find((prompt) => prompt.id === detail.id);
                    if (selectedPrompt) {
                      setInputValue(selectedPrompt.prompt);
                    }
                  }}
                />{' '}
              </Box>
            </SpaceBetween>
          )}
          <Box>
            <SpaceBetween direction="vertical" size="xs">
              <PromptInput
                value={inputValue}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder={placeholder}
                disabled={isLoading}
                actionButtonIconName="send"
                onAction={handlePromptSubmit}
                minRows={3}
              />
              <SpaceBetween direction="horizontal" size="m" alignItems="center">
                <Box fontSize="body-s" color="text-status-info" flex="1">
                  Avoid sharing sensitive information, the Code Intelligence Agent may use third-party services.
                </Box>
                <Checkbox
                  checked={enableCodeIntelligence}
                  onChange={({ detail }) => setEnableCodeIntelligence(detail.checked)}
                  disabled={waitingForResponse}
                >
                  <Box fontSize="body-s">Enable Code Intelligence Agent</Box>
                </Checkbox>
              </SpaceBetween>
            </SpaceBetween>
          </Box>
          {messages.length > 0 && (
            <Button
              variant="normal"
              iconName="refresh"
              onClick={() => {
                clearChat();
                setExpandedSections(new Set());
                setWelcomeAnimated(false);
                setLastMessageCount(0);
                setTimeout(() => {
                  setWelcomeAnimated(true);
                }, 100);
              }}
              disabled={waitingForResponse}
            >
              Clear chat
            </Button>
          )}
        </SpaceBetween>
      </div>
    </div>
  );

  if (showHeader) {
    return (
      <div className={`agent-chat-layout ${className}`} style={customStyles}>
        <Container header={<Header variant="h2">{title}</Header>}>{chatContent}</Container>
      </div>
    );
  }

  return (
    <div className={`agent-chat-layout ${className}`} style={customStyles}>
      {chatContent}
    </div>
  );
};

AgentChatLayout.propTypes = {
  title: PropTypes.string,
  placeholder: PropTypes.string,
  agentConfig: PropTypes.shape({
    agentType: PropTypes.string,
    mutation: PropTypes.oneOfType([PropTypes.object, PropTypes.func]),
    subscription: PropTypes.oneOfType([PropTypes.object, PropTypes.func]),
    method: PropTypes.string,
  }),
  className: PropTypes.string,
  showHeader: PropTypes.bool,
  customStyles: PropTypes.objectOf(PropTypes.oneOfType([PropTypes.string, PropTypes.number])),
};

export default AgentChatLayout;
