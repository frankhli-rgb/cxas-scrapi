"""Structure validation rules — validates app structure and cross-references.

Uses cxas_scrapi Validator for structural checks, plus custom rules for
cross-referencing (e.g., instruction references a tool not in the agent's
tool list — the exact issue that caused the set_variables debugging nightmare).

Rules:
  S001: App structure validation (via Validator.validate_app)
  S002: Agent tool references — instruction mentions tools not in agent's tool list
  S003: Callback file references — agent JSON references callbacks that don't exist
  S004: Child agent references — agent JSON references child agents that don't exist
"""

import json
import re
from pathlib import Path
from typing import List

from . import LintContext, LintResult, Rule, Severity


class AppStructureRule(Rule):
    """S001: Validate app structure using cxas_scrapi Validator."""
    id = "S001"
    name = "app_structure_valid"
    description = "App directory structure matches CES export format"
    default_severity = Severity.ERROR
    category = "structure"

    def check(self, file_path: Path, content: str, context: LintContext) -> List[LintResult]:
        results = []
        try:
            from cxas_scrapi.utils.validator import Validator
            validator = Validator()
            validator.validate_app(str(file_path.parent))
        except ImportError:
            results.append(self.make_result(
                str(file_path), "cxas-scrapi not installed — skipping structure validation",
                severity=Severity.INFO,
            ))
        except FileNotFoundError as e:
            results.append(self.make_result(
                str(file_path), f"Missing required file or directory: {e}",
                fix="Check the app export structure — see project template for reference",
            ))
        except Exception as e:
            results.append(self.make_result(
                str(file_path), f"Structure validation failed: {e}",
            ))
        return results


class AgentToolReferencesRule(Rule):
    """S002: Instruction references tools not in the agent's tool list.

    When an instruction tells the LLM to call a tool that isn't in the agent's
    tool list, the LLM can't call it — it silently improvises by calling other
    tools, skipping the action, or generating text without any tool call.
    This is the most common and hardest-to-diagnose cause of missing tool calls.
    """
    id = "S002"
    name = "agent_tool_references"
    description = "Instruction references tools that exist in the agent's tool list"
    default_severity = Severity.ERROR
    category = "structure"

    # Pattern: {@TOOL: tool_name} or {@TOOL tool_name}
    TOOL_REF_PATTERN = re.compile(r'\{@TOOL[:\s]+([^}]+)\}', re.IGNORECASE)

    def check(self, file_path: Path, content: str, context: LintContext) -> List[LintResult]:
        results = []

        # Only check instruction.txt files
        if file_path.name != "instruction.txt":
            return results

        # Find the agent's JSON config to get its tool list
        agent_dir = file_path.parent
        agent_name = agent_dir.name
        agent_json = None
        for f in agent_dir.iterdir():
            if f.suffix == ".json" and f.stem == agent_name:
                agent_json = f
                break

        if not agent_json or not agent_json.exists():
            return results

        try:
            with open(agent_json) as f:
                agent_config = json.load(f)
        except (json.JSONDecodeError, OSError):
            return results

        agent_tools = set(agent_config.get("tools", []))
        # Also include platform tools that don't need explicit listing
        known_tools = agent_tools | context.platform_tools

        # Find all tool references in the instruction
        referenced_tools = set()
        for match in self.TOOL_REF_PATTERN.finditer(content):
            tool_name = match.group(1).strip()
            referenced_tools.add(tool_name)

        # Check each referenced tool
        for tool_name in referenced_tools:
            if tool_name not in known_tools and tool_name.lower() not in {t.lower() for t in known_tools}:
                line_num = None
                for i, line in enumerate(content.splitlines(), 1):
                    if tool_name in line:
                        line_num = i
                        break
                results.append(self.make_result(
                    str(file_path),
                    f"Instruction references tool '{tool_name}' but it's not in the agent's "
                    f"tool list. The LLM cannot call tools it doesn't have — it will silently "
                    f"improvise with other tools or skip the action entirely.",
                    line=line_num,
                    fix=f"Add '{tool_name}' to the agent's tools list in {agent_json.name}, "
                        f"or remove the reference from the instruction.",
                ))
        return results


class CallbackFileReferencesRule(Rule):
    """S003: Agent JSON references callback files that don't exist."""
    id = "S003"
    name = "callback_file_references"
    description = "Callback code files referenced in agent JSON exist on disk"
    default_severity = Severity.ERROR
    category = "structure"

    def check(self, file_path: Path, content: str, context: LintContext) -> List[LintResult]:
        results = []

        # Only check agent JSON files
        if file_path.suffix != ".json":
            return results

        try:
            agent_config = json.loads(content)
        except json.JSONDecodeError:
            return results

        # Check callback references
        app_dir = context.app_dir
        callback_types = [
            "beforeAgentCallbacks", "afterAgentCallbacks",
            "beforeModelCallbacks", "afterModelCallbacks",
            "beforeToolCallbacks", "afterToolCallbacks",
        ]
        for cb_type in callback_types:
            for cb in agent_config.get(cb_type, []):
                code_path = cb.get("pythonCode", "")
                if code_path:
                    full_path = app_dir / code_path
                    # Also check relative to the app name directory
                    if not full_path.exists():
                        for child in app_dir.iterdir():
                            if child.is_dir() and (child / code_path).exists():
                                full_path = child / code_path
                                break

                    if not full_path.exists():
                        results.append(self.make_result(
                            str(file_path),
                            f"Callback references '{code_path}' but file not found",
                            fix=f"Create the callback file or fix the path in the agent JSON",
                        ))
        return results


class ChildAgentReferencesRule(Rule):
    """S004: Agent JSON references child agents that don't exist."""
    id = "S004"
    name = "child_agent_references"
    description = "Child agent references in agent JSON point to existing agents"
    default_severity = Severity.ERROR
    category = "structure"

    def check(self, file_path: Path, content: str, context: LintContext) -> List[LintResult]:
        results = []

        if file_path.suffix != ".json":
            return results

        try:
            agent_config = json.loads(content)
        except json.JSONDecodeError:
            return results

        child_agents = agent_config.get("childAgents", [])
        for child_name in child_agents:
            if child_name not in context.all_agent_names:
                results.append(self.make_result(
                    str(file_path),
                    f"References child agent '{child_name}' but no agent directory "
                    f"found. Available agents: {sorted(context.all_agent_names)}",
                    fix=f"Create the agent directory or fix the reference",
                ))
        return results


ALL_RULES = [
    AppStructureRule(),
    AgentToolReferencesRule(),
    CallbackFileReferencesRule(),
    ChildAgentReferencesRule(),
]
