import pytest
from unittest.mock import patch, MagicMock
from cxas_scrapi.utils.eval_utils import EvalUtils
import sys
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
                "overall_tool_invocation_result": {"tool_invocation_score": 1.0},
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
