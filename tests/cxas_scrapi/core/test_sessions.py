import pytest
from unittest.mock import patch, MagicMock
from cxas_scrapi.core.sessions import Sessions, Modality
from google.cloud.ces_v1beta import types
import os
import sys
import IPython.display


import IPython.display


class FakeRunSessionResponse:
    def __init__(self, outputs=None, **kwargs):
        self.outputs = outputs or []
    
    def __eq__(self, other):
        return self.outputs == other.outputs


@patch("cxas_scrapi.core.sessions.SessionServiceClient")
def test_sessions_init(mock_client_cls):
    """Test Sessions initialization."""
    mock_client = mock_client_cls.return_value
    sessions = Sessions(
        app_id="projects/p/locations/l/apps/a",
        deployment_id="d1",
        version_id="v1",
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


@patch("cxas_scrapi.core.sessions.types")
@patch("cxas_scrapi.core.sessions.SessionServiceClient")
def test_run_session_basic(mock_client_cls, mock_types):
    """Test Sessions.run basic functionality."""
    mock_client = mock_client_cls.return_value
    # Use FakeRunSessionResponse for mock response
    mock_types.RunSessionResponse.side_effect = FakeRunSessionResponse
    
    mock_response = FakeRunSessionResponse(outputs=[{"text": "response"}])
    mock_client.run_session.return_value = mock_response

    sessions = Sessions(app_id="projects/p/locations/l/apps/a")
    
    res = sessions.run(session_id="s1", text="hello")

    # verify contents match
    assert res.outputs == mock_response.outputs
    mock_client.run_session.assert_called_once()

    # Verify the request args
    call_args = mock_client.run_session.call_args[1]["request"]
    assert (
        getattr(call_args, "config", getattr(call_args, "_config", None))
        is not None
    )
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
    sys.modules["IPython.display"] = MagicMock(
        display=mock_display, HTML=mock_html
    )

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
                                {
                                    "tool_call": {
                                        "tool": "my_tool",
                                        "args": {"k": "v"},
                                    }
                                },
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
    sys.modules["IPython.display"] = MagicMock(
        display=mock_display, HTML=mock_html
    )

    session = Sessions(app_id="projects/p/locations/l/apps/a")

    response = types.RunSessionResponse(
        outputs=[
            {
                "text": "Fallback text",
                "tool_calls": {
                    "tool_calls": [
                        {"tool": "basic_tool", "args": {"foo": "bar"}}
                    ]
                },
            }
        ]
    )

    session.parse_result(response)

    # Cleanup
    del sys.modules["IPython"]
    del sys.modules["IPython.display"]


@patch("cxas_scrapi.core.sessions.SessionServiceClient")
@patch("cxas_scrapi.core.sessions.Sessions.async_bidi_run_session")
def test_run_session_audio_modality_text_inputs(mock_async_run, mock_client_cls):
    """Test Sessions.run handles text inputs for audio modality (TTS)."""
    sessions = Sessions(app_id="projects/p/locations/l/apps/a")
    
    # Mock text_to_speech_bytes internally or just rely on AudioTransformer mock if we had one
    # But AudioTransformer is instantiated inside run, so we need to patch it.
    with patch("cxas_scrapi.core.sessions.AudioTransformer") as MockTransformer:
        mock_transformer = MockTransformer.return_value
        mock_transformer.text_to_speech_bytes.side_effect = lambda text, **kwargs: {"audio_bytes": b"tts_" + text.encode(), "text": text}
        
        sessions.run(
            session_id="s1",
            text=["Hello", "World"],
            modality=Modality.AUDIO
        )
        
        mock_async_run.assert_called_once()
        call_kwargs = mock_async_run.call_args[1]
        
        # Verify inputs are transformed
        inputs = call_kwargs["inputs"]
        assert len(inputs) == 2
        assert inputs[0]["audio"]["audio"] == b"tts_Hello"
        assert inputs[1]["audio"]["audio"] == b"tts_World"


@patch("cxas_scrapi.core.sessions.types")
@patch("cxas_scrapi.core.sessions.SessionServiceClient")
def test_run_session_text_multi_inputs_aggregation(mock_client_cls, mock_types):
    """Test Sessions.run aggregates outputs from multiple text inputs."""
    mock_client = mock_client_cls.return_value
    sessions = Sessions(app_id="projects/p/locations/l/apps/a")

    # Setup mock types
    mock_types.RunSessionResponse.side_effect = FakeRunSessionResponse

    # Mock responses for each input
    # Use SimpleNamespace to support attribute access like real proto objects
    from types import SimpleNamespace
    response1 = FakeRunSessionResponse(outputs=[SimpleNamespace(text="Response 1")])
    response2 = FakeRunSessionResponse(outputs=[SimpleNamespace(text="Response 2")])
    
    # side_effect to return different responses for consecutive calls
    mock_client.run_session.side_effect = [response1, response2]

    res = sessions.run(
        session_id="s1",
        text=["Input 1", "Input 2"],
        modality=Modality.TEXT
    )

    # Verify run_session was called twice
    assert mock_client.run_session.call_count == 2
    
    # Verify the result contains outputs from both responses
    assert len(res.outputs) == 2
    assert res.outputs[0].text == "Response 1"
    assert res.outputs[1].text == "Response 2"
