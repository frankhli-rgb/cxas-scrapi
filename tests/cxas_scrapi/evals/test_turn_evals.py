"""Unit tests for the TurnEvals testing utility."""

import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from cxas_scrapi.evals.turn_evals import (
    TurnEvals,
    TurnTestCase,
    TurnExpectation,
    TurnOperator,
)


class MockTurnResponse:
    def __init__(self, dict_data):
        self._dict_data = dict_data

    @property
    def _pb(self):
        # We'll just define an object that MessageToDict can process, or
        # mock MessageToDict directly. For testing, it's easier to mock MessageToDict
        pass


@pytest.fixture
def mock_turn_evals():
    with patch("cxas_scrapi.evals.turn_evals.Sessions"), patch(
        "cxas_scrapi.evals.turn_evals.Variables"
    ):
        evals = TurnEvals(app_id="test_app_id")
        return evals


def test_load_turn_test_cases_from_yaml(mock_turn_evals):
    yaml_str = """
tests:
  - name: test_greeting
    user: Hello
    variables:
      first_turn: true
    expectations:
      - type: contains
        value: Hi there
      - type: tool_called
        value: search
"""
    cases = mock_turn_evals.load_turn_test_cases_from_yaml(yaml_str)
    assert len(cases) == 1
    assert cases[0].name == "test_greeting"
    assert cases[0].user == "Hello"
    assert cases[0].variables["first_turn"] is True
    assert len(cases[0].expectations) == 2
    assert cases[0].expectations[0].type == TurnOperator.CONTAINS
    assert cases[0].expectations[0].value == "Hi there"
    assert cases[0].expectations[1].type == TurnOperator.TOOL_CALLED
    assert cases[0].expectations[1].value == "search"


@patch("google.protobuf.json_format.MessageToDict")
def test_validate_turn_test_success(mock_message_to_dict, mock_turn_evals):
    mock_message_to_dict.return_value = {
        "outputs": [
            {
                "text": "Hi there! I am your agent.",
                "diagnosticInfo": {
                    "messages": [
                        {
                            "chunks": [
                                {"text": "Hi there! I am your agent."},
                                {
                                    "toolCall": {
                                        "displayName": "product_search",
                                        "args": {"query": "shoes"},
                                    }
                                },
                                {
                                    "toolResponse": {
                                        "displayName": "product_search",
                                        "response": {"status": "SUCCESS"},
                                    }
                                },
                            ]
                        }
                    ]
                },
            }
        ]
    }

    test_case = TurnTestCase(
        name="test_1",
        user="hello",
        expectations=[
            TurnExpectation(type=TurnOperator.CONTAINS, value="your agent"),
            TurnExpectation(
                type=TurnOperator.EQUALS, value="Hi there! I am your agent. "
            ),  # Expects trailing space due to chunk mapping loop
            TurnExpectation(
                type=TurnOperator.TOOL_CALLED, value="product_search"
            ),
            TurnExpectation(
                type=TurnOperator.TOOL_INPUT, value={"query": "shoes"}
            ),
            TurnExpectation(
                type=TurnOperator.TOOL_OUTPUT, value={"status": "SUCCESS"}
            ),
        ],
    )

    errors = mock_turn_evals.validate_turn_test(test_case, MagicMock())
    assert len(errors) == 0


@patch("google.protobuf.json_format.MessageToDict")
def test_validate_turn_test_failures(mock_message_to_dict, mock_turn_evals):
    mock_message_to_dict.return_value = {
        "outputs": [
            {
                "diagnosticInfo": {
                    "messages": [
                        {
                            "chunks": [
                                {"text": "Nope."},
                                {
                                    "toolCall": {
                                        "displayName": "other_tool",
                                        "args": {"query": "hats"},
                                    }
                                },
                            ]
                        }
                    ]
                }
            }
        ]
    }

    test_case = TurnTestCase(
        name="test_2",
        user="hello",
        expectations=[
            TurnExpectation(type=TurnOperator.CONTAINS, value="your agent"),
            TurnExpectation(
                type=TurnOperator.EQUALS, value="Hi there! I am your agent. "
            ),
            TurnExpectation(
                type=TurnOperator.TOOL_CALLED, value="product_search"
            ),
            TurnExpectation(
                type=TurnOperator.TOOL_INPUT, value={"query": "shoes"}
            ),
            TurnExpectation(type=TurnOperator.NO_TOOLS_CALLED, value=None),
        ],
    )

    errors = mock_turn_evals.validate_turn_test(test_case, MagicMock())
    assert len(errors) == 5
    assert any("CONTAINS failed" in e for e in errors)
    assert any("EQUALS failed" in e for e in errors)
    assert any("TOOL_CALLED failed" in e for e in errors)
    assert any("TOOL_INPUT failed" in e for e in errors)
    assert any("NO_TOOLS_CALLED failed" in e for e in errors)


@patch("google.protobuf.json_format.MessageToDict")
def test_run_turn_tests(mock_message_to_dict, mock_turn_evals):
    mock_message_to_dict.return_value = {"text": "Hello!"}

    # Mock the session run to return a dummy response
    mock_turn_evals.sessions_client.run.return_value = MagicMock()

    cases = [
        TurnTestCase(
            name="t1",
            user="hi",
            expectations=[
                TurnExpectation(type=TurnOperator.CONTAINS, value="Hello")
            ],
        )
    ]

    df = mock_turn_evals.run_turn_tests(cases)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert df.iloc[0]["status"] == "SUCCESS"
    assert df.iloc[0]["errors"] == ""
    assert mock_turn_evals.sessions_client.run.call_count == 1
