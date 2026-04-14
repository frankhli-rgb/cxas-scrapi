"""Tool lint rules (T001–T009).

Validates agent tool Python files against GECX conventions.
"""

import re
from pathlib import Path

from . import LintContext, LintResult, Rule, Severity


class T001_MissingAgentAction(Rule):
    id = "T001"
    name = "tool-error-pattern"
    description = "Tool must return agent_action on error for deterministic recovery"
    default_severity = Severity.ERROR
    category = "tools"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        if not str(file_path).endswith(".py"):
            return []
        rel = str(file_path.relative_to(context.project_root))
        if "agent_action" not in content:
            return [self.make_result(
                file=rel,
                message="Missing agent_action error return pattern",
                fix='Add: return {"agent_action": "error message for agent to relay"}',
            )]
        return []


class T002_MissingDocstring(Rule):
    id = "T002"
    name = "tool-docstring"
    description = "Tool missing docstring — CES uses this as tool description"
    default_severity = Severity.ERROR
    category = "tools"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        if not str(file_path).endswith(".py"):
            return []
        rel = str(file_path.relative_to(context.project_root))
        if '"""' not in content and "'''" not in content:
            return [self.make_result(
                file=rel,
                message="Missing docstring — the LLM uses tool docstrings to decide when and how to call the tool",
                fix="Add a descriptive docstring explaining when and how the LLM should use this tool",
            )]
        return []


class T003_MissingTypeHints(Rule):
    id = "T003"
    name = "tool-type-hints"
    description = "Tool function arguments lack type hints"
    default_severity = Severity.INFO
    category = "tools"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        if not str(file_path).endswith(".py"):
            return []
        rel = str(file_path.relative_to(context.project_root))
        fn_match = re.search(r'def\s+\w+\s*\(([^)]*)\)', content)
        if fn_match:
            args_str = fn_match.group(1)
            if args_str.strip() and ":" not in args_str:
                return [self.make_result(
                    file=rel, line=1,
                    message="Function arguments lack type hints",
                    fix="Add type hints: def tool_name(arg: str, count: int) -> dict:",
                )]
        return []


class T004_FunctionNameMismatch(Rule):
    id = "T004"
    name = "tool-fn-name"
    description = "Tool function name should match tool directory name"
    default_severity = Severity.WARNING
    category = "tools"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        if not str(file_path).endswith(".py"):
            return []
        rel = str(file_path.relative_to(context.project_root))
        # Tool dir name is two levels up: tools/<name>/python_function/python_code.py
        tool_dir_name = file_path.parent.parent.name

        fn_match = re.search(r'def\s+(\w+)\s*\(', content)
        if fn_match:
            actual_fn = fn_match.group(1)
            if actual_fn != tool_dir_name:
                return [self.make_result(
                    file=rel, line=1,
                    message=f"Function named '{actual_fn}', expected '{tool_dir_name}' (matching directory)",
                    fix=f"Rename to: def {tool_dir_name}(...):",
                )]
        else:
            return [self.make_result(
                file=rel, line=1,
                message="No function definition found in tool file",
            )]
        return []


class T005_HighCardinalityArgs(Rule):
    id = "T005"
    name = "tool-high-cardinality"
    description = "High-cardinality input arguments reduce deterministic tool selection"
    default_severity = Severity.INFO
    category = "tools"

    HIGH_CARDINALITY_PATTERNS = [
        (r'timestamp', "timestamp — hard for voice users to express"),
        (r'latitude|longitude|coordinates', "coordinates — high cardinality"),
        (r'session_id|request_id|trace_id', "internal ID — not voice-expressible"),
    ]

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        if not str(file_path).endswith(".py"):
            return []
        rel = str(file_path.relative_to(context.project_root))
        results = []

        fn_match = re.search(r'def\s+\w+\s*\(([^)]*)\)', content)
        if fn_match:
            args_str = fn_match.group(1)
            for pattern, label in self.HIGH_CARDINALITY_PATTERNS:
                if re.search(pattern, args_str, re.IGNORECASE):
                    results.append(self.make_result(
                        file=rel,
                        message=f"High-cardinality argument: {label}",
                        fix="Design args that a human can express in voice mode (e.g., region, category, last_n_days)",
                    ))
        return results


class T006_ExcessiveReturnData(Rule):
    id = "T006"
    name = "tool-return-explosion"
    description = "Tool returning excessive data bloats LLM context"
    default_severity = Severity.INFO
    category = "tools"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        if not str(file_path).endswith(".py"):
            return []
        rel = str(file_path.relative_to(context.project_root))
        results = []

        # Heuristic: returning raw API responses without filtering
        if re.search(r'return\s+response\.json\(\)', content):
            results.append(self.make_result(
                file=rel,
                message="Returning raw API response — may include data the LLM doesn't need",
                fix="Filter the response to only include fields the LLM needs for decision-making",
            ))
        if re.search(r'return\s+json\.loads\(', content):
            results.append(self.make_result(
                file=rel,
                message="Returning parsed JSON directly — consider filtering to relevant fields only",
                fix="Only return data that the LLM needs to see",
            ))
        return results


class T007_ToolNameNotSnakeCase(Rule):
    id = "T007"
    name = "tool-name-snake-case"
    description = "Tool JSON name/displayName must be snake_case (no spaces or mixed case)"
    default_severity = Severity.ERROR
    category = "tools"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        if not str(file_path).endswith(".py"):
            return []
        # Navigate from python_code.py to the tool JSON
        # tools/<name>/python_function/python_code.py → tools/<name>/<name>.json
        tool_dir = file_path.parent.parent
        tool_name = tool_dir.name
        json_path = tool_dir / f"{tool_name}.json"
        if not json_path.exists():
            return []

        import json as json_mod
        try:
            tool_config = json_mod.loads(json_path.read_text())
        except (json_mod.JSONDecodeError, OSError):
            return []

        results = []
        rel = str(json_path.relative_to(context.project_root))
        for field in ("name", "displayName"):
            value = tool_config.get(field, "")
            if value and (" " in value or value != value.lower()):
                results.append(self.make_result(
                    file=rel,
                    message=f"Tool {field} '{value}' is not snake_case — agent JSON references tools by displayName and must match exactly",
                    fix=f'Change to: "{field}": "{re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")}"',
                ))
        return results


class T008_ToolDisplayNameMismatch(Rule):
    id = "T008"
    name = "tool-displayname-unreferenced"
    description = "Tool displayName not referenced by any agent's tools array"
    default_severity = Severity.WARNING
    category = "tools"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        if not str(file_path).endswith(".py"):
            return []
        tool_dir = file_path.parent.parent
        tool_name = tool_dir.name
        json_path = tool_dir / f"{tool_name}.json"
        if not json_path.exists():
            return []

        import json as json_mod
        try:
            tool_config = json_mod.loads(json_path.read_text())
        except (json_mod.JSONDecodeError, OSError):
            return []

        display_name = tool_config.get("displayName", "")
        if not display_name:
            return []

        # Check if any agent config references this displayName
        agents_dir = file_path.parent.parent.parent.parent / "agents"
        if not agents_dir.exists():
            return []

        referenced = False
        for agent_dir in agents_dir.iterdir():
            if not agent_dir.is_dir():
                continue
            agent_json = agent_dir / f"{agent_dir.name}.json"
            if not agent_json.exists():
                continue
            try:
                agent_config = json_mod.loads(agent_json.read_text())
                if display_name in agent_config.get("tools", []):
                    referenced = True
                    break
            except (json_mod.JSONDecodeError, OSError):
                continue

        if not referenced:
            rel = str(json_path.relative_to(context.project_root))
            return [self.make_result(
                file=rel,
                message=f"Tool displayName '{display_name}' not found in any agent's tools array",
                fix="Add this tool to the relevant agent's JSON config, or remove the tool if unused",
            )]
        return []


class T009_KwargsInSignature(Rule):
    id = "T009"
    name = "tool-kwargs-signature"
    description = "Tool function uses **kwargs — GECX requires explicit named parameters"
    default_severity = Severity.ERROR
    category = "tools"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        if not str(file_path).endswith(".py"):
            return []
        rel = str(file_path.relative_to(context.project_root))
        fn_match = re.search(r'def\s+\w+\s*\(([^)]*)\)', content)
        if fn_match:
            args_str = fn_match.group(1)
            if "**" in args_str:
                line = content[:fn_match.start()].count("\n") + 1
                return [self.make_result(
                    file=rel, line=line,
                    message="Tool function uses **kwargs — GECX requires explicit named parameters to generate the tool schema. Tools with **kwargs are silently dropped during import",
                    fix="Replace **kwargs with explicit parameters: def my_tool(param1: str = '', param2: str = '') -> dict:",
                )]
        return []


class T010_InvalidPythonSyntax(Rule):
    id = "T010"
    name = "tool-python-syntax"
    description = "Tool Python file must have valid syntax"
    default_severity = Severity.ERROR
    category = "tools"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        if not str(file_path).endswith(".py"):
            return []
        rel = str(file_path.relative_to(context.project_root))
        try:
            compile(content, rel, "exec")
        except SyntaxError as e:
            return [self.make_result(
                file=rel, line=e.lineno,
                message=f"Invalid Python syntax: {e.msg}",
                fix="Fix the syntax error before pushing — invalid Python causes tools to be silently dropped during import",
            )]
        return []


class T011_NoneDefaultValue(Rule):
    id = "T011"
    name = "tool-none-default"
    description = "Tool function parameter uses None as default — platform requires type-matching defaults"
    default_severity = Severity.ERROR
    category = "tools"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        if not str(file_path).endswith(".py"):
            return []
        rel = str(file_path.relative_to(context.project_root))
        fn_match = re.search(r'def\s+\w+\s*\(([^)]*)\)', content, re.DOTALL)
        if not fn_match:
            return []

        args_str = fn_match.group(1)
        results = []
        for param in args_str.split(","):
            param = param.strip()
            if "=" in param and re.search(r'=\s*None\s*$', param):
                param_name = param.split(":")[0].strip()
                line = content[:fn_match.start()].count("\n") + 1
                results.append(self.make_result(
                    file=rel, line=line,
                    message=f"Parameter '{param_name}' uses None as default — the platform silently drops tools with None defaults during import. Use a type-matching default instead (e.g., str = \"\", int = 0)",
                    fix=f"Change '{param_name}: str = None' to '{param_name}: str = \"\"'",
                ))
        return results


ALL_RULES = [
    T001_MissingAgentAction(),
    T002_MissingDocstring(),
    T003_MissingTypeHints(),
    T004_FunctionNameMismatch(),
    T005_HighCardinalityArgs(),
    T006_ExcessiveReturnData(),
    T007_ToolNameNotSnakeCase(),
    T008_ToolDisplayNameMismatch(),
    T009_KwargsInSignature(),
    T010_InvalidPythonSyntax(),
    T011_NoneDefaultValue(),
]
