"""ConversationHistory class for CXAS Scrapi."""

# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Dict, List, Optional, Any
from google.cloud.ces_v1beta import AgentServiceClient, types
import yaml
from cxas_scrapi.core.common import Common

class ConversationHistory(Common):
    """Core Class for managing Conversation History."""

    def __init__(
        self,
        app_id: str = None,
        creds_path: str = None,
        creds_dict: Dict[str, str] = None,
        creds: Any = None,
        scope: List[str] = None,
    ):
        super().__init__(
            creds_path=creds_path,
            creds_dict=creds_dict,
            creds=creds,
            scope=scope,
        )

        # APP_ID format: projects/{project}/locations/{location}/apps/{app}
        self.app_id = app_id

        # Initialize Client
        if app_id:
            self.client_options = self._get_client_options(self.app_id)
            self.client = AgentServiceClient(
                credentials=self.creds, client_options=self.client_options
            )

    @staticmethod
    def parse_conversation_to_yaml(filepath):
        """Parses a direct CXAS Conversation History textproto into the target FDE YAML format."""
        with open(filepath, 'r') as f:
            text = f.read()
            
        parsed = Common.parse_textproto(text)
        return ConversationHistory.conversation_dict_to_yaml(parsed)

    @staticmethod
    def conversation_dict_to_yaml(conv_dict):
        """Parses a direct CXAS Conversation History dictionary into the target FDE YAML format."""
        turns = conv_dict.get('turns', [])
        if not isinstance(turns, list):
            turns = [turns]

        out_yaml = {
            "name": "Converted_Conversation",
            "turns": [],
            "expectations": [], 
            "mocks": []
        }
        
        id_to_tool = {}
        
        for turn in turns:
            if 'user_utterance' in turn:
                ui = turn['user_utterance']
                if 'text' in ui:
                    out_yaml["turns"].append({"user": ui['text']})
                elif 'event' in ui:
                    out_yaml["turns"].append({"user_event": str(ui['event'])})
                    
            if 'agent_utterance' in turn:
                au = turn['agent_utterance']
                chunks = au.get('messages', []) 
                if not isinstance(chunks, list): chunks = [chunks]
                text = " ".join([c.get('text', '') for c in chunks if 'text' in c])
                if text:
                    out_yaml["turns"].append({"agent": text})

            tool_calls = turn.get('tool_calls', [])
            if not isinstance(tool_calls, list): tool_calls = [tool_calls]
            for tc in tool_calls:
                args = tc.get('args', {})
                unwrapped = Common.unwrap_struct(args)
                name = tc.get('display_name', tc.get('name', tc.get('tool', '')))
                out_yaml["turns"].append({
                    "tool_call": {
                        "tool": name,
                        "args": unwrapped
                    }
                })
                id_to_tool[tc.get('id', '')] = name
                
            tool_responses = turn.get('tool_responses', [])
            if not isinstance(tool_responses, list): tool_responses = [tool_responses]
            for tr in tool_responses:
                res = tr.get('response', {})
                unwrapped = Common.unwrap_struct(res)
                name = id_to_tool.get(tr.get('id', ''), tr.get('tool', ''))
                out_yaml["mocks"].append({
                    "tool": name,
                    "response": unwrapped
                })
                
        return out_yaml

    def list_conversations(self, app_id: str = None) -> Any:
        """Lists conversations in the configured app."""
        if self.app_id:
            app_id = self.app_id

        request = types.ListConversationsRequest(parent=app_id)

        # Return the response iterator directly to allow auto-pagination
        return list(self.client.list_conversations(request=request))

    def get_conversation(self, conversation_id: str) -> types.Conversation:
        """Gets a specific conversation by its ID."""
        # Name format: projects/{project}/locations/{location}/apps/{app}/conversations/{conversation}
        if conversation_id.startswith("projects/"):
            name = conversation_id
        else:
            name = f"{self.app_id}/conversations/{conversation_id}"
        request = types.GetConversationRequest(name=name)
        return self.client.get_conversation(request=request)

    def delete_conversation(self, conversation_id: str) -> None:
        """Deletes a specific conversation by its ID."""
        if conversation_id.startswith("projects/"):
            name = conversation_id
        else:
            name = f"{self.app_id}/conversations/{conversation_id}"
        request = types.DeleteConversationRequest(name=name)
        self.client.delete_conversation(request=request)

    def export_conversation_to_yaml(self, conversation_id: str) -> str:
        """
        Fetches a specific conversation and exports it to the FDE YAML format.
        
        Args:
            conversation_id: Full resource name or ID of the conversation.
            
        Returns:
            A string containing the formatted YAML.
        """
        conv_obj = self.get_conversation(conversation_id=conversation_id)
        # Convert to dictionary
        conv_dict = type(conv_obj).to_dict(conv_obj)
        out_yaml_dict = self.conversation_dict_to_yaml(conv_dict)
        return yaml.dump(out_yaml_dict, sort_keys=False, allow_unicode=True)
