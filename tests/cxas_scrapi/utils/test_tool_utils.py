import pytest
from unittest.mock import MagicMock, patch

from cxas_scrapi.utils.tool_utils import (
    Operator,
    Expectation,
    ToolUtils,
    ToolTestCase,
)


def test_operator_enum():
    assert Operator.EQUALS.value == "equals"
    assert Operator.CONTAINS.value == "contains"


def test_expectation_model():
    exp = Expectation(path="$.result", operator=Operator.EQUALS, value="PASSED")
    assert exp.path == "$.result"
    assert exp.operator == Operator.EQUALS
    assert exp.value == "PASSED"


@patch("cxas_scrapi.utils.tool_utils.Tools")
@patch("cxas_scrapi.utils.tool_utils.Variables")
def test_tool_utils_init(mock_variables, mock_tools):
    mock_tools_instance = mock_tools.return_value
    mock_tools_instance.get_tools_map.return_value = {"tool1": "id1"}

    tu = ToolUtils(app_id="test_app", creds=None)
    assert tu.app_id == "test_app"
    assert tu.tool_map == {"tool1": "id1"}
    mock_tools_instance.get_tools_map.assert_called_once_with(
        "test_app", reverse=True
    )


def test_parse_variables_input():
    assert ToolUtils.parse_variables_input(None) == {}
    assert ToolUtils.parse_variables_input('{"a": 1}') == {"a": 1}
    assert ToolUtils.parse_variables_input("invalid") == {}
    assert ToolUtils.parse_variables_input(["a", "b"]) == {"a": None, "b": None}
    assert ToolUtils.parse_variables_input({"a": 1}) == {"a": 1}
    assert ToolUtils.parse_variables_input(123) == {}


def test_parse_python_code():
    code = """
def my_tool(arg1, arg2):
    return {"status": "SUCCESS", "id": 123}
"""
    args, returns = ToolUtils._parse_python_code(code)
    assert args == {"arg1": "[arg1]", "arg2": "[arg2]"}
    assert set(returns) == {"status", "id"}


def test_parse_python_code_invalid():
    args, returns = ToolUtils._parse_python_code("def foo( *invalid syntax")
    assert args == {}
    assert returns == []


def test_parse_properties():
    # Helper to avoid instantiating ToolUtils to test isolated util
    tu = ToolUtils.__new__(ToolUtils)
    props = {
        "str_prop": {"type": "string"},
        "int_prop": {"type": "integer"},
        "bool_prop": {"type": "boolean"},
        "arr_prop": {"type": "array", "items": {"type": "string"}},
        "obj_prop": {
            "type": "object",
            "properties": {"nested": {"type": "string"}},
        },
        "unknown_prop": {"type": "unknown"},
    }
    parsed = tu._parse_properties(props)
    assert parsed["str_prop"] == "[str_prop]"
    assert parsed["int_prop"] == 0
    assert parsed["bool_prop"] is False
    assert parsed["arr_prop"] == ["[arr_prop_1]", "[arr_prop_2]"]
    assert parsed["obj_prop"] == {"nested": "[nested]"}
    assert parsed["unknown_prop"] == "[unknown_prop]"


def test_get_value_at_path():
    tu = ToolUtils.__new__(ToolUtils)
    data = {"a": {"b": [{"c": 1}, {"c": 2}]}}
    assert tu._get_value_at_path(data, "$.a.b[0].c") == 1
    assert tu._get_value_at_path(data, "$.a.b[*].c") == [1, 2]
    assert tu._get_value_at_path(data, "$.not.found") is None


def test_check_expectation():
    tu = ToolUtils.__new__(ToolUtils)
    assert tu._check_expectation(
        1, Expectation(path="", operator=Operator.EQUALS, value=1)
    )
    assert not tu._check_expectation(
        1, Expectation(path="", operator=Operator.EQUALS, value=2)
    )

    assert tu._check_expectation(
        "abc", Expectation(path="", operator=Operator.CONTAINS, value="b")
    )
    assert not tu._check_expectation(
        "abc", Expectation(path="", operator=Operator.CONTAINS, value="d")
    )
    assert not tu._check_expectation(
        123, Expectation(path="", operator=Operator.CONTAINS, value="1")
    )

    assert tu._check_expectation(
        5, Expectation(path="", operator=Operator.GREATER_THAN, value=3)
    )
    assert tu._check_expectation(
        3, Expectation(path="", operator=Operator.LESS_THAN, value=5)
    )

    assert tu._check_expectation(
        [1, 2], Expectation(path="", operator=Operator.LENGTH_EQUALS, value=2)
    )
    assert tu._check_expectation(
        [1, 2, 3],
        Expectation(path="", operator=Operator.LENGTH_GREATER_THAN, value=2),
    )
    assert tu._check_expectation(
        [1], Expectation(path="", operator=Operator.LENGTH_LESS_THAN, value=2)
    )

    assert tu._check_expectation(
        None, Expectation(path="", operator=Operator.IS_NULL)
    )
    assert tu._check_expectation(
        1, Expectation(path="", operator=Operator.IS_NOT_NULL)
    )


def test_tool_test_case_validation():
    # Test that empty expectations works
    tc = ToolTestCase(name="t1", tool="tool1")
    assert tc.args == {}
    assert tc.response_expectations == []

    # Test parsing aliases
    tc2 = ToolTestCase(
        name="t2",
        tool="tool2",
        args={"a": 1},
        expectations={
            "response": [{"path": "$.x", "operator": "equals", "value": 1}]
        },
    )
    assert tc2.response_expectations[0].path == "$.x"


def test_parse_python_function():
    tu = ToolUtils.__new__(ToolUtils)
    # Tool with properties in schema
    t1 = {
        "python_function": {
            "parameters": {"properties": {"foo": {"type": "string"}}}
        }
    }
    args, returns = tu._parse_python_function(t1)
    assert args == {"foo": "[foo]"}
    assert returns == []

    # Tool with just python_code
    t2 = {
        "python_function": {
            "python_code": "def func(hello):\n    return {'world': 1}"
        }
    }
    args2, returns2 = tu._parse_python_function(t2)
    assert args2 == {"hello": "[hello]"}
    assert returns2 == ["world"]


def test_parse_openapi_toolset():
    tu = ToolUtils.__new__(ToolUtils)
    schema = """
paths:
  /test:
    get:
      operationId: getTest
      parameters:
        - name: q
          schema:
            type: string
    post:
      operationId: postTest
      requestBody:
        content:
          application/json:
            schema:
              properties:
                body_prop:
                  type: integer
"""
    t1 = {"open_api_toolset": {"open_api_schema": schema}}

    args, returns = tu._parse_openapi_toolset(t1, "MyTool_getTest")
    assert args == {"q": "[q]"}
    assert returns == []

    args2, returns2 = tu._parse_openapi_toolset(t1, "MyTool_postTest")
    assert args2 == {"body_prop": 0}
    assert returns2 == []


def test_validate_tool_test():
    tu = ToolUtils.__new__(ToolUtils)

    tc = ToolTestCase(
        name="test1",
        tool="tool1",
        expectations={
            "response": [
                {"path": "$.status", "operator": "equals", "value": "OK"}
            ],
            "variables": [{"path": "$.var1", "operator": "is_not_null"}],
        },
    )

    resp_pass = {"response": {"status": "OK"}, "variables": {"var1": "found"}}
    errors = tu.validate_tool_test(tc, resp_pass)
    assert len(errors) == 0

    resp_fail = {"response": {"status": "ERROR"}, "variables": {}}
    errors = tu.validate_tool_test(tc, resp_fail)
    assert len(errors) == 2
    assert "Response expectation failed" in errors[0]
    assert "Variable expectation failed" in errors[1]


@patch("cxas_scrapi.utils.tool_utils.Tools")
@patch("cxas_scrapi.utils.tool_utils.Variables")
def test_run_tool_tests(mock_variables, mock_tools):
    mock_tools_instance = mock_tools.return_value
    mock_tools_instance.get_tools_map.return_value = {"tool1": "id1"}
    mock_tools_instance.execute_tool.return_value = {
        "response": {"status": "OK"}
    }

    mock_var_instance = mock_variables.return_value
    mock_var_instance.list_variables.return_value = []

    tu = ToolUtils(app_id="test_app", creds=None)

    tc = ToolTestCase(
        name="test1",
        tool="tool1",
        expectations={
            "response": [
                {"path": "$.status", "operator": "equals", "value": "OK"}
            ]
        },
    )

    # Run tests
    df = tu.run_tool_tests([tc])

    assert len(df) == 1
    assert df.iloc[0]["status"] == "PASSED"
    assert df.iloc[0]["test_name"] == "test1"

    # Ensure it calls execute_tool correctly
    mock_tools_instance.execute_tool.assert_called_once_with(
        app_id="test_app", tool_display_name="tool1", args={}, variables={}
    )
