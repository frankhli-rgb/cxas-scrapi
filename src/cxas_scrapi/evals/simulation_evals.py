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

"""Eval conversation classes for CXAS Scrapi."""

import time
from typing import Dict, List, Optional, Any

import json
import uuid

from google import genai
import pydantic
import enum
import pandas as pd

from cxas_scrapi.prompts import llm_user_prompts
from cxas_scrapi.core.apps import Apps
from cxas_scrapi.core.sessions import Sessions

_FIRST_UTTERANCE = "Hi"
_MAX_TURNS = 30
_DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite-preview"


class Step(pydantic.BaseModel):
    goal: str = ""
    success_criteria: str = ""
    response_guide: str = ""
    max_turns: int = 0
    static_utterance: str = ""


class StepStatus(str, enum.Enum):
    NOT_STARTED = "Not Started"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"


class StepProgress(pydantic.BaseModel):
    step: Step = Step()
    status: StepStatus = StepStatus.NOT_STARTED
    justification: str = ""


class ExpectationStatus(str, enum.Enum):
    MET = "Met"
    NOT_MET = "Not Met"


class ExpectationResult(pydantic.BaseModel):
    expectation: str
    status: ExpectationStatus = ExpectationStatus.NOT_MET
    justification: str = ""


class ExpectationOutput(pydantic.BaseModel):
    results: List[ExpectationResult] = []


class SimulationReport:
    """A report containing both Goals and Expectations DataFrames."""

    def __init__(
        self,
        goals_df: pd.DataFrame,
        expectations_df: Optional[pd.DataFrame] = None,
    ):
        self.goals_df = goals_df
        self.expectations_df = expectations_df

    def __str__(self):
        res = "--- Goal Progress ---\n" + self.goals_df.to_string()
        if self.expectations_df is not None:
            res += (
                "\n\n--- Expectations ---\n"
                + self.expectations_df.to_string()
            )
        return res

    def _repr_html_(self):
        html = "<h3>Goal Progress</h3>" + self.goals_df._repr_html_()
        if self.expectations_df is not None:
            html += "<h3>Expectations</h3>" + self.expectations_df._repr_html_()
        return html


class Conversation:
    """Base class for users."""

    def __init__(self):
        self.current_turn = 0
        self.utterance_turn = 0
        self.transcript = []

    def get_num_turns(self) -> int:
        """Gets the number of turns in the conversation."""
        return self.current_turn

    def get_transcript(self) -> str:
        """Gets the transcript of the conversation."""
        return "\n".join(self.transcript)

    def _add_agent_response(self, agent_response: str) -> None:
        """Adds an agent response to the transcript."""
        self.transcript.append(f"Agent: {agent_response}")

    def _add_user_utterance(self, user_utterance: str) -> None:
        """Adds a user utterance to the transcript."""
        self.transcript.append(f"User: {user_utterance}")

    def next_user_utterance(self, last_agent_response: str) -> str:
        """Gets the next user utterance."""
        raise NotImplementedError

    def get_parsed_user_utterances(
        self,
    ) -> tuple[list[str], dict[str, str], dict[int, float]]:
        """Gets all user utterances."""
        raise NotImplementedError


class LLMUserConversation(Conversation):
    """An interactive user that provides input from the command line."""

    class Output(pydantic.BaseModel):
        next_user_utterance: str = ""
        step_progresses: list[StepProgress] = []

    def __init__(
        self,
        genai_client: genai.Client,
        genai_model: str,
        test_case: Dict[str, Any],
        max_turns: int = _MAX_TURNS,
    ):
        super().__init__()
        self.genai_client = genai_client
        self.genai_model = genai_model
        self.test_case = test_case
        self.max_turns = max_turns
        self.steps_progress = []
        for step in test_case["steps"]:
            self.steps_progress.append(
                StepProgress(
                    step=Step(**step),
                    status=StepStatus.NOT_STARTED,
                    justification="",
                )
            )
        self.expectations = test_case.get("expectations", [])
        self.expectation_results: List[ExpectationResult] = []

    def _next_user_utterance(self) -> str:
        """Generates the next user utterance based on the conversation history.

        This method uses an LLM to determine the next utterance, considering the
        current turn, maximum turns, and the completion status of the
        defined steps.

        Returns:
          The generated next user utterance as a string. Returns an empty string
          if the conversation has reached the maximum number of turns or
          all steps
          are completed.
        """
        if self.current_turn == 0:
            return _FIRST_UTTERANCE

        if self.current_turn >= self.max_turns:
            return ""

        # If all steps are completed, then the conversation is complete.
        if all(
            item.status == StepStatus.COMPLETED for item in self.steps_progress
        ):
            return ""

        step_list = self.test_case["steps"]
        json_step_list = json.dumps(step_list, indent=2)
        prompt = llm_user_prompts.LLM_USER_PROMPT.replace(
            "{input_user_config}",
            json_step_list,
        )
        prompt = prompt.replace(
            "{current_conversation_history}",
            self.get_transcript(),
        )
        step_progress_list = [step.model_dump() for step in self.steps_progress]
        json_step_progress_list = json.dumps(step_progress_list, indent=2)
        prompt = prompt.replace(
            "{current_step_progress}",
            json_step_progress_list,
        )
        response = self.genai_client.models.generate_content(
            contents=prompt,
            model=self.genai_model,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=LLMUserConversation.Output,
            ),
        )
        output: LLMUserConversation.Output = response.parsed
        self.steps_progress = output.step_progresses
        return output.next_user_utterance

    def next_user_utterance(self, last_agent_response: str) -> str:
        """Returns the next user utterance from the LLM user."""
        self._add_agent_response(last_agent_response)
        next_user_utterance = self._next_user_utterance()
        self._add_user_utterance(next_user_utterance)
        self.current_turn += 1
        return next_user_utterance

    def generate_report(self) -> Any:
        """
        Generates a pandas DataFrame report of the conversation step
        progress.
        """
        records = []
        for prog in self.steps_progress:
            records.append(
                {
                    "goal": prog.step.goal,
                    "success_criteria": prog.step.success_criteria,
                    "status": prog.status.value,
                    "justification": prog.justification,
                }
            )
        goals_df = pd.DataFrame(records)

        expectations_df = None
        if self.expectation_results:
            exp_records = []
            for res in self.expectation_results:
                exp_records.append(
                    {
                        "expectation": res.expectation,
                        "status": res.status.value,
                        "justification": res.justification,
                    }
                )
            expectations_df = pd.DataFrame(exp_records)

        return SimulationReport(goals_df, expectations_df)


class SimulationEvals(Apps):
    """Wrapper class to simulate entire multi-turn conversations with a
    CXAS Agent."""

    max_retries: int = 3
    retry_delay_base: int = 2

    def __init__(self, app_name: str, **kwargs):
        self.app_name = app_name
        project_id = app_name.split("/")[1]
        location = app_name.split("/")[3]
        super().__init__(project_id=project_id, location=location, **kwargs)
        self.sessions_client = Sessions(app_name, **kwargs)

        # Vertex AI requires a specific region (e.g. global), whereas CXAS
        # Apps use 'us' or 'eu'
        location_map = {"us": "global", "global": "global", "eu": "global"}
        vertex_location = location_map.get(location, location)

        self.genai_client = genai.Client(
            vertexai=True,
            project=self.project_id,
            location=vertex_location,
            credentials=self.creds,
        )

    def _parse_agent_response(
        self, response: Any
    ) -> tuple[str, list[str], bool]:
        """Parses the agent response to extract text and trace information.

        Returns:
            A tuple of (agent_text, trace_chunks, session_ended)
        """
        agent_text = ""
        session_ended = False
        trace_chunks = []

        for output in response.outputs:
            if hasattr(output, "text") and output.text:
                agent_text += output.text + " "
                trace_chunks.append(f"Agent Text: {output.text}")

            tool_calls_msg = getattr(output, "tool_calls", None)
            if tool_calls_msg and hasattr(tool_calls_msg, "tool_calls"):
                for tc in tool_calls_msg.tool_calls:
                    tool_name = getattr(tc, "tool", "") or getattr(
                        tc, "display_name", ""
                    )
                    expanded_args = Sessions._expand_pb_struct(tc.args)
                    trace_chunks.append(
                        f"Tool Call (Output): {tool_name} "
                        f"with args {expanded_args}"
                    )
                    if "end_session" in tool_name:
                        session_ended = True

            diagnostic_info = getattr(output, "diagnostic_info", None)
            if diagnostic_info and hasattr(diagnostic_info, "messages"):
                for message in diagnostic_info.messages:
                    for chunk in getattr(message, "chunks", []):
                        add_text, ended = self._process_diagnostic_chunk(
                            chunk, trace_chunks
                        )
                        agent_text += add_text
                        if ended:
                            session_ended = True

        return agent_text.strip(), trace_chunks, session_ended

    def _process_diagnostic_chunk(
        self, chunk: Any, trace_chunks: list[str]
    ) -> tuple[str, bool]:
        """Processes a single diagnostic chunk and updates trace_chunks."""
        agent_text_add = ""
        session_ended = False

        chunk_type = (
            chunk._pb.WhichOneof("data")
            if hasattr(chunk, "_pb")
            else None
        )
        if chunk_type == "tool_call":
            tc = chunk.tool_call
            tool_name = getattr(tc, "tool", "") or getattr(
                tc, "display_name", ""
            )
            expanded_args = Sessions._expand_pb_struct(tc.args)
            trace_chunks.append(
                f"Tool Call: {tool_name} with args "
                f"{expanded_args}"
            )
            if "end_session" in tool_name:
                session_ended = True
        elif chunk_type == "tool_response":
            tr = chunk.tool_response
            tool_name = tr.tool or tr.display_name
            expanded_response = Sessions._expand_pb_struct(tr.response)
            trace_chunks.append(
                f"Tool Response: {tool_name} with result "
                f"{expanded_response}"
            )
        elif chunk_type == "text":
            agent_text_add = chunk.text + " "
            trace_chunks.append(f"Agent Text (Diag): {chunk.text}")

        return agent_text_add, session_ended

    def _evaluate_expectations(
        self,
        eval_conv: LLMUserConversation,
        detailed_trace: list[str],
        model: str,
        console_logging: bool,
    ) -> None:
        """Evaluates expectations against the conversation trace.

        Modifies `eval_conv.expectation_results` in place.
        """
        if eval_conv.expectations and isinstance(eval_conv.expectations, list):
            if console_logging:
                print("\nEvaluating Expectations...")
            full_trace_str = "\n\n".join(detailed_trace)
            prompt = llm_user_prompts.EVALUATE_EXPECTATIONS_PROMPT.replace(
                "{trace}", full_trace_str
            )
            prompt = prompt.replace(
                "{expectations}", json.dumps(eval_conv.expectations, indent=2)
            )

            try:
                response = self.genai_client.models.generate_content(
                    contents=prompt,
                    model=model,
                    config=genai.types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ExpectationOutput,
                    ),
                )
                output: ExpectationOutput = response.parsed
                eval_conv.expectation_results = output.results
            except Exception as e:
                if console_logging:
                    print(f"Error evaluating expectations: {e}")

    def simulate_conversation(
        self,
        test_case: Dict[str, Any],
        initial_utterance: str = _FIRST_UTTERANCE,
        model: str = _DEFAULT_GEMINI_MODEL,
        session_id: Optional[str] = None,
        console_logging: bool = True,
        modality: str = "text",
    ) -> LLMUserConversation:
        """Runs the simulated conversation loop.

        Args:
            test_case: The test case dictionary defining evaluation steps.
            initial_utterance: The starting user string (default "Hi").
            model: The Gemini model used for evaluating turns.
            console_logging: Whether to print interaction transcript to
                the console.
        """
        if session_id is None:
            session_id = str(uuid.uuid4())
        eval_conv = LLMUserConversation(
            genai_client=self.genai_client,
            genai_model=model,
            test_case=test_case,
        )

        if console_logging:
            print("Starting simulated conversation...")

        # Initialize the first turn manually
        user_utterance = initial_utterance
        eval_conv._add_user_utterance(user_utterance)
        eval_conv.current_turn += 1

        detailed_trace = []
        detailed_trace.append(f"User: {user_utterance}")

        while user_utterance:
            # Send utterance to the CES Agent with exponential backoff for
            # transient 500s
            for attempt in range(self.max_retries):
                try:
                    response = self.sessions_client.run(
                        session_id=session_id,
                        text=user_utterance,
                        modality=modality,
                    )
                    break
                except Exception as e:
                    if attempt == self.max_retries - 1:
                        raise e
                    if console_logging:
                        print(
                            "Warning: CXAS Agent request failed "
                            f"({e}). Retrying in "
                            f"{self.retry_delay_base**attempt}s..."
                        )
                    time.sleep(self.retry_delay_base**attempt)

            if not response:
                break

            if console_logging:
                self.sessions_client.parse_result(response)

            agent_text, trace_chunks, session_ended = (
                self._parse_agent_response(response)
            )
            detailed_trace.append("\n".join(trace_chunks))

            if session_ended:
                if console_logging:
                    print(
                        "\nSession has been closed by the Agent via "
                        "end_session tool."
                    )
                break

            # Get the next simulated user utterance based on the agent's
            # response
            user_utterance = eval_conv.next_user_utterance(agent_text)
            if user_utterance:
                detailed_trace.append(f"User: {user_utterance}")

        if console_logging:
            print("\n--- Conversation Complete ---")
            print("Final Step Progress:")
            for step_prog in eval_conv.steps_progress:
                print(
                    f"- Goal: {step_prog.step.goal} | "
                    f"Status: {step_prog.status.value}"
                )
                if step_prog.justification:
                    print(f"  Justification: {step_prog.justification}")

        self._evaluate_expectations(
            eval_conv, detailed_trace, model, console_logging
        )

        return eval_conv
