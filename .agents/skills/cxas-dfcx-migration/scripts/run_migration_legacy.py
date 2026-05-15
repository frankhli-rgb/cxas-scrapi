#!/usr/bin/env python3
# DEPRECATED — replaced by `migrate.py` (and `stage1.py` / `stage2.py` for
# optimization). See SKILL.md. This file is kept for one release cycle.
import sys as _sys
print(
    "[deprecation] run_migration.py is deprecated. Use migrate.py / stage1.py "
    "/ stage2.py instead.",
    file=_sys.stderr,
)

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

"""CLI script for migrating DFCX agents to CXAS.

Supports both fully scripted (via CLI args) and interactive modes.
Mirrors the options from CLIDashboard.compose_config() and
CLIDashboard.run() in cli_dashboard.py.
"""

import argparse
import asyncio
import copy
import json
import logging
import os
import sys
from datetime import datetime

from rich.console import Console
from rich.logging import RichHandler
from rich.prompt import Confirm, Prompt
from rich.table import Table

# Skill-local helpers (sit alongside this script).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _phase_tracker  # noqa: E402
import _shared  # noqa: E402
import _visualizer  # noqa: E402

from cxas_scrapi.core.versions import Versions
from cxas_scrapi.migration.config import AGENT_MODELS, DEFAULT_MODEL
from cxas_scrapi.migration.data_models import MigrationConfig
from cxas_scrapi.migration.dfcx_dep_analyzer import DependencyAnalyzer
from cxas_scrapi.migration.dfcx_exporter import ConversationalAgentsAPI
from cxas_scrapi.migration.eval_generator import DeterministicEvalGenerator
from cxas_scrapi.migration.main_visualizer import MainVisualizer
from cxas_scrapi.migration.service import MigrationService

logger = logging.getLogger(__name__)
console = Console()


def load_source_agent(args):
    """Load source agent data from Agent ID or Zip file."""
    cx_api = ConversationalAgentsAPI()

    if args.zip_file:
        zip_path = os.path.expanduser(args.zip_file)
        console.print(f"Loading agent from zip: {zip_path}")
        with open(zip_path, "rb") as f:
            content = f.read()
        agent_data = cx_api.process_local_agent_zip(content)
        agent_id = "uploaded-agent"
    elif args.source_agent_id:
        agent_id = args.source_agent_id
        console.print(f"Loading Agent ID: {agent_id}")
        agent_data = cx_api.fetch_full_agent_details(agent_id, use_export=True)
    else:
        choice = Prompt.ask(
            "Load source agent from",
            choices=["ID", "Zip File"],
            default="Zip File",
        )
        if choice == "ID":
            source_project = Prompt.ask("Enter Source Project ID")
            source_location = Prompt.ask("Enter Source Location", default="global")
            
            console.print(f"Fetching agents for project {source_project} in {source_location}...")
            try:
                agents = cx_api.list_agents(source_project, source_location)
            except Exception as e:
                console.print(f"[red]Failed to list agents: {e}[/]")
                agents = []
                
            if agents:
                console.print("[bold]Available Agents:[/]")
                for i, agent in enumerate(agents, 1):
                    console.print(f"  {i}. {agent.get('displayName')} ({agent.get('name')})")
                console.print(f"  {len(agents) + 1}. Enter ID manually")
                
                choice_idx = Prompt.ask("Select an agent", default="1")
                
                try:
                    idx = int(choice_idx)
                    if 1 <= idx <= len(agents):
                        agent_id = agents[idx - 1]['name']
                    elif idx == len(agents) + 1:
                        agent_id = Prompt.ask("Enter Source Agent ID")
                    else:
                        console.print("[yellow]Invalid selection. Entering manual mode.[/]")
                        agent_id = Prompt.ask("Enter Source Agent ID")
                except ValueError:
                    if choice_idx.startswith("projects/"):
                        agent_id = choice_idx
                    else:
                        console.print("[yellow]Invalid input. Entering manual mode.[/]")
                        agent_id = Prompt.ask("Enter Source Agent ID")
            else:
                console.print("No agents found or failed to list. Please enter manually.")
                agent_id = Prompt.ask("Enter Source Agent ID")
                
            console.print(f"Loading Agent ID: {agent_id}")
            agent_data = cx_api.fetch_full_agent_details(
                agent_id, use_export=True
            )
        else:
            zip_path = Prompt.ask("Enter path to local agent export (.zip)")
            zip_path = os.path.expanduser(zip_path)
            console.print(f"Loading agent from {zip_path}")
            with open(zip_path, "rb") as f:
                content = f.read()
            agent_data = cx_api.process_local_agent_zip(content)
            agent_id = "uploaded-agent"

    if not agent_data:
        console.print("[red]Failed to load agent data.[/]")
        sys.exit(1)

    console.print("[green]Agent data loaded successfully.[/]")
    return agent_data, agent_id, cx_api


def collect_config(args):
    """Collect migration configuration from args or interactive prompts."""
    default_name = (
        f"migrated_agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    project_id = args.project_id or Prompt.ask("Enter Google Cloud Project ID")

    target_name = args.target_name or Prompt.ask(
        "Enter Target Agent Name", default=default_name
    )

    env = args.env or Prompt.ask(
        "Enter Environment", choices=["PROD", "AUTOPUSH"], default="PROD"
    )

    model = args.model or Prompt.ask(
        "Enter Global App Model",
        choices=AGENT_MODELS,
        default=DEFAULT_MODEL,
    )

    migration_version = args.migration_version or Prompt.ask(
        "Enter Logic Version", choices=["1.0", "2.0"], default="2.0"
    )

    if args.gen_report is not None:
        gen_report = args.gen_report
    else:
        gen_report = Confirm.ask("Generate Migration Report?", default=True)

    if args.gen_unit_tests is not None:
        gen_unit_tests = args.gen_unit_tests
    else:
        gen_unit_tests = Confirm.ask(
            "Generate Unit Tests (Auto-Fix)?", default=True
        )

    if args.gen_hillclimbing_evals is not None:
        gen_hillclimbing_evals = args.gen_hillclimbing_evals
    else:
        gen_hillclimbing_evals = Confirm.ask(
            "Generate Hillclimbing Evals?", default=False
        )

    eval_runner_target = args.eval_runner_target or Prompt.ask(
        "Enter Eval Target",
        choices=["Custom API Runner", "Native Product Eval (Stub)"],
        default="Custom API Runner",
    )

    if args.optimize_for_cxas is not None:
        optimize_for_cxas = args.optimize_for_cxas
    else:
        optimize_for_cxas = Confirm.ask("Optimize for CXAS?", default=False)

    return MigrationConfig(
        project_id=project_id,
        target_name=target_name,
        env=env,
        model=model,
        gen_report=gen_report,
        gen_unit_tests=gen_unit_tests,
        gen_hillclimbing_evals=gen_hillclimbing_evals,
        eval_runner_target=eval_runner_target,
        migration_version=migration_version,
        optimize_for_cxas=optimize_for_cxas,
    )


def select_resources(agent_data):
    """Prompt user to select resources to migrate."""
    console.print("\n[bold blue]=== Resource Selection ===[/]\n")

    playbooks = agent_data.playbooks
    flows = agent_data.flows

    all_resources = []
    for pb in playbooks:
        all_resources.append(
            ("Playbook", pb.get("displayName", "Unnamed"), pb)
        )
    for flow in flows:
        f = flow.flow_data
        all_resources.append(
            ("Flow", f.get("displayName", "Unnamed"), flow)
        )

    if not all_resources:
        console.print("No playbooks or flows found in agent data.")
        return agent_data

    console.print("[bold]Available Resources:[/]")
    for i, (res_type, name, _) in enumerate(all_resources, 1):
        console.print(f"  {i}. [{res_type}] {name}")

    console.print("\nOptions:")
    console.print("  - Press Enter to start with ALL selected")
    console.print("  - Enter 'none' to start with NONE selected")
    console.print(
        "  - Enter comma-separated numbers to EXCLUDE/INCLUDE"
    )

    mode = Prompt.ask("Your choice", default="")

    if mode.lower() == "none":
        console.print(
            "\n[bold]Enter comma-separated numbers to INCLUDE "
            "(e.g., 1,3) or Enter to finish:[/]"
        )
        answer = Prompt.ask("Include numbers", default="")
        is_include = True
    else:
        console.print(
            "\n[bold]Enter comma-separated numbers to EXCLUDE "
            "(e.g., 1,3) or Enter to finish:[/]"
        )
        answer = Prompt.ask("Exclude numbers", default="")
        is_include = False

    if not answer:
        if is_include:
            filtered_data = agent_data.model_copy()
            filtered_data.playbooks = []
            filtered_data.flows = []
            return filtered_data
        else:
            return agent_data

    try:
        indices = []
        for part in answer.split(","):
            part = part.strip()
            if "-" in part:
                start, end = map(int, part.split("-"))
                indices.extend(range(start, end + 1))
            else:
                indices.append(int(part))

        indices = [i - 1 for i in indices]

        selected_playbooks = []
        selected_flows = []

        for i, (res_type, _name, data) in enumerate(all_resources):
            should_select = i in indices if is_include else i not in indices
            if should_select:
                if res_type == "Playbook":
                    selected_playbooks.append(data)
                elif res_type == "Flow":
                    selected_flows.append(data)

        filtered_data = agent_data.model_copy()
        filtered_data.playbooks = selected_playbooks
        filtered_data.flows = selected_flows
        return filtered_data

    except ValueError:
        console.print(
            "[red]Invalid input. Proceeding with default selection.[/]"
        )
        if is_include:
            filtered_data = agent_data.model_copy()
            filtered_data.playbooks = []
            filtered_data.flows = []
            return filtered_data
        else:
            return agent_data


def run_dependency_analysis(full_data, filtered_data):
    """Run dependency analysis and show results."""
    console.print("\n[bold blue]=== Dependency Analysis ===[/]\n")

    analyzer = DependencyAnalyzer(full_data)

    selected_ids = []
    for pb in filtered_data.playbooks:
        selected_ids.append(pb.get("name"))
    for flow in filtered_data.flows:
        f = flow.flow_data
        selected_ids.append(f.get("name"))

    outgoing, incoming = analyzer.get_impact(selected_ids)

    if outgoing:
        console.print("[yellow]Missing Dependencies (Outgoing):[/]")
        console.print(
            " The selected resources reference these items, "
            "but they are NOT selected:"
        )
        for rid in outgoing:
            det = analyzer.get_details(rid)
            console.print(f"  - [{det['type']}] {det['name']}")
    else:
        console.print("[green]No missing dependencies detected.[/]")

    if incoming:
        console.print("\n[cyan]Incoming References:[/]")
        console.print(
            " These unselected resources reference your selection:"
        )
        for rid in incoming:
            det = analyzer.get_details(rid)
            console.print(f"  - [{det['type']}] {det['name']}")


def display_status(ir):
    """Display the status of resources in the IR."""
    console.print("\n[bold blue]=== Migration Status ===[/]\n")
    _shared.display_status_table(ir, console, title="Resources Status")


def export_unit_tests(ir, target_name: str) -> tuple[dict[str, int], str] | None:
    """Generate deterministic unit tests via DeterministicEvalGenerator and
    write them to <target>_unit_tests.json. Returns (per-agent counts, path)
    or None on failure / no tests."""
    try:
        generator = DeterministicEvalGenerator(ir)
        by_agent: dict[str, list] = {}
        for agent_name in ir.agents:
            tests = generator.generate_tests_for_agent(agent_name)
            if tests:
                by_agent[agent_name] = [tc.model_dump(mode="json") for tc in tests]
        if not by_agent:
            return None
        path = f"{target_name}_unit_tests.json"
        with open(path, "w") as f:
            json.dump(by_agent, f, indent=2, default=str)
        counts = {name: len(cases) for name, cases in by_agent.items()}
        console.print(
            f"[green]Wrote {sum(counts.values())} deterministic tests for "
            f"{len(counts)} agents → {path}[/]"
        )
        return counts, path
    except Exception as exc:  # noqa: BLE001
        logger.warning("Deterministic unit test generation failed: %s", exc)
        console.print(f"[yellow]Unit test generation failed: {exc}[/]")
        return None


def surface_versions(ir) -> list[tuple[str, str]]:
    """List CXAS Version checkpoints created during the migration (only
    populated when optimize_for_cxas=True). Returns [(display_name, name), ...]."""
    app_resource = ir.metadata.app_resource_name
    if not app_resource:
        return []
    try:
        client = Versions(app_resource)
        versions = client.list_versions()
        rows = [(v.display_name, v.name) for v in versions]
        if rows:
            console.print("\n[bold]CXAS Version checkpoints:[/]")
            for display, name in rows:
                console.print(f"  • {display}  ({name})")
        return rows
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not list versions: %s", exc)
        return []


def get_parser():
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Migrate a DFCX agent to CXAS.",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--source-agent-id",
        help=(
            "Full resource name of the source DFCX agent.\n"
            "Format: projects/<project>/locations/<location>/agents/<uuid>"
        ),
    )
    source_group.add_argument(
        "--zip-file",
        help="Path to a local DFCX agent export (.zip).",
    )

    parser.add_argument(
        "--project-id",
        help="Target Google Cloud Project ID.",
    )
    parser.add_argument(
        "--target-name",
        help="Display name for the new CXAS agent.",
    )
    parser.add_argument(
        "--env",
        choices=["PROD", "AUTOPUSH"],
        help="Deployment environment (default: PROD).",
    )
    parser.add_argument(
        "--model",
        choices=AGENT_MODELS,
        help=f"Global app model (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--migration-version",
        choices=["1.0", "2.0"],
        help="Logic version (default: 2.0).",
    )
    parser.add_argument(
        "--location",
        default="global",
        help="GCP location for the CXAS app (default: global).",
    )

    parser.add_argument(
        "--gen-report",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Generate migration report (default: yes).",
    )
    parser.add_argument(
        "--gen-unit-tests",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Generate unit tests with auto-fix (default: yes).",
    )
    parser.add_argument(
        "--gen-hillclimbing-evals",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Generate hillclimbing evals (default: no).",
    )
    parser.add_argument(
        "--eval-runner-target",
        choices=["Custom API Runner", "Native Product Eval (Stub)"],
        help="Eval runner backend (default: Custom API Runner).",
    )
    parser.add_argument(
        "--optimize-for-cxas",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Apply CXAS-specific optimizations (default: no).",
    )

    parser.add_argument(
        "--skip-resource-selection",
        action="store_true",
        help="Skip interactive resource selection (migrate all).",
    )
    parser.add_argument(
        "--skip-dependency-analysis",
        action="store_true",
        help="Skip dependency analysis.",
    )
    parser.add_argument(
        "--skip-visualization",
        action="store_true",
        help="Skip visualization generation.",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompts.",
    )
    parser.add_argument(
        "--no-preview-html",
        action="store_true",
        help="Skip the pre-migration HTML tree preview.",
    )
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help=(
            "Generate the HTML tree preview and exit (no migration). Useful "
            "for inspecting source agent structure before committing to a "
            "long migration run."
        ),
    )

    return parser


def main():
    parser = get_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )

    console.print(
        "[bold green]DFCX to CXAS Migration Tool[/bold green]"
    )
    console.print(
        "This tool migrates Dialogflow CX agents to CXAS "
        "generative agents.\n"
    )

    # Step 1: Load source agent
    agent_data, agent_id, cx_api = load_source_agent(args)

    # Step 1.5: Pre-migration HTML preview of the extracted DFCX tree.
    if not args.no_preview_html:
        try:
            from cxas_scrapi.migration.dfcx_dep_analyzer import DependencyAnalyzer
            preview_target = args.target_name or "preview"
            analyzer = DependencyAnalyzer(agent_data)
            preview_path = _visualizer.generate_html_report(
                agent_data,
                analyzer,
                output_path=f"{preview_target}_tree_preview.html",
            )
            topo_path, tools_path = _visualizer.write_mermaid_files(
                agent_data, analyzer, preview_target
            )
            stats = _visualizer.collect_stats(agent_data, analyzer)
            console.print()
            console.print(
                f"[bold green]Preview ready:[/] {preview_path}\n"
                f"  • {stats['playbook_count']} playbooks, {stats['flow_count']} flows, "
                f"{stats['tool_count']} tools, {stats['routing_edge_count']} routing edges\n"
                f"  • Estimated 1:1 migration time: ~{stats['estimated_minutes']} min\n"
                f"  • Mermaid sources: {topo_path}, {tools_path}\n"
                f"  • Open the HTML in a browser before kicking off the long migration."
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Preview HTML generation failed: %s", exc)

    if args.preview_only:
        console.print(
            "\n[yellow]--preview-only set; exiting without running the migration.[/]"
        )
        return

    while True:
        # Step 2: Collect configuration
        console.print("\n[bold blue]=== Migration Configuration ===[/]\n")
        config = collect_config(args)

        # Step 3: Resource selection
        if args.skip_resource_selection:
            filtered_data = agent_data
        else:
            filtered_data = select_resources(agent_data)

        # Step 4: Dependency analysis
        if not args.skip_dependency_analysis:
            if args.yes or Confirm.ask(
                "Run Dependency Analysis?", default=True
            ):
                full_data_dict = agent_data
                run_dependency_analysis(full_data_dict, filtered_data)

        # Step 5: Visualization
        if not args.skip_visualization:
            if not args.yes and Confirm.ask(
                "Generate Visualizations (SVG & Markdown)?", default=True
            ):
                visualizer = MainVisualizer(filtered_data)
                prefix = config.target_name or "agent"
                visualizer.export_visualizations(prefix)
                console.print(
                    f"Topology graph exported to: "
                    f"[cyan]{prefix}_topology.svg[/]"
                )
                console.print(
                    f"Detailed resources exported to: "
                    f"[cyan]{prefix}_detailed_resources.md[/]"
                )

        # Step 6: Review
        console.print("\n[bold blue]=== Review ===[/]\n")
        console.print(f"Target Agent:        {config.target_name}")
        console.print(f"Project:             {config.project_id}")
        console.print(f"Environment:         {config.env}")
        console.print(f"Model:               {config.model}")
        console.print(f"Logic Version:       {config.migration_version}")
        console.print(
            f"Selected Playbooks:  {len(filtered_data.playbooks)}"
        )
        console.print(
            f"Selected Flows:      {len(filtered_data.flows)}"
        )

        pb_count = len(filtered_data.playbooks)
        flow_count = len(filtered_data.flows)
        if pb_count > 0 and flow_count == 0:
            migration_type = "Pure Playbooks"
        elif flow_count > 0 and pb_count == 0:
            migration_type = "Pure Flows"
        elif flow_count > 0 and pb_count > 0:
            migration_type = "Hybrid Agent"
        else:
            migration_type = "No Resources Selected"

        console.print(f"Migration Type:      {migration_type}")

        if flow_count > 0 and config.migration_version != "2.0":
            console.print(
                "\n[bold red]WARNING: Flows or Hybrid agents require "
                "Logic Version 2.0. Current version is "
                f"{config.migration_version}.[/]"
            )

        if args.yes or Confirm.ask("Proceed to Migration?", default=True):
            break
        elif not Confirm.ask(
            "Re-configure and re-select resources?", default=True
        ):
            console.print("Aborting migration.")
            return

    # Step 7: Execute migration
    if not args.yes:
        if not Confirm.ask("START MIGRATION?", default=True):
            console.print("Migration cancelled.")
            return

    config.source_agent_data_override = filtered_data

    migration_service = MigrationService(
        project_id=config.project_id,
        location=args.location,
        default_model=config.model,
    )

    console.print(
        f"\nStarting Migration to '{config.target_name}'...\n"
    )

    asyncio.run(
        migration_service.run_migration(
            source_cx_agent_id=agent_id,
            config=config,
        )
    )

    if hasattr(migration_service, "ir") and migration_service.ir:
        display_status(migration_service.ir)

        # Surface in-flight artifacts the user might otherwise miss.
        unit_tests = None
        if config.gen_unit_tests:
            unit_tests = export_unit_tests(
                migration_service.ir, config.target_name
            )
        if config.optimize_for_cxas:
            surface_versions(migration_service.ir)
            stage_logs = (
                migration_service.ir.optimization_logs.get("stages")
                if hasattr(migration_service.ir, "optimization_logs")
                else None
            )
            if stage_logs:
                console.print("\n[bold]CXASOptimizer stage summary:[/]")
                for stage, entries in stage_logs.items():
                    console.print(f"  • {stage}: {len(entries)} log entries")

        # Final summary of artifact paths.
        console.print("\n[bold green]Migration complete.[/]")
        if config.gen_report:
            console.print(
                f"  • Migration report: {config.target_name}_migration_report.md"
            )
        if unit_tests:
            console.print(f"  • Unit tests:       {unit_tests[1]}")
        app_id = getattr(migration_service.ir.metadata, "app_id", None)
        if app_id:
            console.print(
                "  • App console:     "
                f"https://ces.cloud.google.com/projects/{config.project_id}"
                f"/locations/{args.location}/apps/{app_id}"
            )


if __name__ == "__main__":
    main()
