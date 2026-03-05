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
import datetime
import logging
import pandas as pd
from google.cloud.ces_v1beta import AgentServiceClient, types
import yaml
from cxas_scrapi.core.common import Common

logger = logging.getLogger(__name__)


class ConversationHistory(Common):
    """Core Class for managing Conversation History."""

    def __init__(
        self,
        app_id: str = None,
        creds_path: str = None,
        creds_dict: Dict[str, str] = None,
        creds: Any = None,
        scope: List[str] = None, **kwargs
    ):
        super().__init__(
            creds_path=creds_path,
            creds_dict=creds_dict,
            creds=creds,
            scope=scope, **kwargs
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
        with open(filepath, "r") as f:
            text = f.read()

        parsed = Common.parse_textproto(text)
        return ConversationHistory.conversation_dict_to_yaml(parsed)

    @staticmethod
    def conversation_dict_to_yaml(conv_dict):
        """Parses a direct CXAS Conversation History dictionary into the target FDE YAML format."""
        turns = conv_dict.get("turns", [])
        if not isinstance(turns, list):
            turns = [turns]

        out_yaml = {
            "name": "Converted_Conversation",
            "turns": [],
            "expectations": [],
            "mocks": [],
        }

        id_to_tool = {}

        for turn in turns:
            if "user_utterance" in turn:
                ui = turn["user_utterance"]
                if "text" in ui:
                    out_yaml["turns"].append({"user": ui["text"]})
                elif "event" in ui:
                    out_yaml["turns"].append({"user_event": str(ui["event"])})

            if "agent_utterance" in turn:
                au = turn["agent_utterance"]
                chunks = au.get("messages", [])
                if not isinstance(chunks, list):
                    chunks = [chunks]
                text = " ".join(
                    [c.get("text", "") for c in chunks if "text" in c]
                )
                if text:
                    out_yaml["turns"].append({"agent": text})

            tool_calls = turn.get("tool_calls", [])
            if not isinstance(tool_calls, list):
                tool_calls = [tool_calls]
            for tc in tool_calls:
                args = tc.get("args", {})
                unwrapped = Common.unwrap_struct(args)
                name = tc.get(
                    "display_name", tc.get("name", tc.get("tool", ""))
                )
                out_yaml["turns"].append(
                    {"tool_call": {"tool": name, "args": unwrapped}}
                )
                id_to_tool[tc.get("id", "")] = name

            tool_responses = turn.get("tool_responses", [])
            if not isinstance(tool_responses, list):
                tool_responses = [tool_responses]
            for tr in tool_responses:
                res = tr.get("response", {})
                unwrapped = Common.unwrap_struct(res)
                name = id_to_tool.get(tr.get("id", ""), tr.get("tool", ""))
                out_yaml["mocks"].append({"tool": name, "response": unwrapped})

        return out_yaml

    def list_conversations(
        self,
        app_id: str = None,
        time_filter: str = None,
        source_filter: str = None,
    ) -> Any:
        """Lists conversations in the configured app.

        Args:
            app_id: The specific App ID string.
            time_filter: An optional relative time filter (e.g. '7d', '24h', '1m').
            source_filter: An optional enum string filter (e.g. 'LIVE', 'SIMULATOR', 'EVAL').
        """
        if self.app_id:
            app_id = self.app_id

        filter_str = None
        if time_filter:
            now = datetime.datetime.utcnow()
            valid = False
            if time_filter.endswith("d"):
                days = int(time_filter[:-1])
                past = now - datetime.timedelta(days=days)
                valid = True
            elif time_filter.endswith("h"):
                hours = int(time_filter[:-1])
                past = now - datetime.timedelta(hours=hours)
                valid = True
            elif time_filter.endswith("m"):
                minutes = int(time_filter[:-1])
                past = now - datetime.timedelta(minutes=minutes)
                valid = True
            if valid:
                formatted_time = past.strftime("%Y-%m-%dT%H:%M:%SZ")
                filter_str = f'start_time > "{formatted_time}"'
            else:
                logger.warning(
                    f"Unrecognized time_filter format: {time_filter}. Ignoring."
                )

        request_kwargs = {"parent": app_id, "filter": filter_str}

        if source_filter:
            source_enum_val = getattr(
                types.Conversation.Source, source_filter.upper(), None
            )
            if source_enum_val is not None:
                request_kwargs["source"] = source_enum_val
            else:
                logger.warning(
                    f"Unrecognized source_filter format: {source_filter}. Ignoring."
                )

        request = types.ListConversationsRequest(**request_kwargs)

        # Return the response iterator directly to allow auto-pagination
        return list(self.client.list_conversations(request=request))

    def get_latency_metrics_dfs(
        self,
        app_id: Optional[str] = None,
        time_filter: str = "7d",
        source_filter: str = None,
        limit: int = 50,
    ) -> Dict[str, pd.DataFrame]:
        """Generates latency metrics DataFrames from recent conversation traces.

        Args:
            app_id: Optional App ID override.
            time_filter: Relative timeframe to fetch (e.g. '7d', '24h').
            source_filter: Optional source environment to filter by (e.g. 'LIVE', 'SIMULATOR').
            limit: Maximum number of conversations to retrieve and parse.

        Returns:
            Dictionary containing DataFrames: tool_summary, tool_details, callback_summary, callback_details, guardrail_summary, guardrail_details
        """
        from cxas_scrapi.utils.latency_parser import LatencyParser

        target_app = app_id or self.app_id
        if not target_app:
            raise ValueError(
                "app_id must be provided to fetch conversational latency metrics."
            )

        convs = self.list_conversations(
            app_id=target_app,
            time_filter=time_filter,
            source_filter=source_filter,
        )
        if not convs:
            logger.warning(
                f"No conversations found for time_filter: {time_filter} and source_filter: {source_filter}"
            )
            return {
                "tool_summary": pd.DataFrame(),
                "tool_details": pd.DataFrame(),
                "callback_summary": pd.DataFrame(),
                "callback_details": pd.DataFrame(),
                "guardrail_summary": pd.DataFrame(),
                "guardrail_details": pd.DataFrame(),
            }

        # Extract the string IDs, limiting to the requested amount
        conv_ids = [c.name.split("/")[-1] for c in convs[:limit]]

        traces = LatencyParser.fetch_conversation_traces(
            conv_ids, self.get_conversation
        )
        return LatencyParser.extract_trace_metrics(
            traces, context_type="conversation"
        )

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
