import pytest
from unittest.mock import patch, MagicMock
from cxas_scrapi.core.deployments import Deployments


@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_list_deployments(mock_client_cls):
    mock_client = mock_client_cls.return_value
    mock_dep = MagicMock()
    mock_dep.name = "dep1"
    mock_client.list_deployments.return_value = [mock_dep]

    deps = Deployments("projects/p/locations/l/apps/A")
    res = deps.list_deployments("app1")
    assert len(res) == 1
    assert res[0].name == "dep1"


@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_get_deployments_map(mock_client_cls):
    mock_client = mock_client_cls.return_value
    mock_dep1 = MagicMock()
    mock_dep1.name = "d1"
    mock_dep1.display_name = "n1"
    mock_dep2 = MagicMock()
    mock_dep2.name = "d2"
    mock_dep2.display_name = "n2"
    mock_client.list_deployments.return_value = [mock_dep1, mock_dep2]

    deps = Deployments("projects/p/locations/l/apps/A")
    res = deps.get_deployments_map("app1")
    assert res["d1"] == "n1"
    assert res["d2"] == "n2"

    res_rev = deps.get_deployments_map("app1", reverse=True)
    assert res_rev["n1"] == "d1"
    assert res_rev["n2"] == "d2"


@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_get_deployment(mock_client_cls):
    mock_client = mock_client_cls.return_value
    mock_dep = MagicMock()
    mock_dep.name = "dep_id"
    mock_client.get_deployment.return_value = mock_dep

    deps = Deployments("projects/p/locations/l/apps/A")
    res = deps.get_deployment("dep_id")
    assert res.name == "dep_id"
    mock_client.get_deployment.assert_called_once()


@patch("cxas_scrapi.core.deployments.types.CreateDeploymentRequest")
@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_create_deployment(mock_client_cls, mock_req_cls):
    mock_client = mock_client_cls.return_value
    mock_client.create_deployment.return_value = MagicMock()

    def side_effect(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items():
            setattr(m, k, v)
        return m

    mock_req_cls.side_effect = side_effect

    deps = Deployments("projects/p/locations/l/apps/A")
    res = deps.create_deployment("app1", "dep_id", "my_dep", "v1")
    mock_client.create_deployment.assert_called_once()
    args = mock_client.create_deployment.call_args[1]["request"]
    assert args.parent == "app1"
    assert args.deployment_id == "dep_id"


@patch("cxas_scrapi.core.deployments.types.Deployment")
@patch("cxas_scrapi.core.deployments.types.UpdateDeploymentRequest")
@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_update_deployment(mock_client_cls, mock_req_cls, mock_dep_cls):
    mock_client = mock_client_cls.return_value
    mock_client.update_deployment.return_value = MagicMock()

    def side_effect(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items():
            setattr(m, k, v)
        return m

    mock_req_cls.side_effect = side_effect
    mock_dep_cls.side_effect = side_effect

    deps = Deployments("projects/p/locations/l/apps/A")
    res = deps.update_deployment("dep_id", display_name="new_name")
    mock_client.update_deployment.assert_called_once()
    args = mock_client.update_deployment.call_args[1]["request"]
    assert args.deployment.name == "dep_id"
    assert args.deployment.display_name == "new_name"


@patch("cxas_scrapi.core.deployments.types.DeleteDeploymentRequest")
@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_delete_deployment(mock_client_cls, mock_req_cls):
    mock_client = mock_client_cls.return_value

    def side_effect(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items():
            setattr(m, k, v)
        return m

    mock_req_cls.side_effect = side_effect

    deps = Deployments("projects/p/locations/l/apps/A")
    deps.delete_deployment("dep_id")
    mock_client.delete_deployment.assert_called_once()
    args = mock_client.delete_deployment.call_args[1]["request"]
    assert args.name == "dep_id"
