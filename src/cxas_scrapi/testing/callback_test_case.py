# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Base test case for GECX Python callbacks unit testing."""

import builtins
from typing import Any, Dict, List, Optional
import unittest

from cxas_scrapi.utils.callback_libs import (
    CallbackContext,
    Content,
    Event,
    FunctionCall,
    FunctionResponse,
    LlmRequest,
    LlmResponse,
    Part,
)


class CallbackTestCase(unittest.TestCase):
    """Base test case for GECX Python callbacks with auto-mocked builtins."""

    def setUp(self) -> None:
        super().setUp()
        # Auto-inject GECX types into builtins to prevent NameErrors in imported callback modules
        self._injected_builtins = {
            "CallbackContext": CallbackContext,
            "Content": Content,
            "Event": Event,
            "FunctionCall": FunctionCall,
            "FunctionResponse": FunctionResponse,
            "LlmRequest": LlmRequest,
            "LlmResponse": LlmResponse,
            "Part": Part,
        }
        for name, cls in self._injected_builtins.items():
            setattr(builtins, name, cls)

    def tearDown(self) -> None:
        # Clean up injected builtins to preserve environment state hygiene
        for name in self._injected_builtins:
            if hasattr(builtins, name):
                delattr(builtins, name)
        super().tearDown()

    def create_mock_context(
        self,
        state: Optional[Dict[str, Any]] = None,
        user_text: Optional[str] = None,
        events: Optional[List[Event]] = None,
        agent_name: str = "Main_Agent",
        session_id: str = "mock-session-123",
    ) -> CallbackContext:
        """Helper to create a populated, clean CallbackContext for unit testing."""
        ctx_state = state or {}
        ctx_events = events or []

        if user_text and not ctx_events:
            # If user_text is provided, automatically populate a single user event
            user_part = Part.from_text(text=user_text)
            user_content = Content(parts=[user_part], role="user")
            user_event = Event(
                id="event-1",
                author="user",
                timestamp=1000,
                invocation_id="inv-1",
                content=user_content,
                turn_complete=True,
            )
            ctx_events.append(user_event)

        ctx = CallbackContext(
            state=ctx_state,
            events=ctx_events,
            agent_name=agent_name,
            session_id=session_id,
        )

        if user_text:
            ctx.user_content = Content(
                parts=[Part.from_text(text=user_text)], role="user"
            )

        return ctx

    # --- Semantic Assertions Helpers ---

    def assert_agent_reply(
        self, response: Optional[LlmResponse], expected_substring: str
    ) -> None:
        """Asserts that the LLM response contains a text part matching or containing the expected substring."""
        self.assertIsNotNone(response, "LlmResponse must not be None")
        if response is None or response.content is None or response.content.parts is None:
            raise AssertionError("LlmResponse content or parts must not be None")

        found = False
        all_texts = []
        for part in response.content.parts:
            if part.text:
                all_texts.append(part.text)
                if expected_substring in part.text:
                    found = True
                    break

        self.assertTrue(
            found,
            f"Expected agent reply to contain '{expected_substring}', but got"
            f" parts: {all_texts}",
        )

    def assert_transferred_to_agent(
        self, response: Optional[LlmResponse], expected_agent: str
    ) -> None:
        """Asserts that the response issues a transfer_to_agent function call tool targeting the expected agent."""
        self.assertIsNotNone(response, "LlmResponse must not be None")
        if response is None or response.content is None or response.content.parts is None:
            raise AssertionError("LlmResponse content or parts must not be None")

        found = False
        actual_transfers = []
        for part in response.content.parts:
            if part.function_call:
                fc = part.function_call
                if fc.name == "transfer_to_agent":
                    agent_name = None
                    if fc.args is not None:
                        agent_name = fc.args.get("agent_name")
                    actual_transfers.append(agent_name)
                    if agent_name == expected_agent:
                        found = True
                        break
                # Shorthand for custom transfer calls if any
                elif fc.name == expected_agent:
                    found = True
                    break

        self.assertTrue(
            found,
            f"Expected transfer function call to '{expected_agent}', but"
            f" actual transfers were: {actual_transfers}",
        )

    def assert_end_session(
        self,
        response: Optional[LlmResponse],
        expected_reason: Optional[str] = None,
        expected_escalated: Optional[bool] = None,
    ) -> None:
        """Asserts that the response issues an end_session function call tool with correct parameters."""
        self.assertIsNotNone(response, "LlmResponse must not be None")
        if response is None or response.content is None or response.content.parts is None:
            raise AssertionError("LlmResponse content or parts must not be None")

        found = False
        actual_ends = []
        for part in response.content.parts:
            if part.function_call and part.function_call.name == "end_session":
                fc = part.function_call
                reason = None
                escalated = None
                if fc.args is not None:
                    reason = fc.args.get("reason")
                    escalated = fc.args.get("session_escalated") or fc.args.get(
                        "escalated"
                    )
                actual_ends.append({"reason": reason, "escalated": escalated})

                reason_match = (
                    expected_reason is None or reason == expected_reason
                )
                escalated_match = (
                    expected_escalated is None or escalated == expected_escalated
                )

                if reason_match and escalated_match:
                    found = True
                    break

        self.assertTrue(
            found,
            f"Expected end_session(reason={expected_reason},"
            f" escalated={expected_escalated}), but actual ends were:"
            f" {actual_ends}",
        )

    def assert_state_variable(
        self, context: CallbackContext, key: str, expected_value: Any
    ) -> None:
        """Asserts that the target context state variable matches the expected value."""
        self.assertIsNotNone(context, "CallbackContext must not be None")
        actual_value = context.state.get(key)
        self.assertEqual(
            actual_value,
            expected_value,
            f"Expected state variable '{key}' to be '{expected_value}', but"
            f" was '{actual_value}'",
        )
