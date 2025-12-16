# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
Analytics agent logger utility for monitoring tool execution and context flow.
"""

import json
import logging
from typing import Any, Dict


class AnalyticsLogger:
    """Logger for analytics agent events and content."""

    def __init__(self):
        self._events: Dict[str, str] = {}  # event -> time_string mapping
        self._event_counters: Dict[str, int] = {}  # track multiple calls
        self._logger = logging.getLogger(__name__)

    def log_event(self, event: str, duration: float) -> None:
        """
        Log event execution time and store in events map.

        Args:
            event: Name of the event/tool that was executed
            duration: Duration in seconds
        """
        # Handle multiple calls by adding counter
        if event in self._event_counters:
            self._event_counters[event] += 1
            event_key = f"{event}_{self._event_counters[event]}"
        else:
            self._event_counters[event] = 1
            event_key = f"{event}_1"

        duration_str = f"{duration:.2f}"
        self._events[event_key] = duration_str

        self._logger.info(f"[{event}][{duration_str}s]")

    def log_content(self, event: str, content: Any, mode: str = "size") -> None:
        """
        Log content with different display modes (separate from events map).

        Args:
            event: Name of the event for context
            content: Content to log
            mode: Display mode - "size", "preview", or "full"
        """
        if content is None:
            self._logger.info(f"[{event}] Content: None")
            return

        try:
            if isinstance(content, (dict, list)):
                content_str = json.dumps(content, indent=2)
            else:
                content_str = str(content)

            char_count = len(content_str)

            if mode == "size":
                kb_size = char_count / 1024
                if kb_size > 1:
                    size_info = f"{kb_size:.1f}KB"
                else:
                    size_info = f"{char_count} chars"
                self._logger.info(f"[{event}] Content size: {size_info}")

            elif mode == "preview":
                preview = (
                    content_str[:100] + "..." if len(content_str) > 100 else content_str
                )
                self._logger.info(f"[{event}] Content preview: {preview}")

            elif mode == "full":
                self._logger.info(f"[{event}] Full content:")
                self._logger.info(content_str)

        except Exception as e:
            self._logger.error(f"[{event}] Error logging content: {e}")

    def get_events(self) -> Dict[str, str]:
        """
        Return copy of events map.

        Returns:
            Dict mapping event names to duration strings
        """
        return self._events.copy()

    def clear_events(self) -> None:
        """
        Clear all stored events and reset counters.
        """
        self._events.clear()
        self._event_counters.clear()

    def display_summary(self) -> None:
        """
        Display formatted table of all events.
        """
        if not self._events:
            self._logger.info("No events recorded")
            return

        self._logger.info("\n" + "=" * 50)
        self._logger.info("EVENT EXECUTION SUMMARY")
        self._logger.info("=" * 50)
        self._logger.info(f"{'EVENT':<30} {'TIME':<10}")
        self._logger.info("-" * 50)

        total_time = 0.0
        for event, duration_str in self._events.items():
            self._logger.info(f"{event:<30} {duration_str}s")
            total_time += float(duration_str)

        self._logger.info("-" * 50)
        self._logger.info(f"{'TOTAL':<30} {total_time:.2f}s")
        self._logger.info("=" * 50)


# Singleton instance
analytics_logger = AnalyticsLogger()
