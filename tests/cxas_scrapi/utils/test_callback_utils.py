"""Unit tests for the CallbackUtils testing utility."""

import pandas as pd
from cxas_scrapi.utils.callback_utils import CallbackUtils


def test_run_callback_tests_no_files(tmp_path):
    utils = CallbackUtils()
    result = utils.run_callback_tests(app_root_dir=str(tmp_path))
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0
    assert list(result.columns) == [
            "agent_name",
            "callback_type",
            "test_name",
            "status",
            "error_message",
    ]


def test_run_callback_tests_missing_python_code(tmp_path):
    utils = CallbackUtils()

    agent_dir = tmp_path / "agents" / "agentA" / "my_callbacks" / "cb1"
    agent_dir.mkdir(parents=True)
    test_file = agent_dir / "test.py"
    test_file.write_text("def test_dummy(): pass")

    result = utils.run_callback_tests(app_root_dir=str(tmp_path))
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0


def test_run_callback_tests_success(tmp_path):
    utils = CallbackUtils()

    agent_dir = tmp_path / "agents" / "agentA" / "my_callbacks" / "cb1"
    agent_dir.mkdir(parents=True)
    test_file = agent_dir / "test.py"
    test_file.write_text("""def test_dummy():
        assert True
""")

    python_code_file = agent_dir / "python_code.py"
    python_code_file.write_text("def my_func(): pass\n")

    result = utils.run_callback_tests(app_root_dir=str(tmp_path))
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 1
    assert result.iloc[0]["status"] == "passed"
    assert result.iloc[0]["test_name"] == "test_dummy"
    assert result.iloc[0]["agent_name"] == "agentA"
    assert result.iloc[0]["callback_type"] == "my_callbacks"


def test_run_callback_tests_failure(tmp_path):
    utils = CallbackUtils()

    agent_dir = tmp_path / "agents" / "agentA" / "my_callbacks" / "cb1"
    agent_dir.mkdir(parents=True)
    test_file = agent_dir / "test.py"
    test_file.write_text("""def test_dummy_fail():
        assert False, 'Failed purposely'
""")

    python_code_file = agent_dir / "python_code.py"
    python_code_file.write_text("def my_func(): pass\n")

    result = utils.run_callback_tests(app_root_dir=str(tmp_path))
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 1
    assert result.iloc[0]["status"] == "failed"
    assert result.iloc[0]["test_name"] == "test_dummy_fail"
    assert result.iloc[0]["agent_name"] == "agentA"
    assert result.iloc[0]["callback_type"] == "my_callbacks"
    assert "Failed purposely" in str(result.iloc[0]["error_message"])
