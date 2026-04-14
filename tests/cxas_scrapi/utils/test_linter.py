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

"""Tests for the linter framework, configuration, discovery, and runner."""

import json
import pytest

from cxas_scrapi.utils.linter import (
    Discovery,
    LintConfig,
    LintReport,
    LintResult,
    Rule,
    RuleRegistry,
    Severity,
    build_context,
    build_registry,
    reset_registry,
    run_rules,
    rule,
)


# ── Severity ─────────────────────────────────────────────────────────────

def test_severity_from_str():
    assert Severity.from_str("error") == Severity.ERROR
    assert Severity.from_str("WARNING") == Severity.WARNING
    assert Severity.from_str("Info") == Severity.INFO
    assert Severity.from_str("off") == Severity.OFF


def test_severity_from_str_invalid():
    with pytest.raises(ValueError):
        Severity.from_str("invalid")


# ── LintResult ───────────────────────────────────────────────────────────

def test_lint_result_str_format():
    result = LintResult(
        file="agents/root/instruction.txt",
        rule_id="I001",
        severity=Severity.ERROR,
        message="Missing required XML tag: <role>",
    )
    output = str(result)
    assert "[E]" in output
    assert "I001" in output
    assert "Missing required XML tag" in output


def test_lint_result_str_with_line():
    result = LintResult(
        file="agents/root/instruction.txt",
        rule_id="I004",
        severity=Severity.WARNING,
        message="Negative trigger",
        line=42,
    )
    output = str(result)
    assert "[W]" in output
    assert ":42" in output


def test_lint_result_to_dict():
    result = LintResult(
        file="app.json",
        rule_id="A001",
        severity=Severity.ERROR,
        message="Invalid JSON",
        line=5,
        fix_suggestion="Fix the JSON syntax",
    )
    d = result.to_dict()
    assert d["file"] == "app.json"
    assert d["rule_id"] == "A001"
    assert d["severity"] == "error"
    assert d["line"] == 5
    assert d["fix_suggestion"] == "Fix the JSON syntax"


# ── LintReport ───────────────────────────────────────────────────────────

def test_lint_report_add_and_counts():
    report = LintReport()
    report.add(LintResult("a.txt", "I001", Severity.ERROR, "err"))
    report.add(LintResult("b.txt", "I002", Severity.WARNING, "warn"))
    report.add(LintResult("c.txt", "I003", Severity.INFO, "info"))

    assert len(report.errors) == 1
    assert len(report.warnings) == 1
    assert len(report.results) == 3


def test_lint_report_to_json():
    report = LintReport()
    report.add(LintResult("a.txt", "I001", Severity.ERROR, "err"))

    parsed = json.loads(report.to_json())
    assert len(parsed) == 1
    assert parsed[0]["rule_id"] == "I001"
    assert parsed[0]["severity"] == "error"


def test_lint_report_empty(capsys):
    report = LintReport()
    report.print_summary()
    captured = capsys.readouterr()
    assert "All checks passed" in captured.out


# ── RuleRegistry ─────────────────────────────────────────────────────────

def test_rule_registry_lookup():
    registry = RuleRegistry()

    class DummyRule(Rule):
        id = "X001"
        name = "dummy"
        category = "test"
        default_severity = Severity.WARNING

        def check(self, file_path, content, context):
            return []

    r = DummyRule()
    registry.register(r)

    assert registry.get("X001") is r
    assert registry.get("X999") is None
    assert len(registry.rules_for_category("test")) == 1
    assert len(registry.rules_for_category("nonexistent")) == 0


def test_rule_decorator_deduplication():
    """@rule with the same ID twice should not create duplicate entries."""
    from cxas_scrapi.utils.linter import _RULE_REGISTRY

    # Record the initial count so the test is additive-safe
    initial_count = sum(len(v) for v in _RULE_REGISTRY.values())

    @rule("test_dedup")
    class DedupRule(Rule):
        id = "XDUP001"
        name = "dedup-test"
        description = "test"
        default_severity = Severity.INFO
        def check(self, fp, content, ctx):
            return []

    after_first = sum(len(v) for v in _RULE_REGISTRY.values())
    assert after_first == initial_count + 1

    # Applying @rule again with the same class/id should be a no-op
    @rule("test_dedup")
    class DedupRule2(Rule):
        id = "XDUP001"
        name = "dedup-test"
        description = "test"
        default_severity = Severity.INFO
        def check(self, fp, content, ctx):
            return []

    after_second = sum(len(v) for v in _RULE_REGISTRY.values())
    assert after_second == after_first, "Duplicate rule ID was registered twice"


def test_reset_registry():
    """reset_registry() clears all registered rules."""
    from cxas_scrapi.utils.linter import _RULE_REGISTRY, _REGISTERED_IDS

    # Ensure there are rules registered
    registry = build_registry()
    assert len(registry.all_rules()) >= 55

    # Reset
    reset_registry()
    assert len(_RULE_REGISTRY) == 0
    assert len(_REGISTERED_IDS) == 0

    # build_registry re-imports, but since modules are already imported
    # the @rule decorators won't re-fire — registry stays empty
    registry_after = RuleRegistry()
    for _cat, rules in _RULE_REGISTRY.items():
        registry_after.register_all(rules)
    assert len(registry_after.all_rules()) == 0

    # Re-populate for other tests by forcing re-registration
    # (reload the rule modules so decorators fire again)
    import importlib
    import cxas_scrapi.utils.lint_rules.instructions as mod_i
    import cxas_scrapi.utils.lint_rules.callbacks as mod_c
    import cxas_scrapi.utils.lint_rules.tools as mod_t
    import cxas_scrapi.utils.lint_rules.evals as mod_e
    import cxas_scrapi.utils.lint_rules.config as mod_a
    import cxas_scrapi.utils.lint_rules.structure as mod_s
    import cxas_scrapi.utils.lint_rules.schema as mod_v
    for mod in [mod_i, mod_c, mod_t, mod_e, mod_a, mod_s, mod_v]:
        importlib.reload(mod)

    registry_restored = build_registry()
    assert len(registry_restored.all_rules()) == 55


# ── LintConfig ───────────────────────────────────────────────────────────

def test_lint_config_load_defaults(tmp_path):
    config = LintConfig.load(tmp_path)
    assert config.app_dir == "."
    assert config.evals_dir == "evals/"
    assert config.rules == {}
    assert config.ignore == []


def test_lint_config_load_from_yaml(tmp_path):
    (tmp_path / "cxaslint.yaml").write_text(
        "app_dir: my_app/\n"
        "evals_dir: my_evals/\n"
        "rules:\n"
        "  I001: off\n"
        "  I003: error\n"
        "ignore:\n"
        "  - '**/__pycache__/**'\n"
    )
    config = LintConfig.load(tmp_path)
    assert config.app_dir == "my_app/"
    assert config.evals_dir == "my_evals/"
    assert config.rules["I001"] == Severity.OFF
    assert config.rules["I003"] == Severity.ERROR
    assert "**/__pycache__/**" in config.ignore


def test_lint_config_severity_override():
    config = LintConfig()
    config.rules["I001"] = Severity.OFF

    class DummyRule(Rule):
        id = "I001"
        default_severity = Severity.ERROR

        def check(self, file_path, content, context):
            return []

    r = DummyRule()
    assert config.get_severity(r) == Severity.OFF


def test_lint_config_per_file_override():
    config = LintConfig()
    config.per_file = {"**/root_agent/**": {"I007": "off"}}

    class DummyRule(Rule):
        id = "I007"
        default_severity = Severity.INFO

        def check(self, file_path, content, context):
            return []

    r = DummyRule()
    assert config.get_severity(r, "app/agents/root_agent/instruction.txt") == Severity.OFF
    assert config.get_severity(r, "app/agents/billing/instruction.txt") == Severity.INFO


def test_lint_config_is_ignored():
    config = LintConfig()
    config.ignore = ["**/__pycache__/**", "**/test_*.py"]

    assert config.is_ignored("app/__pycache__/foo.pyc") is True
    assert config.is_ignored("tests/test_something.py") is True
    assert config.is_ignored("app/agents/root/instruction.txt") is False


# ── Discovery ────────────────────────────────────────────────────────────

def _make_app(tmp_path, agents=None, tools=None):
    """Helper to create a minimal app directory structure."""
    (tmp_path / "app.json").write_text('{"name": "test", "displayName": "Test"}')
    (tmp_path / "agents").mkdir()
    for name in (agents or []):
        agent_dir = tmp_path / "agents" / name
        agent_dir.mkdir()
        (agent_dir / "instruction.txt").write_text("<role>test</role>")
        (agent_dir / f"{name}.json").write_text(f'{{"displayName": "{name}"}}')
    if tools:
        (tmp_path / "tools").mkdir()
        for name in tools:
            tool_dir = tmp_path / "tools" / name / "python_function"
            tool_dir.mkdir(parents=True)
            (tool_dir / "python_code.py").write_text(f'def {name}(): pass')


def test_discovery_direct_app_root(tmp_path):
    _make_app(tmp_path, agents=["root_agent"])
    evals_dir = tmp_path / "evals"
    evals_dir.mkdir()

    discovery = Discovery(tmp_path, evals_dir)
    assert discovery.app_root == tmp_path


def test_discovery_nested_app_root(tmp_path):
    nested = tmp_path / "my_app"
    nested.mkdir()
    _make_app(nested, agents=["root_agent"])
    evals_dir = tmp_path / "evals"
    evals_dir.mkdir()

    discovery = Discovery(tmp_path, evals_dir)
    assert discovery.app_root == nested


def test_discovery_agents(tmp_path):
    _make_app(tmp_path, agents=["root_agent", "billing_agent"])
    discovery = Discovery(tmp_path, tmp_path / "evals")

    agents = discovery.discover_agents()
    assert "root_agent" in agents
    assert "billing_agent" in agents
    assert agents["root_agent"].name == "instruction.txt"


def test_discovery_tools(tmp_path):
    _make_app(tmp_path, tools=["get_balance", "transfer_funds"])
    discovery = Discovery(tmp_path, tmp_path / "evals")

    tools = discovery.discover_tools()
    assert "get_balance" in tools
    assert "transfer_funds" in tools


def test_discovery_callbacks(tmp_path):
    _make_app(tmp_path, agents=["root_agent"])
    cb_dir = tmp_path / "agents" / "root_agent" / "before_model_callbacks" / "greet_01"
    cb_dir.mkdir(parents=True)
    (cb_dir / "python_code.py").write_text("def before_model_callback(ctx, req): pass")

    discovery = Discovery(tmp_path, tmp_path / "evals")
    callbacks = discovery.discover_callbacks()
    assert len(callbacks) == 1
    assert callbacks[0][0] == "root_agent"
    assert callbacks[0][1] == "before_model_callbacks"


def test_discovery_no_app(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    discovery = Discovery(empty, tmp_path / "evals")
    assert discovery.app_root is None
    assert discovery.discover_agents() == {}


def test_discovery_app_config(tmp_path):
    _make_app(tmp_path)
    discovery = Discovery(tmp_path, tmp_path / "evals")
    assert discovery.discover_app_config().name == "app.json"


def test_discovery_agent_configs(tmp_path):
    _make_app(tmp_path, agents=["root_agent"])
    discovery = Discovery(tmp_path, tmp_path / "evals")
    configs = discovery.discover_agent_configs()
    assert "root_agent" in configs


# ── Runner ───────────────────────────────────────────────────────────────

def test_build_registry_all_rules():
    registry = build_registry()
    all_rules = registry.all_rules()
    assert len(all_rules) == 55


def test_build_context(tmp_path):
    _make_app(tmp_path, agents=["root_agent"], tools=["get_info"])
    config = LintConfig()
    discovery = Discovery(tmp_path, tmp_path / "evals")

    context = build_context(tmp_path, config, discovery)
    assert "root_agent" in context.all_agent_names
    assert "get_info" in context.all_tool_names
    assert "end_session" in context.platform_tools


def test_run_rules_categories_filter(tmp_path):
    _make_app(tmp_path, agents=["root_agent"])
    config = LintConfig()
    discovery = Discovery(tmp_path, tmp_path / "evals")
    context = build_context(tmp_path, config, discovery)
    registry = build_registry()

    # Run only config rules
    report = LintReport()
    run_rules(registry, config, context, discovery, report,
              categories=["config"])

    # Should only have config rule results (A-prefixed)
    for r in report.results:
        assert r.rule_id.startswith("A"), f"Expected A-rule, got {r.rule_id}"


def test_run_rules_specific_rules_filter(tmp_path):
    _make_app(tmp_path, agents=["root_agent"])
    config = LintConfig()
    discovery = Discovery(tmp_path, tmp_path / "evals")
    context = build_context(tmp_path, config, discovery)
    registry = build_registry()

    report = LintReport()
    run_rules(registry, config, context, discovery, report,
              specific_rules={"I001"})

    for r in report.results:
        assert r.rule_id == "I001", f"Expected I001, got {r.rule_id}"


def test_structure_rules_dispatched_by_target(tmp_path):
    """Structure rules are dispatched by their ``target`` property,
    not by hardcoded rule IDs in the runner.  A new rule with
    target='agent_config' should automatically receive agent JSON
    files without any runner changes."""
    from cxas_scrapi.utils.linter import _RULE_REGISTRY, _REGISTERED_IDS

    _make_app(tmp_path, agents=["root_agent"])
    config = LintConfig()
    discovery = Discovery(tmp_path, tmp_path / "evals")
    context = build_context(tmp_path, config, discovery)

    # Create a custom structure rule with target="agent_config"
    @rule("structure")
    class FakeStructureRule(Rule):
        id = "S999"
        name = "fake-structure"
        description = "Test target dispatch"
        default_severity = Severity.WARNING
        target = "agent_config"

        def check(self, file_path, content, ctx):
            return [self.make_result(
                str(file_path), "S999 was dispatched correctly"
            )]

    registry = build_registry()
    report = LintReport()
    run_rules(registry, config, context, discovery, report,
              categories=["structure"], specific_rules={"S999"})

    assert any(r.rule_id == "S999" for r in report.results), \
        "S999 with target='agent_config' was not dispatched by the runner"

    # Cleanup: remove the fake rule so it doesn't affect other tests
    _RULE_REGISTRY["structure"] = [
        r for r in _RULE_REGISTRY["structure"] if r.id != "S999"
    ]
    _REGISTERED_IDS.discard("S999")
