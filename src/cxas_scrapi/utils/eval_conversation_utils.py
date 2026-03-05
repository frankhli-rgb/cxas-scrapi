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

import logging
from typing import Dict, List, Optional, Any

import json
import re

from google import genai
import pydantic
import enum

from cxas_scrapi.prompts import llm_user_prompts

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


_FIRST_UTTERANCE = "Hi"
_MAX_TURNS = 30
_DEFAULT_GEMINI_MODEL = "gemini-3.0-flash"


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

  def _next_user_utterance(self) -> str:
    """Generates the next user utterance based on the conversation history.

    This method uses an LLM to determine the next utterance, considering the
    current turn, maximum turns, and the completion status of the defined steps.

    Returns:
      The generated next user utterance as a string. Returns an empty string
      if the conversation has reached the maximum number of turns or all steps
      are completed.
    """
    if self.current_turn == 0:
      return _FIRST_UTTERANCE

    if self.current_turn >= self.max_turns:
      return ""

    # If all steps are completed, then the conversation is complete.
    if all(
        item.status == StepStatus.COMPLETED
        for item in self.steps_progress
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


def get_eval_conversation(
    test_case: Dict[str, Any],
    genai_client: genai.Client,
    model: str = _DEFAULT_GEMINI_MODEL,
) -> Conversation:
  """Returns the conversation generator for evaluation."""
  return LLMUserConversation(
      genai_client=genai_client, genai_model=model, test_case=test_case
  )
