import pytest
from unittest.mock import patch, MagicMock
from cxas_scrapi.core.sessions import Sessions
from google.cloud.ces_v1beta import types
import os
import sys
import IPython.display


@patch("cxas_scrapi.core.sessions.SessionServiceClient")
def test_sessions_init(mock_client_cls):
    """Test Sessions initialization."""
    mock_client = mock_client_cls.return_value
    sessions = Sessions(
        app_id="projects/p/locations/l/apps/a", deployment_id="d1", version_id="v1"
    )
    assert sessions.app_id == "projects/p/locations/l/apps/a"
    assert sessions.deployment_id == "d1"
    assert sessions.version_id == "v1"


def test_get_file_data(tmp_path):
    """Test static method get_file_data."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world")

    res = Sessions.get_file_data(str(test_file))
    assert res["mime_type"] == "text/plain"
    assert res["data"] == b"hello world"

    with pytest.raises(FileNotFoundError):
        Sessions.get_file_data("non_existent_file.txt")


@patch("cxas_scrapi.core.sessions.SessionServiceClient")
def test_run_session_basic(mock_client_cls):
    """Test Sessions.run basic functionality."""
    mock_client = mock_client_cls.return_value
    mock_response = MagicMock()
    mock_client.run_session.return_value = mock_response

    sessions = Sessions(app_id="projects/p/locations/l/apps/a")
    res = sessions.run(session_id="s1", text="hello")

    assert res == mock_response
    mock_client.run_session.assert_called_once()

    # Verify the request args
    call_args = mock_client.run_session.call_args[1]["request"]
    assert getattr(call_args, "config", getattr(call_args, "_config", None)) is not None
    # We just ensure it was called since proto-plus handles the object construction


@patch("cxas_scrapi.core.sessions.SessionServiceClient")
def test_run_session_advanced(mock_client_cls):
    """Test Sessions.run with multiple parameters."""
    mock_client = mock_client_cls.return_value
    sessions = Sessions(app_id="projects/p/locations/l/apps/a")

    sessions.run(
        session_id="s1",
        event="custom_event",
        event_vars={"key": "val"},
        blob=b"image_data",
        blob_mime_type="image/jpeg",
        variables={"var1": "value1"},
        deployment_id="dep1",
        version_id="ver1",
    )

    mock_client.run_session.assert_called_once()


@patch("cxas_scrapi.core.sessions.SessionServiceClient")
def test_send_event(mock_client_cls):
    """Test Sessions.send_event."""
    mock_client = mock_client_cls.return_value
    sessions = Sessions(app_id="projects/p/locations/l/apps/a")

    sessions.send_event("unique_id", "my_event", {"var1": "val1"})

    mock_client.run_session.assert_called_once()


@patch("cxas_scrapi.core.sessions.SessionServiceClient")
def test_session_id_setup(mock_client_cls):
    """Test session ID generation logic."""
    sessions = Sessions(app_id="projects/p/locations/l/apps/a")

    # Restart session (should gen new UUID)
    s1 = sessions.session_id_setup("old_session", restart_session=True)
    assert "old_session" not in s1
    assert "projects/p/locations/l/apps/a/sessions/" in s1

    # Existing session (full path)
    s2 = sessions.session_id_setup(
        "projects/p/locations/l/apps/a/sessions/ex", restart_session=False
    )
    assert s2 == "projects/p/locations/l/apps/a/sessions/ex"

    # Unique ID only
    s3 = sessions.session_id_setup("uid_123", restart_session=False)
    assert s3 == "projects/p/locations/l/apps/a/sessions/uid_123"


@patch("cxas_scrapi.core.sessions.SessionServiceClient")
def test_parse_result_with_diagnostic_info(mock_client_cls):
    """Test parse_result with a full diagnostic trace ensures no crash."""
    mock_display = MagicMock()
    mock_html = MagicMock(side_effect=lambda x: x)
    sys.modules["IPython"] = MagicMock()
    sys.modules["IPython.display"] = MagicMock(display=mock_display, HTML=mock_html)

    session = Sessions(app_id="projects/p/locations/l/apps/a")

    response = types.RunSessionResponse(
        outputs=[
            {
                "diagnostic_info": {
                    "messages": [
                        {"role": "user", "chunks": [{"text": "Hello user"}]},
                        {
                            "role": "agent",
                            "chunks": [
                                {"text": "Hi back"},
                                {"tool_call": {"tool": "my_tool", "args": {"k": "v"}}},
                            ],
                        },
                    ]
                }
            }
        ]
    )

    session.parse_result(response)

    # Cleanup
    del sys.modules["IPython"]
    del sys.modules["IPython.display"]


@patch("cxas_scrapi.core.sessions.SessionServiceClient")
def test_parse_result_fallback(mock_client_cls):
    """Test parse_result without diagnostic info but with basic and tool responses ensures no crash."""
    mock_display = MagicMock()
    mock_html = MagicMock(side_effect=lambda x: x)
    sys.modules["IPython"] = MagicMock()
    sys.modules["IPython.display"] = MagicMock(display=mock_display, HTML=mock_html)

    session = Sessions(app_id="projects/p/locations/l/apps/a")

    response = types.RunSessionResponse(
        outputs=[
            {
                "text": "Fallback text",
                "tool_calls": {
                    "tool_calls": [{"tool": "basic_tool", "args": {"foo": "bar"}}]
                },
            }
        ]
    )

    session.parse_result(response)

    # Cleanup
    del sys.modules["IPython"]
    del sys.modules["IPython.display"]
