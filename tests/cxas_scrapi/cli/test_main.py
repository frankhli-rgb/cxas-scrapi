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

"""Tests for the main CLI entry point."""

import argparse
import subprocess
import sys
from unittest.mock import patch

import pytest

from cxas_scrapi.cli.main import get_parser, run_migration_dashboard


def test_get_parser():
    """Test that the parser can be initialized and parses help correctly."""
    parser = get_parser()
    assert parser is not None

    # Test parsing a simple command to verify the parser structure
    args = parser.parse_args(
        ["apps", "list", "--project-id", "test-project", "--location", "us"]
    )
    assert args.command == "apps"
    assert args.project_id == "test-project"
    assert args.location == "us"


def test_cli_installed_help():
    """Test that the 'cxas' command is installed and executable (verifies
    setup.py)."""
    # This tests the installation of the wheel we just built and installed.
    # When running tests via 'conda run -n cxas-scrapi pytest', 'cxas'
    # should be in the PATH.
    try:
        py_code = (
            "import sys; "
            "sys.argv[0]='cxas'; "
            "from cxas_scrapi.cli.main import main; "
            "main()"
        )
        result = subprocess.run(
            [sys.executable, "-c", py_code, "--help"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.returncode == 0
        assert "usage: cxas" in result.stdout
    except FileNotFoundError:
        pytest.fail(
            "The 'cxas' command was not found in the environment. "
            "Is it installed?"
        )
    except subprocess.CalledProcessError as e:
        pytest.fail(
            f"'cxas --help' failed with return code {e.returncode}. "
            f"Output: {e.output}"
        )


def test_migrate_dfcx_default_parser():
    parser = get_parser()
    args = parser.parse_args(["migrate", "dfcx"])
    assert args.migrate_command == "dfcx"
    assert args.run is False
    assert args.optimize is False
    assert args.default_agent_name == "migrated-agent"


def test_migrate_dfcx_run_parser():
    parser = get_parser()
    args = parser.parse_args(
        [
            "migrate",
            "dfcx",
            "--run",
            "--source-agent-id",
            "projects/p/locations/g/agents/a",
            "--project-id",
            "target-project",
            "--target-name",
            "test-target",
            "--persist-bundle",
            "--yes",
        ]
    )
    assert args.run is True
    assert args.source_agent_id == "projects/p/locations/g/agents/a"
    assert args.project_id == "target-project"
    assert args.target_name == "test-target"
    assert args.persist_bundle is True
    assert args.yes is True


def test_migrate_dfcx_run_mutually_exclusive_sources():
    parser = get_parser()
    with pytest.raises(SystemExit):
        # Passing both agent ID and zip path should fail
        parser.parse_args(
            [
                "migrate",
                "dfcx",
                "--run",
                "--source-agent-id",
                "projects/p/locations/g/agents/a",
                "--source-zip",
                "/tmp/agent.zip",
                "--project-id",
                "target-project",
                "--target-name",
                "test-target",
            ]
        )


def test_migrate_dfcx_optimize_parser():
    parser = get_parser()
    args = parser.parse_args(
        [
            "migrate",
            "dfcx",
            "--optimize",
            "--stage",
            "3",
            "--target-name",
            "test-target",
            "--dry-run",
        ]
    )
    assert args.optimize is True
    assert args.stage == "3"
    assert args.target_name == "test-target"
    assert args.dry_run is True


def test_migrate_dfcx_optimize_mutually_exclusive_modes():
    parser = get_parser()
    with pytest.raises(SystemExit):
        # Passing both --run and --optimize should fail
        parser.parse_args(
            [
                "migrate",
                "dfcx",
                "--run",
                "--optimize",
                "--stage",
                "1",
                "--target-name",
                "test-target",
            ]
        )


@patch("cxas_scrapi.cli.main.run_end_to_end")
def test_run_migration_dashboard_routes_run(mock_run):

    args = argparse.Namespace(
        run=True,
        optimize=False,
        source_agent_id="projects/p/locations/g/agents/a",
        source_zip=None,
        project_id="target-project",
        target_name="test-target",
    )
    run_migration_dashboard(args)
    mock_run.assert_called_once_with(args)


@patch("cxas_scrapi.cli.main.run_stage3")
def test_run_migration_dashboard_routes_optimize_stage3(mock_stage3):

    args = argparse.Namespace(
        run=False,
        optimize=True,
        stage="3",
        target_name="test-target",
        version_label=None,
    )
    run_migration_dashboard(args)

    # Assert that Stage 3 version_label defaults to "0.0.4"!
    assert args.version_label == "0.0.4"
    mock_stage3.assert_called_once_with(args)


@patch("cxas_scrapi.cli.main.run_stage2")
def test_run_migration_dashboard_routes_optimize_stage2_with_custom_flags(
    mock_stage2,
):

    args = argparse.Namespace(
        run=False,
        optimize=True,
        stage="2",
        target_name="test-target",
        version_label="0.0.3-custom",
        no_unit_tests=True,
        no_lint=True,
        no_report=True,
        no_persist=True,
    )
    run_migration_dashboard(args)

    mock_stage2.assert_called_once_with(args)
    call_args = mock_stage2.call_args[0][0]
    assert call_args.no_unit_tests is True
    assert call_args.no_lint is True
    assert call_args.no_report is True
    assert call_args.no_persist is True
    assert call_args.version_label == "0.0.3-custom"
