import pytest
from unittest.mock import patch, MagicMock
from cxas_scrapi.core.tools import Tools

@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_list_tools(mock_client_cls):
    mock_client = mock_client_cls.return_value
    
    mock_tool = MagicMock()
    mock_tool.name = "t1"
    mock_tools_resp = MagicMock()
    mock_tools_resp.tools = [mock_tool]
    mock_client.list_tools.return_value = mock_tools_resp
    
    mock_toolset = MagicMock()
    mock_toolset.name = "ts1"
    mock_toolsets_resp = MagicMock()
    mock_toolsets_resp.toolsets = [mock_toolset]
    mock_client.list_toolsets.return_value = mock_toolsets_resp

    t = Tools("p", "l")
    res = t.list_tools("app1")
    assert len(res) == 2
    assert res[0].name == "t1"
    assert res[1].name == "ts1"

@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_get_tools_map(mock_client_cls):
    mock_client = mock_client_cls.return_value
    
    mock_t1 = MagicMock()
    mock_t1.name = "t1"
    mock_t1.display_name = "n1"
    mock_client.list_tools.return_value.tools = [mock_t1]
    
    mock_ts1 = MagicMock()
    mock_ts1.name = "ts1"
    mock_ts1.display_name = "ns1"
    mock_client.list_toolsets.return_value.toolsets = [mock_ts1]

    t = Tools("p", "l")
    res = t.get_tools_map("app1")
    assert res["t1"] == "n1"
    assert res["ts1"] == "ns1"

    res_rev = t.get_tools_map("app1", reverse=True)
    assert res_rev["n1"] == "t1"
    assert res_rev["ns1"] == "ts1"

@patch("cxas_scrapi.core.tools.types.GetToolRequest")
@patch("cxas_scrapi.core.tools.types.GetToolsetRequest")
@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_get_tool(mock_client_cls, mock_ts_req_cls, mock_t_req_cls):
    mock_client = mock_client_cls.return_value
    
    def side_effect(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items(): setattr(m, k, v)
        return m
    mock_ts_req_cls.side_effect = side_effect
    mock_t_req_cls.side_effect = side_effect

    t = Tools("p", "l")
    
    # Test tool
    mock_client.get_tool.return_value = MagicMock(name="t1")
    res = t.get_tool("apps/A/tools/T")
    mock_client.get_tool.assert_called_once()
    assert mock_client.get_tool.call_args[1]["request"].name == "apps/A/tools/T"
    
    # Test toolset
    mock_client.get_toolset.return_value = MagicMock(name="ts1")
    res = t.get_tool("apps/A/toolsets/TS")
    mock_client.get_toolset.assert_called_once()
    assert mock_client.get_toolset.call_args[1]["request"].name == "apps/A/toolsets/TS"

@patch("cxas_scrapi.core.tools.types.Tool")
@patch("cxas_scrapi.core.tools.types.CreateToolRequest")
@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_create_tool(mock_client_cls, mock_req_cls, mock_tool_cls):
    mock_client = mock_client_cls.return_value
    
    def side_effect(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items(): setattr(m, k, v)
        return m
    mock_req_cls.side_effect = side_effect
    mock_tool_cls.side_effect = side_effect

    t = Tools("p", "l")
    
    res = t.create_tool(
        app_id="app1", 
        tool_id="t1", 
        display_name="my_tool", 
        payload={"python_code": "print(1)"},
        tool_type="python_function",
        description="desc"
    )
    
    mock_client.create_tool.assert_called_once()
    args = mock_client.create_tool.call_args[1]["request"]
    assert args.parent == "app1"
    assert args.tool_id == "t1"
    assert args.tool.display_name == "my_tool"

@patch("cxas_scrapi.core.tools.types.Toolset")
@patch("cxas_scrapi.core.tools.types.CreateToolsetRequest")
@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_create_toolset(mock_client_cls, mock_req_cls, mock_tool_cls):
    mock_client = mock_client_cls.return_value
    
    def side_effect(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items(): setattr(m, k, v)
        return m
    mock_req_cls.side_effect = side_effect
    mock_tool_cls.side_effect = side_effect

    t = Tools("p", "l")
    
    res = t.create_tool(
        app_id="app1", 
        tool_id="ts1", 
        display_name="my_toolset", 
        payload={"open_api_schema": "yaml"},
        tool_type="open_api_toolset",
        description="desc"
    )
    
    mock_client.create_toolset.assert_called_once()
    args = mock_client.create_toolset.call_args[1]["request"]
    assert args.parent == "app1"
    assert args.toolset_id == "ts1"
    assert args.toolset.display_name == "my_toolset"
    assert args.toolset.description == "desc"

@patch("cxas_scrapi.core.tools.types.Tool")
@patch("cxas_scrapi.core.tools.types.UpdateToolRequest")
@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_update_tool(mock_client_cls, mock_req_cls, mock_tool_cls):
    mock_client = mock_client_cls.return_value
    
    def side_effect(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items(): setattr(m, k, v)
        return m
    mock_req_cls.side_effect = side_effect
    mock_tool_cls.side_effect = side_effect

    t = Tools("p", "l")
    res = t.update_tool("apps/A/tools/T", display_name="new_name")
    
    mock_client.update_tool.assert_called_once()
    args = mock_client.update_tool.call_args[1]["request"]
    assert args.tool.name == "apps/A/tools/T"
    assert args.tool.display_name == "new_name"

@patch("cxas_scrapi.core.tools.types.Toolset")
@patch("cxas_scrapi.core.tools.types.UpdateToolsetRequest")
@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_update_toolset(mock_client_cls, mock_req_cls, mock_ts_cls):
    mock_client = mock_client_cls.return_value
    
    def side_effect(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items(): setattr(m, k, v)
        return m
    mock_req_cls.side_effect = side_effect
    mock_ts_cls.side_effect = side_effect

    t = Tools("p", "l")
    res = t.update_tool("apps/A/toolsets/TS", display_name="new_name")
    
    mock_client.update_toolset.assert_called_once()
    args = mock_client.update_toolset.call_args[1]["request"]
    assert args.toolset.name == "apps/A/toolsets/TS"
    assert args.toolset.display_name == "new_name"

@patch("cxas_scrapi.core.tools.types.DeleteToolRequest")
@patch("cxas_scrapi.core.tools.types.DeleteToolsetRequest")
@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_delete_tool(mock_client_cls, mock_ts_req_cls, mock_t_req_cls):
    mock_client = mock_client_cls.return_value
    
    def side_effect(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items(): setattr(m, k, v)
        return m
    mock_ts_req_cls.side_effect = side_effect
    mock_t_req_cls.side_effect = side_effect

    t = Tools("p", "l")
    
    t.delete_tool("apps/A/tools/T")
    mock_client.delete_tool.assert_called_once()
    args = mock_client.delete_tool.call_args[1]["request"]
    assert args.name == "apps/A/tools/T"
    
    t.delete_tool("apps/A/toolsets/TS")
    mock_client.delete_toolset.assert_called_once()
    args2 = mock_client.delete_toolset.call_args[1]["request"]
    assert args2.name == "apps/A/toolsets/TS"
