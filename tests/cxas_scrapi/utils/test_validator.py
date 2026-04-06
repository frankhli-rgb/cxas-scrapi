import pytest
from pathlib import Path
from cxas_scrapi.utils.validator import Validator


@pytest.fixture
def validator():
    return Validator()


def test_validate_agent_valid_yaml(tmp_path, validator):
    from unittest.mock import patch, MagicMock

    agent_dir = tmp_path / "MyAgent"
    agent_dir.mkdir()
    (agent_dir / "MyAgent.yaml").write_text("displayName: MyAgent")
    (agent_dir / "instruction.txt").write_text("Be helpful.")

    with patch.object(validator, "load_agent") as mock_load:
        mock_load.return_value = MagicMock()
        assert validator.validate_agent(str(agent_dir)) is True


def test_validate_agent_valid_json(tmp_path, validator):
    from unittest.mock import patch, MagicMock

    agent_dir = tmp_path / "MyAgent"
    agent_dir.mkdir()
    (agent_dir / "MyAgent.json").write_text('{"displayName": "MyAgent"}')
    (agent_dir / "instruction.txt").write_text("Be helpful.")

    with patch.object(validator, "load_agent") as mock_load:
        mock_load.return_value = MagicMock()
        assert validator.validate_agent(str(agent_dir)) is True


def test_validate_agent_missing_dir(validator):
    with pytest.raises(FileNotFoundError):
        validator.validate_agent("/path/to/nonexistent/agent")


# Obsolete tests for directory structure validation removed.


def test_load_agent_valid_yaml(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    agent_dir = agents_dir / "MyAgent"
    agent_dir.mkdir()

    (agent_dir / "MyAgent.yaml").write_text(
        "displayName: MyAgent\ninstruction: agents/MyAgent/instruction.txt"
    )
    (agent_dir / "instruction.txt").write_text("Be helpful.")

    with patch(
        "cxas_scrapi.utils.validator.json_format.ParseDict"
    ) as mock_parse_dict:
        agent = validator.load_agent(str(agent_dir))

        expected_dict = {"displayName": "MyAgent", "instruction": "Be helpful."}
        mock_parse_dict.assert_called_once()
        args, kwargs = mock_parse_dict.call_args
        assert args[0] == expected_dict
        assert agent._pb == args[1]


def test_load_agent_valid_json(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    agent_dir = agents_dir / "MyAgent"
    agent_dir.mkdir()

    (agent_dir / "MyAgent.json").write_text(
        '{"displayName": "MyAgent", "instruction": "agents/MyAgent/instruction.txt"}'
    )
    (agent_dir / "instruction.txt").write_text("Be helpful.")

    with patch(
        "cxas_scrapi.utils.validator.json_format.ParseDict"
    ) as mock_parse_dict:
        agent = validator.load_agent(str(agent_dir))

        expected_dict = {"displayName": "MyAgent", "instruction": "Be helpful."}
        mock_parse_dict.assert_called_once()
        args, kwargs = mock_parse_dict.call_args
        assert args[0] == expected_dict
        assert agent._pb == args[1]


def test_load_agent_missing_referenced_file(tmp_path, validator, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    agent_dir = agents_dir / "MyAgent"
    agent_dir.mkdir()

    (agent_dir / "MyAgent.yaml").write_text(
        "displayName: MyAgent\ninstruction: agents/MyAgent/nonexistent.txt"
    )

    with pytest.raises(FileNotFoundError) as exc_info:
        validator.load_agent(str(agent_dir))
    assert "Referenced file not found" in str(exc_info.value)


def test_load_agent_with_referenced_file_resolved_via_prefix(
    tmp_path, validator, monkeypatch
):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)

    app_root = tmp_path / "app_root"
    app_root.mkdir()
    agents_dir = app_root / "agents"
    agents_dir.mkdir()
    agent_dir = agents_dir / "MyAgent"
    agent_dir.mkdir()

    (agent_dir / "MyAgent.yaml").write_text(
        "displayName: MyAgent\ninstruction: agents/MyAgent/instruction.txt"
    )
    (agent_dir / "instruction.txt").write_text(
        "Be helpful from prefix resolution."
    )

    with patch(
        "cxas_scrapi.utils.validator.json_format.ParseDict"
    ) as mock_parse_dict:
        agent = validator.load_agent(str(agent_dir))

        expected_dict = {
            "displayName": "MyAgent",
            "instruction": "Be helpful from prefix resolution.",
        }
        mock_parse_dict.assert_called_once()
        args, kwargs = mock_parse_dict.call_args
        assert args[0] == expected_dict


def test_load_tool_valid_yaml(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    tool_dir = tools_dir / "MyTool"
    tool_dir.mkdir()

    (tool_dir / "MyTool.yaml").write_text("displayName: MyTool")

    with patch(
        "cxas_scrapi.utils.validator.json_format.ParseDict"
    ) as mock_parse_dict:
        tool = validator.load_tool(str(tool_dir))

        expected_dict = {
            "displayName": "MyTool",
        }
        mock_parse_dict.assert_called_once()
        args, kwargs = mock_parse_dict.call_args
        assert args[0] == expected_dict
        assert tool._pb == args[1]


def test_load_tool_valid_json(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    tool_dir = tools_dir / "MyTool"
    tool_dir.mkdir()

    (tool_dir / "MyTool.json").write_text('{"displayName": "MyTool"}')

    with patch(
        "cxas_scrapi.utils.validator.json_format.ParseDict"
    ) as mock_parse_dict:
        tool = validator.load_tool(str(tool_dir))

        expected_dict = {
            "displayName": "MyTool",
        }
        mock_parse_dict.assert_called_once()
        args, kwargs = mock_parse_dict.call_args
        assert args[0] == expected_dict
        assert tool._pb == args[1]


def test_load_tool_missing_referenced_file(tmp_path, validator, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    tool_dir = tools_dir / "MyTool"
    tool_dir.mkdir()

    (tool_dir / "MyTool.yaml").write_text(
        "displayName: MyTool\ninstruction: tools/MyTool/nonexistent.txt"
    )

    with pytest.raises(FileNotFoundError) as exc_info:
        validator.load_tool(str(tool_dir))
    assert "Referenced file not found" in str(exc_info.value)


def test_validate_tool_valid(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    tool_dir = tools_dir / "MyTool"
    tool_dir.mkdir()

    (tool_dir / "MyTool.yaml").write_text("displayName: MyTool")

    with patch.object(validator, "load_tool") as mock_load:
        mock_load.return_value = MagicMock()
        assert validator.validate_tool(str(tool_dir)) is True


def test_load_toolset_valid_yaml(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    toolsets_dir = tmp_path / "toolsets"
    toolsets_dir.mkdir()
    toolset_dir = toolsets_dir / "MyToolset"
    toolset_dir.mkdir()

    (toolset_dir / "MyToolset.yaml").write_text("displayName: MyToolset")

    with patch(
        "cxas_scrapi.utils.validator.json_format.ParseDict"
    ) as mock_parse_dict:
        toolset = validator.load_toolset(str(toolset_dir))

        expected_dict = {
            "displayName": "MyToolset",
        }
        mock_parse_dict.assert_called_once()
        args, kwargs = mock_parse_dict.call_args
        assert args[0] == expected_dict
        assert toolset._pb == args[1]


def test_load_toolset_valid_json(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    toolsets_dir = tmp_path / "toolsets"
    toolsets_dir.mkdir()
    toolset_dir = toolsets_dir / "MyToolset"
    toolset_dir.mkdir()

    (toolset_dir / "MyToolset.json").write_text('{"displayName": "MyToolset"}')

    with patch(
        "cxas_scrapi.utils.validator.json_format.ParseDict"
    ) as mock_parse_dict:
        toolset = validator.load_toolset(str(toolset_dir))

        expected_dict = {
            "displayName": "MyToolset",
        }
        mock_parse_dict.assert_called_once()
        args, kwargs = mock_parse_dict.call_args
        assert args[0] == expected_dict
        assert toolset._pb == args[1]


def test_load_toolset_missing_referenced_file(tmp_path, validator, monkeypatch):
    monkeypatch.chdir(tmp_path)
    toolsets_dir = tmp_path / "toolsets"
    toolsets_dir.mkdir()
    toolset_dir = toolsets_dir / "MyToolset"
    toolset_dir.mkdir()

    (toolset_dir / "MyToolset.yaml").write_text(
        "displayName: MyToolset\nopenApiSchema: toolsets/MyToolset/schema.json"
    )

    with pytest.raises(FileNotFoundError) as exc_info:
        validator.load_toolset(str(toolset_dir))
    assert "Referenced file not found" in str(exc_info.value)


def test_load_toolset_with_referenced_file(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    toolsets_dir = tmp_path / "toolsets"
    toolsets_dir.mkdir()
    toolset_dir = toolsets_dir / "MyToolset"
    toolset_dir.mkdir()

    (toolset_dir / "MyToolset.yaml").write_text(
        "displayName: MyToolset\nopenApiSchema: toolsets/MyToolset/schema.json"
    )
    (toolset_dir / "schema.json").write_text('{"openapi": "3.0.0"}')

    with patch(
        "cxas_scrapi.utils.validator.json_format.ParseDict"
    ) as mock_parse_dict:
        toolset = validator.load_toolset(str(toolset_dir))

        expected_dict = {
            "displayName": "MyToolset",
            "openApiSchema": '{"openapi": "3.0.0"}',
        }
        mock_parse_dict.assert_called_once()
        args, kwargs = mock_parse_dict.call_args
        assert args[0] == expected_dict
        assert toolset._pb == args[1]


def test_validate_toolset_valid(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    toolsets_dir = tmp_path / "toolsets"
    toolsets_dir.mkdir()
    toolset_dir = toolsets_dir / "MyToolset"
    toolset_dir.mkdir()

    (toolset_dir / "MyToolset.yaml").write_text("displayName: MyToolset")

    with patch.object(validator, "load_toolset") as mock_load:
        mock_load.return_value = MagicMock()
        assert validator.validate_toolset(str(toolset_dir)) is True


def test_load_guardrail_valid_yaml(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    guardrails_dir = tmp_path / "guardrails"
    guardrails_dir.mkdir()
    guardrail_dir = guardrails_dir / "MyGuardrail"
    guardrail_dir.mkdir()

    (guardrail_dir / "MyGuardrail.yaml").write_text("displayName: MyGuardrail")

    with patch(
        "cxas_scrapi.utils.validator.json_format.ParseDict"
    ) as mock_parse_dict:
        guardrail = validator.load_guardrail(str(guardrail_dir))

        expected_dict = {
            "displayName": "MyGuardrail",
        }
        mock_parse_dict.assert_called_once()
        args, kwargs = mock_parse_dict.call_args
        assert args[0] == expected_dict
        assert guardrail._pb == args[1]


def test_load_guardrail_valid_json(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    guardrails_dir = tmp_path / "guardrails"
    guardrails_dir.mkdir()
    guardrail_dir = guardrails_dir / "MyGuardrail"
    guardrail_dir.mkdir()

    (guardrail_dir / "MyGuardrail.json").write_text(
        '{"displayName": "MyGuardrail"}'
    )

    with patch(
        "cxas_scrapi.utils.validator.json_format.ParseDict"
    ) as mock_parse_dict:
        guardrail = validator.load_guardrail(str(guardrail_dir))

        expected_dict = {
            "displayName": "MyGuardrail",
        }
        mock_parse_dict.assert_called_once()
        args, kwargs = mock_parse_dict.call_args
        assert args[0] == expected_dict
        assert guardrail._pb == args[1]


def test_validate_guardrail_valid(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    guardrails_dir = tmp_path / "guardrails"
    guardrails_dir.mkdir()
    guardrail_dir = guardrails_dir / "MyGuardrail"
    guardrail_dir.mkdir()

    (guardrail_dir / "MyGuardrail.yaml").write_text("displayName: MyGuardrail")

    with patch.object(validator, "load_guardrail") as mock_load:
        mock_load.return_value = MagicMock()
        assert validator.validate_guardrail(str(guardrail_dir)) is True


def test_load_evaluation_valid_yaml(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    evaluations_dir = tmp_path / "evaluations"
    evaluations_dir.mkdir()
    evaluation_dir = evaluations_dir / "MyEvaluation"
    evaluation_dir.mkdir()

    (evaluation_dir / "MyEvaluation.yaml").write_text(
        "displayName: MyEvaluation"
    )

    with patch(
        "cxas_scrapi.utils.validator.json_format.ParseDict"
    ) as mock_parse_dict:
        evaluation = validator.load_evaluation(str(evaluation_dir))

        expected_dict = {
            "displayName": "MyEvaluation",
        }
        mock_parse_dict.assert_called_once()
        args, kwargs = mock_parse_dict.call_args
        assert args[0] == expected_dict
        assert evaluation._pb == args[1]


def test_load_evaluation_valid_json(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    evaluations_dir = tmp_path / "evaluations"
    evaluations_dir.mkdir()
    evaluation_dir = evaluations_dir / "MyEvaluation"
    evaluation_dir.mkdir()

    (evaluation_dir / "MyEvaluation.json").write_text(
        '{"displayName": "MyEvaluation"}'
    )

    with patch(
        "cxas_scrapi.utils.validator.json_format.ParseDict"
    ) as mock_parse_dict:
        evaluation = validator.load_evaluation(str(evaluation_dir))

        expected_dict = {
            "displayName": "MyEvaluation",
        }
        mock_parse_dict.assert_called_once()
        args, kwargs = mock_parse_dict.call_args
        assert args[0] == expected_dict
        assert evaluation._pb == args[1]


def test_load_evaluation_invalid_yaml(tmp_path, validator, monkeypatch):
    from google.protobuf import json_format
    import pytest

    monkeypatch.chdir(tmp_path)
    evaluations_dir = tmp_path / "evaluations"
    evaluations_dir.mkdir()
    evaluation_dir = evaluations_dir / "MyEvaluation"
    evaluation_dir.mkdir()

    (evaluation_dir / "MyEvaluation.yaml").write_text(
        "displayName: MyEvaluation\nnon_existent_field: value"
    )

    with pytest.raises(json_format.ParseError):
        validator.load_evaluation(str(evaluation_dir))


def test_load_evaluation_expectations_valid_yaml(
    tmp_path, validator, monkeypatch
):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    expectations_dir = tmp_path / "evaluation_expectations"
    expectations_dir.mkdir()
    expectation_dir = expectations_dir / "MyExpectation"
    expectation_dir.mkdir()

    (expectation_dir / "MyExpectation.yaml").write_text(
        "displayName: MyExpectation"
    )

    with patch(
        "cxas_scrapi.utils.validator.json_format.ParseDict"
    ) as mock_parse_dict:
        expectation = validator.load_evaluation_expectations(
            str(expectation_dir)
        )

        expected_dict = {
            "displayName": "MyExpectation",
        }
        mock_parse_dict.assert_called_once()
        args, kwargs = mock_parse_dict.call_args
        assert args[0] == expected_dict
        assert expectation._pb == args[1]


def test_load_evaluation_expectations_valid_json(
    tmp_path, validator, monkeypatch
):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    expectations_dir = tmp_path / "evaluation_expectations"
    expectations_dir.mkdir()
    expectation_dir = expectations_dir / "MyExpectation"
    expectation_dir.mkdir()

    (expectation_dir / "MyExpectation.json").write_text(
        '{"displayName": "MyExpectation"}'
    )

    with patch(
        "cxas_scrapi.utils.validator.json_format.ParseDict"
    ) as mock_parse_dict:
        expectation = validator.load_evaluation_expectations(
            str(expectation_dir)
        )

        expected_dict = {
            "displayName": "MyExpectation",
        }
        mock_parse_dict.assert_called_once()
        args, kwargs = mock_parse_dict.call_args
        assert args[0] == expected_dict
        assert expectation._pb == args[1]


def test_load_evaluation_expectations_invalid_yaml(
    tmp_path, validator, monkeypatch
):
    from google.protobuf import json_format
    import pytest

    monkeypatch.chdir(tmp_path)
    expectations_dir = tmp_path / "evaluation_expectations"
    expectations_dir.mkdir()
    expectation_dir = expectations_dir / "MyExpectation"
    expectation_dir.mkdir()

    (expectation_dir / "MyExpectation.yaml").write_text(
        "displayName: MyExpectation\nnon_existent_field: value"
    )

    with pytest.raises(json_format.ParseError):
        validator.load_evaluation_expectations(str(expectation_dir))


def test_load_app_valid_yaml(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()
    app_dir = apps_dir / "MyApp"
    app_dir.mkdir()

    (app_dir / "app.yaml").write_text("displayName: MyApp")

    with patch(
        "cxas_scrapi.utils.validator.json_format.ParseDict"
    ) as mock_parse_dict:
        app = validator.load_app(str(app_dir))

        expected_dict = {
            "displayName": "MyApp",
        }
        mock_parse_dict.assert_called_once()
        args, kwargs = mock_parse_dict.call_args
        assert args[0] == expected_dict
        assert app._pb == args[1]


def test_load_app_with_referenced_file_relative(tmp_path, validator):
    from unittest.mock import patch, MagicMock

    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()
    app_dir = apps_dir / "MyApp"
    app_dir.mkdir()

    (app_dir / "app.yaml").write_text(
        "displayName: MyApp\nglobal_instruction: global_instruction.txt"
    )
    (app_dir / "global_instruction.txt").write_text("Global rules.")

    with patch(
        "cxas_scrapi.utils.validator.json_format.ParseDict"
    ) as mock_parse_dict:
        app = validator.load_app(str(app_dir))

        expected_dict = {
            "displayName": "MyApp",
            "global_instruction": "Global rules.",
        }
        mock_parse_dict.assert_called_once()
        args, kwargs = mock_parse_dict.call_args
        assert args[0] == expected_dict


def test_validate_app_valid(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()
    app_dir = apps_dir / "MyApp"
    app_dir.mkdir()

    (app_dir / "MyApp.yaml").write_text("displayName: MyApp")
    (app_dir / "agents").mkdir()

    with patch.object(validator, "load_app") as mock_load:
        mock_load.return_value = MagicMock()
        assert validator.validate_app(str(app_dir)) is True


def test_validate_app_invalid(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()
    app_dir = apps_dir / "MyApp"
    app_dir.mkdir()

    (app_dir / "MyApp.yaml").write_text("displayName: MyApp")

    with patch.object(validator, "load_app") as mock_load:
        mock_load.side_effect = ValueError("Invalid structure")
        with pytest.raises(ValueError, match="Invalid structure"):
            validator.validate_app(str(app_dir))


def test_validate_app_missing_agents_dir(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()
    app_dir = apps_dir / "MyApp"
    app_dir.mkdir()

    (app_dir / "MyApp.yaml").write_text("displayName: MyApp")

    with patch.object(validator, "load_app") as mock_load:
        mock_load.return_value = MagicMock()
        with pytest.raises(
            FileNotFoundError, match="Missing agents/ subdirectory"
        ):
            validator.validate_app(str(app_dir))


def test_validate_app_calls_sub_validators(tmp_path, validator, monkeypatch):
    from unittest.mock import patch, MagicMock

    monkeypatch.chdir(tmp_path)
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()
    app_dir = apps_dir / "MyApp"
    app_dir.mkdir()

    (app_dir / "MyApp.yaml").write_text("displayName: MyApp")

    agents_dir = app_dir / "agents"
    agents_dir.mkdir()
    agent1_dir = agents_dir / "Agent1"
    agent1_dir.mkdir()

    tools_dir = app_dir / "tools"
    tools_dir.mkdir()
    tool1_dir = tools_dir / "Tool1"
    tool1_dir.mkdir()

    toolsets_dir = app_dir / "toolsets"
    toolsets_dir.mkdir()
    toolset1_dir = toolsets_dir / "Toolset1"
    toolset1_dir.mkdir()

    guardrails_dir = app_dir / "guardrails"
    guardrails_dir.mkdir()
    guardrail1_dir = guardrails_dir / "Guardrail1"
    guardrail1_dir.mkdir()

    evaluations_dir = app_dir / "evaluations"
    evaluations_dir.mkdir()
    evaluation1_dir = evaluations_dir / "Evaluation1"
    evaluation1_dir.mkdir()

    expectations_dir = app_dir / "evaluation_expectations"
    expectations_dir.mkdir()
    expectation1_dir = expectations_dir / "Expectation1"
    expectation1_dir.mkdir()

    with patch.object(validator, "load_app") as mock_load, patch.object(
        validator, "validate_agent"
    ) as mock_val_agent, patch.object(
        validator, "validate_tool"
    ) as mock_val_tool, patch.object(
        validator, "validate_toolset"
    ) as mock_val_toolset, patch.object(
        validator, "validate_guardrail"
    ) as mock_val_guardrail, patch.object(
        validator, "validate_evaluation"
    ) as mock_val_evaluation, patch.object(
        validator, "validate_evaluation_expectations"
    ) as mock_val_evaluation_expectations:

        mock_load.return_value = MagicMock()

        assert validator.validate_app(str(app_dir)) is True

        mock_val_agent.assert_called_once_with(str(agent1_dir))
        mock_val_tool.assert_called_once_with(str(tool1_dir))
        mock_val_toolset.assert_called_once_with(str(toolset1_dir))
        mock_val_guardrail.assert_called_once_with(str(guardrail1_dir))
        mock_val_evaluation.assert_called_once_with(str(evaluation1_dir))
        mock_val_evaluation_expectations.assert_called_once_with(
            str(expectation1_dir)
        )
