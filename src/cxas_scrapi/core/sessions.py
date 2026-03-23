from typing import Dict, Any, List, Optional
import os
import mimetypes
import base64
import uuid
from google.cloud.ces_v1beta import SessionServiceClient, types
from google.cloud import ces_v1beta
from cxas_scrapi.core.conversation_history import ConversationHistory
from cxas_scrapi.core.common import Common
from cxas_scrapi.core.audio_transformer import AudioTransformer
import logging
import threading
import time
import json
import websocket
import ssl
import certifi
from google.protobuf import json_format
from enum import Enum


logger = logging.getLogger(__name__)


class Modality(str, Enum):
    TEXT = "text"
    AUDIO = "audio"


BIDI_SESSION_URI = "wss://ces.googleapis.com/ws/google.cloud.ces.v1.SessionService/BidiRunSession/locations/"
AUDIO_CHUNK_SIZE = 3200
CHUNK_DELAY = 0.1
SILENCE_PADDING_CHUNKS = 3
SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2


class AgentTurnManager:
    """Manages the agent's turn by simulating audio playback time."""

    def __init__(
        self, sample_rate: int = SAMPLE_RATE, sample_width: int = SAMPLE_WIDTH
    ):
        self.sample_rate = sample_rate
        self.sample_width = sample_width
        self.bytes_per_second = sample_rate * sample_width

        self.len_audio_bytes_received = 0
        self.turn_completed_flag = False
        self.first_audio_received_time = None
        self.lock = threading.Lock()

    def add_audio(self, audio_bytes: bytes):
        with self.lock:
            if self.first_audio_received_time is None:
                self.first_audio_received_time = time.time()
            self.len_audio_bytes_received += len(audio_bytes)

    def mark_turn_completed(self):
        with self.lock:
            self.turn_completed_flag = True

    def reset(self):
        with self.lock:
            self.len_audio_bytes_received = 0
            self.turn_completed_flag = False
            self.first_audio_received_time = None

    def is_agent_done_talking(self) -> bool:
        with self.lock:
            if not self.turn_completed_flag:
                return False

            if self.first_audio_received_time is None:
                return True  # Agent didn't send any audio

            audio_duration_seconds = (
                self.len_audio_bytes_received / self.bytes_per_second
            )
            current_playback_time = time.time() - self.first_audio_received_time

            return current_playback_time >= audio_duration_seconds


class BidiSessionHandler:
    """Handles the Bidi WebSocket session with the session service."""

    def __init__(
        self,
        location: str,
        token: str,
        config: Dict[str, Any],
        inputs: List[Dict[str, Any]],
    ):
        self.uri = BIDI_SESSION_URI + location
        self.token = token
        self.config = config
        self.inputs = inputs
        self.agent_turn_manager = AgentTurnManager()
        self.ws_app = None
        self.outputs = []

    def _send_silence(self, num_chunks: int):
        silence_chunk = b"\x00" * AUDIO_CHUNK_SIZE
        for _ in range(num_chunks):
            query_message = ces_v1beta.BidiSessionClientMessage(
                realtime_input=ces_v1beta.SessionInput(audio=silence_chunk)
            )
            query_json = json_format.MessageToJson(
                query_message._pb,
                preserving_proto_field_name=False,
                indent=None,
            )
            self.ws_app.send(query_json)
            time.sleep(CHUNK_DELAY)

    def _send_audio_message(
        self, audio_payload: Dict[str, Any], turn_index: int
    ):
        audio_bytes = audio_payload["audio"]
        text_label = audio_payload.get("text")

        if text_label and text_label != "Audio Input":
            self.outputs.append(
                ces_v1beta.SessionOutput(
                    {
                        "diagnostic_info": {
                            "messages": [
                                {
                                    "role": "USER",
                                    "chunks": [{"text": text_label}],
                                }
                            ]
                        }
                    }
                )
            )

        logging.debug("Sending leading silence before turn %d...", turn_index)
        self._send_silence(
            SILENCE_PADDING_CHUNKS
        )  # 0.3 seconds of leading silence

        logging.debug("Sending audio chunks for turn %d...", turn_index)

        for i in range(0, len(audio_bytes), AUDIO_CHUNK_SIZE):
            chunk = audio_bytes[i : i + AUDIO_CHUNK_SIZE]
            query_message = ces_v1beta.BidiSessionClientMessage(
                realtime_input=ces_v1beta.SessionInput(audio=chunk)
            )
            query_json = json_format.MessageToJson(
                query_message._pb,
                preserving_proto_field_name=False,
                indent=None,
            )
            self.ws_app.send(query_json)
            time.sleep(CHUNK_DELAY)

        logging.debug(
            "Sending trailing silence for turn %d to trigger endpointing...",
            turn_index,
        )
        self._send_silence(
            SILENCE_PADDING_CHUNKS
        )  # 0.3 seconds of trailing silence

        logging.debug("Waiting for agent to finish turn %d...", turn_index)
        while not self.agent_turn_manager.is_agent_done_talking():
            self._send_silence(1)

        self.agent_turn_manager.reset()
        time.sleep(1)  # Small pause between turns

    def _send_inputs(self):
        try:
            logging.debug("Config dict: %s", self.config)
            config_message = ces_v1beta.BidiSessionClientMessage(
                config=ces_v1beta.SessionConfig(
                    session=self.config["session"],
                    input_audio_config=self.config.get("input_audio_config"),
                    output_audio_config=self.config.get("output_audio_config"),
                )
            )
            config_json = json_format.MessageToJson(
                config_message._pb,
                preserving_proto_field_name=False,
                indent=None,
            )
            logging.debug("Sending config: %s", config_json)
            self.ws_app.send(config_json)

            if not self.inputs:
                logging.debug("No inputs provided.")
                self.ws_app.close()
                return

            for idx, input_item in enumerate(self.inputs):
                if "audio" in input_item:
                    self._send_audio_message(input_item["audio"], idx)
                    continue

                # Handle non-audio structured inputs (event, text, variables)
                try:
                    session_input_pb = ces_v1beta.SessionInput()._pb
                    json_format.ParseDict(
                        input_item,
                        session_input_pb,
                        ignore_unknown_fields=False,
                    )
                    session_input = ces_v1beta.SessionInput(session_input_pb)

                    query_message = ces_v1beta.BidiSessionClientMessage(
                        realtime_input=session_input
                    )
                    query_json = json_format.MessageToJson(
                        query_message._pb,
                        preserving_proto_field_name=False,
                        indent=None,
                    )
                    logging.debug("Sending non-audio input: %s", query_json)
                    self.ws_app.send(query_json)

                    if "text" in input_item or "event" in input_item:
                        logging.debug(
                            "Waiting for agent to finish processing turn %d...",
                            idx,
                        )
                        while (
                            not self.agent_turn_manager.is_agent_done_talking()
                        ):
                            time.sleep(1)

                        self.agent_turn_manager.reset()
                        time.sleep(1)

                except Exception as e:
                    logging.debug("Failed to send generic input: %s", e)

            logging.debug("All inputs sent and turns completed.")
            time.sleep(1)  # arbitrary short wait before disconnecting
            self.ws_app.close()

        except Exception as e:
            logging.debug("Error during send_inputs: %s", e)
            if self.ws_app:
                self.ws_app.close()

    def _on_open(self, ws):
        logging.debug("WebSocket connection opened")
        threading.Thread(target=self._send_inputs, daemon=True).start()

    def _on_message(self, ws, message):
        logging.debug("===============")
        logging.debug("Received message: %s...", message[:100])
        try:
            response_pb = ces_v1beta.BidiSessionServerMessage()._pb
            json_format.Parse(
                message,
                response_pb,
                ignore_unknown_fields=True,
            )
            response = ces_v1beta.BidiSessionServerMessage(response_pb)

            if response.session_output:
                self.outputs.append(response.session_output)

                if response.session_output.audio:
                    self.agent_turn_manager.add_audio(
                        response.session_output.audio
                    )

                if response.session_output.turn_completed:
                    logging.debug(
                        "Agent turn network payload completed. Waiting for audio playback."
                    )
                    self.agent_turn_manager.mark_turn_completed()

        except Exception as e:
            logging.debug("Failed to parse message: %s", e)

    def _on_error(self, ws, error):
        logging.debug("WebSocket error: %s", error)

    def _on_close(self, ws, close_status_code, close_msg):
        logging.debug(
            "WebSocket connection closed with code %s and reason: %s",
            close_status_code,
            close_msg,
        )

    def run(self):
        logging.debug("Connecting to WebSocket: %s", self.uri)
        self.ws_app = websocket.WebSocketApp(
            self.uri,
            header={"Authorization": f"Bearer {self.token}"},
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )

        wst = threading.Thread(
            target=self.ws_app.run_forever,
            kwargs={"sslopt": {"ca_certs": certifi.where()}},
        )
        wst.daemon = True
        wst.start()

        logging.debug("Waiting for session to complete...")
        wst.join()

        return ces_v1beta.RunSessionResponse(outputs=self.outputs)


class Sessions(Common):
    def __init__(
        self,
        app_name: str,
        deployment_id: str = None,
        version_id: str = None,
        **kwargs,
    ):
        """Initializes the Sessions client."""
        super().__init__(app_name=app_name, **kwargs)

        # Initialize Sessions Client
        self.client = SessionServiceClient(
            credentials=self.creds, client_options=self.client_options
        )

        self.app_name = app_name
        self.deployment_id = deployment_id
        self.version_id = version_id

    @staticmethod
    def get_file_data(file_path: str) -> Dict[str, Any]:
        """
        Reads a local file, returns a blob dict.
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found at path: {file_path}")
            raise FileNotFoundError(
                f"The file specified at {file_path} was not found."
            )

        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            mime_type = "application/octet-stream"

        with open(file_path, "rb") as f:
            raw_bytes = f.read()

        return {"mime_type": mime_type, "data": raw_bytes}

    @staticmethod
    def _expand_pb_struct(pb_struct):
        try:
            return json.loads(json_format.MessageToJson(pb_struct))
        except Exception:
            pass

        if hasattr(pb_struct, "items"):
            res = {}
            for k, v in pb_struct.items():
                res[k] = Sessions._expand_pb_struct(v)
            return res
        elif hasattr(pb_struct, "__iter__") and not isinstance(pb_struct, str):
            return [Sessions._expand_pb_struct(item) for item in pb_struct]
        else:
            return pb_struct

    def parse_result(self, res: Any):
        """
        Parses the CX Agent Studio session response to extract and print
        turn-by-turn interactions including User Queries, Agent Responses,
        Tool Calls, Tool Results, and Agent Transfers.
        Requires Jupyter Notebook or IPython environment for HTML rendering.
        """
        try:
            from IPython.display import display, HTML
        except ImportError:
            print(
                "parse_result requires IPython.display.HTML. Please run this in a Jupyter/Colab environment."
            )
            return

        tool_call_font = "<font color='darkred'><b>TOOL CALL:</b></font>"
        tool_res_font = "<font color='goldenrod'><b>TOOL RESULT:</b></font>"
        query_font = "<font color='darkgreen'><b>USER QUERY:</b></font>"
        response_font = "<font color='purple'><b>AGENT RESPONSE:</b></font>"
        transfer_font = "<font color='darkorange'><b>AGENT TRANSFER:</b></font>"

        outputs = getattr(res, "outputs", [])
        if not outputs:
            return

        for output in outputs:
            diagnostic_info = getattr(output, "diagnostic_info", None)

            # If diagnostic_info is available, use it for a rich turn-by-turn trace
            if diagnostic_info and hasattr(diagnostic_info, "messages"):
                messages = getattr(diagnostic_info, "messages", [])
                for message in messages:
                    role = getattr(message, "role", "")
                    chunks = getattr(message, "chunks", [])

                    for chunk in chunks:
                        # Depending on the generated class, WhichOneof is available on the internal _pb message
                        chunk_type = (
                            chunk._pb.WhichOneof("data")
                            if hasattr(chunk, "_pb")
                            else None
                        )

                        if chunk_type == "text":
                            if role.lower() == "user":
                                logging.debug(f"USER QUERY: {chunk.text}")
                                display(HTML(f"{query_font} {chunk.text}"))
                            else:
                                logging.debug(
                                    f"AGENT RESPONSE: [{role}] {chunk.text}"
                                )
                                display(
                                    HTML(
                                        f"{response_font} [{role}] {chunk.text}"
                                    )
                                )

                        elif chunk_type == "tool_call":
                            tc = chunk.tool_call
                            tool_name = tc.tool or tc.display_name
                            expanded_args = Sessions._expand_pb_struct(tc.args)
                            logging.debug(
                                f"TOOL CALL: [{role}] {tool_name} -- Args: {expanded_args}"
                            )
                            display(
                                HTML(
                                    f"{tool_call_font} [{role}] {tool_name} -- Args: {expanded_args}"
                                )
                            )

                        elif chunk_type == "tool_response":
                            tr = chunk.tool_response
                            tool_name = tr.tool or tr.display_name
                            expanded_response = Sessions._expand_pb_struct(
                                tr.response
                            )
                            logging.debug(
                                f"TOOL RESULT: [{role}] {tool_name} -- Result: {expanded_response}"
                            )
                            display(
                                HTML(
                                    f"{tool_res_font} [{role}] {tool_name} -- Result: {expanded_response}"
                                )
                            )

                        elif chunk_type == "agent_transfer":
                            at = chunk.agent_transfer
                            logging.debug(
                                f"AGENT TRANSFER: [{role}] Transferred to {at.display_name}"
                            )
                            display(
                                HTML(
                                    f"{transfer_font} [{role}] Transferred to {at.display_name}"
                                )
                            )

                        elif chunk_type == "payload":
                            logging.debug(
                                f"CUSTOM PAYLOAD: [{role}] {chunk.payload}"
                            )
                            display(
                                HTML(
                                    f"<font color='brown'><b>CUSTOM PAYLOAD:</b></font> [{role}] {chunk.payload}"
                                )
                            )

            else:
                # Fallback to high-level outputs if no diagnostic trace is available
                text = getattr(output, "text", None)
                if text:
                    logging.debug(f"AGENT RESPONSE: {text}")
                    display(HTML(f"{response_font} {text}"))
                payload = getattr(output, "payload", None)
                if payload:
                    logging.debug(f"CUSTOM PAYLOAD: {payload}")
                    display(
                        HTML(
                            f"<font color='brown'><b>CUSTOM PAYLOAD:</b></font> {payload}"
                        )
                    )

                tool_calls_msg = getattr(output, "tool_calls", None)
                if tool_calls_msg and hasattr(tool_calls_msg, "tool_calls"):
                    for tc in tool_calls_msg.tool_calls:
                        tool_name = tc.tool or tc.display_name
                        expanded_args = Sessions._expand_pb_struct(tc.args)
                        logging.debug(
                            f"TOOL CALL: {tool_name} -- Args: {expanded_args}"
                        )
                        display(
                            HTML(
                                f"{tool_call_font} {tool_name} -- Args: {expanded_args}"
                            )
                        )

    def async_bidi_run_session(
        self, config: dict, inputs: list[dict[str, Any]]
    ):
        handler = BidiSessionHandler(self.location, self.token, config, inputs)
        return handler.run()

    def make_text_request(self, config: dict, inputs: list[dict[str, Any]]):
        request = types.RunSessionRequest(config=config, inputs=inputs)
        return self.client.run_session(request=request)

    def run(
        self,
        session_id: str,
        text: Optional[str | list[str]] = None,
        event: Optional[str] = None,
        event_vars: Optional[Dict[str, Any]] = None,
        blob: bytes = None,
        blob_mime_type: str = "application/octet-stream",
        variables: Optional[Dict[str, Any]] = None,
        tool_responses: Optional[List[Dict[str, Any]]] = None,
        audio: bytes = None,
        audio_config: Optional[Dict[str, Any]] = None,
        input_audio_config: Optional[Dict[str, Any]] = None,
        output_audio_config: Optional[Dict[str, Any]] = None,
        deployment_id: Optional[str] = None,
        version_id: Optional[str] = None,
        historical_contexts: Optional[List[Dict[str, Any]] | str] = None,
        turn_count: Optional[int] = None,
        modality: Modality | str = Modality.TEXT,
    ):
        """Sends inputs to a Conversational Agents Session and returns the response."""

        if isinstance(modality, str):
            try:
                modality = Modality(modality.lower())
            except ValueError:
                raise ValueError(
                    f"Invalid modality: {modality}. Must be 'text' or 'audio'."
                )

        config = {"session": f"{self.app_name}/sessions/{session_id}"}
        inputs = []

        if modality == Modality.AUDIO:
            config["input_audio_config"] = (
                input_audio_config
                or ces_v1beta.InputAudioConfig(
                    audio_encoding=ces_v1beta.AudioEncoding.LINEAR16,
                    sample_rate_hertz=SAMPLE_RATE,
                )
            )
            config["output_audio_config"] = (
                output_audio_config
                or ces_v1beta.OutputAudioConfig(
                    audio_encoding=ces_v1beta.AudioEncoding.LINEAR16,
                    sample_rate_hertz=SAMPLE_RATE,
                )
            )

        # Determine deployment/version
        if deployment_id or self.deployment_id:
            config["deployment"] = (
                f"{self.app_name}/deployments/{deployment_id or self.deployment_id}"
            )
        if version_id or self.version_id:
            config["app_version"] = (
                f"{self.app_name}/app_versions/{version_id or self.version_id}"
            )

        if historical_contexts:
            parsed_contexts = []
            if isinstance(historical_contexts, str):
                ch = ConversationHistory(app_id=self.app_id, creds=self.creds)
                conv = ch.get_conversation(historical_contexts)
                d = type(conv).to_dict(conv)
                if "turns" in d and d["turns"]:
                    turns_to_process = d["turns"]
                    if turn_count is not None and turn_count > 0:
                        turns_to_process = turns_to_process[:turn_count]

                    for turn in turns_to_process:
                        msgs = turn.get("messages", [])
                        for m in msgs:
                            # only add chunks that have a role and text
                            if "role" in m and "chunks" in m:
                                parsed_contexts.append(
                                    {"role": m["role"], "chunks": m["chunks"]}
                                )
            else:
                for ctx in historical_contexts:
                    if isinstance(ctx, dict):
                        if "role" in ctx and "chunks" in ctx:
                            parsed_contexts.append(ctx)
                        elif "user" in ctx:
                            parsed_contexts.append(
                                {
                                    "role": "user",
                                    "chunks": [{"text": str(ctx["user"])}],
                                }
                            )
                        elif "agent" in ctx or "model" in ctx:
                            role_name = ctx.get("name", "model")
                            text_val = ctx.get("text", "")

                            if not text_val:
                                val = ctx.get("agent") or ctx.get("model")
                                if isinstance(val, str):
                                    text_val = val

                            parsed_contexts.append(
                                {
                                    "role": role_name,
                                    "chunks": [{"text": str(text_val)}],
                                }
                            )
                        else:
                            parsed_contexts.append(ctx)
                    else:
                        raise ValueError(
                            f"historical_contexts must be a list of dictionaries. Received: {type(ctx)}"
                        )
            config["historical_contexts"] = parsed_contexts

        if variables is not None:
            inputs.append({"variables": variables})

        if event is not None:
            event_payload = {"event": event}
            if event_vars:
                event_payload["variables"] = event_vars
            inputs.append({"event": event_payload})

        # Wrap blob input correctly
        if blob is not None:
            inputs.append({"blob": {"mime_type": blob_mime_type, "data": blob}})

        if audio is not None:
            audio_payload = {"audio": audio}
            if audio_config:
                audio_payload["config"] = audio_config
            inputs.append({"audio": audio_payload})

        # Wrap tool responses correctly
        if tool_responses is not None:
            inputs.append(
                {"tool_responses": {"tool_responses": tool_responses}}
            )

        if modality == Modality.AUDIO:
            if text is not None:
                if isinstance(text, str):
                    logger.warning(
                        "Single string input for audio modality introduces minor latency before user utterances."
                    )
                    text = [text]
                audio_transformer = AudioTransformer()
                input_audio_bytes = []
                for input in text:
                    input_audio_bytes.append(
                        audio_transformer.text_to_speech_bytes(
                            text=input,
                            credentials=self.creds,
                            project_id=self.project_id,
                        )
                    )
                for input_data in input_audio_bytes:
                    # Construct input payload matching sessions.py expectation
                    audio_payload = {
                        "audio": input_data["audio_bytes"],
                        "text": input_data["text"],
                    }
                    inputs.append({"audio": audio_payload})
                return self.async_bidi_run_session(config=config, inputs=inputs)
            elif inputs:
                return self.async_bidi_run_session(config=config, inputs=inputs)
            else:
                raise ValueError(
                    "Input payloads (text, audio, event, etc.) must be provided for audio modality."
                )
        elif modality == Modality.TEXT:
            if text is not None and isinstance(text, str):
                text = [text]

            all_outputs = []
            final_response = None

            if text:
                for input in text:
                    inputs.append({"text": input})
                    response = self.make_text_request(config, inputs)
                    inputs.pop()

                    if response:
                        if hasattr(response, "outputs"):
                            all_outputs.extend(response.outputs)
                        final_response = response
            elif inputs:
                # Handle case where only event/blob/variables are provided without text
                response = self.make_text_request(config, inputs)
                if response:
                    if hasattr(response, "outputs"):
                        all_outputs.extend(response.outputs)
                    final_response = response
            else:
                raise ValueError(
                    "Text or valid inputs (e.g. event) must be provided."
                )

            if final_response:
                return types.RunSessionResponse(outputs=all_outputs)
            return final_response
        else:
            if text is None and not inputs:
                raise ValueError("Text or inputs must be provided.")
            raise ValueError("Modality must be either 'text' or 'audio'.")

    def send_event(
        self, unique_id: str, event_name: str, event_vars: Dict[str, Any]
    ):
        config = {"session": f"{self.app_name}/sessions/{unique_id}"}
        inputs = [{"event": {"event": event_name, "variables": event_vars}}]

        request = types.RunSessionRequest(config=config, inputs=inputs)

        return self.client.run_session(request=request)
