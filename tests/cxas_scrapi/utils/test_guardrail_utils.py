"""Tests for GuardrailUtils class in cxas_scrapi."""

import pytest
import pandas as pd
from unittest.mock import MagicMock, patch

from cxas_scrapi.utils.guardrail_utils import GuardrailUtils

@pytest.fixture
def dummy_app_id():
    return "projects/test-project/locations/us-central1/apps/test-app"

@pytest.fixture
def mock_df():
    data = {
        "user_input": ["test query 1", "test query 2"],
        "expected_guardrail_name": ["Profanity", None],
        "expected_guardrail_type": ["ON_DEMAND", None]
    }
    return pd.DataFrame(data)

@patch("cxas_scrapi.utils.guardrail_utils.Sessions")
@patch("cxas_scrapi.utils.guardrail_utils.Apps")
@patch("cxas_scrapi.utils.guardrail_utils.Agents")
def test_guardrail_execution_flow(
    mock_agents_class,
    mock_apps_class,
    mock_sessions_class,
    dummy_app_id,
    mock_df
):
    """
    Tests the end-to-end execution flow of GuardrailUtils similar to the
    Google Sheets/Notebook workflow without making live GCP API calls.
    """
    # Setup Mocks
    mock_sessions = mock_sessions_class.return_value
    mock_apps = mock_apps_class.return_value
    mock_agents = mock_agents_class.return_value

    mock_sessions.create_session_id.return_value = "projects/p/locations/l/sessions/123"

    # Mocking Apps.get_app response
    mock_app_obj = MagicMock()
    mock_app_obj.display_name = "Mocked Test App"
    mock_app_obj.model_settings.model = "gemini-1.5-pro"
    mock_apps.get_app.return_value = mock_app_obj

    # 1. First Response simulates a Guardrail Trigger (Profanity)
    response_triggered = MagicMock()
    output_triggered = MagicMock()
    output_triggered.message.text = "I cannot fulfill this request."
    
    # Needs to duck-type into the recursive `_search_span_dict` logic
    mock_root_span_dict = {
        "childSpans": [
            {
                "attributes": {
                    "name": "Profanity",
                    "type": "ON_DEMAND"
                }
            }
        ]
    }
    # Mock behavior for `dict(root_span)` to return our mock dictionary
    output_triggered.diagnostic_info.root_span = mock_root_span_dict
    response_triggered.outputs = [output_triggered]

    # 2. Second Response simulates a Pass (No guardrails triggered)
    response_clean = MagicMock()
    output_clean = MagicMock()
    output_clean.message.text = "Here is the information you requested!"
    output_clean.diagnostic_info.root_span = {"childSpans": []}
    response_clean.outputs = [output_clean]

    # Assign side effects to Sessions.run()
    mock_sessions.run.side_effect = [response_triggered, response_clean]

    # Initialize GuardrailUtils securely with mock args
    guard_utils = GuardrailUtils(app_id=dummy_app_id)

    # Execute tests
    results_df = guard_utils.run_guardrail_tests(mock_df, console_logging=False)

    # Validate the results DataFrame returned the appended metrics
    assert "pass" in results_df.columns
    assert len(results_df) == 2

    # Verify first test passed its evaluation logic 
    # (Expects Profanity, actually got Profanity)
    assert results_df.iloc[0]["pass"] == True
    assert results_df.iloc[0]["actual_guardrail_name"] == "Profanity"
    
    # Verify second test passed its evaluation logic 
    # (Expects None, actually got None)
    assert results_df.iloc[1]["pass"] == True
    assert results_df.iloc[1]["actual_guardrail_name"] is None

    # Test the reporting functionality
    summary_df = guard_utils.generate_report(results_df)
    
    assert "pass_rate" in summary_df.columns
    assert len(summary_df) == 1
    # 2 out of 2 passed matches intention
    assert summary_df.iloc[0]["pass_count"] == 2
    assert summary_df.iloc[0]["pass_rate"] == 1.0
