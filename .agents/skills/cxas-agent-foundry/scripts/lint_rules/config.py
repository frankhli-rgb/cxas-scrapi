"""App and agent config lint rules (A001–A005).

Validates app.json and agent JSON configuration files.
"""

import json
from pathlib import Path

from . import LintContext, LintResult, Rule, Severity


class A001_InvalidJson(Rule):
    id = "A001"
    name = "config-json-parse"
    description = "Config file must be valid JSON"
    default_severity = Severity.ERROR
    category = "config"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            return [self.make_result(
                file=rel,
                message=f"Invalid JSON: {e}",
            )]
        return []


class A002_MissingRequiredFields(Rule):
    id = "A002"
    name = "config-required-fields"
    description = "Config must have required fields (name, displayName)"
    default_severity = Severity.ERROR
    category = "config"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return []  # A001 handles parse errors

        results = []
        # app.json requires name and displayName
        if file_path.name == "app.json":
            for field in ["name", "displayName"]:
                if field not in data:
                    results.append(self.make_result(
                        file=rel,
                        message=f"Missing required field: '{field}'",
                    ))
        return results


class A003_AgentToolNotExists(Rule):
    id = "A003"
    name = "config-tool-exists"
    description = "Agent config references non-existent tool"
    default_severity = Severity.ERROR
    category = "config"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))

        # Only check agent config JSONs (not app.json)
        if file_path.name == "app.json":
            return []

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return []

        results = []
        for tool in data.get("tools", []):
            if tool not in context.all_known_tools:
                results.append(self.make_result(
                    file=rel,
                    message=f"Agent config lists tool '{tool}' but it does not exist",
                    fix=f"Available tools: {', '.join(sorted(context.all_known_tools))}",
                ))
        return results


class A004_AgentMissingInstruction(Rule):
    id = "A004"
    name = "config-missing-instruction"
    description = "Agent directory must have an instruction.txt file"
    default_severity = Severity.ERROR
    category = "config"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))

        if file_path.name == "app.json":
            return []

        # Check if sibling instruction.txt exists
        agent_dir = file_path.parent
        instruction = agent_dir / "instruction.txt"
        if not instruction.exists():
            return [self.make_result(
                file=rel,
                message=f"Agent '{agent_dir.name}' has config but no instruction.txt",
                fix="Create instruction.txt with <role>, <persona>, and <taskflow> sections",
            )]
        return []


class A005_RootAgentMissingEndSession(Rule):
    id = "A005"
    name = "config-root-missing-end-session"
    description = "Root agent must have end_session tool associated"
    default_severity = Severity.ERROR
    category = "config"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))

        # Only check app.json
        if file_path.name != "app.json":
            return []

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return []

        root_agent_name = data.get("rootAgent")
        if not root_agent_name:
            return []  # No root agent set — other rules handle this

        # Find the root agent's config JSON
        agent_dir = file_path.parent / "agents" / root_agent_name
        agent_json = agent_dir / f"{root_agent_name}.json"
        if not agent_json.exists():
            return []

        try:
            agent_data = json.loads(agent_json.read_text())
        except (json.JSONDecodeError, OSError):
            return []

        tools = agent_data.get("tools", [])
        if "end_session" not in tools:
            return [self.make_result(
                file=rel,
                message=f"Root agent '{root_agent_name}' is missing 'end_session' tool — the agent cannot terminate conversations",
                fix=f"Associate end_session with the root agent via: agents_client.update_agent(agent_name=..., tools=[..., 'end_session'])",
            )]
        return []


ALL_RULES = [
    A001_InvalidJson(),
    A002_MissingRequiredFields(),
    A003_AgentToolNotExists(),
    A004_AgentMissingInstruction(),
    A005_RootAgentMissingEndSession(),
]
