import pytest
from unittest.mock import patch, MagicMock
from cxas_scrapi.utils.eval_utils import EvalUtils
import sys
import sys

def test_evals_to_dataframe_empty():
    """Test evals_to_dataframe with empty list."""
    utils = EvalUtils(app_id="p/l/a/a")
    sys.modules['pandas'] = MagicMock()
    df = utils.evals_to_dataframe([])
    assert df is not None

@patch('builtins.type')
def test_evals_to_dataframe_with_data(mock_type):
    """Test evals_to_dataframe with valid metrics."""
    utils = EvalUtils(app_id="p/l/a/a")
    
    res = MagicMock()
    res_dict = {
        "name": "eval/123",
        "evaluation_status": "PASS",
        "golden_result": {
            "metrics": {
                "semantic_similarity_result": {"score": 5},
                "overall_tool_invocation_result": {"tool_invocation_score": 1.0},
                "expectation_results": [
                    {
                        "expectation": "Agent should pass",
                        "met_count": 1,
                        "not_met_count": 0,
                        "met_percentage": 100.0,
                        "not_met_percentage": 0.0
                    }
                ]
            }
        }
    }
    
    mock_to_dict = MagicMock(return_value=res_dict)
    mock_type.return_value.to_dict = mock_to_dict
    
    mock_pd = MagicMock()
    sys.modules['pandas'] = mock_pd
    
    utils.evals_to_dataframe([res])
    
    mock_pd.DataFrame.assert_called_once()
    args = mock_pd.DataFrame.call_args[0][0]
    
    assert len(args) == 1
    assert args[0]["expectation"] == "Agent should pass"
    assert args[0]["met_count"] == 1
    assert args[0]["semantic_score"] == 5

def test_to_bigquery():
    """Test to_bigquery export without requiring pandas."""
    utils = EvalUtils(app_id="projects/test_project/locations/l/apps/a")
    
    # Mock the dataframe and its to_gbq method
    mock_df = MagicMock()
    
    # Mock out the google.cloud.bigquery and pandas_gbq imports
    sys.modules['google'] = MagicMock()
    sys.modules['google.cloud'] = MagicMock()
    sys.modules['google.cloud.bigquery'] = MagicMock()
    sys.modules['pandas_gbq'] = MagicMock()
    
    utils.to_bigquery(mock_df, "my_dataset.my_table")
    
    mock_df.to_gbq.assert_called_once_with(
        destination_table="my_dataset.my_table",
        project_id="test_project",
        if_exists="append",
        credentials=utils.creds
    )
    
    # Cleanup mocks
    del sys.modules['google.cloud.bigquery']
    del sys.modules['pandas_gbq']
