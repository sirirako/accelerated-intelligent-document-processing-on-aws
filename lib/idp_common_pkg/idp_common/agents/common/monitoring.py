# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Monitoring and callback system for tracking Strands agent execution in IDP.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List

from strands.hooks import HookProvider, HookRegistry
from strands.hooks.events import (
    AfterInvocationEvent,
    AgentInitializedEvent,
    BeforeInvocationEvent,
    MessageAddedEvent,
)

# Try to import experimental events if available
try:
    from strands.experimental.hooks import (
        AfterModelInvocationEvent,
        AfterToolInvocationEvent,
        BeforeModelInvocationEvent,
        BeforeToolInvocationEvent,
    )

    EXPERIMENTAL_EVENTS_AVAILABLE = True
except ImportError:
    EXPERIMENTAL_EVENTS_AVAILABLE = False

logger = logging.getLogger(__name__)


class AgentMonitor(HookProvider):
    """
    Comprehensive monitoring hook provider for Strands agents.

    This class provides detailed tracking of agent execution including:
    - Message flow monitoring (MessageAddedEvent)
    - Tool invocation tracking
    - Model invocation tracking
    - Request lifecycle monitoring
    """

    def __init__(
        self, log_level: int = logging.INFO, enable_detailed_logging: bool = True
    ):
        """
        Initialize the agent monitor.

        Args:
            log_level: Logging level for monitor output
            enable_detailed_logging: Whether to log detailed event information
        """
        self.log_level = log_level
        self.enable_detailed_logging = enable_detailed_logging
        self.execution_stats = {
            "messages_added": 0,
            "tool_invocations": 0,
            "model_invocations": 0,
            "requests_processed": 0,
            "start_time": None,
            "end_time": None,
        }
        self.message_history: List[Dict[str, Any]] = []
        self.tool_history: List[Dict[str, Any]] = []
        self.model_history: List[Dict[str, Any]] = []

        # Set up logger for this monitor
        self.monitor_logger = logging.getLogger(f"{__name__}.AgentMonitor")
        self.monitor_logger.setLevel(log_level)

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register all monitoring callbacks with the hook registry."""
        # Core events
        registry.add_callback(AgentInitializedEvent, self.on_agent_initialized)
        registry.add_callback(BeforeInvocationEvent, self.on_before_invocation)
        registry.add_callback(AfterInvocationEvent, self.on_after_invocation)
        registry.add_callback(MessageAddedEvent, self.on_message_added)

        # Experimental events (if available)
        if EXPERIMENTAL_EVENTS_AVAILABLE:
            print("\n\n REGISTERING EXPERIMENTAL HOOKS \n\n")
            registry.add_callback(
                BeforeToolInvocationEvent, self.on_before_tool_invocation
            )
            registry.add_callback(
                AfterToolInvocationEvent, self.on_after_tool_invocation
            )
            registry.add_callback(
                BeforeModelInvocationEvent, self.on_before_model_invocation
            )
            registry.add_callback(
                AfterModelInvocationEvent, self.on_after_model_invocation
            )
        else:
            self.monitor_logger.warning(
                "Experimental events not available - tool and model monitoring disabled"
            )

    def on_agent_initialized(self, event: AgentInitializedEvent) -> None:
        """Handle agent initialization event."""
        self.monitor_logger.info("🤖 Agent initialized and ready")
        if self.enable_detailed_logging:
            self.monitor_logger.debug(f"Agent details: {event.agent}")

    def on_before_invocation(self, event: BeforeInvocationEvent) -> None:
        """Handle request start event."""
        self.execution_stats["start_time"] = datetime.now()
        self.execution_stats["requests_processed"] += 1

        self.monitor_logger.info("🚀 Starting new agent request")
        if self.enable_detailed_logging:
            self.monitor_logger.debug(f"Request details: Agent={event.agent}")

    def on_after_invocation(self, event: AfterInvocationEvent) -> None:
        """Handle request completion event."""
        self.execution_stats["end_time"] = datetime.now()

        if self.execution_stats["start_time"]:
            duration = (
                self.execution_stats["end_time"] - self.execution_stats["start_time"]
            )
            self.monitor_logger.info(
                f"✅ Agent request completed in {duration.total_seconds():.2f}s"
            )
        else:
            self.monitor_logger.info("✅ Agent request completed")

        # Log execution summary
        self.log_execution_summary()

    def on_message_added(self, event: MessageAddedEvent) -> None:
        """
        Handle message added event - this is the main event requested for monitoring.

        This callback tracks all messages added to the agent's conversation history,
        including user messages, assistant responses, and tool results.
        """
        self.execution_stats["messages_added"] += 1

        message = event.message
        message_info = {
            "timestamp": datetime.now().isoformat(),
            **self._get_message_preview(message),
        }

        self.message_history.append(message_info)

        # Log the message event
        role = message_info["role"]
        content_preview = (
            message_info["content"][:100] + "..."
            if len(message_info["content"]) > 100
            else message_info["content"]
        )

        self.monitor_logger.info(f"💬 Message added: [{role}] {content_preview}")

        if self.enable_detailed_logging:
            self.monitor_logger.info(f"Full message details: {message}")

    def on_before_tool_invocation(self, event) -> None:
        """Handle before tool invocation event."""
        if not EXPERIMENTAL_EVENTS_AVAILABLE:
            return

        tool_name = event.tool_use.get("name", "unknown")
        tool_input = event.tool_use.get("input", {})

        self.monitor_logger.info(f"🔧 Invoking tool: {tool_name}")
        if self.enable_detailed_logging:
            self.monitor_logger.debug(f"Tool input: {json.dumps(tool_input, indent=2)}")

    def on_after_tool_invocation(self, event) -> None:
        """Handle after tool invocation event."""
        if not EXPERIMENTAL_EVENTS_AVAILABLE:
            return

        self.execution_stats["tool_invocations"] += 1

        tool_name = event.tool_use.get("name", "unknown")
        result_preview = self._get_tool_result_preview(event.result)

        tool_info = {
            "timestamp": datetime.now().isoformat(),
            "tool_name": tool_name,
            "result_preview": result_preview,
        }

        self.tool_history.append(tool_info)

        self.monitor_logger.info(f"✅ Tool completed: {tool_name} -> {result_preview}")

        if self.enable_detailed_logging:
            self.monitor_logger.debug(f"Full tool result: {event.result}")

    def on_before_model_invocation(self, event) -> None:
        """Handle before model invocation event."""
        if not EXPERIMENTAL_EVENTS_AVAILABLE:
            return

        self.monitor_logger.info("🧠 Invoking language model")
        if self.enable_detailed_logging:
            self.monitor_logger.debug(f"Model invocation details: {event}")

    def on_after_model_invocation(self, event) -> None:
        """Handle after model invocation event."""
        if not EXPERIMENTAL_EVENTS_AVAILABLE:
            return

        self.execution_stats["model_invocations"] += 1

        model_info = {
            "timestamp": datetime.now().isoformat(),
        }

        self.model_history.append(model_info)

        self.monitor_logger.info("✅ Model invocation completed")
        if self.enable_detailed_logging:
            self.monitor_logger.debug(f"Model response details: {event}")

    def _get_message_preview(self, message) -> Dict[str, Any]:
        """Get message content and metadata for logging."""

        # Example message: message={'role': 'user', 'content': [{'text': 'How many documents have I processed each day?'}]}
        try:
            content = message["content"]
            role = message["role"]

            # Special case for tool result messages
            if role == "user":
                for c in message["content"]:
                    if "toolResult" in c:
                        res = {
                            "role": "tool",
                            "content": f"Tool completed with status '{c['toolResult']['status']}'.",
                            "debug_tool_output": c["toolResult"],
                            "message_type": type(message).__name__,
                        }
                        self.monitor_logger.debug(f"Full tool use output: {res}")
                        return res

            # For all other user/assistant messages, return full content
            # Note some assistant messages are themselves a list, with one
            #  text message followed by a tool request message
            return {
                "role": role,
                "content": content,
                "message_type": type(message).__name__,
            }

        except Exception as e:
            return {
                "role": "unknown",
                "content": f"<Error extracting message: {e}>",
                "message_type": type(message).__name__,
            }

    def _get_tool_result_preview(self, result) -> str:
        """Get a preview of tool result for logging."""
        try:
            if isinstance(result, dict):
                if "success" in result:
                    success = result["success"]
                    if success:
                        data_preview = str(result.get("data", ""))[:50]
                        return f"Success: {data_preview}..."
                    else:
                        error = result.get("error", "Unknown error")
                        return f"Error: {error}"
                else:
                    # Generic dict preview
                    return str(result)[:50] + "..."
            else:
                return str(result)[:50] + "..."
        except Exception as e:
            return f"<Error getting preview: {e}>"

    def log_execution_summary(self) -> None:
        """Log a summary of the execution statistics."""
        stats = self.execution_stats

        self.monitor_logger.info("📊 Execution Summary:")
        self.monitor_logger.info(f"  • Messages added: {stats['messages_added']}")
        self.monitor_logger.info(f"  • Tool invocations: {stats['tool_invocations']}")
        self.monitor_logger.info(f"  • Model invocations: {stats['model_invocations']}")
        self.monitor_logger.info(
            f"  • Requests processed: {stats['requests_processed']}"
        )

        if stats["start_time"] and stats["end_time"]:
            duration = stats["end_time"] - stats["start_time"]
            self.monitor_logger.info(
                f"  • Total duration: {duration.total_seconds():.2f}s"
            )

    def get_execution_report(self) -> Dict[str, Any]:
        """Get a comprehensive execution report."""
        return {
            "execution_stats": self.execution_stats.copy(),
            "message_history": self.message_history.copy(),
            "tool_history": self.tool_history.copy(),
            "model_history": self.model_history.copy(),
        }

    def reset_stats(self) -> None:
        """Reset all execution statistics and history."""
        self.execution_stats = {
            "messages_added": 0,
            "tool_invocations": 0,
            "model_invocations": 0,
            "requests_processed": 0,
            "start_time": None,
            "end_time": None,
        }
        self.message_history.clear()
        self.tool_history.clear()
        self.model_history.clear()


class MessageTracker(HookProvider):
    """
    Simplified hook provider that focuses specifically on MessageAddedEvent monitoring.

    This is a lightweight alternative to AgentMonitor for cases where you only
    need to track message flow.
    """

    def __init__(self, callback_fn=None):
        """
        Initialize the message tracker.

        Args:
            callback_fn: Optional custom callback function to call when messages are added
        """
        self.callback_fn = callback_fn
        self.messages = []
        self.logger = logging.getLogger(f"{__name__}.MessageTracker")

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register the message tracking callback."""
        registry.add_callback(MessageAddedEvent, self.on_message_added)

    def on_message_added(self, event: MessageAddedEvent) -> None:
        """Handle message added events."""
        message_data = {
            "timestamp": datetime.now().isoformat(),
            "message": event.message,
            "role": getattr(event.message, "role", "unknown"),
        }

        self.messages.append(message_data)

        # Log the message
        role = message_data["role"]
        self.logger.info(f"📝 Message tracked: [{role}] (Total: {len(self.messages)})")

        # Call custom callback if provided
        if self.callback_fn:
            try:
                self.callback_fn(event, message_data)
            except Exception as e:
                self.logger.error(f"Error in custom callback: {e}")

    def get_messages(self) -> List[Dict[str, Any]]:
        """Get all tracked messages."""
        return self.messages.copy()

    def clear_messages(self) -> None:
        """Clear all tracked messages."""
        self.messages.clear()
