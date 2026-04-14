"""Callback lint rules (C001–C009).

Validates agent callback Python files against GECX conventions.
"""

import re
from pathlib import Path

from . import LintContext, LintResult, Rule, Severity


CALLBACK_SIGNATURES = {
    "before_model_callbacks": ("before_model_callback", ["callback_context", "llm_request"]),
    "after_model_callbacks": ("after_model_callback", ["callback_context", "llm_response"]),
    "before_agent_callbacks": ("before_agent_callback", ["callback_context"]),
    "after_agent_callbacks": ("after_agent_callback", ["callback_context"]),
    "before_tool_callbacks": ("before_tool_callback", ["tool", "input", "callback_context"]),
    "after_tool_callbacks": ("after_tool_callback", ["tool", "input", "callback_context", "tool_response"]),
}


def _find_entry_function(content: str, expected_fn: str) -> re.Match | None:
    """Find the entry callback function, not helper functions.

    Callbacks can have helper functions defined before the entry function.
    The entry function is the one whose name matches the expected callback
    signature (e.g., before_model_callback). If not found by name, fall back
    to the first function.
    """
    # First, look for the function with the expected name
    entry = re.search(rf'def\s+({re.escape(expected_fn)})\s*\(', content)
    if entry:
        return entry
    # Fall back: no function with expected name found — return None
    # (C001 will report the missing entry function)
    return None


class C001_WrongFunctionName(Rule):
    id = "C001"
    name = "callback-fn-name"
    description = "Callback function name must match callback type"
    default_severity = Severity.ERROR
    category = "callbacks"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        cb_type = file_path.parent.parent.name
        expected_fn, _ = CALLBACK_SIGNATURES.get(cb_type, (None, None))
        if not expected_fn:
            return []

        # Check if any function definition exists at all
        all_fns = re.findall(r'def\s+(\w+)\s*\(', content)
        if not all_fns:
            return [self.make_result(
                file=rel, line=1,
                message="No function definition found in callback file",
                fix=f"Define: def {expected_fn}(...):",
            )]

        # Check if the expected entry function exists (helper functions are fine)
        if expected_fn not in all_fns:
            return [self.make_result(
                file=rel, line=1,
                message=f"No '{expected_fn}' function found (found: {', '.join(all_fns)})",
                fix=f"Add entry function: def {expected_fn}(...)",
            )]
        return []


class C002_WrongArgCount(Rule):
    id = "C002"
    name = "callback-args"
    description = "Callback must have correct argument count for its type"
    default_severity = Severity.ERROR
    category = "callbacks"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        cb_type = file_path.parent.parent.name
        expected_fn, expected_args = CALLBACK_SIGNATURES.get(cb_type, (None, None))
        if not expected_args:
            return []

        # Find the entry function specifically, not helper functions
        entry = _find_entry_function(content, expected_fn)
        if not entry:
            return []  # C001 handles missing entry function

        # Get the full signature of the entry function
        # Search from the entry function's position
        args_match = re.search(r'def\s+' + re.escape(expected_fn) + r'\s*\(([^)]*)\)', content)
        if not args_match:
            return []

        args = [a.strip().split(":")[0].strip()
                for a in args_match.group(1).split(",") if a.strip()]
        if len(args) != len(expected_args):
            return [self.make_result(
                file=rel, line=1,
                message=f"Expected {len(expected_args)} args ({', '.join(expected_args)}), got {len(args)} ({', '.join(args)})",
                fix=f"Use signature: def {expected_fn}({', '.join(expected_args)}):",
            )]
        return []


class C003_CamelCaseFunction(Rule):
    id = "C003"
    name = "callback-camelcase"
    description = "CES requires snake_case function names, not camelCase"
    default_severity = Severity.ERROR
    category = "callbacks"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        results = []
        camel_fns = re.findall(r'def\s+((?:[a-z]+[A-Z])\w*)\s*\(', content)
        for fn in camel_fns:
            results.append(self.make_result(
                file=rel,
                message=f"camelCase function '{fn}' — CES requires snake_case",
                fix="Rename to snake_case",
            ))
        return results


class C004_ReturnsDictNotLlmResponse(Rule):
    id = "C004"
    name = "callback-return-type"
    description = "Model callbacks should return LlmResponse, not dict"
    default_severity = Severity.WARNING
    category = "callbacks"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        cb_type = file_path.parent.parent.name

        if cb_type not in ("before_model_callbacks", "after_model_callbacks"):
            return []

        if "return {" in content and "LlmResponse" not in content:
            return [self.make_result(
                file=rel,
                message="Callback returns a dict — should return LlmResponse or None",
                fix="Use: return LlmResponse.from_parts(parts=[Part.from_text(text='...')])",
            )]
        return []


class C005_HardcodedPhraseList(Rule):
    id = "C005"
    name = "callback-hardcoded-phrases"
    description = "Hardcoded phrase lists for intent detection — keep detection in instructions"
    default_severity = Severity.WARNING
    category = "callbacks"

    # Patterns that suggest hardcoded phrase matching for detection
    PATTERNS = [
        r'\[.*"[^"]+",\s*"[^"]+",\s*"[^"]+".*\]',  # ["word", "word", "word"]
        r'if\s+.*\bin\s+\[',                         # if x in [...]
        r'any\(\s*\w+\s+in\s+',                      # any(word in ...)
    ]

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        results = []
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            for pattern in self.PATTERNS:
                if re.search(pattern, line):
                    # Check if it looks like intent/phrase detection vs config
                    lower = line.lower()
                    if any(kw in lower for kw in ["detect", "intent", "phrase", "keyword",
                                                   "profan", "escalat", "frustrat"]):
                        results.append(self.make_result(
                            file=rel, line=i,
                            message="Hardcoded phrase list for intent detection — misses natural variations",
                            fix="Keep detection in instructions (LLM understands intent). Use callbacks for execution only.",
                        ))
                        break
        return results


class C006_BareExcept(Rule):
    id = "C006"
    name = "callback-bare-except"
    description = "Bare except without logging swallows errors silently"
    default_severity = Severity.WARNING
    category = "callbacks"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        results = []
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped == "except:" or re.match(r'except\s*:', stripped):
                results.append(self.make_result(
                    file=rel, line=i,
                    message="Bare 'except:' — catches all errors silently. Platform tool errors bypass try/except.",
                    fix="Use 'except Exception as e:' with logging, or catch specific exceptions",
                ))
        return results


class C007_ToolNamingConvention(Rule):
    id = "C007"
    name = "callback-tool-naming"
    description = "Verify tools.* call uses correct naming convention"
    default_severity = Severity.INFO
    category = "callbacks"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        results = []
        tool_calls = re.findall(r'tools\.(\w+)\s*\(', content)
        for tool_name in tool_calls:
            if tool_name not in context.all_known_tools:
                results.append(self.make_result(
                    file=rel,
                    message=f"tools.{tool_name}() — verify naming: Python tools use function name, API connectors use DisplayName_OperationId",
                    fix="Check the exact tool name from the platform. Platform errors from wrong names bypass try/except.",
                ))
        return results


class C008_MissingTypingImport(Rule):
    id = "C008"
    name = "callback-missing-typing-import"
    description = "Callback uses typing types (Optional, Iterator, etc.) without importing them"
    default_severity = Severity.ERROR
    category = "callbacks"

    # Types that need explicit import from typing
    TYPING_TYPES = {"Optional", "Iterator", "List", "Dict", "Tuple", "Set", "Union", "Any"}

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        if not str(file_path).endswith(".py"):
            return []

        results = []
        rel = str(file_path.relative_to(context.project_root))

        # Check if code uses typing types
        has_typing_import = "from typing import" in content or "import typing" in content
        if has_typing_import:
            return []

        # Check for usage of typing types in annotations and code
        used_types = []
        for type_name in self.TYPING_TYPES:
            # Match usage in type annotations (-> Optional[X], : Optional[X])
            # and standalone usage, but not inside strings/comments
            patterns = [
                rf'-> {type_name}\[',      # return type annotation
                rf'-> {type_name}\b',       # return type without brackets
                rf': {type_name}\[',        # parameter annotation
                rf': {type_name}\b',        # parameter annotation without brackets
            ]
            for pattern in patterns:
                if re.search(pattern, content):
                    used_types.append(type_name)
                    break

        if used_types:
            types_str = ", ".join(sorted(set(used_types)))
            results.append(self.make_result(
                file=rel,
                message=f"Uses {types_str} without importing from typing — will fail with 'name not defined' at push time",
                fix=f"Add: from typing import {types_str}",
            ))

        return results


EXPECTED_SIGNATURES = {
    "before_model_callbacks": {
        "fn": "before_model_callback",
        "params": {"callback_context": "CallbackContext", "llm_request": "LlmRequest"},
        "return": "Optional[LlmResponse]",
    },
    "after_model_callbacks": {
        "fn": "after_model_callback",
        "params": {"callback_context": "CallbackContext", "llm_response": "LlmResponse"},
        "return": "Optional[LlmResponse]",
    },
    "before_agent_callbacks": {
        "fn": "before_agent_callback",
        "params": {"callback_context": "CallbackContext"},
        "return": "Optional[Content]",
    },
    "after_agent_callbacks": {
        "fn": "after_agent_callback",
        "params": {"callback_context": "CallbackContext"},
        "return": "Optional[Content]",
    },
    "before_tool_callbacks": {
        "fn": "before_tool_callback",
        "params": {"tool": "Tool", "input": "dict[str, Any]", "callback_context": "CallbackContext"},
        "return": "Optional[dict[str, Any]]",
    },
    "after_tool_callbacks": {
        "fn": "after_tool_callback",
        "params": {"tool": "Tool", "input": "dict[str, Any]", "callback_context": "CallbackContext", "tool_response": "dict[str, Any]"},
        "return": "Optional[dict[str, Any]]",
    },
}


class C009_WrongCallbackSignature(Rule):
    id = "C009"
    name = "callback-signature"
    description = "Callback function must have correct type annotations"
    default_severity = Severity.ERROR
    category = "callbacks"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        cb_type = file_path.parent.parent.name
        expected = EXPECTED_SIGNATURES.get(cb_type)
        if not expected:
            return []

        fn_name = expected["fn"]
        # Find the entry function signature (may span multiple lines)
        pattern = rf'def\s+{re.escape(fn_name)}\s*\(([^)]*)\)(\s*->\s*[^:]+)?:'
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            return []  # C001 handles missing function

        args_str = match.group(1)
        return_str = match.group(2)

        results = []

        # Check parameter type annotations
        params = [p.strip() for p in args_str.split(",") if p.strip()]
        for param in params:
            parts = param.split(":")
            param_name = parts[0].strip()
            if len(parts) < 2:
                expected_type = expected["params"].get(param_name)
                if expected_type:
                    results.append(self.make_result(
                        file=rel,
                        message=f"Parameter '{param_name}' missing type annotation, expected '{param_name}: {expected_type}'",
                        fix=f"def {fn_name}({', '.join(f'{k}: {v}' for k, v in expected['params'].items())}) -> {expected['return']}:",
                    ))
            else:
                param_type = parts[1].strip()
                expected_type = expected["params"].get(param_name)
                if expected_type and param_type != expected_type:
                    results.append(self.make_result(
                        file=rel,
                        message=f"Parameter '{param_name}' has type '{param_type}', expected '{expected_type}'",
                        fix=f"def {fn_name}({', '.join(f'{k}: {v}' for k, v in expected['params'].items())}) -> {expected['return']}:",
                    ))

        # Check return type annotation
        if not return_str:
            results.append(self.make_result(
                file=rel,
                message=f"Missing return type annotation, expected '-> {expected['return']}'",
                fix=f"def {fn_name}({', '.join(f'{k}: {v}' for k, v in expected['params'].items())}) -> {expected['return']}:",
            ))
        else:
            actual_return = return_str.strip().lstrip("->").strip()
            if actual_return != expected["return"]:
                results.append(self.make_result(
                    file=rel,
                    message=f"Return type is '{actual_return}', expected '{expected['return']}'",
                    fix=f"def {fn_name}({', '.join(f'{k}: {v}' for k, v in expected['params'].items())}) -> {expected['return']}:",
                ))

        return results


class C010_InvalidPythonSyntax(Rule):
    id = "C010"
    name = "callback-python-syntax"
    description = "Callback Python file must have valid syntax"
    default_severity = Severity.ERROR
    category = "callbacks"

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
                fix="Fix the syntax error before pushing — invalid Python causes callbacks to silently fail on the platform",
            )]
        return []


ALL_RULES = [
    C001_WrongFunctionName(),
    C002_WrongArgCount(),
    C003_CamelCaseFunction(),
    C004_ReturnsDictNotLlmResponse(),
    C005_HardcodedPhraseList(),
    C006_BareExcept(),
    C007_ToolNamingConvention(),
    C008_MissingTypingImport(),
    C009_WrongCallbackSignature(),
    C010_InvalidPythonSyntax(),
]
