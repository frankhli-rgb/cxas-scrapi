"""Eval lint rules (E001–E006).

Validates golden, scenario, and simulation YAML files.
"""

import re
import yaml
from pathlib import Path

from . import LintContext, LintResult, Rule, Severity


class E001_InvalidYaml(Rule):
    id = "E001"
    name = "eval-yaml-parse"
    description = "Eval file must be valid YAML"
    default_severity = Severity.ERROR
    category = "evals"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as e:
            return [self.make_result(
                file=rel,
                message=f"Invalid YAML: {e}",
            )]
        return []


class E002_MissingConversations(Rule):
    id = "E002"
    name = "eval-structure"
    description = "Golden eval must have 'conversations' key"
    default_severity = Severity.ERROR
    category = "evals"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))

        # Only applies to golden evals (in goldens/ directory)
        if "goldens" not in str(file_path):
            return []

        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            return []  # E001 handles parse errors

        if not data:
            return [self.make_result(file=rel, message="Eval file is empty")]

        if "conversations" not in data:
            return [self.make_result(
                file=rel,
                message="Missing 'conversations' key in golden eval YAML",
            )]
        return []


class E003_InvalidToolCall(Rule):
    id = "E003"
    name = "eval-tool-exists"
    description = "Tool calls in evals must reference existing tools"
    default_severity = Severity.WARNING
    category = "evals"

    SPECIAL_ACTIONS = {"transfer_to_agent", "end_session"}

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        results = []

        # Golden evals may reference tools from the platform app, not from the
        # locally pulled cxas_app/ directory. Only validate tool_calls if the
        # eval lives alongside the app (not in the evals/ directory which may
        # belong to a different app).
        if "goldens" in str(file_path) or str(file_path).startswith(str(context.evals_dir)):
            # Evals in evals/ directory may reference tools from a different app
            # than what's in cxas_app/. Skip cross-referencing — these tools
            # are validated at runtime by the platform.
            return []

        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            return []

        if not data:
            return []

        conversations = data.get("conversations", [])
        if isinstance(data, list):
            # Scenario/simulation format — list of evals
            conversations = data

        for conv in conversations:
            if not isinstance(conv, dict):
                continue
            conv_name = conv.get("conversation", conv.get("name", ""))
            turns = conv.get("turns", [])
            for i, turn in enumerate(turns):
                if not isinstance(turn, dict):
                    continue
                for tc in turn.get("tool_calls", []):
                    action = tc.get("action", "")
                    if action and action not in context.all_known_tools and action not in self.SPECIAL_ACTIONS:
                        results.append(self.make_result(
                            file=rel,
                            message=f"Conv '{conv_name}' turn {i+1}: tool_call '{action}' not found in local app tools",
                            fix=f"Available local tools: {', '.join(sorted(context.all_known_tools))}",
                        ))
        return results


class E004_UndeclaredSessionParam(Rule):
    id = "E004"
    name = "eval-session-param"
    description = "Session parameters should reference known variables"
    default_severity = Severity.WARNING
    category = "evals"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        # This rule needs app variable declarations — skip if not available
        return []


class E005_DuplicateYamlKeys(Rule):
    id = "E005"
    name = "eval-duplicate-keys"
    description = "Duplicate YAML keys in same mapping (second overwrites first)"
    default_severity = Severity.ERROR
    category = "evals"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        results = []
        lines = content.split("\n")

        # Simple heuristic: find consecutive tool_calls: at same indentation
        prev_key = ""
        prev_indent = -1
        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            key_match = re.match(r'^(\w+):', stripped)
            if key_match:
                key = key_match.group(1)
                if key == prev_key and indent == prev_indent and key == "tool_calls":
                    results.append(self.make_result(
                        file=rel, line=i,
                        message=f"Duplicate '{key}:' key at same level — second overwrites first",
                        fix="Combine into a single tool_calls: list",
                    ))
                prev_key = key
                prev_indent = indent
            elif stripped and not stripped.startswith("-") and not stripped.startswith("#"):
                prev_key = ""

        return results


class E006_GoldenWithoutMocks(Rule):
    id = "E006"
    name = "eval-no-mocks"
    description = "Golden eval with tool_calls but no session_parameters"
    default_severity = Severity.WARNING
    category = "evals"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))

        if "goldens" not in str(file_path):
            return []

        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            return []

        if not data:
            return []

        has_common_params = data.get("common_session_parameters") is not None

        has_tool_calls = False
        for conv in data.get("conversations", []):
            for turn in conv.get("turns", []):
                if isinstance(turn, dict) and turn.get("tool_calls"):
                    has_tool_calls = True
                    break

        if has_tool_calls and not has_common_params:
            return [self.make_result(
                file=rel,
                message="Golden eval has tool_calls but no common_session_parameters",
                fix="Add session parameters for reliable tool responses",
            )]
        return []


class E007_GoldenAgentFieldNotString(Rule):
    id = "E007"
    name = "eval-agent-not-string"
    description = "Golden agent response must be a plain string, not a dict"
    default_severity = Severity.ERROR
    category = "evals"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        if "goldens" not in str(file_path):
            return []
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            return []
        if not data:
            return []

        results = []
        rel = str(file_path.relative_to(context.project_root))
        for conv in data.get("conversations", []):
            conv_name = conv.get("conversation", "")
            for i, turn in enumerate(conv.get("turns", [])):
                if not isinstance(turn, dict):
                    continue
                agent_val = turn.get("agent")
                if agent_val is not None and not isinstance(agent_val, str):
                    results.append(self.make_result(
                        file=rel, line=None,
                        message=f"Conv '{conv_name}' turn {i+1}: 'agent' field is a {type(agent_val).__name__}, must be a plain string. $matchType is only valid inside tool_calls.args",
                        fix="Replace the dict with a plain string containing the expected agent response text",
                    ))
        return results


class E008_GoldenMissingAgentField(Rule):
    id = "E008"
    name = "eval-missing-agent"
    description = "Golden turn missing 'agent' field — causes automatic FAIL from unexpected response"
    default_severity = Severity.WARNING
    category = "evals"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        if "goldens" not in str(file_path):
            return []
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            return []
        if not data:
            return []

        results = []
        rel = str(file_path.relative_to(context.project_root))
        for conv in data.get("conversations", []):
            conv_name = conv.get("conversation", "")
            for i, turn in enumerate(conv.get("turns", [])):
                if not isinstance(turn, dict):
                    continue
                if "user" in turn and "agent" not in turn:
                    results.append(self.make_result(
                        file=rel,
                        message=f"Conv '{conv_name}' turn {i+1}: has 'user' but no 'agent' field — any agent response will be flagged as UNEXPECTED RESPONSE causing automatic FAIL",
                        fix="Add an 'agent' field with the expected response text",
                    ))
        return results


class E009_SimMissingTags(Rule):
    id = "E009"
    name = "eval-sim-missing-tags"
    description = "Simulation eval missing 'tags' field — won't match --priority filters"
    default_severity = Severity.WARNING
    category = "evals"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        if "simulations" not in str(file_path):
            return []
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            return []
        if not data:
            return []

        results = []
        rel = str(file_path.relative_to(context.project_root))
        evals_list = data.get("evals", []) if isinstance(data, dict) else data if isinstance(data, list) else []
        for ev in evals_list:
            if not isinstance(ev, dict):
                continue
            name = ev.get("name", "")
            if "tags" not in ev:
                results.append(self.make_result(
                    file=rel,
                    message=f"Sim '{name}' has no 'tags' field — won't be found by --priority P0/P1/P2 filters",
                    fix=f'Add: tags: ["P0", "category"]',
                ))
        return results


class E010_ToolTestWrongKey(Rule):
    id = "E010"
    name = "eval-tool-test-wrong-key"
    description = "Tool test YAML uses 'test_cases' instead of 'tests' — SCRAPI silently returns 0 tests"
    default_severity = Severity.ERROR
    category = "evals"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        if "tool_tests" not in str(file_path):
            return []
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            return []
        if not data or not isinstance(data, dict):
            return []

        results = []
        rel = str(file_path.relative_to(context.project_root))
        if "test_cases" in data and "tests" not in data:
            results.append(self.make_result(
                file=rel,
                message="Uses 'test_cases' key but SCRAPI expects 'tests' — all tests will be silently skipped",
                fix="Rename 'test_cases:' to 'tests:'",
            ))
        # Also check for old format with top-level tool_name
        if "tool_name" in data and "tests" not in data:
            results.append(self.make_result(
                file=rel,
                message="Uses top-level 'tool_name' (old format) — SCRAPI expects 'tool' on each test case inside 'tests'",
                fix="Restructure: move tool_name into each test case as 'tool:', rename 'test_cases:' to 'tests:'",
            ))
        return results


class E011_InvalidMatchType(Rule):
    id = "E011"
    name = "eval-invalid-match-type"
    description = "Invalid $matchType value in golden tool_calls args"
    default_severity = Severity.ERROR
    category = "evals"

    VALID_MATCH_TYPES = {"ignore", "semantic", "contains", "regexp"}
    COMMON_TYPOS = {
        "regex": "regexp",
        "exact": None,  # exact is the default (no $matchType needed)
        "fuzzy": "semantic",
    }

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        if "goldens" not in str(file_path):
            return []
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            return []
        if not data:
            return []

        results = []
        rel = str(file_path.relative_to(context.project_root))
        for conv in data.get("conversations", []):
            conv_name = conv.get("conversation", "")
            for i, turn in enumerate(conv.get("turns", [])):
                if not isinstance(turn, dict):
                    continue
                for tc in turn.get("tool_calls", []):
                    args = tc.get("args", {})
                    if not isinstance(args, dict):
                        continue
                    for arg_name, arg_val in args.items():
                        if not isinstance(arg_val, dict):
                            continue
                        match_type = arg_val.get("$matchType")
                        if match_type is None:
                            continue
                        if match_type not in self.VALID_MATCH_TYPES:
                            suggestion = self.COMMON_TYPOS.get(match_type)
                            fix = f'Did you mean "{suggestion}"?' if suggestion else f"Valid values: {', '.join(sorted(self.VALID_MATCH_TYPES))}"
                            results.append(self.make_result(
                                file=rel,
                                message=f"Conv '{conv_name}' turn {i+1}: arg '{arg_name}' has invalid $matchType '{match_type}'",
                                fix=fix,
                            ))
        return results


ALL_RULES = [
    E001_InvalidYaml(),
    E002_MissingConversations(),
    E003_InvalidToolCall(),
    E004_UndeclaredSessionParam(),
    E005_DuplicateYamlKeys(),
    E006_GoldenWithoutMocks(),
    E007_GoldenAgentFieldNotString(),
    E008_GoldenMissingAgentField(),
    E009_SimMissingTags(),
    E010_ToolTestWrongKey(),
    E011_InvalidMatchType(),
]
