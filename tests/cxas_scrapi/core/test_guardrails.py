import pytest
from unittest.mock import patch, MagicMock
from cxas_scrapi.core.guardrails import Guardrails


@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_list_guardrails(mock_client_cls):
    mock_client = mock_client_cls.return_value
    mock_gr = MagicMock()
    mock_gr.name = "gr1"
    mock_client.list_guardrails.return_value = [mock_gr]

    grs = Guardrails("projects/p/locations/l/apps/A")
    res = grs.list_guardrails("app1")
    assert len(res) == 1
    assert res[0].name == "gr1"


@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_get_guardrails_map(mock_client_cls):
    mock_client = mock_client_cls.return_value
    mock_gr1 = MagicMock()
    mock_gr1.name = "g1"
    mock_gr1.display_name = "n1"
    mock_gr2 = MagicMock()
    mock_gr2.name = "g2"
    mock_gr2.display_name = "n2"
    mock_client.list_guardrails.return_value = [mock_gr1, mock_gr2]

    grs = Guardrails("projects/p/locations/l/apps/A")
    res = grs.get_guardrails_map("app1")
    assert res["g1"] == "n1"
    assert res["g2"] == "n2"

    res_rev = grs.get_guardrails_map("app1", reverse=True)
    assert res_rev["n1"] == "g1"
    assert res_rev["n2"] == "g2"


@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_get_guardrail(mock_client_cls):
    mock_client = mock_client_cls.return_value
    mock_gr = MagicMock()
    mock_gr.name = "gr_id"
    mock_client.get_guardrail.return_value = mock_gr

    grs = Guardrails("projects/p/locations/l/apps/A")
    res = grs.get_guardrail("gr_id")
    assert res.name == "gr_id"
    mock_client.get_guardrail.assert_called_once()


@patch("cxas_scrapi.core.guardrails.types.Guardrail")
@patch("cxas_scrapi.core.guardrails.types.CreateGuardrailRequest")
@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_create_guardrail(mock_client_cls, mock_req_cls, mock_gr_cls):
    mock_client = mock_client_cls.return_value
    mock_client.create_guardrail.return_value = MagicMock()

    def side_effect(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items():
            setattr(m, k, v)
        return m

    mock_req_cls.side_effect = side_effect
    mock_gr_cls.side_effect = side_effect

    grs = Guardrails("projects/p/locations/l/apps/A")

    payload = {"model_safety": {"safety_settings": []}, "display_name": "ignore_me"}
    res = grs.create_guardrail("app1", "gr_id", "my_gr", payload=payload)
    mock_client.create_guardrail.assert_called_once()

    args = mock_client.create_guardrail.call_args[1]["request"]
    assert args.parent == "app1"
    assert args.guardrail_id == "gr_id"
    assert args.guardrail.display_name == "my_gr"
    assert args.guardrail.model_safety is not None


@patch("cxas_scrapi.core.guardrails.types.Guardrail")
@patch("cxas_scrapi.core.guardrails.types.UpdateGuardrailRequest")
@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_update_guardrail(mock_client_cls, mock_req_cls, mock_gr_cls):
    mock_client = mock_client_cls.return_value
    mock_client.update_guardrail.return_value = MagicMock()

    def side_effect(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items():
            setattr(m, k, v)
        return m

    mock_req_cls.side_effect = side_effect
    mock_gr_cls.side_effect = side_effect

    grs = Guardrails("projects/p/locations/l/apps/A")
    res = grs.update_guardrail("gr_id", action="DENY")
    mock_client.update_guardrail.assert_called_once()

    args = mock_client.update_guardrail.call_args[1]["request"]
    assert args.guardrail.name == "gr_id"
    assert args.guardrail.action == "DENY"


@patch("cxas_scrapi.core.guardrails.types.DeleteGuardrailRequest")
@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_delete_guardrail(mock_client_cls, mock_req_cls):
    mock_client = mock_client_cls.return_value

    def side_effect(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items():
            setattr(m, k, v)
        return m

    mock_req_cls.side_effect = side_effect

    grs = Guardrails("projects/p/locations/l/apps/A")
    grs.delete_guardrail("gr_id")
    mock_client.delete_guardrail.assert_called_once()

    args = mock_client.delete_guardrail.call_args[1]["request"]
    assert args.name == "gr_id"
