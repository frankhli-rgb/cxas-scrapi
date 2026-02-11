import pytest
from unittest.mock import patch, MagicMock
from cxas_scrapi.core.versions import Versions

@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_list_versions(mock_client_cls):
    mock_client = mock_client_cls.return_value
    mock_ver = MagicMock()
    mock_ver.name = "v1"
    mock_resp = MagicMock()
    mock_resp.app_versions = [mock_ver]
    mock_client.list_app_versions.return_value = mock_resp

    v = Versions("p", "l")
    res = v.list_versions("app1")
    assert len(res) == 1
    assert res[0].name == "v1"
    mock_client.list_app_versions.assert_called_once()


@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_get_versions_map(mock_client_cls):
    mock_client = mock_client_cls.return_value
    mock_v1 = MagicMock()
    mock_v1.name = "v1"
    mock_v1.display_name = "n1"
    mock_v2 = MagicMock()
    mock_v2.name = "v2"
    mock_v2.display_name = "n2"
    mock_resp = MagicMock()
    mock_resp.app_versions = [mock_v1, mock_v2]
    mock_client.list_app_versions.return_value = mock_resp

    v = Versions("p", "l")
    res = v.get_versions_map("app1")
    assert res["v1"] == "n1"
    assert res["v2"] == "n2"

    res_rev = v.get_versions_map("app1", reverse=True)
    assert res_rev["n1"] == "v1"
    assert res_rev["n2"] == "v2"

@patch("cxas_scrapi.core.versions.types.GetAppVersionRequest")
@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_get_version(mock_client_cls, mock_req_cls):
    mock_client = mock_client_cls.return_value
    mock_v = MagicMock()
    mock_v.name = "v_id"
    mock_client.get_app_version.return_value = mock_v

    def side_effect(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items(): setattr(m, k, v)
        return m
    mock_req_cls.side_effect = side_effect

    v = Versions("p", "l")
    res = v.get_version("v_id")
    assert res.name == "v_id"
    mock_client.get_app_version.assert_called_once()
    assert mock_client.get_app_version.call_args[1]["request"].name == "v_id"


@patch("cxas_scrapi.core.versions.types.DeleteAppVersionRequest")
@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_delete_version(mock_client_cls, mock_req_cls):
    mock_client = mock_client_cls.return_value

    def side_effect(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items(): setattr(m, k, v)
        return m
    mock_req_cls.side_effect = side_effect

    v = Versions("p", "l")
    v.delete_version("v_id")
    mock_client.delete_app_version.assert_called_once()
    args = mock_client.delete_app_version.call_args[1]["request"]
    assert args.name == "v_id"


@patch("cxas_scrapi.core.versions.types.RestoreAppVersionRequest")
@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_revert_version(mock_client_cls, mock_req_cls):
    mock_client = mock_client_cls.return_value
    mock_client.restore_app_version.return_value = MagicMock()

    def side_effect(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items(): setattr(m, k, v)
        return m
    mock_req_cls.side_effect = side_effect

    v = Versions("p", "l")
    res = v.revert_version("v_id")
    mock_client.restore_app_version.assert_called_once()
    args = mock_client.restore_app_version.call_args[1]["request"]
    assert args.name == "v_id"
