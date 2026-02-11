import sys
from unittest.mock import MagicMock
sys.modules["google.cloud.ces_v1beta"] = MagicMock()
import pytest
from unittest.mock import patch, MagicMock
from cxas_scrapi.core.evaluations import Evaluations

@patch("cxas_scrapi.core.evaluations.EvaluationServiceClient")
def test_evaluations_list(mock_client_cls):
    """Test Evaluations.list_evaluations."""
    mock_client = mock_client_cls.return_value
    mock_eval = MagicMock()
    mock_eval.name = "projects/p/locations/l/apps/a/evaluations/e1"
    mock_eval.display_name = "Eval 1"
    
    mock_response = MagicMock()
    mock_response.evaluations = [mock_eval]
    mock_client.list_evaluations.return_value = mock_response

    evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")
    res = evals_client.list_evaluations()
    
    assert len(res) == 1
    assert res[0].display_name == "Eval 1"
    mock_client.list_evaluations.assert_called_once()

@patch("cxas_scrapi.core.evaluations.EvaluationServiceClient")
def test_evaluations_get_map(mock_client_cls):
    """Test Evaluations.get_evaluations_map."""
    mock_client = mock_client_cls.return_value
    mock_eval = MagicMock()
    mock_eval.name = "projects/p/locations/l/apps/a/evaluations/e1"
    mock_eval.display_name = "Eval 1"
    
    mock_response = MagicMock()
    mock_response.evaluations = [mock_eval]
    mock_client.list_evaluations.return_value = mock_response

    evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")
    
    res_normal = evals_client.get_evaluations_map()
    assert res_normal["projects/p/locations/l/apps/a/evaluations/e1"] == "Eval 1"
    
    res_reverse = evals_client.get_evaluations_map(reverse=True)
    assert res_reverse["Eval 1"] == "projects/p/locations/l/apps/a/evaluations/e1"

@patch("cxas_scrapi.core.evaluations.EvaluationServiceClient")
def test_evaluations_get(mock_client_cls):
    """Test Evaluations.get_evaluation."""
    mock_client = mock_client_cls.return_value
    mock_eval = MagicMock()
    mock_eval.name = "projects/p/locations/l/apps/a/evaluations/e1"
    mock_client.get_evaluation.return_value = mock_eval

    evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")
    res = evals_client.get_evaluation("projects/p/locations/l/apps/a/evaluations/e1")
    
    assert res.name == "projects/p/locations/l/apps/a/evaluations/e1"
    mock_client.get_evaluation.assert_called_once()

def test_eval_dict_to_yaml():
    """Test static method eval_dict_to_yaml."""
    eval_dict = {
        "display_name": "Test Eval",
        "golden": {
            "turns": [
                {
                    "steps": [
                        {
                            "user_input": {"text": "hi"}
                        },
                        {
                            "expectation": {
                                "agent_response": {
                                    "chunks": [{"text": "hello"}]
                                }
                            }
                        }
                    ]
                }
            ]
        }
    }
    
    res = Evaluations.eval_dict_to_yaml(eval_dict)
    assert res["name"] == "Test Eval"
    assert len(res["turns"]) == 2
    assert res["turns"][0] == {"user": "hi"}
    assert res["turns"][1] == {"agent": "hello"}

@patch("cxas_scrapi.core.evaluations.Evaluations.get_evaluation")
def test_export_evaluation_to_yaml(mock_get_eval):
    """Test Evaluations.export_evaluation_to_yaml."""
    mock_obj = MagicMock()
    mock_obj.display_name = "Exported Eval"
    
    # Mock the to_dict method
    with patch("cxas_scrapi.core.evaluations.type") as mock_type:
        mock_to_dict = MagicMock(return_value={"display_name": "Exported Eval", "golden": {"turns": []}})
        mock_type.return_value.to_dict = mock_to_dict
        
        evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")
        # We also need to mock credentials properly if it tries to init client
        with patch("cxas_scrapi.core.evaluations.EvaluationServiceClient"):
            yaml_str = evals_client.export_evaluation_to_yaml("projects/p/locations/l/apps/a/evaluations/e1")
            assert "name: Exported Eval" in yaml_str
