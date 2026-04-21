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

import json
import logging
from typing import Any, Dict, Optional

from cxas_scrapi.utils.gemini import GeminiGenerate

logger = logging.getLogger(__name__)


class AIAugment:
    """Handles AI-powered augmentation tasks for the migration service."""

    def __init__(self, gemini_client: GeminiGenerate):
        """Initializes the AIAugment service.

        Args:
            gemini_client: An instance of the GeminiGenerate class.
        """
        self.gemini_client = gemini_client
        logger.info("AIAugment service initialized.")

    async def generate_agent_description(
        self, playbook_data: Dict[str, Any]
    ) -> Optional[str]:
        """Generates a concise, one-sentence description for a Polysynth agent

        based on its source DFCX Playbook's goal and instructions.

        Args:
            playbook_data: The source Dialogflow CX Playbook data as a dictionary.

        Returns:
            A generated one-sentence description string, or None on failure.
        """
        display_name = playbook_data.get("displayName", "Unnamed Playbook")
        goal = playbook_data.get("goal", "No goal provided.")

        # Serialize it to a string to ensure all details are captured in the
        # prompt.
        instruction_str = json.dumps(
            playbook_data.get("instruction", {}), indent=2
        )

        system_prompt = """You are an expert AI agent architect.
        Your task is to create a concise, one-sentence description for a Polysynth agent based on its detailed instructions and goal.
        The generated description will be used by either a parent 'router' agent to decide when to transfer a user to this specialist agent, or by other LLM agents to determine if they should route a task to this agent. The description must be clear, accurate, and focus on the agent's primary capability.
        Do not use conversational language. Output only the single sentence description."""

        prompt = f"""
        Generate a one-sentence description for an agent with the following characteristics:

        Agent Name: {display_name}

        Agent Goal:
        {goal}

        Agent Instructions (JSON format):
        {instruction_str}
        """

        description = await self.gemini_client.generate_async(
            prompt=prompt, system_prompt=system_prompt
        )
        logger.info(f"***Generated agent description***: {description}")

        if description:
            # Clean up the response, removing potential quotes or extra whitespace
            return description.strip().strip('"')

        return None

    async def generate_eval_set(
        self, agent_data: Dict[str, Any]
    ) -> Optional[list]:
        """Generates a structured evaluation set, instructing the LLM to

        dynamically size it based on agent complexity.

        Args:
            agent_data: The complete dictionary of the source DFCX agent.

        Returns:
            A list of dictionaries representing the eval set, or None on
            failure.
        """
        # The logic for sizing is now moved into the system prompt.
        system_prompt = """You are a world-class Senior Quality Assurance (QA) Engineer specializing in conversational AI. Your goal is to create a high-quality, comprehensive evaluation set in a structured JSON format to rigorously test a new agent against its source specification.

        **Phase 1: Comprehensive Analysis and Test Strategy Formulation**
        First, deeply understand the agent by meticulously analyzing the provided agent JSON configuration.
        1.  **Agent Identity and Purpose:** Analyze the agent's `displayName`, goals, and tools to infer its domain (e.g., "E-commerce Retail," "Airline Bookings") and primary business objectives.
        2.  **Core Capabilities and User Journeys:** Examine each playbook's `goal` and `instruction` to synthesize "critical user journeys." A journey might involve multiple playbooks and tools. Use the provided `examples` to understand the expected conversational flow.
        3.  **Tool Integration:** Analyze each tool's `description` or `openApiSpec`. Identify what function each tool performs, what inputs it needs, and which user intents should trigger it.

        **Phase 2: Evaluation Set Generation and Strict Formatting**
        Based on your analysis, generate the evaluation set. Your final output MUST be a single JSON list of turn objects. Each object in the list represents one turn in a conversation.

        Each **turn object** must have the following keys:
        - `conversation_id`: (Integer) A unique ID for the conversation flow, starting from 1. All turns within the same conversation share the same ID.
        - `action_id`: (Integer) A sequential ID for the action within a single conversation, starting from 1 for each new conversation.
        - `scenario`: (String) A brief, one-sentence description of what this conversation is testing. This should be present on the first turn (`action_id: 1`) of each conversation and can be `null` for subsequent turns.
        - `user_utterance`: (String or `null`) The text spoken by the user for this turn.
        - `agent_utterance`: (String or `null`) The expected text response from the agent for this turn.
        - `action_input_parameters`: (JSON Object or `null`) If the agent is expected to call a tool, this object contains the exact parameters for that tool call for this turn.
        - `action_type`: (String) Must be one of 3 values: `"User Utterance"` (for user queries), `"Agent Response"` (for text outputs) or `"Tool Invocation"` (for tool calls).
        - `notes`: (String or `null`) Optional notes about the test case, such as what edge case it's testing or a potential point of failure.

        **Generation Guidelines:**
        - **Determine Test Size:** Use your expert QA judgment to decide the number of conversations needed to cover the critical journeys. A simple agent may need 2-3 conversations; a complex one may need 5-7.
        - **Create Test Cases:** Generate multi-turn conversations that test happy paths, tool-triggering scenarios, handoffs, and edge cases.

        **CRITICAL RULE: Each turn object represents exactly ONE action. A user speaking is one action. An agent responding with text is another action. An agent calling a tool is a third type of action. Do NOT combine a user utterance and an agent response in the same turn object.**

        **Example of a Correct Multi-Turn Sequence:**
        ```json
        [
          {
            "conversation_id": 1,
            "action_id": 1,
            "scenario": "User asks for a flight, agent calls a tool, then agent responds with text.",
            "user_utterance": "I need a flight from SFO to JFK tomorrow.",
            "agent_utterance": null,
            "action_input_parameters": null,
            "action_type": "User Utterance",
            "notes": null
          },
          {
            "conversation_id": 1,
            "action_id": 2,
            "scenario": null,
            "user_utterance": null,
            "agent_utterance": null,
            "action_input_parameters": { "origin": "SFO", "destination": "JFK", "departure_date": "2024-07-19" },
            "action_type": "Tool Invocation",
            "notes": "Agent should gather all necessary info and call the tool."
          },
          {
            "conversation_id": 1,
            "action_id": 3,
            "scenario": null,
            "user_utterance": null,
            "agent_utterance": "I found a flight for you on United for $350. Would you like to book it?",
            "action_input_parameters": null,
            "action_type": "Agent Response",
            "notes": "Agent should summarize the tool's findings."
          }
        ]

        Your response MUST begin directly with the opening bracket `[` of the JSON list. Do not include any introductory text, analysis, or markdown fences.
        """

        prompt = f"""
        Please act as a Senior QA Engineer. Analyze the following agent configuration and generate an appropriately sized, high-quality evaluation set in the required JSON format.

        Agent Configuration:
        {json.dumps(agent_data, indent=2)}
        """

        logger.info("Requesting dynamically sized eval set from the model...")
        response_str = await self.gemini_client.generate_async(
            prompt=prompt, system_prompt=system_prompt
        )
        logger.debug(f"***Generated the eval set***: {response_str}")

        if not response_str:
            logger.error("Eval set generation failed: No response from model.")
            return None

        try:
            # Find the start of the first JSON array '[' or object '{'
            json_start_index = -1
            first_bracket = response_str.find("[")
            first_brace = response_str.find("{")

            if first_bracket != -1 and (
                first_brace == -1 or first_bracket < first_brace
            ):
                json_start_index = first_bracket
            elif first_brace != -1:
                json_start_index = first_brace

            if json_start_index == -1:
                raise json.JSONDecodeError(
                    "No JSON object/array found in the response.",
                    response_str,
                    0,
                )

            # Extract from the start of the JSON to the end of the string
            json_str = response_str[json_start_index:]

            # Clean up any trailing markdown backticks
            json_str = json_str.strip().rstrip("`")

            eval_set = json.loads(json_str)
            if isinstance(eval_set, list):
                logger.info(
                    f"-> Successfully extracted and parsed an eval set with {len(eval_set)} turns."
                )
                return eval_set
            else:
                logger.error(
                    f"Eval set generation failed: Parsed JSON is not a list. Got: {type(eval_set)}"
                )
                return None

        except json.JSONDecodeError as e:
            logger.error(
                f"Eval set generation failed: Could not decode JSON from model response. Error: {e}"
            )
            logger.debug(f"Raw response: {response_str}")
            return None

    async def evaluate_conversations(
        self, eval_results: list, eval_set: list
    ) -> Optional[dict]:
        """Uses an LLM to evaluate conversation results against the original

        eval set.

        Args:
            eval_results: The list of conversation results from AgentComparer.
            eval_set: The original evaluation set with expected outcomes.

        Returns:
            A dictionary containing the LLM's evaluation summary, or None on
            failure.
        """
        system_prompt = """You are a meticulous Senior Quality Assurance Analyst specializing in conversational AI. Your task is to analyze a JSON dataset containing the results of a side-by-side agent evaluation and produce a concise, insightful summary report in Markdown format.

        The input JSON contains two top-level keys:
        1.  `golden_set`: The ground-truth test script, detailing scenarios and the expected agent actions (text or tool calls) for each turn.
        2.  `conversation_results`: The actual turn-by-turn logs from running the `golden_set` against two agents: a source 'DFCX' agent and a target 'Polysynth' agent.

        Your report MUST have two sections:

        **1. Per-Scenario Analysis:**
        Iterate through each conversation scenario. For each one:
        - Announce the scenario's goal (e.g., `### Scenario 1: Full happy path...`).
        - For EACH agent (DFCX and Polysynth), provide a sub-section with the following evaluations based on the metrics library:
            - **Conversation Correctness (Score 1-5):** Did the agent follow the expected conversational flow and achieve the scenario's goal? (1=Completely failed, 5=Perfectly achieved).
            - **Agent Response Agreement (Score 1-5):** How semantically similar were the agent's text responses to the golden responses? (1=Totally different, 5=Identical meaning).
            - **Conversation Fluency (Score 1-5):** Was the conversation natural, coherent, and not repetitive? (1=Confusing/robotic, 5=Very natural).
        - Provide a brief, bulleted justification for your scores for each agent.

        **2. Overall Summary & Recommendations:**
        - **High-Level Summary:** Write a paragraph comparing the two agents' overall performance based on the qualitative metrics you just scored.
        - **Key Findings:** Provide a bulleted list of the most important observations (e.g., "Polysynth struggled with multi-turn context," or "DFCX was less fluent").
        - **Final Recommendation:** Conclude with a clear recommendation. Is the Polysynth agent ready, ready with conditions, or does it need significant work?

        Generate ONLY the Markdown report. Do not include any other text or conversational filler.
        """

        # Group golden set by conversation_id for easier lookup in the prompt
        golden_set_by_convo = {}
        for turn in eval_set:
            convo_id = turn["conversation_id"]
            if convo_id not in golden_set_by_convo:
                golden_set_by_convo[convo_id] = {
                    "scenario": turn["scenario"],
                    "turns": [],
                }
            golden_set_by_convo[convo_id]["turns"].append(turn)

        prompt_data = {
            "golden_set": list(golden_set_by_convo.values()),
            "conversation_results": eval_results,
        }

        prompt = f"""
        Please analyze the following agent evaluation results and generate the summary report.

        **Evaluation Data JSON:**
        ```json
        {json.dumps(prompt_data, indent=2)}
        ```
        """

        logger.info(
            "\n🤖 Submitting evaluation results to Gemini for analysis..."
        )
        summary = await self.gemini_client.generate_async(
            prompt=prompt, system_prompt=system_prompt
        )
        return summary
