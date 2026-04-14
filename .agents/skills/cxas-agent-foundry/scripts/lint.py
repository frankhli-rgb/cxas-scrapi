#!/usr/bin/env python3
"""GECX Agent Linter — validates agent code before pushing to CXAS.

Tier 1 (deterministic): XML structure, callback signatures, tool patterns,
eval YAML, config consistency, and GECX design guide anti-patterns.
Tier 2 (LLM, --deep): Gemini-powered analysis of instruction quality,
progressive disclosure, voice naturalness, and routing completeness.

Configuration: gecxlint.yaml (rules, severity overrides, per-file ignores)

Usage:
    python .agents/skills/cxas-agent-foundry/scripts/lint.py                      # Tier 1 only
    python .agents/skills/cxas-agent-foundry/scripts/lint.py --deep               # Tier 1 + Tier 2 (Gemini)
    python .agents/skills/cxas-agent-foundry/scripts/lint.py --fix                # Show fix suggestions
    python .agents/skills/cxas-agent-foundry/scripts/lint.py --only instructions  # Single category
    python .agents/skills/cxas-agent-foundry/scripts/lint.py --only callbacks
    python .agents/skills/cxas-agent-foundry/scripts/lint.py --only tools
    python .agents/skills/cxas-agent-foundry/scripts/lint.py --only evals
    python .agents/skills/cxas-agent-foundry/scripts/lint.py --only config
    python .agents/skills/cxas-agent-foundry/scripts/lint.py --only structure
    python .agents/skills/cxas-agent-foundry/scripts/lint.py --json               # JSON output (for hooks)
    python .agents/skills/cxas-agent-foundry/scripts/lint.py --list-rules         # List all rules
    python .agents/skills/cxas-agent-foundry/scripts/lint.py --rule I003,C005     # Run specific rules only
"""

import argparse
import json
import sys
from pathlib import Path

from lint_rules import (
    Discovery,
    LintConfig,
    LintContext,
    LintReport,
    RuleRegistry,
    Severity,
)
from lint_rules.instructions import ALL_RULES as INSTRUCTION_RULES
from lint_rules.callbacks import ALL_RULES as CALLBACK_RULES
from lint_rules.tools import ALL_RULES as TOOL_RULES
from lint_rules.evals import ALL_RULES as EVAL_RULES
from lint_rules.config import ALL_RULES as CONFIG_RULES
from lint_rules.structure import ALL_RULES as STRUCTURE_RULES


def _resolve_project_root() -> Path:
    """Resolve the active project directory using the same logic as config.py.

    Search order:
    1. GECX_PROJECT env var
    2. CWD contains gecx-config.json
    3. .active-project pointer at workspace root
    4. Single project auto-detect
    5. Fallback: script's grandparent (legacy behavior)
    """
    import os

    def _find_workspace():
        path = os.getcwd()
        for _ in range(10):
            if (os.path.isdir(os.path.join(path, ".agents"))
                    or os.path.isdir(os.path.join(path, ".claude"))
                    or os.path.isdir(os.path.join(path, ".gemini"))):
                return path
            parent = os.path.dirname(path)
            if parent == path:
                break
            path = parent
        return os.getcwd()

    workspace = _find_workspace()

    # 1. Env var
    env_project = os.environ.get("GECX_PROJECT")
    if env_project:
        candidate = os.path.join(workspace, env_project)
        if os.path.exists(os.path.join(candidate, "gecx-config.json")):
            return Path(candidate)

    # 2. CWD has gecx-config.json
    if os.path.exists(os.path.join(os.getcwd(), "gecx-config.json")):
        return Path(os.getcwd())

    # 3. .active-project pointer
    pointer = os.path.join(workspace, ".active-project")
    if os.path.exists(pointer):
        with open(pointer) as f:
            name = f.read().strip()
        if name:
            candidate = os.path.join(workspace, name)
            if os.path.exists(os.path.join(candidate, "gecx-config.json")):
                return Path(candidate)

    # 4. Single project auto-detect
    projects = []
    for entry in os.listdir(workspace):
        full = os.path.join(workspace, entry)
        if os.path.isdir(full) and not entry.startswith(".") and os.path.exists(os.path.join(full, "gecx-config.json")):
            projects.append(full)
    if len(projects) == 1:
        return Path(projects[0])

    # 5. Fallback: legacy behavior
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _resolve_project_root()


def build_registry() -> RuleRegistry:
    registry = RuleRegistry()
    registry.register_all(INSTRUCTION_RULES)
    registry.register_all(CALLBACK_RULES)
    registry.register_all(TOOL_RULES)
    registry.register_all(EVAL_RULES)
    registry.register_all(CONFIG_RULES)
    registry.register_all(STRUCTURE_RULES)
    return registry


def build_context(config: LintConfig, discovery: Discovery) -> LintContext:
    agents = discovery.discover_agents()
    tools = discovery.discover_tools()

    context = LintContext(
        project_root=PROJECT_ROOT,
        app_dir=PROJECT_ROOT / config.app_dir,
        evals_dir=PROJECT_ROOT / config.evals_dir,
        all_agent_names=set(agents.keys()),
        all_agent_display_names={
            discovery.dir_name_to_display(name) for name in agents
        },
        all_tool_names=set(tools.keys()),
        all_tool_dirs={name: path.parent for name, path in tools.items()},
        options=config.options,
    )
    return context


def run_rules(registry: RuleRegistry, config: LintConfig, context: LintContext,
              discovery: Discovery, report: LintReport,
              only: str = None, specific_rules: set = None):
    """Run lint rules against discovered files."""

    def should_run(rule):
        if specific_rules and rule.id not in specific_rules:
            return False
        if only and rule.category != only:
            return False
        return True

    def get_severity(rule, file_rel):
        sev = config.get_severity(rule, file_rel)
        return sev if sev != Severity.OFF else None

    # Instructions — only lint instruction.txt files, not JSON configs
    if not only or only == "instructions":
        agents = discovery.discover_agents()
        rules = [r for r in registry.rules_for_category("instructions") if should_run(r)]
        for agent_name, inst_path in agents.items():
            if inst_path.name != "instruction.txt":
                continue  # Skip JSON-only agents for instruction linting
            rel = str(inst_path.relative_to(PROJECT_ROOT))
            if config.is_ignored(rel):
                continue
            content = inst_path.read_text()
            for rule in rules:
                sev = get_severity(rule, rel)
                if sev is None:
                    continue
                for result in rule.check(inst_path, content, context):
                    result.severity = sev
                    report.add(result)

    # Callbacks
    if not only or only == "callbacks":
        callbacks = discovery.discover_callbacks()
        rules = [r for r in registry.rules_for_category("callbacks") if should_run(r)]
        for agent_name, cb_type, cb_name, code_path in callbacks:
            rel = str(code_path.relative_to(PROJECT_ROOT))
            if config.is_ignored(rel):
                continue
            content = code_path.read_text()
            for rule in rules:
                sev = get_severity(rule, rel)
                if sev is None:
                    continue
                for result in rule.check(code_path, content, context):
                    result.severity = sev
                    report.add(result)

    # Tools
    if not only or only == "tools":
        tools = discovery.discover_tools()
        rules = [r for r in registry.rules_for_category("tools") if should_run(r)]
        for tool_name, code_path in tools.items():
            rel = str(code_path.relative_to(PROJECT_ROOT))
            if config.is_ignored(rel):
                continue
            content = code_path.read_text()
            for rule in rules:
                sev = get_severity(rule, rel)
                if sev is None:
                    continue
                for result in rule.check(code_path, content, context):
                    result.severity = sev
                    report.add(result)

    # Evals
    if not only or only == "evals":
        evals = discovery.discover_evals()
        rules = [r for r in registry.rules_for_category("evals") if should_run(r)]
        for eval_name, eval_path in evals.items():
            rel = str(eval_path.relative_to(PROJECT_ROOT))
            if config.is_ignored(rel):
                continue
            content = eval_path.read_text()
            for rule in rules:
                sev = get_severity(rule, rel)
                if sev is None:
                    continue
                for result in rule.check(eval_path, content, context):
                    result.severity = sev
                    report.add(result)

    # Config
    if not only or only == "config":
        rules = [r for r in registry.rules_for_category("config") if should_run(r)]

        # App config
        app_config = discovery.discover_app_config()
        if app_config:
            rel = str(app_config.relative_to(PROJECT_ROOT))
            if not config.is_ignored(rel):
                content = app_config.read_text()
                for rule in rules:
                    sev = get_severity(rule, rel)
                    if sev is None:
                        continue
                    for result in rule.check(app_config, content, context):
                        result.severity = sev
                        report.add(result)

        # Agent configs
        agent_configs = discovery.discover_agent_configs()
        for agent_name, json_path in agent_configs.items():
            rel = str(json_path.relative_to(PROJECT_ROOT))
            if config.is_ignored(rel):
                continue
            content = json_path.read_text()
            for rule in rules:
                sev = get_severity(rule, rel)
                if sev is None:
                    continue
                for result in rule.check(json_path, content, context):
                    result.severity = sev
                    report.add(result)

    # Structure — app-wide structural validation and cross-references
    if not only or only == "structure":
        rules = [r for r in registry.rules_for_category("structure") if should_run(r)]

        # S001: validate whole app via Validator
        app_config = discovery.discover_app_config()
        if app_config:
            rel = str(app_config.relative_to(PROJECT_ROOT))
            content = app_config.read_text()
            for rule in rules:
                if rule.id == "S001":
                    sev = get_severity(rule, rel)
                    if sev:
                        for result in rule.check(app_config, content, context):
                            result.severity = sev
                            report.add(result)

        # S002: check instruction tool references against agent tool list
        agents = discovery.discover_agents()
        for agent_name, inst_path in agents.items():
            if inst_path.name != "instruction.txt":
                continue
            rel = str(inst_path.relative_to(PROJECT_ROOT))
            content = inst_path.read_text()
            for rule in rules:
                if rule.id == "S002":
                    sev = get_severity(rule, rel)
                    if sev:
                        for result in rule.check(inst_path, content, context):
                            result.severity = sev
                            report.add(result)

        # S003, S004: check agent JSON cross-references
        agent_configs = discovery.discover_agent_configs()
        for agent_name, json_path in agent_configs.items():
            rel = str(json_path.relative_to(PROJECT_ROOT))
            content = json_path.read_text()
            for rule in rules:
                if rule.id in ("S003", "S004"):
                    sev = get_severity(rule, rel)
                    if sev:
                        for result in rule.check(json_path, content, context):
                            result.severity = sev
                            report.add(result)


def main():
    parser = argparse.ArgumentParser(description="GECX Agent Linter")
    parser.add_argument("--deep", action="store_true",
                        help="Enable Tier 2 LLM linting (Gemini)")
    parser.add_argument("--fix", action="store_true",
                        help="Show fix suggestions")
    parser.add_argument("--only",
                        choices=["instructions", "callbacks", "tools", "evals", "config", "structure"],
                        help="Only run a specific linter category")
    parser.add_argument("--rule", type=str,
                        help="Run specific rules only (comma-separated IDs, e.g. I003,C005)")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    parser.add_argument("--list-rules", action="store_true",
                        help="List all available rules")
    parser.add_argument("--project-dir", type=str,
                        help="Override project directory (default: auto-resolved)")
    args = parser.parse_args()

    # Build registry
    registry = build_registry()

    if args.list_rules:
        print("GECX Agent Linter — Available Rules")
        print("=" * 60)
        registry.list_rules()
        sys.exit(0)

    # Resolve project root — CLI override takes precedence
    global PROJECT_ROOT
    if args.project_dir:
        PROJECT_ROOT = Path(args.project_dir).resolve()

    # Load config
    config = LintConfig.load(PROJECT_ROOT)

    # Discovery
    app_dir = PROJECT_ROOT / config.app_dir
    evals_dir = PROJECT_ROOT / config.evals_dir
    discovery = Discovery(app_dir, evals_dir)

    if not discovery.app_root:
        if not args.json:
            print(f"ERROR: No app directory found under {config.app_dir}")
            print("Pull the app first with: cxas pull ...")
        else:
            print(json.dumps([{
                "file": config.app_dir,
                "severity": "error",
                "rule_id": "SETUP",
                "message": f"No app directory found under {config.app_dir}",
            }]))
        sys.exit(1)

    # Build context
    context = build_context(config, discovery)

    if not args.json:
        print(f"Linting app: {discovery.app_root.name}")
        print("=" * 60)
        agents = discovery.discover_agents()
        tools = discovery.discover_tools()
        callbacks = discovery.discover_callbacks()
        evals = discovery.discover_evals()
        print(f"  Agents: {len(agents)}")
        print(f"  Tools: {len(tools)}")
        print(f"  Callbacks: {len(callbacks)}")
        print(f"  Evals: {len(evals)}")

    # Parse specific rules
    specific_rules = None
    if args.rule:
        specific_rules = set(r.strip() for r in args.rule.split(","))

    # Run Tier 1
    report = LintReport()
    run_rules(registry, config, context, discovery, report,
              only=args.only, specific_rules=specific_rules)

    # Run Tier 2 (LLM)
    if args.deep and (not args.only or args.only == "instructions"):
        if not args.json:
            print(f"\n--- Tier 2: LLM Analysis ---")
        from lint_rules.llm import lint_with_gemini
        agents = discovery.discover_agents()
        lint_with_gemini(agents, PROJECT_ROOT, report)

    # Report
    if args.json:
        print(report.to_json())
    else:
        print("\n" + "=" * 60)
        print("LINT RESULTS")
        print("=" * 60)
        report.print_summary(show_fixes=args.fix)

        if report.errors:
            print(f"\nLint FAILED with {len(report.errors)} error(s).")
            sys.exit(1)
        else:
            print("\nLint PASSED (no errors).")
            sys.exit(0)


if __name__ == "__main__":
    main()
