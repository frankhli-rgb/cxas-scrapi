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

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console

from cxas_scrapi.migration.data_models import (
    IRAgent,
    IRMetadata,
    MigrationIR,
    MigrationStatus,
)
from cxas_scrapi.migration.service import MigrationService
from cxas_scrapi.migration.topology_optimizer import (
    AppTopologyGraph,
    CoreHarmonyReport,
    SubAgentClassification,
    TopologyOptimizer,
)


def _make_test_ir() -> MigrationIR:
    """Constructs a test MigrationIR with one steering, two core,
    and two helper agents.
    """
    return MigrationIR(
        metadata=IRMetadata(
            app_name="test-app",
            app_id="test-app-id-123",
            app_resource_name="projects/p/locations/us/apps/test-app",
        ),
        agents={
            "Welcome_Flow": IRAgent(
                type="PLAYBOOK",
                display_name="Welcome Flow",
                instruction=(
                    '<state id="init"><instructions>'
                    "- Greet user."
                    "</instructions></state>"
                ),
                status=MigrationStatus.COMPILED,
            ),
            "Authentication": IRAgent(
                type="PLAYBOOK",
                display_name="Authentication",
                instruction=(
                    '<state id="auth"><instructions>'
                    "- Validate PIN."
                    "</instructions></state>"
                ),
                status=MigrationStatus.COMPILED,
            ),
            "Billing_Inquiry": IRAgent(
                type="PLAYBOOK",
                display_name="Billing Inquiry",
                instruction=(
                    '<state id="billing"><instructions>'
                    "- Show statement."
                    "</instructions></state>"
                ),
                status=MigrationStatus.COMPILED,
            ),
            "Troubleshoot_Router": IRAgent(
                type="PLAYBOOK",
                display_name="Troubleshoot Router",
                instruction=(
                    '<state id="troubleshoot"><instructions>'
                    "- Reboot router."
                    "</instructions></state>"
                ),
                status=MigrationStatus.COMPILED,
            ),
            "Graceful_Signoff": IRAgent(
                type="PLAYBOOK",
                display_name="Graceful Signoff",
                instruction=(
                    '<state id="exit"><instructions>'
                    "- Thank user."
                    "</instructions></state>"
                ),
                status=MigrationStatus.COMPILED,
            ),
        },
    )


@pytest.mark.asyncio
async def test_topology_classification_success():
    """Verifies the LLM semantically designates sub-agents as CORE or HELPER."""
    ir = _make_test_ir()
    mock_gemini = MagicMock()

    # Create fake JSON output matching AppTopologyGraph
    fake_graph = AppTopologyGraph(
        classifications=[
            SubAgentClassification(
                key="Welcome_Flow",
                designation="HELPER",
                semantic_role="Greeting and call setup",
                merger_target="Steering_Agent",
            ),
            SubAgentClassification(
                key="Authentication",
                designation="HELPER",
                semantic_role="User verification PIN",
                merger_target="Steering_Agent",
            ),
            SubAgentClassification(
                key="Billing_Inquiry",
                designation="CORE",
                semantic_role="Manage billing and statements",
            ),
            SubAgentClassification(
                key="Troubleshoot_Router",
                designation="CORE",
                semantic_role="Technical router diagnostics",
            ),
            SubAgentClassification(
                key="Graceful_Signoff",
                designation="HELPER",
                semantic_role="Call exit and teardown",
                merger_target="Session_Termination_Agent",
            ),
        ]
    )
    mock_gemini.generate_async = AsyncMock(return_value=fake_graph)

    optimizer = TopologyOptimizer(ir, mock_gemini)
    graph = await optimizer.analyze_app_topology()

    assert len(graph.classifications) == 5
    helpers = [c for c in graph.classifications if c.designation == "HELPER"]
    cores = [c for c in graph.classifications if c.designation == "CORE"]
    assert len(helpers) == 3
    assert len(cores) == 2
    assert helpers[0].merger_target == "Steering_Agent"

    # Assert table prints without error
    console = Console(record=True)
    optimizer.print_designations_table(graph, console)
    table_output = console.export_text()
    assert "Welcome_Flow" in table_output
    assert "Billing_Inquiry" in table_output


@pytest.mark.asyncio
async def test_organic_prompt_merger_success():
    """Asserts helper prompts are cleanly woven into parent Core prompts."""
    ir = _make_test_ir()
    mock_gemini = MagicMock()
    mock_gemini.generate_async = AsyncMock(
        return_value=(
            '<state id="billing"><instructions>'
            "- Show statement."
            "</instructions>"
            "<authentication_protocol>"
            "- Validate PIN."
            "</authentication_protocol></state>"
        )
    )

    optimizer = TopologyOptimizer(ir, mock_gemini)
    merged_xml = await optimizer.organically_merge_agent_prompts(
        core_agent=ir.agents["Billing_Inquiry"],
        helper_agent=ir.agents["Authentication"],
    )

    assert "<authentication_protocol>" in merged_xml
    assert "Validate PIN." in merged_xml


@pytest.mark.asyncio
async def test_core_harmony_qa_checks():
    """Verifies that verify_merged_core_harmony checks for logical prompt
    conflicts.
    """
    ir = _make_test_ir()
    mock_gemini = MagicMock()

    # Scenario 1: Cohesion check passed
    passed_report = CoreHarmonyReport(
        passed=True,
        final_optimized_instruction=(
            '<state id="billing"><instructions>'
            "- Show statement."
            "</instructions></state>"
        ),
    )
    mock_gemini.generate_async = AsyncMock(return_value=passed_report)

    optimizer = TopologyOptimizer(ir, mock_gemini)
    core_agent = ir.agents["Billing_Inquiry"]
    ok = await optimizer.verify_merged_core_harmony(core_agent)
    assert ok is True
    assert "STAGE 3 COHESION INTEGRATION WARNINGS" not in core_agent.instruction

    # Scenario 2: Cohesion check failed (returns warning block appended)
    failed_report = CoreHarmonyReport(
        passed=False,
        final_optimized_instruction=(
            '<state id="billing"><instructions>'
            "- Show statement."
            "</instructions></state>"
        ),
        detected_contradictions=[
            "Billing rule mismatch: Member A refunds $50, Member B refunds $0"
        ],
        reconciliation_suggestions=[
            "Default to $0 refunds unless customer escalates to manager."
        ],
    )
    mock_gemini.generate_async = AsyncMock(return_value=failed_report)

    ok_fail = await optimizer.verify_merged_core_harmony(core_agent)
    assert ok_fail is False
    assert "STAGE 3 COHESION INTEGRATION WARNINGS" in core_agent.instruction
    assert "Default to $0 refunds" in core_agent.instruction


def test_assert_child_agent_limit_triggers_warning():
    """Asserts that child agent limit warning triggers when active child
    spokes > 7.
    """
    ir = _make_test_ir()
    # Add 6 more core agents to make it 8 total
    for i in range(6):
        ir.agents[f"Core_Spoke_{i}"] = IRAgent(
            type="PLAYBOOK",
            display_name=f"Core Spoke {i}",
            instruction="<state/>",
            status=MigrationStatus.COMPILED,
        )

    optimizer = TopologyOptimizer(ir, MagicMock())

    with patch("logging.Logger.warning") as mock_warning:
        optimizer.assert_child_agent_limit(max_children=7)
        mock_warning.assert_called_once()
        assert "exceed maximum cap" in mock_warning.call_args[0][0]


@pytest.mark.asyncio
async def test_verify_final_ces_compilation_success():
    """Asserts that verify_final_ces_compilation returns True when cloud
    console compiles cleanly.
    """
    service = MigrationService(
        project_id="test-project",
        ps_apps_client=MagicMock(),
        ps_agents_client=MagicMock(),
        ps_tools_client=MagicMock(),
        ps_toolsets_client=MagicMock(),
        secret_manager_client=MagicMock(),
        cx_api_client=MagicMock(),
    )
    service.ir = _make_test_ir()

    mock_apps = MagicMock()
    mock_apps.get_app.return_value = MagicMock(displayName="test-app")

    with patch("cxas_scrapi.core.apps.Apps", return_value=mock_apps):
        console = Console()
        ok = await service.verify_final_ces_compilation(console)
        assert ok is True
