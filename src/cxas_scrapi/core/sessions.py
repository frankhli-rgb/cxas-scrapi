from typing import Dict, Any, List, Optional
import os
import mimetypes
import base64
import uuid
from google.cloud.ces_v1beta import SessionServiceClient, types
from cxas_scrapi.core.common import Common
import logging

logger = logging.getLogger(__name__)

class Sessions(Common):
    def __init__(
        self,
        app_id: str,
        deployment_id: str = None,
        version_id: str = None,
    ):
        """Initializes the Sessions client."""
        super().__init__(agent_id=app_id)

        # Initialize Sessions Client
        self.client = SessionServiceClient(
            credentials=self.creds,
            client_options=self.client_options
        )

        self.app_id = app_id
        self.current_session_id = None
        self.deployment_id = deployment_id
        self.version_id = version_id

    @staticmethod
    def get_file_data(file_path: str) -> Dict[str, Any]:
        """
        Reads a local file, returns a blob dict.
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found at path: {file_path}")
            raise FileNotFoundError(f"The file specified at {file_path} was not found.")

        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            mime_type = "application/octet-stream"

        with open(file_path, "rb") as f:
            raw_bytes = f.read()

        return {"mime_type": mime_type, "data": raw_bytes}

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
            print("parse_result requires IPython.display.HTML. Please run this in a Jupyter/Colab environment.")
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
                        chunk_type = chunk._pb.WhichOneof("data") if hasattr(chunk, "_pb") else None
                        
                        if chunk_type == "text":
                            if role.lower() == "user":
                                display(HTML(f"{query_font} {chunk.text}"))
                            else:
                                display(HTML(f"{response_font} [{role}] {chunk.text}"))
                                
                        elif chunk_type == "tool_call":
                            tc = chunk.tool_call
                            tool_name = tc.tool or tc.display_name
                            display(HTML(f"{tool_call_font} [{role}] {tool_name} -- Args: {tc.args}"))
                            
                        elif chunk_type == "tool_response":
                            tr = chunk.tool_response
                            tool_name = tr.tool or tr.display_name
                            display(HTML(f"{tool_res_font} [{role}] {tool_name} -- Result: {tr.response}"))
                            
                        elif chunk_type == "agent_transfer":
                            at = chunk.agent_transfer
                            display(HTML(f"{transfer_font} [{role}] Transferred to {at.display_name}"))
                            
                        elif chunk_type == "payload":
                            display(HTML(f"<font color='brown'><b>CUSTOM PAYLOAD:</b></font> [{role}] {chunk.payload}"))

            else:
                # Fallback to high-level outputs if no diagnostic trace is available
                text = getattr(output, "text", None)
                if text:
                    display(HTML(f"{response_font} {text}"))
                payload = getattr(output, "payload", None)
                if payload:
                    display(HTML(f"<font color='brown'><b>CUSTOM PAYLOAD:</b></font> {payload}"))
                
                tool_calls_msg = getattr(output, "tool_calls", None)
                if tool_calls_msg and hasattr(tool_calls_msg, "tool_calls"):
                    for tc in tool_calls_msg.tool_calls:
                         tool_name = tc.tool or tc.display_name
                         display(HTML(f"{tool_call_font} {tool_name} -- Args: {tc.args}"))

    def session_id_setup(self, session_id: str, restart_session: bool) -> str:
        """Manage the setup of new or existing session IDs."""
        if session_id:
            # Honor explicitly provided session IDs
            session_id = self.create_session_id(unique_id=session_id)
        elif restart_session or not self.current_session_id:
            session_id = self.create_session_id()
        else:
            session_id = self.current_session_id
        return session_id

    def create_session_id(self, unique_id: str = None):
        """Create a new session_id resource name."""
        if unique_id:
            if "/" in unique_id:
                 session_id = unique_id
            else:
                 session_id = f"{self.app_id}/sessions/{unique_id}"
        else:
            session_id = f"{self.app_id}/sessions/{str(uuid.uuid4())}"

        self.current_session_id = session_id
        logger.info(f"Starting new session with Session ID: {self.current_session_id}")
        return self.current_session_id

    def run(
        self,
        session_id: str,
        text: Optional[str] = None,
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
        restart_session: bool = False,
        deployment_id: Optional[str] = None,
        version_id: Optional[str] = None,
    ):
        """Sends inputs to a Conversational Agents Session and returns the response."""
        
        session_id = self.session_id_setup(session_id, restart_session=restart_session)

        # Construct SessionConfig
        config = {"session": session_id}
        if input_audio_config:
            config["input_audio_config"] = input_audio_config
        if output_audio_config:
            config["output_audio_config"] = output_audio_config
        
        # Determine deployment/version
        if deployment_id:
            config["deployment"] = deployment_id
        if version_id:
            config["app_version"] = version_id

        # Construct SessionInputs based on user args
        inputs = []
        
        if text is not None:
            inputs.append({"text": text})
            
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
            inputs.append({"tool_responses": {"tool_responses": tool_responses}})

        request = types.RunSessionRequest(
            config=config,
            inputs=inputs
        )

        return self.client.run_session(request=request)

    def send_event(self, unique_id: str, event_name: str, event_vars: Dict[str, Any]):
        session_id = f"{self.app_id}/sessions/{unique_id}"
        
        config = {"session": session_id}
        inputs = [{"event": {"event": event_name, "variables": event_vars}}]
        
        request = types.RunSessionRequest(
            config=config,
            inputs=inputs
        )

        return self.client.run_session(request=request)
