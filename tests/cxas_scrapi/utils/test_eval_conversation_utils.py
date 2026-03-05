"""Unit tests for the eval conversation utility."""

import pytest
from unittest.mock import MagicMock, patch

from cxas_scrapi.utils.eval_conversation_utils import LLMUserConversation
from cxas_scrapi.utils.eval_conversation_utils import Step
from cxas_scrapi.utils.eval_conversation_utils import StepProgress
from cxas_scrapi.utils.eval_conversation_utils import StepStatus


def test_llm_user_conversation():
    mock_genai_client = MagicMock()

    user_utterance_0 = "Hi"
    agent_response_1 = "Hi, how can I help you?"
    user_utterance_1 = "I want to book a flight."
    agent_response_2 = "Done"

    step_1 = Step(
        goal="Book a flight", success_criteria="Successfully booked a flight"
    )

    mock_genai_client.models.generate_content.return_value.parsed = (
        LLMUserConversation.Output(
            next_user_utterance=user_utterance_1,
            step_progresses=[
                StepProgress(
                    step=step_1,
                    status=StepStatus.COMPLETED,
                    justification="User booked a flight.",
                )
            ],
        )
    )

    test_case = {
        "name": "test_case_2",
        "user_utterances": [],
        "steps": [step_1.model_dump()],
    }

    llm_conv = LLMUserConversation(
        genai_client=mock_genai_client,
        genai_model="gemini-1.5-flash",
        test_case=test_case,
    )

    assert llm_conv.steps_progress[0].status == StepStatus.NOT_STARTED

    got_user_utterance_0 = llm_conv.next_user_utterance("")
    assert got_user_utterance_0 == user_utterance_0
    assert llm_conv.get_num_turns() == 1
    assert llm_conv.get_transcript() == "\n".join(["Agent: ", f"User: {user_utterance_0}"])

    got_user_utterance_1 = llm_conv.next_user_utterance(agent_response_1)
    assert got_user_utterance_1 == user_utterance_1
    assert llm_conv.get_num_turns() == 2
    assert llm_conv.get_transcript() == "\n".join([
        "Agent: ",
        f"User: {user_utterance_0}",
        f"Agent: {agent_response_1}",
        f"User: {user_utterance_1}",
    ])

    assert llm_conv.steps_progress[0].status == StepStatus.COMPLETED

    got_user_utterance_2 = llm_conv.next_user_utterance(agent_response_2)
    assert got_user_utterance_2 == ""
    assert llm_conv.get_num_turns() == 3
    assert llm_conv.get_transcript() == "\n".join([
        "Agent: ",
        f"User: {user_utterance_0}",
        f"Agent: {agent_response_1}",
        f"User: {user_utterance_1}",
        f"Agent: {agent_response_2}",
        "User: ",
    ])

    mock_genai_client.models.generate_content.assert_called_once()


def test_llm_user_conversation_max_turns():
    mock_genai_client = MagicMock()

    user_utterance_0 = "Hi"
    agent_response_1 = "Hi, how can I help you?"

    step_1 = Step(
        goal="Book a flight", success_criteria="Successfully booked a flight"
    )

    test_case = {
        "name": "test_case_max_turns",
        "user_utterances": [],
        "steps": [step_1.model_dump()],
    }

    llm_conv = LLMUserConversation(
        genai_client=mock_genai_client,
        genai_model="gemini-1.5-flash",
        test_case=test_case,
        max_turns=1,
    )

    got_user_utterance_0 = llm_conv.next_user_utterance("")
    assert got_user_utterance_0 == user_utterance_0
    assert llm_conv.get_num_turns() == 1
    assert llm_conv.get_transcript() == "\n".join(["Agent: ", f"User: {user_utterance_0}"])

    # Last turn since we reached the max turns.
    got_user_utterance_1 = llm_conv.next_user_utterance(agent_response_1)
    assert got_user_utterance_1 == ""
    assert llm_conv.get_num_turns() == 2
    assert llm_conv.get_transcript() == "\n".join([
        "Agent: ",
        f"User: {user_utterance_0}",
        f"Agent: {agent_response_1}",
        "User: ",
    ])

    # LLM call never gets made because we reached the max turns.
    mock_genai_client.models.generate_content.assert_not_called()
    assert llm_conv.steps_progress[0].status == StepStatus.NOT_STARTED
