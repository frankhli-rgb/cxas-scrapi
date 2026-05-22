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

"""Tests for the DFCX Migration CLI Parser and Router."""

from __future__ import annotations

import argparse
import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cxas_scrapi.cli.migration_cli import MigrationCLI, run_stage3
from cxas_scrapi.migration.data_models import (
    DFCXAgentIR,
    IRMetadata,
    MigrationConfig,
    MigrationIR,
)


def _make_config(**overrides) -> MigrationConfig:
    base = {
        "project_id": "test-project",
        "target_name": "test_target",
        "model": "gemini-2.5-flash-001",
        "optimize_for_cxas": True,
    }
    base.update(overrides)
    return MigrationConfig(**base)


def _make_source() -> DFCXAgentIR:
    return DFCXAgentIR(
        name="projects/p/locations/us/agents/src",
        display_name="Test Source",
        default_language_code="en",
    )


def _make_service_mock():
    service = MagicMock()
    service.location = "us"
    service.ir = MigrationIR(
        metadata=IRMetadata(
            app_name="test-app",
            app_id="11111111-1111-1111-1111-111111111111",
            app_resource_name="projects/p/locations/us/apps/X",
        ),
    )
    service.run_stage1 = AsyncMock(return_value=None)
    service.run_stage3 = AsyncMock(return_value=(1, 0, 0))
    service.persist_bundle = MagicMock(return_value="bundle.json")
    return service


@pytest.mark.asyncio
async def test_post_migration_opt_ins_all_off_skips_everything():
    """With all opt-in flags off, no service methods are invoked."""
    cli = MigrationCLI()
    service = _make_service_mock()
    config = _make_config(run_stage3=False, persist_bundle=False)

    await cli._run_post_migration_opt_ins(service, config, _make_source())

    service.run_stage1.assert_not_called()
    service.run_stage3.assert_not_called()
    service.persist_bundle.assert_not_called()


@pytest.mark.asyncio
async def test_post_migration_opt_ins_persist_only_calls_persist_bundle():
    cli = MigrationCLI()
    service = _make_service_mock()
    config = _make_config(persist_bundle=True, run_stage3=False)

    await cli._run_post_migration_opt_ins(service, config, _make_source())

    service.persist_bundle.assert_called_once()
    call = service.persist_bundle.call_args
    assert call.args[1] == "test_target_ir.json"
    assert call.kwargs["phase"] == "migrate"
    assert call.kwargs["status"] == "ok"
    service.run_stage1.assert_not_called()
    service.run_stage3.assert_not_called()


@pytest.mark.asyncio
async def test_post_migration_opt_ins_stage3_calls_run_stage3():
    cli = MigrationCLI()
    service = _make_service_mock()
    config = _make_config(run_stage3=True, persist_bundle=False)

    await cli._run_post_migration_opt_ins(service, config, _make_source())

    service.run_stage3.assert_awaited_once()
    stage3_kwargs = service.run_stage3.call_args.kwargs
    assert stage3_kwargs["persist_bundle_path"] is None


def _run_help(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "cxas_scrapi.cli.main", *args],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def test_dfcx_help_still_renders():
    """The unified `cxas migrate dfcx --help` parser renders successfully
    and lists E2E/TUI options.
    """
    r = _run_help("migrate", "dfcx", "--help")
    assert r.returncode == 0, r.stderr
    assert "--default-agent-name" in r.stdout
    assert "--run" in r.stdout
    assert "--optimize" in r.stdout
    assert "--stage" in r.stdout


def test_run_stage3_delegates_with_custom_version_label():
    args = argparse.Namespace(
        ir_bundle="/tmp/fake_bundle.json",
        target_name=None,
        project_id=None,
        location=None,
        yes=True,
        dry_run=False,
        version_label="0.0.4-custom",
        no_persist=False,
    )

    fake_service = MagicMock()
    fake_service.run_stage3 = AsyncMock(return_value=(2, 0, 0))
    fake_bundle = MagicMock()

    with patch(
        "cxas_scrapi.cli.migration_cli._restore_service_and_bundle",
        return_value=(fake_service, fake_bundle, "/tmp/fake_bundle.json"),
    ):
        run_stage3(args)

    fake_service.run_stage3.assert_awaited_once()
    kwargs = fake_service.run_stage3.call_args.kwargs
    assert kwargs["version_label"] == "0.0.4-custom"
    assert kwargs["persist_bundle_path"] == "/tmp/fake_bundle.json"


def test_cli_dashboard_choice_id_resolves_and_cleans_urls():
    cli = MigrationCLI()

    mock_cx_api = MagicMock()
    mock_cx_api.fetch_full_agent_details.return_value = _make_source()

    with (
        patch("rich.prompt.Prompt.ask") as mock_ask,
        patch("rich.prompt.Confirm.ask", return_value=True),
        patch.object(cli, "check_auth", return_value=True),
        patch.object(cli, "compose_config", return_value=_make_config()),
        patch.object(cli, "select_resources", return_value=_make_source()),
        patch("cxas_scrapi.cli.migration_cli.asyncio.run") as mock_async_run,
    ):
        # 1. Choose "ID" source mode
        # 2. Enter full browser Console URL
        mock_ask.side_effect = [
            "ID",
            "https://dialogflow.cloud.google.com/cx/projects/test-proj-456/locations/global/agents/a4371f49-5982-4293-801b-551cf940ab65/playbooks...",
        ]

        def mock_run_side_effect(coro):
            coro.close()

        mock_async_run.side_effect = mock_run_side_effect

        cli.run(default_agent_name="test-agent", cx_api=mock_cx_api)

        # Verify the exporter is queried with the extracted clean Resource Name!
        mock_cx_api.fetch_full_agent_details.assert_called_once_with(
            "projects/test-proj-456/locations/global/agents/a4371f49-5982-4293-801b-551cf940ab65",
            use_export=True,
        )
