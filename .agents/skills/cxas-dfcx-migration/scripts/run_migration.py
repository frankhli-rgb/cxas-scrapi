#!/usr/bin/env python3

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
import logging
import os
import sys
from datetime import datetime

from rich.console import Console
from rich.logging import RichHandler
from rich.prompt import Confirm, Prompt
from rich.table import Table

from cxas_scrapi.migration.config import AGENT_MODELS, DEFAULT_MODEL
from cxas_scrapi.migration.data_models import MigrationConfig
from cxas_scrapi.migration.dfcx_dep_analyzer import DependencyAnalyzer
from cxas_scrapi.migration.dfcx_exporter import ConversationalAgentsAPI
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

    table = Table(title="Resources Status")
    table.add_column("Type", style="cyan")
    table.add_column("Name", style="magenta")
    table.add_column("Status", style="green")

    for tool in ir.tools.values():
        table.add_row(tool.type, tool.id, tool.status.value)

    for agent in ir.agents.values():
        table.add_row(agent.type, agent.display_name, agent.status.value)

    console.print(table)


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


if __name__ == "__main__":
    main()
