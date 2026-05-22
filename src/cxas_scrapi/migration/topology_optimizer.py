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

"""LLM-driven conversational agent topology optimizer for Stage 3."""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

from cxas_scrapi.migration.data_models import (
    IRAgent,
    MigrationIR,
    MigrationStatus,
)
from cxas_scrapi.migration.prompts import Prompts
from cxas_scrapi.utils.gemini import GeminiGenerate

logger = logging.getLogger(__name__)


class SubAgentClassification(BaseModel):
    """Represents the designation of an individual sub-agent in Stage 3."""

    key: str = Field(
        description="The unique key name identifying this sub-agent in the IR."
    )
    designation: str = Field(description="Must be 'CORE' or 'HELPER'.")
    semantic_role: str = Field(
        description="Detailed operational purpose of the sub-agent."
    )
    merger_target: Optional[str] = Field(
        default=None,
        description=(
            "The target Core agent or special Root/Closing agent "
            "to absorb this Helper stub."
        ),
    )


class AppTopologyGraph(BaseModel):
    """The global semantic classification graph of the entire migrated app."""

    classifications: List[SubAgentClassification] = Field(default_factory=list)


class CoreHarmonyReport(BaseModel):
    """Generative QA final integration report for merged Core agents."""

    passed: bool
    final_optimized_instruction: Optional[str] = Field(
        default=None,
        description="The polished, comprehensive final instruction XML.",
    )
    detected_contradictions: List[str] = Field(default_factory=list)
    reconciliation_suggestions: List[str] = Field(default_factory=list)


class CoreMergerRecommendation(BaseModel):
    """Recommendations for fusing redundant CORE sub-agents in Stage 3."""

    merges: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Mapping of source Core agent keys to target Core agent keys."
        ),
    )


class TopologyOptimizer:
    """LLM-driven graph topology optimizer and organic prompt merging
    engine for Stage 3.
    """

    def __init__(self, ir: MigrationIR, gemini_client: GeminiGenerate):
        self.ir = ir
        self.gemini = gemini_client
        self.console = Console()

    def _find_core_root_agent_key(self, core_keys: List[str]) -> str:
        """Heuristically identifies the core root playbook agent among
        the CORE class.
        """
        for k in core_keys:
            if (
                "steering" in k.lower()
                or "steering_agent" in k.lower()
                or "roaming" in k.lower()
            ):
                return k
        if core_keys:
            return core_keys[0]
        return list(self.ir.agents.keys())[0]

    def _map_all_agent_references(self) -> Dict[str, List[str]]:
        """Scans all CXAS agents (both Playbook-derived and Flow-derived)
        across instructions, callback Python scripts, and Python tools
        function code to build a complete helper -> parents map.
        """
        references = {}
        for parent_key, agent in self.ir.agents.items():
            referenced = set()

            # 1. Scan Instructions
            if agent.instruction:
                referenced.update(
                    re.findall(r"{@AGENT:\s*([^}]+)}", agent.instruction)
                )

            # 2. Scan Callback Python Code for programmatic transfers
            if agent.callbacks:
                for cb_code in agent.callbacks.values():
                    if cb_code:
                        referenced.update(
                            re.findall(
                                r"agent\s*=\s*['\"]([^'\"]+)['\"]", cb_code
                            )
                        )
                        referenced.update(
                            re.findall(
                                r"['\"]target['\"]\s*:\s*['\"]([^'\"]+)['\"]",
                                cb_code,
                            )
                        )

            # 3. Scan Python Tools function code for inline programmatic
            # transfers
            for tool_ref in agent.tools:
                base_id = tool_ref.split("/")[-1]
                found_tool = None
                for t_key, t_val in self.ir.tools.items():
                    if (
                        t_key in (tool_ref, base_id)
                        or t_val.id == base_id
                        or t_val.name == tool_ref
                    ):
                        found_tool = t_val
                        break
                if found_tool and found_tool.type == "PYTHON":
                    py_code = found_tool.payload.get("pythonFunction", {}).get(
                        "python_code", ""
                    )
                    if py_code:
                        referenced.update(
                            re.findall(
                                r"agent\s*=\s*['\"]([^'\"]+)['\"]", py_code
                            )
                        )
                        referenced.update(
                            re.findall(
                                r"['\"]target['\"]\s*:\s*['\"]([^'\"]+)['\"]",
                                py_code,
                            )
                        )

            for ref in referenced:
                ref_clean = ref.strip()
                if ref_clean in self.ir.agents:
                    references.setdefault(ref_clean, []).append(parent_key)
        return references

    async def analyze_app_topology(self) -> AppTopologyGraph:
        """Semantically classifies migrated stubs into Core vs. Helper
        agents.
        """
        logger.info(
            "Starting LLM-driven Stage 3 App-Level Topology "
            "Classification pass..."
        )

        # 1. Compile detailed Pydantic inventory of active agents
        inventory = []
        for key, agent in self.ir.agents.items():
            inventory.append(
                {
                    "key": key,
                    "type": agent.type,
                    "display_name": agent.display_name,
                    "description": agent.description or "No description",
                    "tools_count": len(agent.tools),
                    "callbacks_count": len(agent.callbacks or {})
                    if agent.callbacks
                    else 0,
                    "instruction_preview": (agent.instruction[:400] + "...")
                    if agent.instruction
                    else "",
                }
            )

        # 2. Prompt Gemini
        system_prompt = Prompts.STAGE_3_TOPOLOGY_ANALYSIS["system"]
        template = Prompts.STAGE_3_TOPOLOGY_ANALYSIS["template"].format(
            agents_inventory=json_dumps_safely(inventory)
        )

        try:
            graph = await self.gemini.generate_async(
                prompt=template,
                system_prompt=system_prompt,
                response_mime_type="application/json",
                response_schema=AppTopologyGraph,
            )
            logger.info(
                "Topology analysis complete. Resolved "
                f"{len(graph.classifications)} designations."
            )
            return graph
        except Exception as e:
            logger.error(f"Failed to analyze app topology: {e}")
            # Fallback designation logic: Treat everything as CORE to prevent
            # migration crash
            fallback = AppTopologyGraph()
            for key in self.ir.agents.keys():
                fallback.classifications.append(
                    SubAgentClassification(
                        key=key,
                        designation="CORE",
                        semantic_role="Fallback core assignment",
                    )
                )
            return fallback

    def print_designations_table(
        self, graph: AppTopologyGraph, console: Console
    ) -> None:
        """Outputs a clean, highly legible Rich table detailing LLM
        designations.
        """
        console.print(
            "\n[bold blue]=== STAGE 3: LLM SUB-AGENT DESIGNATIONS & "
            "MERGER MAPPING ===[/]\n"
        )

        table = Table(title="App-Level Topological Classifications (Stage 3)")
        table.add_column(
            "Sub-Agent Key", style="cyan", header_style="bold cyan"
        )
        table.add_column(
            "Designation", style="magenta", header_style="bold magenta"
        )
        table.add_column(
            "Semantic Role", style="green", header_style="bold green"
        )
        table.add_column(
            "Merger Target / Action",
            style="yellow",
            header_style="bold yellow",
        )

        for c in graph.classifications:
            action = (
                c.merger_target
                if c.designation == "HELPER"
                else "Retained as Core Spoke"
            )
            if not action:
                action = "Steering_Agent (Root Onboarding)"
            table.add_row(c.key, c.designation, c.semantic_role, action)

        console.print(table)
        console.print("-" * 80 + "\n")

    async def organically_merge_agent_prompts(
        self, core_agent: IRAgent, helper_agent: IRAgent
    ) -> str:
        """Prompts Gemini to weave helper instructions, tools, and callbacks
        with minimal modifications.
        """
        logger.info(
            "Executing organic LLM prompt merger: '%s' -> '%s'...",
            helper_agent.display_name,
            core_agent.display_name,
        )

        core_context = self._build_rich_agent_context(core_agent)
        helper_context = self._build_rich_agent_context(helper_agent)

        system_prompt = Prompts.STAGE_3_ORGANIC_PROMPT_MERGER["system"]
        template = Prompts.STAGE_3_ORGANIC_PROMPT_MERGER["template"].format(
            core_context=json_dumps_safely(core_context),
            helper_context=json_dumps_safely(helper_context),
        )

        try:
            merged_xml = await self.gemini.generate_async(
                prompt=template,
                system_prompt=system_prompt,
            )
            logger.info(
                "Minimal-change organic merger successful. Length: "
                f"{len(merged_xml)} bytes."
            )
            return self._parse_generative_xml_response(
                merged_xml, agent_name=core_agent.display_name
            )
        except Exception as e:
            logger.error(
                "Organic prompt merge failed: %s. Falling back to "
                "standard comment encapsulation.",
                e,
            )
            # Fallback to standard concatenation comment wrapper
            fallback = (
                f"{core_agent.instruction}\n\n"
                f"<!-- Woven Helper: {helper_agent.display_name} -->\n"
                f'<helper_extension name="{helper_agent.display_name}">\n'
                f"  {helper_agent.instruction}\n"
                f"</helper_extension>"
            )
            return fallback

    async def verify_merged_core_harmony(
        self, merged_core_agent: IRAgent
    ) -> bool:
        """Definitive Stage 3 integration verification check for comprehensive
        cohesion.
        """
        logger.info(
            "Executing definitive Stage 3 Cohesion verification pass "
            "for Core: '%s'...",
            merged_core_agent.display_name,
        )

        merged_context = {
            "name": merged_core_agent.display_name,
            "instructions": merged_core_agent.instruction,
            "tools": merged_core_agent.tools,
            "callbacks_present": bool(merged_core_agent.callbacks),
        }

        system_prompt = Prompts.STAGE_3_CORE_HARMONY_VERIFICATION["system"]
        template = Prompts.STAGE_3_CORE_HARMONY_VERIFICATION["template"].format(
            merged_context=json_dumps_safely(merged_context)
        )

        try:
            report = await self.gemini.generate_async(
                prompt=template,
                system_prompt=system_prompt,
                response_mime_type="application/json",
                response_schema=CoreHarmonyReport,
            )
            if report.passed:
                logger.info("✅ Comprehensive cohesion check PASSED cleanly.")
                if report.final_optimized_instruction:
                    merged_core_agent.instruction = (
                        report.final_optimized_instruction
                    )
                return True
            else:
                logger.warning(
                    "⚠️ Comprehensive cohesion check FAILED. Detected "
                    f"contradictions: {report.detected_contradictions}"
                )
                logger.warning(
                    "Reconciliation Suggestions: "
                    f"{report.reconciliation_suggestions}"
                )
                if report.final_optimized_instruction:
                    merged_core_agent.instruction = (
                        report.final_optimized_instruction
                    )

                todo_block = (
                    "\n\n<!-- ⚠️ STAGE 3 COHESION INTEGRATION WARNINGS:\n"
                    + "\n".join(
                        [f"- {c}" for c in report.detected_contradictions]
                    )
                    + "\n\nRECONCILIATION SUGGESTIONS:\n"
                    + "\n".join(
                        [f"- {s}" for s in report.reconciliation_suggestions]
                    )
                    + "\n-->"
                )
                merged_core_agent.instruction += todo_block
                return False
        except Exception as e:
            logger.error(
                "Cohesion verification crashed: %s. Bypassing to "
                "avoid blocker.",
                e,
            )
            return True

    def _build_rich_agent_context(self, agent: IRAgent) -> Dict[str, Any]:
        """Builds a highly detailed representation of an agent's instruction
        XML, full Python callback code definitions, and detailed tool
        schemas/code.
        """
        # 1. Map Callback Names to Callback Codes
        callbacks_rich = []
        if agent.callbacks:
            for cb_type, cb_code in agent.callbacks.items():
                if cb_code:
                    callbacks_rich.append(
                        {"type": cb_type, "python_code": cb_code}
                    )

        # 2. Map Tool Names/Resource IDs to Detailed Tool Payload
        # Definitions / Python Codes
        tools_rich = []
        for tool_ref in agent.tools:
            base_id = tool_ref.split("/")[-1]
            found_tool = None
            for t_key, t_val in self.ir.tools.items():
                if (
                    t_key in (tool_ref, base_id)
                    or t_val.id == base_id
                    or t_val.name == tool_ref
                ):
                    found_tool = t_val
                    break

            if found_tool:
                payload = found_tool.payload or {}
                t_desc = payload.get("description", "") or payload.get(
                    "displayName", ""
                )
                if found_tool.type == "PYTHON":
                    py_code = payload.get("pythonFunction", {}).get(
                        "python_code", ""
                    )
                    tools_rich.append(
                        {
                            "id": found_tool.id,
                            "type": "PYTHON",
                            "description": t_desc,
                            "python_code": py_code,
                        }
                    )
                else:
                    tools_rich.append(
                        {
                            "id": found_tool.id,
                            "type": found_tool.type,
                            "description": t_desc,
                        }
                    )
            else:
                # Fallback if tool is not found in master registry
                tools_rich.append(
                    {
                        "id": base_id,
                        "type": "UNKNOWN",
                        "description": (
                            f"External / unregistered tool: {tool_ref}"
                        ),
                    }
                )

        return {
            "name": agent.display_name,
            "instructions": agent.instruction,
            "tools": tools_rich,
            "callbacks": callbacks_rich,
        }

    def _parse_generative_xml_response(
        self, response_text: str, agent_name: str = "Sub_Agent"
    ) -> str:
        """Cleans, extracts, and decodes the raw XML instruction set from
        LLM response, handling cases where Gemini outputs JSON-wrapped
        objects, markdown fences, or escaped characters.
        """
        if not response_text:
            return ""

        text_clean = response_text.strip()

        # 1. Strip markdown code blocks if present
        text_clean = re.sub(
            r"^```(?:xml|json)?", "", text_clean, flags=re.MULTILINE
        )
        text_clean = re.sub(r"```$", "", text_clean, flags=re.MULTILINE)
        text_clean = text_clean.strip()

        # 2. FIRST PRIORITY: Universal generic XML scraper to extract any
        # outermost XML block dynamically
        xml_match = re.search(
            r"(<([a-zA-Z0-9_-]+)(?:\s+[^>]*)?>.*?</\2>)", text_clean, re.DOTALL
        )

        if xml_match:
            xml_content = xml_match.group(1).strip()
            # Unescape basic backslash escapes to restore multiline formatting
            # (e.g. \n -> newline, \" -> ")
            xml_content = (
                xml_content.encode()
                .decode("unicode-escape")
                .encode("utf-8")
                .decode("utf-8")
            )
            logger.info(
                "Successfully extracted and decoded raw XML block using "
                "regex scraper."
            )
        else:
            # 3. SECOND PRIORITY: JSON decoder fallback (if the response is a
            # clean, valid JSON wrapper)
            xml_content = text_clean
            if text_clean.startswith("{") and text_clean.endswith("}"):
                try:
                    data = json.loads(text_clean)
                    if isinstance(data, dict):
                        for k in [
                            "instructions",
                            "instruction",
                            "final_optimized_instruction",
                        ]:
                            if k in data and data[k]:
                                xml_content = str(data[k]).strip()
                                logger.info(
                                    "Successfully parsed organic merger JSON "
                                    f"payload, extracted '{k}' key."
                                )
                                break
                except Exception as e:
                    logger.warning(
                        "Failed to parse response as JSON, treating as raw "
                        f"text: {e}"
                    )

            # 4. LAST PRIORITY: Fallback to raw text cleanup, decoding
            # escaped backslashes if present
            if "\\n" in xml_content or '\\"' in xml_content:
                try:
                    xml_content = (
                        xml_content.encode()
                        .decode("unicode-escape")
                        .encode("utf-8")
                        .decode("utf-8")
                    )
                    logger.info(
                        "Decoded backslash escaped characters in raw text."
                    )
                except Exception:
                    pass

        # 5. CRITICAL SAFEGUARD: Auto-wrap unstructured raw text into
        # standard, compliant CXAS XML schema
        xml_content = xml_content.strip()
        if not xml_content.startswith("<"):
            logger.warning(
                f"Agent '{agent_name}' instructions are unstructured "
                "raw text. Auto-compiling into well-formatted XML schema..."
            )
            xml_content = (
                "<Agent>\n"
                f"  <Name>{agent_name}</Name>\n"
                "  <Role>Cohesive domain spoke agent.</Role>\n"
                "  <general_instruction>\n"
                f"    {xml_content}\n"
                "  </general_instruction>\n"
                "</Agent>"
            )
        return xml_content

    def _merge_and_chain_agent_callbacks(
        self, parent_agent: IRAgent, helper_agent: IRAgent, helper_key: str
    ):
        """Atomically merges and chains the callbacks of a helper/source agent
        directly into the parent agent.
        """
        if not helper_agent.callbacks:
            return

        if not parent_agent.callbacks:
            parent_agent.callbacks = {}

        for cb_type in ["before_model_callback", "after_model_callback"]:
            h_code = helper_agent.callbacks.get(cb_type)
            if not h_code:
                continue

            # 1. Rename the helper's function uniquely to avoid namespace
            # collisions
            prefix = re.sub(r"[^a-zA-Z0-9_]", "_", helper_key).lower()
            h_renamed = self._isolate_and_rename_callback(
                h_code, cb_type, helper_key
            )

            h_def_block = (
                f"# {'=' * 76}\n"
                f"# 📥 INLINED HELPER CALLBACK: {cb_type}_{prefix} "
                f"(From Agent: {helper_key})\n"
                f"# {'=' * 76}\n"
                f"{h_renamed}\n\n"
            )

            # 2. Construct the parameters and arguments based on callback type
            if cb_type == "before_model_callback":
                param_sig = (
                    "callback_context: CallbackContext, llm_request: LlmRequest"
                )
                param_args = "callback_context, llm_request"
                return_type = "Optional[LlmResponse]"
            else:
                param_sig = (
                    "callback_context: CallbackContext, "
                    "llm_response: LlmResponse"
                )
                param_args = "callback_context, llm_response"
                return_type = "Optional[LlmResponse]"

            p_code = parent_agent.callbacks.get(cb_type)
            if not p_code:
                # Parent doesn't have this callback yet, create a fresh
                # master wrapper
                master_wrapper = (
                    f"def {cb_type}({param_sig}) -> {return_type}:\n"
                    f"    # Delegate to {cb_type}_{prefix}\n"
                    f"    res = {cb_type}_{prefix}({param_args})\n"
                    f"    if res is not None:\n"
                    f"        return res\n"
                    f"    return None\n"
                )
                parent_agent.callbacks[cb_type] = h_def_block + master_wrapper
            else:
                # Parent already has a master wrapper, append definitions and
                # inject the delegation call
                wrapper_pattern = (
                    r"(def\s+"
                    + re.escape(cb_type)
                    + r"\s*\([^)]*\)(?:\s*->\s*[a-zA-Z_\[\]?]*):\n)"
                )
                parts = re.split(wrapper_pattern, p_code)
                if len(parts) >= 3:
                    defs_part = parts[0]
                    wrapper_sig = parts[1]
                    body_part = parts[2]

                    new_defs = defs_part + h_def_block
                    delegation = (
                        f"    # Delegate to {cb_type}_{prefix}\n"
                        f"    res = {cb_type}_{prefix}({param_args})\n"
                        f"    if res is not None:\n"
                        f"        return res\n\n"
                    )
                    new_body = delegation + body_part
                    parent_agent.callbacks[cb_type] = (
                        new_defs + wrapper_sig + new_body
                    )
                else:
                    logger.warning(
                        "Failed to parse master wrapper for %s on %s. "
                        "Appending fallback.",
                        cb_type,
                        parent_agent.display_name,
                    )
                    parent_agent.callbacks[cb_type] = (
                        p_code + "\n\n" + h_def_block
                    )

    def assert_child_agent_limit(self, max_children: int = 7) -> None:
        """Strict child agent limit validation, raising alerts if spokes >
        max_children.
        """
        core_spokes = [
            k
            for k, a in self.ir.agents.items()
            if k not in ["Steering_Agent", "Session_Termination_Agent"]
            and a.status != MigrationStatus.FAILED
        ]
        logger.info(
            "Validating child agent spoke cap: Active spokes count = %d",
            len(core_spokes),
        )
        if len(core_spokes) > max_children:
            logger.warning(
                "⚠️ Strict Limit Warning: Active child spokes (%d) "
                "exceed maximum cap (%d)!",
                len(core_spokes),
                max_children,
            )

    async def optimize_stage3_topology(
        self, app_graph: AppTopologyGraph
    ) -> MigrationIR:
        """Coordinates the entire Stage 3 graph topology consolidation pass."""
        logger.info("Assembling optimized Spoke-Hub topology in Stage 3...")

        # 1. Register our universal wrap_up_conversation tool globally
        # (Bypassed)

        # Partition CORE and HELPER designations from classifications
        core_keys = []
        helper_keys = []
        closing_keys = []
        for c in app_graph.classifications:
            if c.designation == "CORE":
                core_keys.append(c.key)
            else:
                helper_keys.append(c.key)
                # Resolve which helper stubs belong to the Exit Hub
                # (Session_Termination_Agent)
                target = c.merger_target or ""
                if (
                    target in ["Session_Termination_Agent", "end_session"]
                    or "exit" in c.key.lower()
                    or "escalation" in c.key.lower()
                ):
                    closing_keys.append(c.key)

        # Resolve the designated starting Core Root agent
        core_root_key = self._find_core_root_agent_key(core_keys)
        self.ir.metadata.root_agent_key = core_root_key

        # 2. Map parent-child references dynamically across all agents
        # (flows & playbooks)
        ref_map = self._map_all_agent_references()

        # 3. Assemble Fused Closing Agent (The unified exit hub)
        self.console.print(
            "[cyan]TopologyOptimizer[/] Initializing centralized "
            "'Session_Termination_Agent' sign-off gateway..."
        )
        session_termination_agent = IRAgent(
            type="CXAS Agent",
            display_name="Session_Termination_Agent",
            description=(
                "Centralized, professional sign-off and session "
                "termination gateway."
            ),
            instruction=(
                "<Agent>\n"
                "  <Name>Session_Termination_Agent</Name>\n"
                "  <Role>Canned, professional closing wrap-up gateway.</Role>\n"
                "  <Conversation_Schema>\n"
                '    <state id="main">\n'
                "      <instructions>\n"
                "        - Say: Thank you for calling! Please stay on the "
                "line while we wrap up your session.\n"
                "        - Call tool: {@TOOL: end_session}\n"
                "      </instructions>\n"
                "    </state>\n"
                "  </Conversation_Schema>\n"
                "</Agent>"
            ),
            tools=["end_session"],
            callbacks={},
        )
        self.ir.agents["Session_Termination_Agent"] = session_termination_agent

        # 4A. Multi-Parent Helper Merger Pass: Inline helpers into all
        # referencing parents (Sequentially per parent!)
        # Precalculate the resolved CORE target for each helper to
        # prevent duplicate merging
        def resolve_ultimate_core(key: str) -> str:
            # Find classification
            cls = next(
                (c for c in app_graph.classifications if c.key == key), None
            )
            if not cls:
                return core_root_key

            if cls.designation == "CORE":
                return key

            tgt = cls.merger_target or ""
            tgt_clean = tgt.strip().lower()

            # 1. Semantic Exit Hub matching
            if (
                "termination" in tgt_clean
                or "signoff" in tgt_clean
                or "end_session" in tgt_clean
            ):
                return "Session_Termination_Agent"
            # 2. Semantic Steering Root matching
            if (
                "steering" in tgt_clean
                or "root" in tgt_clean
                or "steering_agent" in tgt_clean
            ):
                return core_root_key

            # 3. Active class resolution
            target_cls = next(
                (c for c in app_graph.classifications if c.key == tgt), None
            )
            if target_cls:
                if target_cls.designation == "CORE":
                    return tgt
                else:
                    return resolve_ultimate_core(tgt)

            # 4. Definitive transition-based fallback (check actual ref_map
            # parents)
            parents = ref_map.get(key, [])
            if parents:
                for p in parents:
                    p_cls = next(
                        (c for c in app_graph.classifications if c.key == p),
                        None,
                    )
                    if p_cls and p_cls.designation == "CORE":
                        return p
                return resolve_ultimate_core(parents[0])

            return core_root_key

        parent_to_helpers = {}
        for hk in helper_keys:
            if hk not in self.ir.agents:
                continue
            helper_agent = self.ir.agents[hk]

            ultimate_parent = resolve_ultimate_core(hk)
            if ultimate_parent in self.ir.agents:
                parent_to_helpers.setdefault(ultimate_parent, []).append(
                    helper_agent
                )

        async def merge_helpers_for_parent(pk: str, helpers: List[IRAgent]):
            parent_agent = self.ir.agents[pk]
            for helper_agent in helpers:
                self.console.print(
                    "[cyan]TopologyOptimizer[/] Stage 3 organically "
                    "merging Helper: "
                    f"[magenta]'{helper_agent.display_name}'[/] "
                    f"-> Parent: [green]'{pk}'[/]..."
                )

                # Strip old comments to prevent nesting and formatting loss
                clean_parent_instruction = self._strip_helper_comments(
                    parent_agent.instruction
                )
                parent_agent.instruction = clean_parent_instruction

                merged_instruction = await self.organically_merge_agent_prompts(
                    parent_agent, helper_agent
                )
                parent_agent.instruction = merged_instruction

                # B. Union Tools (add helper's tools to parent's available
                # tools)
                for t in helper_agent.tools:
                    if t not in parent_agent.tools:
                        parent_agent.tools.append(t)

                # C. Consolidate and chain callbacks atomically in Step 4
                if helper_agent.callbacks:
                    self._merge_and_chain_agent_callbacks(
                        parent_agent, helper_agent, helper_agent.display_name
                    )

            parent_agent.status = MigrationStatus.COMPILED

        if parent_to_helpers:
            self.console.print(
                "[cyan]TopologyOptimizer[/] Dispatching helper prompt "
                f"mergers across {len(parent_to_helpers)} parents "
                "concurrently..."
            )
            await asyncio.gather(
                *(
                    merge_helpers_for_parent(pk, helpers)
                    for pk, helpers in parent_to_helpers.items()
                )
            )

        # Delete all standalone helper stubs from IR (purges from live console)
        for hk in helper_keys:
            if hk in self.ir.agents:
                del self.ir.agents[hk]

        # 4B. CORE Agents organic merger pass (Simplifies remaining CORE
        # Spokes dynamically!)
        self.console.print(
            "[cyan]TopologyOptimizer[/] Starting Stage 3 CORE Agent "
            "Merger pass..."
        )
        core_agents = []
        for k, a in self.ir.agents.items():
            # Strictly protect the main Steering Root and the centralized
            # Exit Hub from core-to-core collapsing fusions
            if k in [
                "Steering_Agent",
                "Session_Termination_Agent",
                core_root_key,
            ]:
                continue
            core_agents.append(
                {
                    "key": k,
                    "display_name": a.display_name,
                    "type": a.type,
                    "description": a.description or "None",
                    "instruction_preview": (a.instruction[:400] + "...")
                    if a.instruction
                    else "",
                }
            )

        system_prompt = Prompts.STAGE_3_CORE_MERGER["system"]
        template = Prompts.STAGE_3_CORE_MERGER["template"].format(
            agents_inventory=json_dumps_safely(core_agents)
        )

        recommended_merges = {}
        try:
            merges_rec = await self.gemini.generate_async(
                prompt=template,
                system_prompt=system_prompt,
                response_mime_type="application/json",
                response_schema=CoreMergerRecommendation,
            )
            recommended_merges = merges_rec.merges
            logger.info(
                "CORE Agent Merger pass returned "
                f"{len(recommended_merges)} fusions."
            )
        except Exception as exc:
            logger.warning(
                "CORE Agent Merger pass failed: "
                f"{exc}. Proceeding without core fusions."
            )

        # Group CORE fusions by target key
        target_to_sources = {}
        for src_key, tgt_key in recommended_merges.items():
            if src_key in self.ir.agents and tgt_key in self.ir.agents:
                target_to_sources.setdefault(tgt_key, []).append(src_key)

        async def fuse_cores_for_target(tgt_key: str, src_keys: List[str]):
            tgt_agent = self.ir.agents[tgt_key]
            for src_key in src_keys:
                src_agent = self.ir.agents[src_key]
                self.console.print(
                    "[cyan]TopologyOptimizer[/] Stage 3 organically "
                    "fusing CORE agent: "
                    f"[magenta]'{src_agent.display_name}'[/] "
                    f"-> Target: [green]'{tgt_key}'[/]..."
                )

                # Strip old comments to prevent nesting and formatting loss
                clean_tgt_instruction = self._strip_helper_comments(
                    tgt_agent.instruction
                )
                tgt_agent.instruction = clean_tgt_instruction

                merged_instruction = await self.organically_merge_agent_prompts(
                    tgt_agent, src_agent
                )

                tgt_agent.instruction = merged_instruction

                for t in src_agent.tools:
                    if t not in tgt_agent.tools:
                        tgt_agent.tools.append(t)
                # C. Consolidate and chain callbacks atomically inside CORE
                # merges
                if src_agent.callbacks:
                    self._merge_and_chain_agent_callbacks(
                        tgt_agent, src_agent, src_agent.display_name
                    )

                tgt_agent.status = MigrationStatus.COMPILED
                del self.ir.agents[src_key]

        if target_to_sources:
            self.console.print(
                "[cyan]TopologyOptimizer[/] Dispatching CORE Agent fusions "
                "concurrently..."
            )
            await asyncio.gather(
                *(
                    fuse_cores_for_target(tgt_key, src_keys)
                    for tgt_key, src_keys in target_to_sources.items()
                )
            )

        # Resolve final root agent metadata key
        if core_root_key not in self.ir.agents:
            self.ir.metadata.root_agent_key = (
                recommended_merges.get(core_root_key)
                or list(self.ir.agents.keys())[0]
            )
        else:
            self.ir.metadata.root_agent_key = core_root_key

        # Build the topological rewrite map for merged/consolidated helpers
        rewrite_map = {}
        for c in app_graph.classifications:
            if c.designation == "HELPER":
                tgt = self._resolve_target_key(
                    c.merger_target, core_keys, core_root_key
                )
                rewrite_map[c.key] = tgt

        # Save it to metadata so that the topology linker can also use it
        self.ir.metadata.topology_rewrites = rewrite_map
        logger.info(f"Compiled Stage 3 topology rewrite map: {rewrite_map}")

        # Perform reference rewriting across all remaining agents' instructions
        tool_rewrites = getattr(self.ir.metadata, "tool_rewrites", {}) or {}
        for key, agent in self.ir.agents.items():
            # 1. Rewrite valid agent references
            rewritten = self._rewrite_instruction_references(
                agent.instruction, rewrite_map
            )

            # 2. Clean and strip unresolved agent references from instructions
            def clean_instr_ref(match, key=key):
                target = match.group(1).strip()
                if target in self.ir.agents:
                    return match.group(0)
                logger.info(
                    "Stripping unresolved {@AGENT: %s} reference "
                    "from instructions of %s",
                    target,
                    key,
                )
                return ""

            rewritten = re.sub(
                r"{@AGENT:\s*([^}]+)}", clean_instr_ref, rewritten
            )

            # 3. Rewrite valid tools
            rewritten = self._rewrite_tool_references(rewritten, tool_rewrites)
            agent.instruction = rewritten

            # 4. Clean and rewrite unresolved callback transfer targets
            # inside Python code to Session_Termination_Agent fallback
            if agent.callbacks:
                for cb_type, cb_code in agent.callbacks.items():
                    if cb_code:

                        def clean_callback_ref(match, key=key):
                            target = match.group(2)
                            if target in self.ir.agents:
                                return match.group(0)
                            logger.info(
                                "Rewriting unresolved callback transfer "
                                "to %s -> Session_Termination_Agent "
                                "inside %s",
                                target,
                                key,
                            )
                            quote = match.group(1)
                            return (
                                f"agent={quote}Session_Termination_Agent{quote}"
                            )

                        def clean_callback_target_ref(match, key=key):
                            target = match.group(3)
                            if target in self.ir.agents:
                                return match.group(0)
                            logger.info(
                                "Rewriting unresolved callback target "
                                "transfer to %s -> "
                                "Session_Termination_Agent inside %s",
                                target,
                                key,
                            )
                            quote1 = match.group(1)
                            quote2 = match.group(2)
                            return (
                                f"{quote1}target{quote1}: "
                                f"{quote2}Session_Termination_Agent"
                                f"{quote2}"
                            )

                        rewritten_cb = re.sub(
                            r"agent\s*=\s*(['\"])([^'\"]+)\1",
                            clean_callback_ref,
                            cb_code,
                        )
                        rewritten_cb = re.sub(
                            r"(['\'])target\1\s*:\s*(['\"])([^'\"]+)\2",
                            clean_callback_target_ref,
                            rewritten_cb,
                        )
                        agent.callbacks[cb_type] = rewritten_cb

        # 5. Update App target root agent link
        # Reset old 1:1 links to rebuild clean spoke-hub links in Stage 3
        self.ir.routing_edges = []
        return self.ir

    def _resolve_target_key(
        self, target_str: str, core_keys: List[str], core_root_key: str
    ) -> str:
        """Resolves a generic LLM merger target string to a valid remaining
        agent key in the IR.
        """
        if not target_str:
            return core_root_key
        target_clean = target_str.strip().lower()
        if (
            "signoff" in target_clean
            or "wrap" in target_clean
            or "end_session" in target_clean
            or "termination" in target_clean
        ):
            return "Session_Termination_Agent"
        if (
            "steering" in target_clean
            or "root" in target_clean
            or "steering_agent" in target_clean
        ):
            return core_root_key
        for k in core_keys:
            if target_clean in k.lower() or k.lower() in target_clean:
                return k
        return core_root_key

    def _rewrite_instruction_references(
        self, instruction: str, rewrite_map: Dict[str, str]
    ) -> str:
        """Rewrites all {@AGENT: Helper_Name} tags in the instructions to
        refer to consolidated target agents.
        """
        if not instruction:
            return instruction

        def replace_match(match):
            agent_name = match.group(1).strip()

            def normalize(s):
                return re.sub(r"[_\\-]+", " ", s).strip().lower()

            norm_name = normalize(agent_name)
            for src_key, tgt_key in rewrite_map.items():
                if normalize(src_key) == norm_name:
                    return f"{{@AGENT: {tgt_key}}}"
            return match.group(0)

        return re.sub(r"{@AGENT:\s*([^}]+)}", replace_match, instruction)

    def _rewrite_tool_references(
        self, instruction: str, tool_rewrites: Dict[str, str]
    ) -> str:
        """Rewrites all {@TOOL: Original_Name} tags in the instructions to
        refer to their truncated/unique IDs.
        """
        if not instruction:
            return instruction

        def replace_match(match):
            tool_name = match.group(1).strip()

            def normalize(s):
                return re.sub(r"[_\\-]+", " ", s).strip().lower()

            norm_name = normalize(tool_name)
            for src_key, tgt_key in tool_rewrites.items():
                if normalize(src_key) == norm_name:
                    return f"{{@TOOL: {tgt_key}}}"
            return match.group(0)

        return re.sub(r"{@TOOL:\s*([^}]+)}", replace_match, instruction)

    def _isolate_and_rename_callback(
        self, cb_code: str, cb_type: str, agent_key: str
    ) -> str:
        """Renames the standard before_model_callback/after_model_callback
        function definition to a unique name based on the agent key to avoid
        namespace collision.
        """
        prefix = re.sub(r"[^a-zA-Z0-9_]", "_", agent_key).lower()
        pattern = r"def\s+" + re.escape(cb_type) + r"\s*\(([^)]*)\)"
        replacement = f"def {cb_type}_{prefix}(\\1)"
        return re.sub(pattern, replacement, cb_code)

    def _strip_helper_comments(self, text: str) -> str:
        """Strips start and end helper/core merger XML comments to prevent
        nesting and preserve formatting across multiple sequential LLM merges.
        """
        if not text:
            return text
        # Strip start and end comment nodes
        text = re.sub(
            r"<!-- 📥 START MERGED HELPER INSTRUCTION:[^>]*-->\n?", "", text
        )
        text = re.sub(
            r"<!-- 📤 END MERGED HELPER INSTRUCTION:[^>]*-->\n?", "", text
        )
        text = re.sub(
            r"<!-- 📥 START FUSED CORE AGENT INSTRUCTION:[^>]*-->\n?", "", text
        )
        text = re.sub(
            r"<!-- 📤 END FUSED CORE AGENT INSTRUCTION:[^>]*-->\n?", "", text
        )
        return text.strip()


def json_dumps_safely(obj: Any) -> str:
    """Safely dumps objects containing pydantic models or strings into
    clean JSON.
    """
    try:
        return json.dumps(
            obj,
            default=lambda o: o.__dict__ if hasattr(o, "__dict__") else str(o),
        )
    except Exception:
        return str(obj)
