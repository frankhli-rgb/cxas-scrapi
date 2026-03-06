"""Unit tests for the eval conversation utility."""

import pytest
from unittest.mock import MagicMock, patch

from cxas_scrapi.evals.simulation_evals import LLMUserConversation
from cxas_scrapi.evals.simulation_evals import Step
from cxas_scrapi.evals.simulation_evals import StepProgress
from cxas_scrapi.evals.simulation_evals import StepStatus


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


from cxas_scrapi.evals.simulation_evals import SimulationEvals

@patch('cxas_scrapi.evals.simulation_evals.Sessions')
@patch('cxas_scrapi.evals.simulation_evals.LLMUserConversation')
def test_user_simulator(mock_llm_conv_class, mock_sessions_class):
    mock_sessions = mock_sessions_class.return_value
    mock_eval_conv = mock_llm_conv_class.return_value

    # Setup the mock conversation sequence
    mock_eval_conv.next_user_utterance.side_effect = ["I want to book a flight", ""]
    mock_eval_conv.steps_progress = []

    # Setup mock agent responses
    mock_response_1 = MagicMock()
    mock_response_1.session.name = "sessions/123"
    mock_output_1 = MagicMock()
    mock_output_1.text = "Where to?"
    mock_response_1.outputs = [mock_output_1]

    mock_response_2 = MagicMock()
    mock_response_2.session.name = "sessions/123"
    mock_output_2 = MagicMock()
    mock_output_2.text = "Flight booked."
    mock_response_2.outputs = [mock_output_2]
    mock_sessions.run.side_effect = [mock_response_1, mock_response_2]
    mock_sessions.create_session_id.return_value = "mock_session"

    # Initialize the SimulationEvals
    app_id = "projects/test/locations/us/apps/123-abc"
    with patch('cxas_scrapi.evals.simulation_evals.genai.Client'):
        with patch('cxas_scrapi.core.apps.AgentServiceClient'):
            simulator = SimulationEvals(app_id=app_id)

    # Run the simulation
    test_case = {"steps": []}
    result_conv = simulator.simulate_conversation(
        test_case=test_case,
        initial_utterance="Hi",
        console_logging=False
    )

    # Assertions
    mock_sessions.run.assert_any_call(session_id="mock_session", text="Hi")
    mock_sessions.run.assert_any_call(session_id="mock_session", text="I want to book a flight")
    mock_eval_conv.next_user_utterance.assert_any_call("Where to?")
    mock_eval_conv.next_user_utterance.assert_any_call("Flight booked.")
    assert result_conv == mock_eval_conv
    assert mock_sessions.run.call_count == 2
