"""Instruction lint rules (I001–I013).

Validates agent instruction files against GECX design guide best practices.
"""

import re
from pathlib import Path

from . import LintContext, LintResult, Rule, Severity


class I001_RequiredXmlStructure(Rule):
    id = "I001"
    name = "required-xml-structure"
    description = "Instruction must contain <role>, <persona>, and <taskflow> tags"
    default_severity = Severity.ERROR
    category = "instructions"

    REQUIRED_TAGS = ["<role>", "<persona>", "<taskflow>"]

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        results = []
        for tag in self.REQUIRED_TAGS:
            if tag not in content:
                results.append(self.make_result(
                    file=rel,
                    message=f"Missing required XML tag: {tag}",
                    fix=f"Add {tag}...{tag.replace('<', '</')} section to instruction",
                ))
        return results


class I002_TaskflowChildren(Rule):
    id = "I002"
    name = "taskflow-children"
    description = "Taskflow must contain <subtask> or <step> children"
    default_severity = Severity.ERROR
    category = "instructions"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        if "<taskflow>" not in content:
            return []
        match = re.search(r"<taskflow>(.*?)</taskflow>", content, re.DOTALL)
        if not match:
            return []
        taskflow = match.group(1)
        if "<subtask" not in taskflow and "<step" not in taskflow:
            return [self.make_result(
                file=rel,
                message="<taskflow> has no <subtask> or <step> children",
                fix="Add <subtask name=\"...\"><step>...</step></subtask> inside <taskflow>",
            )]
        return []


class I003_ExcessiveIfElse(Rule):
    id = "I003"
    name = "excessive-if-else"
    description = "Excessive IF/ELSE logic in instructions (should be in callbacks)"
    default_severity = Severity.WARNING
    category = "instructions"

    # Patterns that suggest programmatic branching
    PATTERNS = [
        (r'(?:^|\n)\s*(?:\d+\.\s*)?(?:\*\*)?IF\b.*?\bELSE\b', "IF...ELSE block"),
        (r'(?:^|\n)\s*(?:\d+\.\s*)?(?:\*\*)?IF\b.*?\bELSE IF\b', "IF...ELSE IF chain"),
        (r'(?:^|\n)\s*(?:\d+\.\s*)?(?:\*\*)?IF\b.*?\bTHEN\b.*?\bELSE\b', "IF...THEN...ELSE"),
    ]

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        results = []
        lines = content.split("\n")

        # Count IF/ELSE occurrences
        if_else_count = 0
        for i, line in enumerate(lines, 1):
            upper = line.upper().strip()
            if re.match(r'.*\bIF\b.*\bELSE\b', upper):
                if_else_count += 1

        if if_else_count >= 3:
            results.append(self.make_result(
                file=rel,
                message=f"Found {if_else_count} IF/ELSE blocks — excessive programmatic logic degrades LLM reliability",
                fix="Move deterministic branching to callbacks. Use simple natural language: 'On the FIRST attempt... On the SECOND...'",
            ))
        return results


class I004_NegativeTriggers(Rule):
    id = "I004"
    name = "negative-triggers"
    description = "Negative conditions in triggers confuse the LLM"
    default_severity = Severity.WARNING
    category = "instructions"

    NEGATIVE_PATTERNS = [
        (r'<trigger>.*\bNOT\b.*</trigger>', "NOT in trigger"),
        (r'<trigger>.*\bis NOT\b.*</trigger>', "is NOT in trigger"),
        (r'<trigger>.*\bnot\s+(?:a|an|the)\b.*</trigger>', "negation in trigger"),
    ]

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        results = []
        for pattern, label in self.NEGATIVE_PATTERNS:
            for m in re.finditer(pattern, content, re.IGNORECASE):
                # Find line number
                pos = m.start()
                line_num = content[:pos].count("\n") + 1
                results.append(self.make_result(
                    file=rel, line=line_num,
                    message=f"Negative condition in trigger: {label}",
                    fix="Use positive triggers only. Put the excluded case as a separate, earlier step.",
                ))
        return results


class I005_ConditionalLogicBlock(Rule):
    id = "I005"
    name = "conditional-logic-block"
    description = "conditional_logic blocks for intent classification confuse the LLM"
    default_severity = Severity.WARNING
    category = "instructions"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        results = []
        for m in re.finditer(r'<conditional_logic>', content):
            pos = m.start()
            line_num = content[:pos].count("\n") + 1
            results.append(self.make_result(
                file=rel, line=line_num,
                message="<conditional_logic> block — LLM gets confused by priority-ordered conditionals",
                fix="Use separate <step> elements with distinct triggers instead",
            ))
        return results


class I006_HardcodedData(Rule):
    id = "I006"
    name = "hardcoded-data"
    description = "Hardcoded data (phone numbers, prices) should come from tools"
    default_severity = Severity.WARNING
    category = "instructions"

    DEFAULT_PATTERNS = [
        (r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', "phone number"),
        (r'\$\d+(?:\.\d{2})?', "price/dollar amount"),
    ]

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        results = []

        # Use custom patterns from config if available, else defaults
        options = context.options.get("I006", {})
        patterns = options.get("patterns", None)
        if patterns:
            check_patterns = [(p, "hardcoded data") for p in patterns]
        else:
            check_patterns = self.DEFAULT_PATTERNS

        lines = content.split("\n")
        for pattern, label in check_patterns:
            for i, line in enumerate(lines, 1):
                # Skip lines that are in variable references or examples
                if "{" in line and "}" in line:
                    continue
                if "<inline_example" in line or "</inline_example" in line:
                    continue
                for m in re.finditer(pattern, line):
                    results.append(self.make_result(
                        file=rel, line=i,
                        message=f"Possible hardcoded {label}: '{m.group()}'",
                        fix="Data should come from tool responses, not hardcoded in instructions",
                    ))
        return results


class I007_InstructionTooLong(Rule):
    id = "I007"
    name = "instruction-too-long"
    description = "Instruction exceeds word count threshold — consider splitting into sub-agents"
    default_severity = Severity.INFO
    category = "instructions"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        options = context.options.get("I007", {})
        max_words = options.get("max_words", 3000)

        word_count = len(content.split())
        if word_count > max_words:
            return [self.make_result(
                file=rel,
                message=f"Instruction is {word_count} words (threshold: {max_words})",
                fix="Consider splitting into sub-agents to reduce context size",
                severity=self.default_severity,
            )]
        return []


class I008_InvalidAgentRef(Rule):
    id = "I008"
    name = "invalid-agent-ref"
    description = "Agent reference points to non-existent agent"
    default_severity = Severity.ERROR
    category = "instructions"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        results = []
        refs = re.findall(r'\{@AGENT:\s*([^}]+)\}', content)
        # Deduplicate — report each unique ref only once per file
        seen = set()
        for ref in refs:
            ref_clean = ref.strip()
            if ref_clean in seen:
                continue
            seen.add(ref_clean)
            # Match against both directory names AND display names
            if (ref_clean not in context.all_agent_names and
                    ref_clean not in context.all_agent_display_names):
                results.append(self.make_result(
                    file=rel,
                    message=f"{{@AGENT: {ref_clean}}} references non-existent agent",
                    fix=f"Available agents: {', '.join(sorted(context.all_agent_names | context.all_agent_display_names))}",
                ))
        return results


class I009_InvalidToolRef(Rule):
    id = "I009"
    name = "invalid-tool-ref"
    description = "Tool reference points to tool not in agent's config"
    default_severity = Severity.ERROR
    category = "instructions"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        results = []
        refs = re.findall(r'\{@TOOL:\s*([^}]+)\}', content)
        for ref in refs:
            ref_clean = ref.strip()
            if ref_clean not in context.all_known_tools:
                results.append(self.make_result(
                    file=rel,
                    message=f"{{@TOOL: {ref_clean}}} references non-existent tool",
                    fix=f"Available tools: {', '.join(sorted(context.all_known_tools))}",
                ))
        return results


class I010_WrongAgentSyntax(Rule):
    id = "I010"
    name = "wrong-agent-syntax"
    description = "Wrong agent reference syntax (must use {@AGENT: Name})"
    default_severity = Severity.ERROR
    category = "instructions"

    WRONG_PATTERNS = [
        (r'\$\{AGENT:([^}]+)\}', '${AGENT:...}'),
        (r'(?<!\{)\{AGENT:([^}]+)\}', '{AGENT:...}'),
        (r'\$\{@AGENT:([^}]+)\}', '${@AGENT:...}'),
    ]

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        results = []
        lines = content.split("\n")
        for pattern, label in self.WRONG_PATTERNS:
            for i, line in enumerate(lines, 1):
                for m in re.finditer(pattern, line):
                    results.append(self.make_result(
                        file=rel, line=i,
                        message=f"Wrong agent reference syntax: {label} found: {m.group(0)}",
                        fix="Use {@AGENT: Display Name} (with @ sign, spaces in name)",
                    ))
        return results


class I011_WrongToolSyntax(Rule):
    id = "I011"
    name = "wrong-tool-syntax"
    description = "Wrong tool reference syntax (must use {@TOOL: Name})"
    default_severity = Severity.ERROR
    category = "instructions"

    WRONG_PATTERNS = [
        (r'\$\{TOOL:([^}]+)\}', '${TOOL:...}'),
        (r'(?<!\{)\{TOOL:([^}]+)\}', '{TOOL:...}'),
        (r'\$\{@TOOL:([^}]+)\}', '${@TOOL:...}'),
    ]

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        results = []
        lines = content.split("\n")
        for pattern, label in self.WRONG_PATTERNS:
            for i, line in enumerate(lines, 1):
                for m in re.finditer(pattern, line):
                    results.append(self.make_result(
                        file=rel, line=i,
                        message=f"Wrong tool reference syntax: {label} found: {m.group(0)}",
                        fix="Use {@TOOL: Tool Name}",
                    ))
        return results


class I012_UnusedToolInConfig(Rule):
    id = "I012"
    name = "unused-tool-in-config"
    description = "Tool in agent JSON but not referenced in instruction"
    default_severity = Severity.WARNING
    category = "instructions"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        results = []

        # Read agent JSON config
        agent_dir = file_path.parent
        agent_json = agent_dir / f"{agent_dir.name}.json"
        if not agent_json.exists():
            return []

        import json
        with open(agent_json) as f:
            config = json.load(f)

        config_tools = set(config.get("tools", []))
        instruction_refs = set(ref.strip() for ref in re.findall(r'\{@TOOL:\s*([^}]+)\}', content))

        for tool in config_tools:
            if tool not in instruction_refs and tool != "end_session":
                results.append(self.make_result(
                    file=str(agent_json.relative_to(context.project_root)),
                    message=f"Agent config lists tool '{tool}' but instruction never references it",
                    fix=f"Add {{@TOOL: {tool}}} in instruction, or remove from agent config if not needed",
                ))
        return results


class I013_ToolNotInConfig(Rule):
    id = "I013"
    name = "tool-not-in-config"
    description = "Tool referenced in instruction but not in agent JSON"
    default_severity = Severity.ERROR
    category = "instructions"

    def check(self, file_path: Path, content: str, context: LintContext) -> list[LintResult]:
        rel = str(file_path.relative_to(context.project_root))
        results = []

        agent_dir = file_path.parent
        agent_json = agent_dir / f"{agent_dir.name}.json"
        if not agent_json.exists():
            return []

        import json
        with open(agent_json) as f:
            config = json.load(f)

        config_tools = set(config.get("tools", []))
        instruction_refs = set(ref.strip() for ref in re.findall(r'\{@TOOL:\s*([^}]+)\}', content))

        for ref in instruction_refs:
            if ref not in config_tools:
                results.append(self.make_result(
                    file=rel,
                    message=f"Instruction references {{@TOOL: {ref}}} but agent config does not list it",
                    fix=f"Only reference tools assigned to this agent. Add '{ref}' to tools array, or remove the reference.",
                ))
        return results


ALL_RULES = [
    I001_RequiredXmlStructure(),
    I002_TaskflowChildren(),
    I003_ExcessiveIfElse(),
    I004_NegativeTriggers(),
    I005_ConditionalLogicBlock(),
    I006_HardcodedData(),
    I007_InstructionTooLong(),
    I008_InvalidAgentRef(),
    I009_InvalidToolRef(),
    I010_WrongAgentSyntax(),
    I011_WrongToolSyntax(),
    I012_UnusedToolInConfig(),
    I013_ToolNotInConfig(),
]
