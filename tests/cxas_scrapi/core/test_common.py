import sys
from unittest.mock import MagicMock

sys.modules["google.cloud.ces_v1beta"] = MagicMock()
import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Ensure correct path
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../src"))
)

from cxas_scrapi.core.common import Common


def test_common_init():
    try:
        base = Common()
        print("PASS: Initialized Common with default creds (ADC).")
    except Exception as e:
        print(f"WARN: Failed to init with ADC (expected if no ADC): {e}")


@patch("cxas_scrapi.core.common.default")
def test_common_auth(mock_auth):
    mock_creds = MagicMock()
    mock_auth.return_value = (mock_creds, "project")
    common = Common()
    assert common.creds == mock_creds


def test_client_options():
    us_id = "projects/my-project/locations/us/agents/my-agent"
    opts = Common._get_client_options(us_id)
    assert opts["api_endpoint"] == "ces.googleapis.com"

    eu_id = "projects/my-project/locations/eu/agents/my-agent"
    opts = Common._get_client_options(eu_id)
    assert opts["api_endpoint"] == "ces.googleapis.com"


def test_project_id_extraction():
    assert (
        Common._get_project_id("projects/test-proj/locations/us/apps/abc")
        == "test-proj"
    )
    assert Common._get_project_id("invalid-format") == None


def test_location_extraction():
    assert Common._get_location("projects/test-proj/locations/us/apps/abc") == "us"
    assert Common._get_location("invalid-format") == None


def test_unwrap_value():
    assert Common.unwrap_value({"string_value": "hello"}) == "hello"
    assert Common.unwrap_value({"number_value": 42}) == 42
    assert Common.unwrap_value({"bool_value": True}) == True
    assert Common.unwrap_value({"list_value": {"values": [{"string_value": "a"}]}}) == [
        "a"
    ]


def test_unwrap_struct():
    struct = {
        "fields": [
            {"key": "name", "value": {"string_value": "test"}},
            {"key": "age", "value": {"number_value": 30}},
        ]
    }
    assert Common.unwrap_struct(struct) == {"name": "test", "age": 30}


def test_tokenize():
    text = '{ key: "value" }'
    tokens = list(Common._tokenize_textproto(text))
    kinds = [t[0] for t in tokens]
    assert kinds == ["LBRACE", "ID", "COLON", "STRING", "RBRACE"]


def test_parse():
    text = '{ key: "value" num: 42 bool_val: true }'
    tokens = Common._tokenize_textproto(text)
    res = Common._parse_textproto_tokens(tokens)
    assert res == {"key": "value", "num": "42", "bool_val": True}


def test_parse_textproto():
    text = '{ key: "value" nested: { inner: 1 } }'
    res = Common.parse_textproto(text)
    assert res == {"key": "value", "nested": {"inner": "1"}}


if __name__ == "__main__":
    test_common_init()
    test_client_options()
    print("Done.")
