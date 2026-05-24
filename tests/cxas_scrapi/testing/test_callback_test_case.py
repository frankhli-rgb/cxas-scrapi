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

"""Unit tests for the GECX CallbackTestCase framework utilities."""

import builtins

from cxas_scrapi.testing import CallbackTestCase
from cxas_scrapi.utils.callback_libs import (
    CallbackContext,
    Content,
    LlmResponse,
    Part,
)


class TestCallbackTestCaseSelf(CallbackTestCase):
    """Tests the assertions and helper lifecycles of our own CallbackTestCase base class."""

    def test_builtins_injection_lifecycle(self) -> None:
        """Verify that GECX classes are successfully injected into builtins during execution setUp."""
        # The setUp method of CallbackTestCase has already executed
        self.assertTrue(hasattr(builtins, "CallbackContext"))
        self.assertTrue(hasattr(builtins, "LlmResponse"))
        self.assertTrue(hasattr(builtins, "Part"))
        self.assertEqual(builtins.CallbackContext, CallbackContext)
        self.assertEqual(builtins.LlmResponse, LlmResponse)
        self.assertEqual(builtins.Part, Part)

    def test_create_mock_context_helpers(self) -> None:
        """Verify that create_mock_context correctly configures initial states and user inputs."""
        # Arrange & Act
        ctx = self.create_mock_context(
            state={"auth_status": "VERIFIED"},
            user_text="I want to check my account balance",
        )

        # Assert
        self.assertIsInstance(ctx, CallbackContext)
        self.assertEqual(ctx.state.get("auth_status"), "VERIFIED")
        self.assertIsNotNone(ctx.user_content)
        self.assertEqual(ctx.user_content.parts[0].text, "I want to check my account balance")

        # Verify last user input retrieval helper
        parts = ctx.get_last_user_input()
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0].text, "I want to check my account balance")

    def test_assert_state_variable(self) -> None:
        """Verify state variable assertions check the state dictionary correctly."""
        ctx = self.create_mock_context(state={"api_failed": "false"})
        self.assert_state_variable(ctx, "api_failed", "false")

        # Verify it raises on mismatch
        with self.assertRaises(AssertionError):
            self.assert_state_variable(ctx, "api_failed", "true")

    def test_assert_agent_reply(self) -> None:
        """Verify the semantic assertion checks agent response reply text."""
        # Arrange
        part = Part.from_text(text="Welcome to Sunday Mobile Support!")
        response = LlmResponse.from_parts(parts=[part])

        # Assert
        self.assert_agent_reply(response, "Welcome")
        self.assert_agent_reply(response, "Sunday Mobile")

        # Verify mismatch raises AssertionError
        with self.assertRaises(AssertionError):
            self.assert_agent_reply(response, "Billing balance")

    def test_assert_transferred_to_agent(self) -> None:
        """Verify the semantic assertion detects target agent transfer tool call."""
        # Arrange
        part = Part.from_agent_transfer(agent="BillingSpecialist")
        response = LlmResponse.from_parts(parts=[part])

        # Assert
        self.assert_transferred_to_agent(response, "BillingSpecialist")

        # Verify mismatch raises AssertionError
        with self.assertRaises(AssertionError):
            self.assert_transferred_to_agent(response, "TriageAgent")

    def test_assert_end_session(self) -> None:
        """Verify semantic assertion verifies session end parameters."""
        # Arrange
        part = Part.from_end_session(reason="Verification failed", escalated=True)
        response = LlmResponse.from_parts(parts=[part])

        # Assert
        self.assert_end_session(response, expected_reason="Verification failed", expected_escalated=True)
        self.assert_end_session(response, expected_escalated=True)
        self.assert_end_session(response)

        # Verify mismatch parameter raises AssertionError
        with self.assertRaises(AssertionError):
            self.assert_end_session(response, expected_reason="Completed successfully")
        with self.assertRaises(AssertionError):
            self.assert_end_session(response, expected_escalated=False)
