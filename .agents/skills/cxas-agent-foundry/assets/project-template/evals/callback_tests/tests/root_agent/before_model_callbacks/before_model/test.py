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

"""Callback Tests — before_model_callback (Root Agent)

Tests the trigger pattern implementation for deterministic escalation.
"""

import os
import sys
from unittest.mock import MagicMock

# 1. Point sys.path at the target python_code.py folder relative to this test.py
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "..",
        "agents",
        "root_agent",
        "before_model_callbacks",
        "before_model",
    ),
)

# 2. Mock GECX globals before import (GECX runtime provides a 'tools' global)
import python_code  # noqa: E402

python_code.tools = MagicMock()

# 3. Import parent CallbackTestCase framework and target callback function
from python_code import before_model_callback  # noqa: E402

from cxas_scrapi.testing import CallbackTestCase


class TestGreeting(CallbackTestCase):
    """Tests for deterministic greeting on session start."""

    def test_session_start_returns_greeting(self) -> None:
        """Session start event returns the fixed greeting."""
        ctx = self.create_mock_context(user_text="<event>session start</event>")
        result = before_model_callback(ctx, llm_request=MagicMock())

        self.assertIsNotNone(result)
        # Semantic check that response has active dialogue reply
        self.assert_agent_reply(result, "virtual assistant")

    def test_normal_message_skips_greeting(self) -> None:
        """A normal user message does not trigger the greeting."""
        ctx = self.create_mock_context(
            state={"_action_trigger": "", "api_failed": "false"},
            user_text="My phone is not working",
        )
        result = before_model_callback(ctx, llm_request=MagicMock())
        self.assertIsNone(result)


class TestNoOpPath(CallbackTestCase):
    """Tests for when the callback should do nothing (return None)."""

    def test_no_trigger_returns_none(self) -> None:
        """No-op: No trigger set, no API failure, normal user message."""
        ctx = self.create_mock_context(
            state={"_action_trigger": "", "api_failed": "false"},
            user_text="Help me check balance",
        )
        result = before_model_callback(ctx, llm_request=MagicMock())
        self.assertIsNone(result)

    def test_missing_trigger_key_returns_none(self) -> None:
        """No-op: _action_trigger key doesn't exist in state."""
        ctx = self.create_mock_context(
            state={},
            user_text="Help me check balance",
        )
        result = before_model_callback(ctx, llm_request=MagicMock())
        self.assertIsNone(result)

    def test_unknown_trigger_returns_none(self) -> None:
        """No-op: Trigger value not in ESCALATION_MAP — unknown trigger."""
        ctx = self.create_mock_context(
            state={"_action_trigger": "unknown_trigger_value"},
            user_text="Help me check balance",
        )
        result = before_model_callback(ctx, llm_request=MagicMock())

        self.assertIsNone(result)
        # State trigger should still be cleared even if unknown
        self.assert_state_variable(ctx, "_action_trigger", "")


class TestEscalationTrigger(CallbackTestCase):
    """Tests for the standard escalation trigger path."""

    def _escalation_ctx(self, **overrides) -> Any:
        state = {
            "_action_trigger": "escalate",
            "_escalation_reason": "Customer wants human",
            "_escalation_topic": "billing",
            **overrides,
        }
        return self.create_mock_context(
            state=state, user_text="Transfer me please"
        )

    def test_escalation_returns_response(self) -> None:
        """Trigger: _action_trigger = 'escalate' — returns escalation response."""
        result = before_model_callback(
            self._escalation_ctx(), llm_request=MagicMock()
        )
        self.assertIsNotNone(result)

    def test_escalation_clears_trigger(self) -> None:
        """Trigger is cleared after handling to prevent re-firing."""
        ctx = self._escalation_ctx()
        before_model_callback(ctx, llm_request=MagicMock())
        self.assert_state_variable(ctx, "_action_trigger", "")

    def test_escalation_includes_text(self) -> None:
        """Response always includes text so customer hears something."""
        result = before_model_callback(
            self._escalation_ctx(), llm_request=MagicMock()
        )
        self.assert_agent_reply(
            result, "Transferring you to a billing specialist"
        )

    def test_escalation_resolves_state_references(self) -> None:
        """Payload args starting with '_' are resolved from state."""
        python_code.tools.reset_mock()
        ctx = self._escalation_ctx(
            _escalation_reason="Billing dispute",
            _escalation_topic="billing",
        )
        before_model_callback(ctx, llm_request=MagicMock())

        # verify direct mock call parameter resolution
        python_code.tools.payload_update_tool.assert_called_once()
        call_args = python_code.tools.payload_update_tool.call_args[0][0]
        self.assertEqual(call_args["escalation_reason"], "Billing dispute")
        self.assertEqual(call_args["main_topic"], "billing")


class TestApiFailurePath(CallbackTestCase):
    """Tests for the API failure escalation path."""

    def test_api_failure_triggers_escalation(self) -> None:
        """api_failed = 'true' triggers escalation even without _action_trigger."""
        ctx = self.create_mock_context(
            state={"api_failed": "true"},
            user_text="Show my bill details",
        )
        result = before_model_callback(ctx, llm_request=MagicMock())
        self.assertIsNotNone(result)
        self.assert_agent_reply(result, "experiencing technical difficulties")
