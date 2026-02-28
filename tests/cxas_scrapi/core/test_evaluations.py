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
    mock_client.list_evaluations.return_value = [mock_eval]

    evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")
    res = evals_client.list_evaluations()

    assert len(res) == 1
    assert res[0].display_name == "Eval 1"
    mock_client.list_evaluations.assert_called_once()


@patch("cxas_scrapi.core.evaluations.EvaluationServiceClient")
def test_evaluations_get_map(mock_client_cls):
    """Test Evaluations.get_evaluations_map."""
    mock_client = mock_client_cls.return_value

    mock_eval1 = MagicMock()
    mock_eval1.name = "projects/p/locations/l/apps/a/evaluations/e1"
    mock_eval1.display_name = "Eval 1"
    mock_eval1.golden = True
    mock_eval1.scenario = None

    mock_eval2 = MagicMock()
    mock_eval2.name = "projects/p/locations/l/apps/a/evaluations/e2"
    mock_eval2.display_name = "Eval 2"
    mock_eval2.golden = None
    mock_eval2.scenario = True

    mock_client.list_evaluations.return_value = [mock_eval1, mock_eval2]

    evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")

    res_normal = evals_client.get_evaluations_map()
    assert (
        res_normal["goldens"]["projects/p/locations/l/apps/a/evaluations/e1"]
        == "Eval 1"
    )
    assert (
        res_normal["scenarios"]["projects/p/locations/l/apps/a/evaluations/e2"]
        == "Eval 2"
    )

    res_reverse = evals_client.get_evaluations_map(reverse=True)
    assert (
        res_reverse["goldens"]["Eval 1"]
        == "projects/p/locations/l/apps/a/evaluations/e1"
    )
    assert (
        res_reverse["scenarios"]["Eval 2"]
        == "projects/p/locations/l/apps/a/evaluations/e2"
    )


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
                        {"user_input": {"text": "hi"}},
                        {
                            "expectation": {
                                "agent_response": {"chunks": [{"text": "hello"}]}
                            }
                        },
                    ]
                }
            ]
        },
    }

    res = Evaluations.eval_dict_to_yaml(eval_dict)
    assert res["name"] == "Test Eval"
    assert len(res["turns"]) == 2
    assert res["turns"][0] == {"user": "hi"}
    assert res["turns"][1] == {"agent": "hello"}


@patch("cxas_scrapi.core.evaluations.Evaluations.get_evaluation")
def test_export_evaluation(mock_get_eval):
    """Test Evaluations.export_evaluation."""
    mock_obj = MagicMock()
    mock_obj.display_name = "Exported Eval"

    # Mock the to_dict method
    with patch("cxas_scrapi.core.evaluations.type") as mock_type:
        mock_to_dict = MagicMock(
            return_value={"display_name": "Exported Eval", "golden": {"turns": []}}
        )
        mock_type.return_value.to_dict = mock_to_dict

        evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")
        # We also need to mock credentials properly if it tries to init client
        with patch("cxas_scrapi.core.evaluations.EvaluationServiceClient"):
            yaml_str = evals_client.export_evaluation(
                "projects/p/locations/l/apps/a/evaluations/e1"
            )
            assert "name: Exported Eval" in yaml_str

            json_str = evals_client.export_evaluation(
                "projects/p/locations/l/apps/a/evaluations/e1", output_format="json"
            )
            assert '"name": "Exported Eval"' in json_str


@patch("cxas_scrapi.core.evaluations.EvaluationServiceClient")
def test_import_evaluations(mock_client_cls):
    """Test Evaluations.import_evaluations."""
    mock_client = mock_client_cls.return_value
    evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")

    # Test GCS URI
    evals_client.import_evaluations(gcs_uri="gs://bucket/file.csv", conflict_strategy=1)
    mock_client.import_evaluations.assert_called_once()

    mock_client.import_evaluations.reset_mock()

    # Test CSV Content
    evals_client.import_evaluations(csv_content=b"foo,bar")
    mock_client.import_evaluations.assert_called_once()

    mock_client.import_evaluations.reset_mock()

    # Test Conversations
    evals_client.import_evaluations(
        conversations=["projects/p/locations/l/apps/a/conversations/c1"]
    )
    mock_client.import_evaluations.assert_called_once()


@patch("cxas_scrapi.core.evaluations.EvaluationServiceClient")
def test_list_evaluation_expectations(mock_client_cls):
    """Test Evaluations.list_evaluation_expectations."""
    mock_client = mock_client_cls.return_value
    mock_client.list_evaluation_expectations.return_value = ["exp1", "exp2"]

    evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")
    res = evals_client.list_evaluation_expectations()

    assert len(res) == 2
    mock_client.list_evaluation_expectations.assert_called_once()


@patch("cxas_scrapi.core.evaluations.EvaluationServiceClient")
def test_get_evaluation_expectation(mock_client_cls):
    """Test Evaluations.get_evaluation_expectation."""
    mock_client = mock_client_cls.return_value
    mock_exp = MagicMock()
    mock_exp.name = "projects/p/locations/l/apps/a/evaluationExpectations/e1"
    mock_client.get_evaluation_expectation.return_value = mock_exp

    evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")
    res = evals_client.get_evaluation_expectation(
        "projects/p/locations/l/apps/a/evaluationExpectations/e1"
    )

    assert res.name == "projects/p/locations/l/apps/a/evaluationExpectations/e1"
    mock_client.get_evaluation_expectation.assert_called_once()


@patch("cxas_scrapi.core.evaluations.EvaluationServiceClient")
def test_create_evaluation_expectation(mock_client_cls):
    """Test Evaluations.create_evaluation_expectation."""
    mock_client = mock_client_cls.return_value
    mock_client.create_evaluation_expectation.return_value = MagicMock(
        name="created_exp"
    )

    evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")

    # Test with dict
    res = evals_client.create_evaluation_expectation({"display_name": "New Exp"})

    mock_client.create_evaluation_expectation.assert_called_once()


@patch("cxas_scrapi.core.evaluations.EvaluationServiceClient")
def test_update_evaluation_expectation(mock_client_cls):
    """Test Evaluations.update_evaluation_expectation."""
    mock_client = mock_client_cls.return_value

    evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")
    mock_exp = MagicMock()

    evals_client.update_evaluation_expectation(mock_exp)

    mock_client.update_evaluation_expectation.assert_called_once()


@patch("cxas_scrapi.core.evaluations.EvaluationServiceClient")
def test_delete_evaluation_expectation(mock_client_cls):
    """Test Evaluations.delete_evaluation_expectation."""
    mock_client = mock_client_cls.return_value

    evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")
    evals_client.delete_evaluation_expectation(
        "projects/p/locations/l/apps/a/evaluationExpectations/e1"
    )

    mock_client.delete_evaluation_expectation.assert_called_once()


@patch("cxas_scrapi.core.evaluations.AgentServiceClient")
def test_get_evaluation_thresholds(mock_agent_client_cls):
    """Test Evaluations.get_evaluation_thresholds."""
    mock_agent_client = mock_agent_client_cls.return_value

    # Create a mock App with thresholds
    from google.cloud.ces_v1beta import types

    app_obj = types.App()

    # Safely assign values simulating what the API would return
    thresholds = (
        app_obj.evaluation_metrics_thresholds.golden_evaluation_metrics_thresholds
    )
    thresholds.turn_level_metrics_thresholds.semantic_similarity_success_threshold = 3
    thresholds.turn_level_metrics_thresholds.overall_tool_invocation_correctness_threshold = (
        1.0
    )

    mock_agent_client.get_app.return_value = app_obj

    with patch(
        "cxas_scrapi.core.evaluations.json_format.MessageToDict"
    ) as mock_message_to_dict:
        mock_message_to_dict.return_value = {
            "evaluation_metrics_thresholds": {
                "golden_evaluation_metrics_thresholds": {
                    "turn_level_metrics_thresholds": {
                        "semantic_similarity_success_threshold": 3
                    }
                }
            }
        }
        evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")
        res = evals_client.get_evaluation_thresholds()

    mock_agent_client.get_app.assert_called_once()

    assert "golden_evaluation_metrics_thresholds" in res
    assert (
        res["golden_evaluation_metrics_thresholds"]["turn_level_metrics_thresholds"][
            "semantic_similarity_success_threshold"
        ]
        == 3
    )


@patch("cxas_scrapi.core.evaluations.types")
@patch("cxas_scrapi.core.evaluations.EvaluationServiceClient")
def test_run_evaluation(mock_client_cls, mock_types):
    """Test Evaluations.run_evaluation."""
    mock_client = mock_client_cls.return_value

    evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")

    mock_map = {
        "goldens": {
            "First Golden": "projects/p/locations/l/apps/a/evaluations/g1",
            "Second Golden": "projects/p/locations/l/apps/a/evaluations/g2",
        },
        "scenarios": {"First Scenario": "projects/p/locations/l/apps/a/evaluations/s1"},
    }

    with patch.object(evals_client, "_get_or_load_evals_map", return_value=mock_map):
        # Test running by display name list
        mock_types.RunEvaluationRequest.reset_mock()
        evals_client.run_evaluation(evaluations=["First Golden", "First Scenario"])
        request_kwargs = mock_types.RunEvaluationRequest.call_args[1]
        assert set(request_kwargs["evaluations"]) == {
            "projects/p/locations/l/apps/a/evaluations/g1",
            "projects/p/locations/l/apps/a/evaluations/s1",
        }

        # Test single evaluation display name
        mock_types.RunEvaluationRequest.reset_mock()
        evals_client.run_evaluation(evaluations="Second Golden")
        request_kwargs = mock_types.RunEvaluationRequest.call_args[1]
        assert list(request_kwargs["evaluations"]) == [
            "projects/p/locations/l/apps/a/evaluations/g2"
        ]

        # Test run by eval_type "goldens"
        mock_types.RunEvaluationRequest.reset_mock()
        evals_client.run_evaluation(eval_type="goldens")
        request_kwargs = mock_types.RunEvaluationRequest.call_args[1]
        assert set(request_kwargs["evaluations"]) == {
            "projects/p/locations/l/apps/a/evaluations/g1",
            "projects/p/locations/l/apps/a/evaluations/g2",
        }

        # Test run by eval_type "all"
        mock_types.RunEvaluationRequest.reset_mock()
        evals_client.run_evaluation(eval_type="all")
        request_kwargs = mock_types.RunEvaluationRequest.call_args[1]
        assert len(request_kwargs["evaluations"]) == 3

        # Test error cases
        with pytest.raises(ValueError):
            evals_client.run_evaluation()

        with pytest.raises(ValueError):
            evals_client.run_evaluation(evaluations=["Not Found"])


@patch("cxas_scrapi.core.evaluations.types")
@patch("cxas_scrapi.core.evaluations.EvaluationServiceClient")
def test_get_evaluation_run(mock_client_cls, mock_types):
    """Test Evaluations.get_evaluation_run."""
    mock_client = mock_client_cls.return_value
    evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")

    mock_types.GetEvaluationRunRequest.reset_mock()
    evals_client.get_evaluation_run(
        evaluation_run_id="projects/p/locations/l/apps/a/evaluationRuns/r1"
    )

    mock_client.get_evaluation_run.assert_called_once()
    request_kwargs = mock_types.GetEvaluationRunRequest.call_args[1]
    assert request_kwargs["name"] == "projects/p/locations/l/apps/a/evaluationRuns/r1"


@patch("cxas_scrapi.core.evaluations.types")
@patch("cxas_scrapi.core.evaluations.EvaluationServiceClient")
def test_list_evaluation_results_by_run(mock_client_cls, mock_types):
    """Test Evaluations.list_evaluation_results_by_run."""
    mock_client = mock_client_cls.return_value
    evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")

    mock_types.ListEvaluationResultsRequest.reset_mock()
    evals_client.list_evaluation_results_by_run(
        evaluation_run_id="projects/p/locations/l/apps/other/evaluationRuns/r1"
    )

    mock_client.list_evaluation_results.assert_called_once()
    request_kwargs = mock_types.ListEvaluationResultsRequest.call_args[1]
    assert request_kwargs["parent"] == "projects/p/locations/l/apps/other/evaluations/-"
    assert (
        request_kwargs["filter"]
        == 'evaluation_run:"projects/p/locations/l/apps/other/evaluationRuns/r1"'
    )

    # Test error condition
    with pytest.raises(ValueError):
        evals_client.list_evaluation_results_by_run(evaluation_run_id="invalid_format")


class MockEval:
    """Mock Evaluation proto object for testing."""

    def __init__(self, display_name, data_dict):
        self.display_name = display_name
        self.data_dict = data_dict

    @classmethod
    def to_dict(cls, obj):
        return obj.data_dict


@patch("cxas_scrapi.core.evaluations.EvaluationServiceClient")
def test_build_search_index(mock_client_cls):
    """Test Evaluations.build_search_index."""
    evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")
    evals_client.list_evaluations = MagicMock(
        return_value=[
            MockEval("My Eval 1", {"foo": "bar", "tools": "projects/p/tools/t1"}),
            MockEval("My Eval 2", {"foo": "baz", "variables": "var_1"}),
        ]
    )

    evals_client.build_search_index()

    assert len(evals_client._eval_search_index) == 2
    assert "projects/p/tools/t1" in evals_client._eval_search_index["My Eval 1"]
    assert "var_1" in evals_client._eval_search_index["My Eval 2"]

    # Test that calling it again without force=True doesn't rebuild
    evals_client.list_evaluations = MagicMock()
    evals_client.build_search_index()
    evals_client.list_evaluations.assert_not_called()

    # Test force=True
    evals_client.build_search_index(force=True)
    evals_client.list_evaluations.assert_called_once()


@patch("cxas_scrapi.core.evaluations.Agents")
@patch("cxas_scrapi.core.evaluations.Tools")
@patch("cxas_scrapi.core.evaluations.EvaluationServiceClient")
def test_search_evaluations(mock_client_cls, mock_tools_cls, mock_agents_cls):
    """Test Evaluations.search_evaluations."""
    evals_client = Evaluations(app_id="projects/p/locations/l/apps/a")
    evals_client.list_evaluations = MagicMock(
        return_value=[
            MockEval(
                "Eval Tool 1", {"tools": "projects/p/tools/t1", "variables": "var1"}
            ),
            MockEval("Eval Agent 1", {"agents": "projects/p/agents/a1"}),
            MockEval(
                "Eval Both",
                {"tools": "projects/p/tools/t2", "agents": "projects/p/agents/a1"},
            ),
        ]
    )

    mock_tools_instance = mock_tools_cls.return_value
    mock_tools_instance.get_tools_map.return_value = {
        "My Tool 1": "projects/p/tools/t1",
        "My Tool 2": "projects/p/tools/t2",
    }

    mock_agents_instance = mock_agents_cls.return_value
    mock_agents_instance.get_agents_map.return_value = {
        "My Agent 1": "projects/p/agents/a1",
    }

    # Search for tool 1
    res = evals_client.search_evaluations(
        app_id="projects/p/locations/l/apps/a", tools=["My Tool 1"]
    )
    assert res == ["Eval Tool 1"]

    # Search for agent 1
    res = evals_client.search_evaluations(
        app_id="projects/p/locations/l/apps/a", agents=["My Agent 1"]
    )
    assert set(res) == {"Eval Agent 1", "Eval Both"}

    # Search by variable
    res = evals_client.search_evaluations(
        app_id="projects/p/locations/l/apps/a", variables=["var1"]
    )
    assert res == ["Eval Tool 1"]

    # Search by multiple
    res = evals_client.search_evaluations(
        app_id="projects/p/locations/l/apps/a",
        tools=["My Tool 2"],
        agents=["My Agent 1"],
    )
    assert res == ["Eval Both"]

    # Test error cases
    with pytest.raises(ValueError):
        evals_client.search_evaluations(
            app_id="projects/p/locations/l/apps/a", tools=["Invalid Tool"]
        )

    with pytest.raises(ValueError):
        evals_client.search_evaluations(
            app_id="projects/p/locations/l/apps/a", agents=["Invalid Agent"]
        )

    with pytest.raises(ValueError, match="Must provide at least one search term"):
        evals_client.search_evaluations(app_id="projects/p/locations/l/apps/a")
