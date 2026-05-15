#!/usr/bin/env python3
# DEPRECATED — replaced by `stage1.py` (variable dedup + consolidation) and
# `stage2.py` (instruction state machines + tool mocks + lint + report). See
# SKILL.md. This file is kept for one release cycle.
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0

"""Post-conversion CXAS migration optimizer.

Pipeline (each phase is skippable via the matching CLI flag):

  A. Compile-only IR     — run MigrationService up to a fully compiled IR
                           with app/vars/tools deployed but agents stub'd.
  B. Stage 1 (pre-group) — global variable dedup via CXASOptimizer.
  C. Dependency analysis — DependencyAnalyzer over the source agent.
  D. Render 1:1 IR tree.
  E. Grouping            — Gemini proposal (or load from --grouping-json).
  F. Interactive review  — accept / re-propose / merge / split / rename / quit.
  G. Consolidation       — collapse N IRAgents → M groups, rewrite topology.
  H. Synthesis           — AsyncAgentDesigner Step 2A/2B per group.
  I. Instruction review  — view / edit / re-synthesize per group.
  J. Deploy              — agents + topology link + set app start agent.
  K. Version 0.0.1       — pre-Stage 2 checkpoint.
  L. Stage 2             — instruction state machines + tool mocks +
                           is_update_pass=True redeploys.
  M. Version 0.0.2       — post-Stage 2 checkpoint.
  N. Unit tests          — DeterministicEvalGenerator per consolidated agent.
  O. Lint                — `cxas pull` + `cxas lint`.
  P. Report              — OptimizationReporter writes audit markdown.
"""

from __future__ import annotations

import sys as _sys
print(
    "[deprecation] optimize_migration.py is deprecated. Use stage1.py and "
    "stage2.py instead.",
    file=_sys.stderr,
)

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

from rich.console import Console
from rich.prompt import Confirm

# Skill-local helpers (sit alongside this script).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _grouping
import _lint
import _optimizer_runner
import _phase_tracker
import _reporter
import _shared
import _synthesis
import _visualizer

from cxas_scrapi.core.versions import Versions
from cxas_scrapi.migration.config import AGENT_MODELS
from cxas_scrapi.migration.data_models import (
    MigrationConfig,
    MigrationIR,
    MigrationStatus,
)
from cxas_scrapi.migration.eval_generator import DeterministicEvalGenerator
from cxas_scrapi.migration.main_visualizer import MainVisualizer
from cxas_scrapi.migration.service import MigrationService
from cxas_scrapi.utils.gemini import GeminiGenerate

logger = logging.getLogger(__name__)
console = Console()


# ---------------------------------------------------------------------------
# Compile-only patches (Phase A)
# ---------------------------------------------------------------------------


@dataclass
class _Patches:
    deploy_pending_agents: Any = None
    link_and_finalize_topology: Any = None
    create_agent: Any = None


async def _noop_async(*_args, **_kwargs):
    return None


def _noop_sync(*_args, **_kwargs):
    return None


def _patch_for_compile_only(service: MigrationService) -> _Patches:
    from cxas_scrapi.core.agents import Agents

    saved = _Patches(
        deploy_pending_agents=service._deploy_pending_agents,
        link_and_finalize_topology=service.topology_linker.link_and_finalize_topology,
        create_agent=Agents.create_agent,
    )
    service._deploy_pending_agents = _noop_async  # type: ignore[assignment]
    service.topology_linker.link_and_finalize_topology = _noop_sync  # type: ignore[assignment]

    def mock_create(*_args, **_kwargs):
        mock_agent = MagicMock()
        mock_agent.name = (
            f"projects/{service.project_id}/locations/{service.location}/"
            f"apps/mock/agents/{uuid.uuid4()}"
        )
        return mock_agent

    Agents.create_agent = mock_create  # type: ignore[assignment]
    return saved


def _restore(service: MigrationService, saved: _Patches) -> None:
    from cxas_scrapi.core.agents import Agents

    service._deploy_pending_agents = saved.deploy_pending_agents  # type: ignore[assignment]
    service.topology_linker.link_and_finalize_topology = (
        saved.link_and_finalize_topology
    )
    Agents.create_agent = saved.create_agent  # type: ignore[assignment]


async def compile_ir_only(
    service: MigrationService, agent_id: str, config: MigrationConfig
) -> tuple[MigrationIR, _Patches]:
    saved = _patch_for_compile_only(service)
    await service.run_migration(source_cx_agent_id=agent_id, config=config)
    return service.ir, saved


# ---------------------------------------------------------------------------
# Phase J: deploy
# ---------------------------------------------------------------------------


async def deploy_consolidated(
    service: MigrationService,
    optimized_ir: MigrationIR,
    root_group: str | None,
    saved: _Patches,
) -> str:
    """Replace the IR's agents with the consolidated set, restore patches,
    deploy, link topology, and set the app's start agent. Returns the app
    console URL."""
    service.ir.agents = optimized_ir.agents
    _restore(service, saved)

    await service._deploy_pending_agents()
    service.topology_linker.link_and_finalize_topology(
        service.ir, service.source_agent_data
    )

    if root_group and root_group in service.ir.agents:
        root_agent = service.ir.agents[root_group]
        if root_agent.resource_name:
            console.print(
                f"Setting App start agent → {root_group} ({root_agent.resource_name})"
            )
            service.ps_apps.update_app(
                service.ir.metadata.app_resource_name,
                root_agent=root_agent.resource_name,
            )

    app_id = service.ir.metadata.app_id
    url = (
        f"https://ces.cloud.google.com/projects/{service.project_id}"
        f"/locations/{service.location}/apps/{app_id}"
    )
    console.print(f"\n[bold green]CXAS app deployed:[/] {url}")
    return url


# ---------------------------------------------------------------------------
# Phase K/M: version checkpoints
# ---------------------------------------------------------------------------


def _create_version_safe(
    app_resource: str, display_name: str, description: str
) -> tuple[str, str] | None:
    try:
        Versions(app_resource).create_version(
            display_name=display_name, description=description
        )
        console.print(
            f"[green]Created version checkpoint {display_name}.[/]"
        )
        return display_name, description
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to create version %s: %s", display_name, exc)
        console.print(
            f"[yellow]Could not create version {display_name}: {exc}[/]"
        )
        return None


# ---------------------------------------------------------------------------
# Phase N: deterministic unit tests
# ---------------------------------------------------------------------------


def _generate_unit_tests(
    ir: MigrationIR, target_name: str
) -> tuple[dict[str, int], str]:
    generator = DeterministicEvalGenerator(ir)
    by_agent: dict[str, list] = {}
    for agent_name in ir.agents:
        tests = generator.generate_tests_for_agent(agent_name)
        if tests:
            by_agent[agent_name] = [tc.model_dump(mode="json") for tc in tests]

    path = f"{target_name}_unit_tests.json"
    with open(path, "w") as f:
        json.dump(by_agent, f, indent=2, default=str)

    counts = {name: len(cases) for name, cases in by_agent.items()}
    console.print(
        f"[green]Wrote {sum(counts.values())} deterministic tests for "
        f"{len(counts)} agents → {path}[/]"
    )
    return counts, path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Optimize and migrate a DFCX agent into a consolidated CXAS app."
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument(
        "--source-agent-id",
        help="Source DFCX agent resource name. Prompted if neither this nor --zip-file is given.",
    )
    src.add_argument("--zip-file", help="Local DFCX export .zip path.")

    parser.add_argument("--project-id", help="Target GCP project ID. Prompted if omitted.")
    parser.add_argument("--target-name", help="Display name for the new CXAS app.")
    parser.add_argument("--env", choices=["PROD", "AUTOPUSH"], default=None)
    parser.add_argument("--model", choices=AGENT_MODELS, default=None)
    parser.add_argument("--location", default="global")
    parser.add_argument(
        "--gemini-model",
        default="gemini-3.1-pro-preview",
        help="Model used for the grouping proposal.",
    )
    parser.add_argument(
        "--export-svg",
        action="store_true",
        help="Also call MainVisualizer for SVG/markdown topology output.",
    )
    parser.add_argument(
        "--yes", "-y", action="store_true",
        help="Accept the first proposal and skip all interactive confirmations.",
    )
    parser.add_argument(
        "--grouping-json",
        default=None,
        help="Load a previously persisted grouping JSON instead of asking Gemini.",
    )
    parser.add_argument(
        "--no-stage1", action="store_true",
        help="Skip CXASOptimizer Stage 1 (pre-grouping variable dedup).",
    )
    parser.add_argument(
        "--no-stage2", action="store_true",
        help="Skip CXASOptimizer Stage 2 (post-deploy instruction + tool-mock optimization).",
    )
    parser.add_argument(
        "--no-instruction-review", action="store_true",
        help="Skip the per-group instruction review step.",
    )
    parser.add_argument(
        "--no-unit-tests", action="store_true",
        help="Skip deterministic unit test generation.",
    )
    parser.add_argument(
        "--no-lint", action="store_true",
        help="Skip post-deploy `cxas lint`.",
    )
    parser.add_argument(
        "--no-report", action="store_true",
        help="Skip the optimization report markdown.",
    )
    parser.add_argument(
        "--no-preview-html", action="store_true",
        help="Skip the pre-migration HTML tree preview.",
    )
    parser.add_argument(
        "--preview-only", action="store_true",
        help=(
            "Generate the HTML tree preview and exit (no compile, no deploy). "
            "Useful for inspecting source agent structure first."
        ),
    )
    return parser


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def _run(args) -> None:
    tracker = _phase_tracker.PhaseTracker(console)

    with tracker.phase("Source load", "fetch + parse DFCX agent"):
        agent_data, agent_id, _ = _shared.load_source_agent(args, console)

    inputs = _shared.collect_common_inputs(args, console, "optimized_agent")

    stage_report = _visualizer.StageReport(
        title=f"Optimization audit · {inputs['target_name']}",
        subtitle=f"Source: {agent_id}",
    )

    # Pre-flight HTML preview of the extracted DFCX tree.
    if not args.no_preview_html:
        with tracker.phase("Preview HTML", "topology + per-resource trees"):
            try:
                from cxas_scrapi.migration.dfcx_dep_analyzer import DependencyAnalyzer
                analyzer_pre = DependencyAnalyzer(agent_data)
                preview_path = _visualizer.generate_html_report(
                    agent_data,
                    analyzer_pre,
                    output_path=f"{inputs['target_name']}_tree_preview.html",
                )
                topo_path, tools_path = _visualizer.write_mermaid_files(
                    agent_data, analyzer_pre, inputs["target_name"]
                )
                stats = _visualizer.collect_stats(agent_data, analyzer_pre)
                console.print(
                    f"[bold green]Preview ready:[/] {preview_path}\n"
                    f"  • {stats['playbook_count']} playbooks, "
                    f"{stats['flow_count']} flows, {stats['tool_count']} tools, "
                    f"{stats['routing_edge_count']} routing edges\n"
                    f"  • Estimated 1:1 migration time: ~{stats['estimated_minutes']} min "
                    "(optimization adds ~30-50% on top)\n"
                    f"  • Mermaid sources: {topo_path}, {tools_path}"
                )
                # Seed the multi-stage report with source-side snapshots.
                stage_report.add_source_overview(agent_data, analyzer_pre)
                stage_report.add_topology_svg(agent_data)
                stage_report.add_playbook_and_flow_trees(agent_data)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Preview HTML generation failed: %s", exc)

    if args.preview_only:
        # Even in preview-only mode, write whatever we have so the user gets
        # the multi-stage HTML (topology SVG + per-resource Rich trees).
        try:
            stage_html_path = f"{inputs['target_name']}_stage_report.html"
            stage_report.write(stage_html_path)
            console.print(f"[green]Stage HTML report → {stage_html_path}[/]")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Stage HTML report failed: %s", exc)
        console.print(
            "\n[yellow]--preview-only set; exiting before any deploy.[/]"
        )
        return

    config = MigrationConfig(
        project_id=inputs["project_id"],
        target_name=inputs["target_name"],
        env=inputs["env"],
        model=inputs["model"],
        source_agent_data_override=agent_data,
        # Skill drives CXASOptimizer manually; do NOT have the service
        # auto-run the in-flight optimizer.
        optimize_for_cxas=False,
    )

    service = MigrationService(
        project_id=inputs["project_id"],
        location=args.location,
        default_model=inputs["model"],
    )

    reporter = _reporter.OptimizationReporter()
    versions: list[tuple[str, str]] = []

    # ---- Phase A: compile-only IR ------------------------------------------
    tracker.start("Phase A", "compile 1:1 IR (no agent deploys)")
    ir, saved = await compile_ir_only(service, agent_id, config)
    if not ir.agents:
        console.print("[red]Base compilation produced no agents. Aborting.[/]")
        tracker.end("Phase A", status="fail", note="no agents compiled")
        sys.exit(1)
    tracker.end("Phase A", note=f"{len(ir.agents)} agents in IR")
    stage_report.add_ir_snapshot("Phase A — 1:1 IR compiled", ir, None)
    before_count = len(ir.agents)

    # ---- Phase B: Stage 1 pre-grouping -------------------------------------
    stage1_optimizer = None
    if not args.no_stage1:
        with tracker.phase("Phase B", "CXASOptimizer Stage 1 (variable dedup)"):
            stage1_optimizer = await _optimizer_runner.run_stage1(
                ir, service.gemini_client, console
            )
            _optimizer_runner.merge_optimizer_logs_into_ir(
                ir, stage1_optimizer, "stage1"
            )
            stage_report.add_optimizer_logs(
                "Phase B — Stage 1 logs",
                stage1_optimizer.optimization_logs if stage1_optimizer else None,
            )
            stage_report.add_ir_snapshot("Phase B — IR after Stage 1", ir, None)

    # ---- Phase C: dependency analysis --------------------------------------
    with tracker.phase("Phase C", "source dependency analysis"):
        analyzer, outgoing, incoming = _shared.run_dependency_analysis(
            service.source_agent_data, service.source_agent_data, console
        )
        dep_summary = _shared.build_dep_summary(analyzer, ir)

    # ---- Phase D: render 1:1 IR --------------------------------------------
    with tracker.phase("Phase D", "render 1:1 IR tree"):
        root_key = _grouping.detect_root_key(ir, service.source_agent_data)
        console.print(_grouping.render_ir_tree(ir, "Original 1:1 IR", root_key))
        if args.export_svg:
            try:
                MainVisualizer(service.source_agent_data).export_visualizations(
                    f"{inputs['target_name']}_original"
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("SVG export failed: %s", exc)

    # ---- Phase E: grouping --------------------------------------------------
    with tracker.phase("Phase E", "Gemini grouping proposal"):
        if args.grouping_json:
            console.print(f"Loading grouping from {args.grouping_json}")
            groupings = _grouping.load_grouping(args.grouping_json)
            _grouping._validate_groupings(ir, groupings, root_key)
        else:
            gemini = GeminiGenerate(
                project_id=inputs["project_id"],
                location="global",
                model_name=args.gemini_model,
                max_concurrent_requests=10,
            )
            groupings = await _grouping.propose_groupings(
                ir, gemini, root_key, dep_summary
            )

    # ---- Phase F: interactive review ---------------------------------------
    with tracker.phase("Phase F", "interactive review"):
        if args.yes:
            optimized = _grouping.consolidate_ir(ir, groupings)
        else:
            gemini = GeminiGenerate(
                project_id=inputs["project_id"],
                location="global",
                model_name=args.gemini_model,
                max_concurrent_requests=10,
            )
            result = await _grouping.interactive_review(
                ir, groupings, gemini, root_key, dep_summary, console
            )
            if result is None:
                console.print(
                    "[yellow]Aborted. App + tools were deployed; no agents were created.[/]"
                )
                return
            optimized, groupings = result

        grouping_path = _grouping.persist_grouping(groupings, inputs["target_name"])
        console.print(f"[green]Grouping persisted → {grouping_path}[/]")
        stage_report.add_grouping_table(groupings)

    # ---- Phase G: consolidation already done by interactive_review/consolidate_ir
    after_count = len(optimized.agents)

    # ---- Phase H: synthesis -------------------------------------------------
    with tracker.phase("Phase H", "synthesize PIF instructions per group"):
        await _synthesis.synthesize_instructions_for_ir(
            optimized, service, groupings, console
        )
        stage_report.add_ir_snapshot(
            "Phase H — Consolidated IR (synthesized)",
            optimized,
            _grouping.root_group_name(groupings, root_key),
        )

    # ---- Phase I: instruction review ---------------------------------------
    if not (args.yes or args.no_instruction_review):
        with tracker.phase("Phase I", "interactive instruction review"):
            await _synthesis.interactive_synthesis_review(
                optimized, service, groupings, console
            )

    # ---- Final deploy gate -------------------------------------------------
    if not args.yes and not Confirm.ask(
        "\nDeploy consolidated agents now?", default=True
    ):
        console.print("[yellow]Deploy skipped.[/]")
        return

    # ---- Phase J: deploy ---------------------------------------------------
    with tracker.phase("Phase J", "deploy consolidated agents"):
        app_url = await deploy_consolidated(
            service,
            optimized,
            _grouping.root_group_name(groupings, root_key),
            saved,
        )

    # ---- Phase K: version 0.0.1 -------------------------------------------
    app_resource = service.ir.metadata.app_resource_name
    if app_resource:
        with tracker.phase("Phase K", "CXAS version 0.0.1 checkpoint"):
            v1 = _create_version_safe(
                app_resource,
                "0.0.1",
                "Initial consolidated agents (pre-Stage 2)",
            )
            if v1:
                versions.append(v1)

    # ---- Phase L: Stage 2 post-grouping -----------------------------------
    stage2_optimizer = None
    if not args.no_stage2:
        with tracker.phase(
            "Phase L", "CXASOptimizer Stage 2 (XML state machines + tool mocks)"
        ):
            for agent in service.ir.agents.values():
                agent.status = MigrationStatus.COMPILED
            stage2_optimizer = await _optimizer_runner.run_stage2(
                service.ir, service.gemini_client, console
            )
            _optimizer_runner.merge_optimizer_logs_into_ir(
                service.ir, stage2_optimizer, "stage2"
            )

            console.print("[cyan]Pushing Stage 2 changes to CXAS…[/]")
            try:
                await service._deploy_base_resources(is_update_pass=True)
                await service._deploy_pending_agents(is_update_pass=True)
            except Exception as exc:  # noqa: BLE001
                logger.error("Stage 2 redeploy failed: %s", exc)
                console.print(f"[red]Stage 2 redeploy failed: {exc}[/]")

            stage_report.add_optimizer_logs(
                "Phase L — Stage 2 logs",
                stage2_optimizer.optimization_logs if stage2_optimizer else None,
            )
            stage_report.add_ir_snapshot(
                "Phase L — IR after Stage 2",
                service.ir,
                _grouping.root_group_name(groupings, root_key),
            )

        # ---- Phase M: version 0.0.2 ---------------------------------------
        if app_resource:
            with tracker.phase("Phase M", "CXAS version 0.0.2 checkpoint"):
                v2 = _create_version_safe(
                    app_resource,
                    "0.0.2",
                    "Stage 2: instruction state machines + tool mocks applied",
                )
                if v2:
                    versions.append(v2)

    # ---- Phase N: deterministic unit tests --------------------------------
    test_counts: dict[str, int] = {}
    test_path = ""
    if not args.no_unit_tests:
        with tracker.phase("Phase N", "deterministic unit tests"):
            try:
                test_counts, test_path = _generate_unit_tests(
                    service.ir, inputs["target_name"]
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Deterministic unit test generation failed: %s", exc)
                console.print(f"[yellow]Unit test generation failed: {exc}[/]")

    # ---- Phase O: lint ----------------------------------------------------
    lint_passed: bool | None = None
    lint_output = ""
    if not args.no_lint:
        with tracker.phase("Phase O", "post-deploy lint"):
            try:
                lint_passed, lint_output = await _lint.run_post_deploy_lint(
                    service, console
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Lint failed to run: %s", exc)
                console.print(f"[yellow]Lint did not run: {exc}[/]")

    # ---- Phase P: report --------------------------------------------------
    with tracker.phase("Phase P", "audit report"):
        _shared.display_status_table(service.ir, console, "Consolidated Resources")
        if not args.no_report:
            reporter.set_app_info(
                agent_id, inputs["target_name"], app_resource or "", app_url
            )
            reporter.set_dependency_summary(outgoing, incoming)
            reporter.set_grouping(groupings, before_count, after_count, grouping_path)
            reporter.set_optimizer_logs(
                stage1_optimizer.optimization_logs if stage1_optimizer else None,
                stage2_optimizer.optimization_logs if stage2_optimizer else None,
            )
            reporter.set_version_checkpoints(versions)
            if test_counts:
                reporter.set_unit_test_summary(test_counts, test_path)
            if lint_passed is not None:
                reporter.set_lint_result(lint_passed, lint_output)
            report_path = reporter.export(
                f"{inputs['target_name']}_optimization_report.md"
            )
            console.print(f"[green]Optimization report → {report_path}[/]")

    console.print()
    console.print(tracker.summary_table())

    # Finalize the stage report (HTML).
    stage_report.add_versions(versions)
    stage_report.add_app_url(app_url)
    stage_report.add_phase_timeline(tracker.to_dict())
    stage_html_path = f"{inputs['target_name']}_stage_report.html"
    try:
        stage_report.write(stage_html_path)
        console.print(f"[green]Stage HTML report → {stage_html_path}[/]")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Stage HTML report failed: %s", exc)
        stage_html_path = ""

    console.print("\n[bold green]Optimization complete.[/]")
    console.print(f"  • Grouping JSON:   {grouping_path}")
    if test_path:
        console.print(f"  • Unit tests:      {test_path}")
    if not args.no_report:
        console.print(
            f"  • Audit report:    {inputs['target_name']}_optimization_report.md"
        )
    if stage_html_path:
        console.print(f"  • Stage report:    {stage_html_path}")
    console.print(f"  • App console:     {app_url}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _build_parser().parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
