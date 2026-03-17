import pytest
from unittest.mock import patch, MagicMock
from cxas_scrapi.core.sessions import (
    Sessions,
    Modality,
    AgentTurnManager,
    BidiSessionHandler,
)
from google.cloud.ces_v1beta import types
import os
import sys
import time
import json
from google.protobuf import json_format
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
        app_name="projects/p/locations/l/apps/a",
        deployment_id="d1",
        version_id="v1",
    )
    assert sessions.app_name == "projects/p/locations/l/apps/a"
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

    sessions = Sessions(app_name="projects/p/locations/l/apps/a")

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
    sessions = Sessions(app_name="projects/p/locations/l/apps/a")

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
    sessions = Sessions(app_name="projects/p/locations/l/apps/a")

    sessions.send_event("unique_id", "my_event", {"var1": "val1"})

    mock_client.run_session.assert_called_once()


@patch("cxas_scrapi.core.sessions.SessionServiceClient")
def test_parse_result_with_diagnostic_info(mock_client_cls):
    """Test parse_result with a full diagnostic trace ensures no crash."""
    mock_display = MagicMock()
    mock_html = MagicMock(side_effect=lambda x: x)
    sys.modules["IPython"] = MagicMock()
    sys.modules["IPython.display"] = MagicMock(
        display=mock_display, HTML=mock_html
    )

    session = Sessions(app_name="projects/p/locations/l/apps/a")

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

    session = Sessions(app_name="projects/p/locations/l/apps/a")

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
def test_run_session_audio_modality_text_inputs(
    mock_async_run, mock_client_cls
):
    """Test Sessions.run handles text inputs for audio modality (TTS)."""
    sessions = Sessions(app_name="projects/p/locations/l/apps/a")

    # Mock text_to_speech_bytes internally or just rely on AudioTransformer mock if we had one
    # But AudioTransformer is instantiated inside run, so we need to patch it.
    with patch("cxas_scrapi.core.sessions.AudioTransformer") as MockTransformer:
        mock_transformer = MockTransformer.return_value
        mock_transformer.text_to_speech_bytes.side_effect = (
            lambda text, **kwargs: {
                "audio_bytes": b"tts_" + text.encode(),
                "text": text,
            }
        )

        sessions.run(
            session_id="s1", text=["Hello", "World"], modality=Modality.AUDIO
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
    sessions = Sessions(app_name="projects/p/locations/l/apps/a")

    # Setup mock types
    mock_types.RunSessionResponse.side_effect = FakeRunSessionResponse

    # Mock responses for each input
    # Use SimpleNamespace to support attribute access like real proto objects
    from types import SimpleNamespace

    response1 = FakeRunSessionResponse(
        outputs=[SimpleNamespace(text="Response 1")]
    )
    response2 = FakeRunSessionResponse(
        outputs=[SimpleNamespace(text="Response 2")]
    )

    # side_effect to return different responses for consecutive calls
    mock_client.run_session.side_effect = [response1, response2]

    res = sessions.run(
        session_id="s1", text=["Input 1", "Input 2"], modality=Modality.TEXT
    )

    # Verify run_session was called twice
    assert mock_client.run_session.call_count == 2

    # Verify the result contains outputs from both responses
    assert len(res.outputs) == 2
    assert res.outputs[0].text == "Response 1"
    assert res.outputs[1].text == "Response 2"


def test_agent_turn_manager_basic():
    manager = AgentTurnManager(sample_rate=16000, sample_width=2)
    assert not manager.is_agent_done_talking()

    # 1 second of audio (16000 * 2 = 32000 bytes)
    manager.add_audio(b"\x00" * 32000)
    manager.mark_turn_completed()

    # Just completed, current time is roughly 0 seconds since start
    assert not manager.is_agent_done_talking()

    # Force the start time to be 2 seconds ago
    manager.first_audio_received_time = time.time() - 2.0
    assert manager.is_agent_done_talking()


def test_agent_turn_manager_no_audio():
    manager = AgentTurnManager()
    manager.mark_turn_completed()
    # If no audio was ever received, it should be done immediately
    assert manager.is_agent_done_talking()


@patch("cxas_scrapi.core.sessions.websocket.WebSocketApp")
@patch("cxas_scrapi.core.sessions.threading.Thread")
def test_bidi_session_handler_run(mock_thread, mock_ws_app):
    config = {"session": "projects/p/locations/us/apps/a/sessions/s1"}
    inputs = [{"text": "Hello"}]
    handler = BidiSessionHandler(
        location="us", token="fake_token", config=config, inputs=inputs
    )

    res = handler.run()

    mock_ws_app.assert_called_once()
    mock_thread.assert_called_once()

    assert handler.outputs == []


def test_bidi_session_handler_on_message():
    config = {"session": "s"}
    handler = BidiSessionHandler(
        location="us", token="fake", config=config, inputs=[]
    )

    # Construct a valid JSON representing BidiSessionServerMessage
    # with a session_output containing turn_completed
    from google.cloud.ces_v1beta import types

    mock_response = types.BidiSessionServerMessage(
        session_output=types.SessionOutput(turn_completed=True)
    )
    json_data = json_format.MessageToJson(
        mock_response._pb, preserving_proto_field_name=False
    )

    mock_ws = MagicMock()
    handler._on_message(mock_ws, json_data)

    assert len(handler.outputs) == 1
    assert handler.agent_turn_manager.turn_completed_flag is True


@patch("cxas_scrapi.core.sessions.time.sleep")
def test_bidi_session_handler_send_inputs(mock_sleep):
    config = {"session": "session_123"}
    audio_msg = {"audio": b"fake_audio", "text": "Hello"}
    inputs = [{"audio": audio_msg}]
    handler = BidiSessionHandler(
        location="us", token="fake", config=config, inputs=inputs
    )

    handler.ws_app = MagicMock()
    handler.agent_turn_manager.is_agent_done_talking = MagicMock(
        return_value=True
    )

    handler._send_inputs()

    assert handler.ws_app.send.call_count > 0
    # First send should be config
    first_call_arg = handler.ws_app.send.call_args_list[0][0][0]
    assert isinstance(first_call_arg, str)
