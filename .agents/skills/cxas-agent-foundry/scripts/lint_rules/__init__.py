"""GECX Agent Linter — Rule framework, registry, discovery, and config.

Inspired by eslint/ruff: rules are first-class objects with IDs, configurable
severity, and per-file overrides. Configuration lives in gecxlint.yaml.
"""

import fnmatch
import json
import re
import yaml
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


# ── Severity ─────────────────────────────────────────────────────────────

class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    OFF = "off"

    @classmethod
    def from_str(cls, s: str) -> "Severity":
        return cls(s.lower())


# ── Lint Result ──────────────────────────────────────────────────────────

@dataclass
class LintResult:
    file: str
    rule_id: str
    severity: Severity
    message: str
    line: Optional[int] = None
    fix_suggestion: str = ""

    def __str__(self):
        prefix = {"error": "E", "warning": "W", "info": "I"}[self.severity.value]
        loc = self.file
        if self.line:
            loc += f":{self.line}"
        return f"  [{prefix}] {loc} [{self.rule_id}] {self.message}"

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "severity": self.severity.value,
            "rule_id": self.rule_id,
            "message": self.message,
            "fix_suggestion": self.fix_suggestion,
        }


# ── Lint Report ──────────────────────────────────────────────────────────

@dataclass
class LintReport:
    results: list = field(default_factory=list)

    @property
    def errors(self):
        return [r for r in self.results if r.severity == Severity.ERROR]

    @property
    def warnings(self):
        return [r for r in self.results if r.severity == Severity.WARNING]

    def add(self, result: LintResult):
        self.results.append(result)

    def add_all(self, results: list):
        self.results.extend(results)

    def print_summary(self, show_fixes=False):
        if not self.results:
            print("\n  All checks passed.")
            return

        for r in sorted(self.results, key=lambda x: (x.severity.value, x.file)):
            print(str(r))
            if show_fixes and r.fix_suggestion:
                print(f"         Fix: {r.fix_suggestion}")

        info_count = len(self.results) - len(self.errors) - len(self.warnings)
        print(f"\n  {len(self.errors)} error(s), {len(self.warnings)} warning(s), "
              f"{info_count} info")

    def to_json(self) -> str:
        return json.dumps([r.to_dict() for r in self.results], indent=2)


# ── Rule Base Class ──────────────────────────────────────────────────────

class Rule(ABC):
    """Base class for all lint rules.

    Each rule has:
    - id: unique identifier (e.g., "I001")
    - name: human-readable name
    - description: what the rule checks
    - default_severity: severity when not overridden by config
    - category: which file type this rule applies to
    """
    id: str = ""
    name: str = ""
    description: str = ""
    default_severity: Severity = Severity.WARNING
    category: str = ""  # instructions, callbacks, tools, evals, config

    @abstractmethod
    def check(self, file_path: Path, content: str, context: "LintContext") -> list[LintResult]:
        """Run this rule against a file. Returns list of LintResults."""
        ...

    def make_result(self, file: str, message: str, severity: Optional[Severity] = None,
                    line: Optional[int] = None, fix: str = "") -> LintResult:
        return LintResult(
            file=file,
            rule_id=self.id,
            severity=severity or self.default_severity,
            message=message,
            line=line,
            fix_suggestion=fix,
        )


# ── Lint Context ─────────────────────────────────────────────────────────

@dataclass
class LintContext:
    """Shared context passed to rules for cross-referencing."""
    project_root: Path
    app_dir: Path
    evals_dir: Path
    all_agent_names: set = field(default_factory=set)       # directory names
    all_agent_display_names: set = field(default_factory=set)
    all_tool_names: set = field(default_factory=set)        # directory names
    all_tool_dirs: dict = field(default_factory=dict)       # name -> Path
    platform_tools: set = field(default_factory=lambda: {"end_session", "customize_response"})
    options: dict = field(default_factory=dict)              # rule-specific options

    @property
    def all_known_tools(self) -> set:
        return self.all_tool_names | self.platform_tools


# ── Rule Registry ────────────────────────────────────────────────────────

class RuleRegistry:
    """Holds all registered rules and applies config overrides."""

    def __init__(self):
        self._rules: dict[str, Rule] = {}

    def register(self, rule: Rule):
        self._rules[rule.id] = rule

    def register_all(self, rules: list[Rule]):
        for r in rules:
            self.register(r)

    def get(self, rule_id: str) -> Optional[Rule]:
        return self._rules.get(rule_id)

    def all_rules(self) -> list[Rule]:
        return sorted(self._rules.values(), key=lambda r: r.id)

    def rules_for_category(self, category: str) -> list[Rule]:
        return [r for r in self.all_rules() if r.category == category]

    def list_rules(self):
        """Print all registered rules."""
        current_cat = ""
        for r in self.all_rules():
            if r.category != current_cat:
                current_cat = r.category
                print(f"\n  {current_cat.upper()}")
            sev = r.default_severity.value.upper()
            print(f"    {r.id}  [{sev:7s}]  {r.name}: {r.description}")


# ── Configuration ────────────────────────────────────────────────────────

@dataclass
class LintConfig:
    """Linter configuration loaded from gecxlint.yaml."""
    app_dir: str = "cxas_app/"
    evals_dir: str = "evals/"
    rules: dict[str, Severity] = field(default_factory=dict)
    options: dict[str, dict] = field(default_factory=dict)
    ignore: list[str] = field(default_factory=list)
    per_file: dict[str, dict[str, str]] = field(default_factory=dict)

    @classmethod
    def load(cls, project_root: Path) -> "LintConfig":
        config = cls()

        # Load gecxlint.yaml if it exists
        lint_config_path = project_root / "gecxlint.yaml"
        if lint_config_path.exists():
            with open(lint_config_path) as f:
                data = yaml.safe_load(f) or {}

            config.app_dir = data.get("app_dir", config.app_dir)
            config.evals_dir = data.get("evals_dir", config.evals_dir)

            for rule_id, severity_str in (data.get("rules") or {}).items():
                config.rules[rule_id] = Severity.from_str(severity_str)

            config.options = data.get("options") or {}
            config.ignore = data.get("ignore") or []
            config.per_file = data.get("per_file") or {}

        # Fall back to gecx-config.json for app_dir
        gecx_config_path = project_root / "gecx-config.json"
        if gecx_config_path.exists() and config.app_dir == "cxas_app/":
            with open(gecx_config_path) as f:
                gecx = json.load(f)
            config.app_dir = gecx.get("app_dir", config.app_dir)

        return config

    def get_severity(self, rule: Rule, file_path: str = "") -> Severity:
        """Get the effective severity for a rule, considering per-file overrides."""
        # Check per-file overrides first
        for pattern, overrides in self.per_file.items():
            if fnmatch.fnmatch(file_path, pattern):
                if rule.id in overrides:
                    return Severity.from_str(overrides[rule.id])

        # Then global rule config
        if rule.id in self.rules:
            return self.rules[rule.id]

        # Fall back to rule default
        return rule.default_severity

    def is_ignored(self, file_path: str) -> bool:
        """Check if a file matches any ignore pattern."""
        return any(fnmatch.fnmatch(file_path, p) for p in self.ignore)

    def get_options(self, rule_id: str) -> dict:
        """Get rule-specific options."""
        return self.options.get(rule_id, {})


# ── Discovery ────────────────────────────────────────────────────────────

class Discovery:
    """Discovers agents, tools, callbacks, evals, and configs in the app directory."""

    def __init__(self, app_dir: Path, evals_dir: Path):
        self.app_dir = app_dir
        self.evals_dir = evals_dir
        # Find the actual app subdirectory (e.g., cxas_app/humana-app-test/)
        self.app_root = self._find_app_root()

    def _find_app_root(self) -> Optional[Path]:
        if not self.app_dir.exists():
            return None
        for d in self.app_dir.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                return d
        return None

    def discover_agents(self) -> dict[str, Path]:
        """Return {dir_name: instruction_path} for all agents.

        An agent is any subdirectory under agents/ that has either an
        instruction.txt or a JSON config file. Agents without instruction.txt
        (e.g., config-only or placeholder agents) are still valid agent
        references for {@AGENT:} validation.
        """
        if not self.app_root:
            return {}
        agents_dir = self.app_root / "agents"
        if not agents_dir.exists():
            return {}
        result = {}
        for d in sorted(agents_dir.iterdir()):
            if d.is_dir():
                inst = d / "instruction.txt"
                if inst.exists():
                    result[d.name] = inst
                else:
                    # Agent exists but has no instruction — still a valid agent
                    # for cross-referencing. Use the directory itself as placeholder.
                    json_file = d / f"{d.name}.json"
                    if json_file.exists():
                        result[d.name] = json_file
        return result

    def discover_tools(self) -> dict[str, Path]:
        """Return {tool_name: code_path} for all tools."""
        if not self.app_root:
            return {}
        tools_dir = self.app_root / "tools"
        if not tools_dir.exists():
            return {}
        result = {}
        for d in sorted(tools_dir.iterdir()):
            if d.is_dir():
                code = d / "python_function" / "python_code.py"
                if code.exists():
                    result[d.name] = code
                else:
                    json_files = list(d.glob("*.json"))
                    if json_files:
                        result[d.name] = json_files[0]
        return result

    def discover_callbacks(self) -> list[tuple[str, str, str, Path]]:
        """Return [(agent_name, cb_type, cb_name, code_path), ...]."""
        if not self.app_root:
            return []
        agents_dir = self.app_root / "agents"
        if not agents_dir.exists():
            return []
        result = []
        cb_types = [
            "before_model_callbacks", "after_model_callbacks",
            "before_agent_callbacks", "after_agent_callbacks",
        ]
        for agent_dir in sorted(agents_dir.iterdir()):
            if not agent_dir.is_dir():
                continue
            for cb_type in cb_types:
                cb_dir = agent_dir / cb_type
                if not cb_dir.exists():
                    continue
                for cb in sorted(cb_dir.iterdir()):
                    code = cb / "python_code.py"
                    if code.exists():
                        result.append((agent_dir.name, cb_type, cb.name, code))
        return result

    def discover_evals(self) -> dict[str, Path]:
        """Return {filename: path} for all eval YAMLs."""
        result = {}
        if not self.evals_dir.exists():
            return result
        for yaml_path in sorted(self.evals_dir.rglob("*.yaml")):
            rel = str(yaml_path.relative_to(self.evals_dir))
            result[rel] = yaml_path
        return result

    def discover_app_config(self) -> Optional[Path]:
        """Return path to app.json."""
        if not self.app_root:
            return None
        app_json = self.app_root / "app.json"
        return app_json if app_json.exists() else None

    def discover_agent_configs(self) -> dict[str, Path]:
        """Return {agent_name: json_path} for all agent configs."""
        if not self.app_root:
            return {}
        agents_dir = self.app_root / "agents"
        if not agents_dir.exists():
            return {}
        result = {}
        for d in sorted(agents_dir.iterdir()):
            if d.is_dir():
                json_file = d / f"{d.name}.json"
                if json_file.exists():
                    result[d.name] = json_file
        return result

    def dir_name_to_display(self, dir_name: str) -> str:
        """Convert directory name to display name."""
        return dir_name.replace("_", " ")
