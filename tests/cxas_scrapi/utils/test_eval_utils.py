"""Tests for evaluation utility functions."""

from unittest.mock import MagicMock, patch
import yaml
from cxas_scrapi.utils.eval_utils import EvalUtils
import sys


def test_evals_to_dataframe_empty():
    """Test evals_to_dataframe with empty list."""
    utils = EvalUtils(app_id="p/l/a/a")
    df = utils.evals_to_dataframe([])
    assert df is not None


def test_evals_to_dataframe_with_data():
    """Test evals_to_dataframe with valid metrics."""
    utils = EvalUtils(app_id="p/l/a/a")

    class MockEvalResult:
        @classmethod
        def to_dict(cls, obj):
            return obj.res_dict

    res = MockEvalResult()
    res.res_dict = {
        "name": "eval/123",
        "evaluation_status": "PASS",
        "golden_result": {
            "metrics": {
                "semantic_similarity_result": {"score": 5},
                "overall_tool_invocation_result": {
                    "tool_invocation_score": 1.0
                },
                "expectation_results": [
                    {
                        "expectation": "Agent should pass",
                        "met_count": 0,
                        "not_met_count": 1,
                        "met_percentage": 0.0,
                        "not_met_percentage": 100.0,
                    }
                ],
            }
        },
    }

    df_dict = utils.evals_to_dataframe([res])
    
    assert len(df_dict["summary"]) == 1
    assert "semantic_score" in df_dict["summary"].columns
    assert "tool_invocation_score" in df_dict["summary"].columns

    assert len(df_dict["failures"]) == 1
    assert df_dict["failures"].iloc[0]["expected"] == "Agent should pass"


def test_to_bigquery():
    """Test to_bigquery export without requiring pandas."""
    utils = EvalUtils(app_id="projects/test_project/locations/l/apps/a")

    # Mock the dataframe and its to_gbq method
    mock_df = MagicMock()

    # Mock out the google.cloud.bigquery and pandas_gbq imports
    sys.modules["google"] = MagicMock()
    sys.modules["google.cloud"] = MagicMock()
    sys.modules["google.cloud.bigquery"] = MagicMock()
    sys.modules["pandas_gbq"] = MagicMock()

    utils.to_bigquery(mock_df, "my_dataset.my_table")

    mock_df.to_gbq.assert_called_once_with(
        destination_table="my_dataset.my_table",
        project_id="test_project",
        if_exists="append",
        credentials=utils.creds,
    )

    # Cleanup mocks
    del sys.modules["google.cloud.bigquery"]
    del sys.modules["pandas_gbq"]


def test_load_golden_eval_from_compressed_yaml():
    """Test load_golden_eval_from_yaml with compressed format."""
    # We want to test that EvalUtils.load_golden_eval_from_yaml parses this
    # correctly from the local example file.

    test_file_path = "tests/testdata/compressed_example.yaml"
    with (
        patch("cxas_scrapi.utils.eval_utils.uuid.uuid4") as mock_uuid,
    ):
        mock_uuid.return_value = "mock_uuid"

        result = EvalUtils.load_golden_eval_from_yaml(test_file_path)

        # Verify "Unlock_Intent1" (the first conversation) was picked up
        assert result["displayName"] == "Unlock_Intent1"
        assert result["tags"] == ["direct", "p0"]

        # Verify turns
        turns = result["golden"]["turns"]
        assert len(turns) == 2  # 2 turns in Unlock_Intent1

        # Turn 1: Implicit greeting -> Agent response
        # user: None -> event: welcome
        # agent: In a sentence or two...
        turn0_steps = turns[0]["steps"]
        assert turn0_steps[0]["userInput"]["event"]["event"] == "welcome"
        assert (
            turn0_steps[1]["expectation"]["agentResponse"]["chunks"][0]["text"]
            == "In a sentence or two, what are you calling about today?"
        )

        # Turn 2: User input -> Tool calls
        # user: "unlock a phone"
        # agent: # silent transfer (so no agentResponse expectation)
        # tool_calls: retrieve_intent_matches, transfer_to_cx
        turn1_steps = turns[1]["steps"]
        assert turn1_steps[0]["userInput"]["text"] == "unlock a phone"

        # Check tool calls
        # We expect toolCall expectations for each tool in the list
        # The order depends on implementation, but likely sequential

        # First tool: retrieve_intent_matches
        tool1 = turn1_steps[1]["expectation"]["toolCall"]
        assert tool1["tool"] == "retrieve_intent_matches"
        assert tool1["id"] == "adk-mock_uuid"

        # Second tool: transfer_to_cx
        tool2 = turn1_steps[2]["expectation"]["toolCall"]
        assert tool2["tool"] == "transfer_to_cx"
        assert tool2["id"] == "adk-mock_uuid"
        assert tool2["args"] == {"intent": "Unlock"}

        # Verify evaluation expectations
        eval_exps = result["golden"]["evaluationExpectations"]
        assert len(eval_exps) == 1


def test_load_golden_eval_from_exported_yaml():
    test_file_path = "tests/testdata/exported_eval_example.yaml"
    with (
        patch("cxas_scrapi.utils.eval_utils.uuid.uuid4") as mock_uuid,
    ):
        mock_uuid.return_value = "mock_uuid"

        result = EvalUtils.load_golden_eval_from_yaml(test_file_path)

        # Verify it returns the parsed data correctly
        assert result["displayName"] == "Basic Product Search Simplified"
        assert len(result["golden"]["turns"]) == 4
        assert (
            result["golden"]["turns"][0]["steps"][0]["userInput"]["event"][
                "event"
            ]
            == "WelcomeEvent"
        )
        assert (
            result["golden"]["evaluationExpectations"][0]["displayName"]
            == "Simple tool expectation 1"
        )
