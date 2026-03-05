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

"""CLI script for running CXAS SCRAPI evaluations."""


import argparse
from typing import Any, Dict, List, Optional
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

import pandas as pd

from cxas_scrapi.core.github import init_github_action
from cxas_scrapi.core.apps import Apps
from cxas_scrapi.core.common import Common
from cxas_scrapi.core.evaluations import Evaluations
from cxas_scrapi.utils.eval_utils import EvalUtils

logger = logging.getLogger(__name__)


def export_eval(args: argparse.Namespace) -> None:
    """Handles the 'export' command."""

    print(f"Exporting evaluation: {args.evaluation_id}")
    # We pass app_id just to initialize the client properly, even though the evaluation ID itself might be the full resource name.
    eval_client = Evaluations(app_id=args.app_id)

    try:
        exported_eval = eval_client.export_evaluation(
            args.evaluation_id, output_format=args.format
        )
        if args.output:
            with open(args.output, "w") as f:
                f.write(exported_eval)
            print(f"Evaluation exported to {args.output}")
        else:
            print(exported_eval)

    except Exception as e:
        print(f"Failed to export evaluation: {e}")
        sys.exit(1)


def wait_for_evaluation_completion(
    eval_utils: EvalUtils, old_result_ids: List[str], app_id: str, timeout_seconds: int = 600
) -> Dict[str, pd.DataFrame]:
    """Waits for a new evaluation result to appear."""
    print("Waiting for evaluation to complete...")
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        # Fetch current evaluation results
        try:
            df_dict = eval_utils.evals_to_dataframe()
            df_current = df_dict.get("summary", pd.DataFrame())
            if df_current.empty:
                time.sleep(5)
                continue

            # Find new runs
            current_result_ids = set(df_current["eval_result_id"].unique())
            new_ids = current_result_ids - old_result_ids

            if new_ids:
                # Assuming one new run at a time for simplicity
                new_run_id = list(new_ids)[0]
                print(f"Evaluation completed. Result ID: {new_run_id}")

                filtered_dict = {}
                for k, v in df_dict.items():
                    if not v.empty and "eval_result_id" in v.columns:
                        filtered_dict[k] = v[v["eval_result_id"] == new_run_id]
                    else:
                        filtered_dict[k] = v
                return filtered_dict

        except Exception as e:
            print(f"Error checking evaluation status: {e}")

        time.sleep(5)

    print("Timeout waiting for evaluation to complete.")
    sys.exit(1)


def filter_metrics_and_assess(df_dict_new_run: Dict[str, pd.DataFrame], filter_auto_metrics: bool) -> bool:
    """Assesses the evaluation run and returns True if passed, False otherwise."""
    passed = True

    df_new_run = df_dict_new_run.get("summary", pd.DataFrame())
    df_expectations = df_dict_new_run.get("expectations", pd.DataFrame())

    # Standard assessment: check standard status first
    # This might encompass semantic and hallucination metrics

    overall_status = (
        df_new_run["evaluation_status"].iloc[0] if not df_new_run.empty else "UNKNOWN"
    )
    print(f"\n--- Evaluation Status: {overall_status} ---")

    if filter_auto_metrics:
        print(
            "\n[Targeted Assessment] Filtering out automated LLM metrics (semantic similarity, hallucination)."
        )
        print("Focusing strictly on custom expectations and tool invocation.")

        if not df_expectations.empty and "record_type" in df_expectations.columns:
            expectation_rows = df_expectations[
                df_expectations["record_type"] == "summary_expectation"
            ]
        else:
            expectation_rows = pd.DataFrame()

        if not expectation_rows.empty:
            failed_expectations = expectation_rows[
                expectation_rows["not_met_count"] > 0
            ]
            if not failed_expectations.empty:
                print(
                    f"FAILED: {len(failed_expectations)} custom expectations not met."
                )
                for _, row in failed_expectations.iterrows():
                    print(
                        f"  - Expectation: {row['expectation']} (Met: {row['met_count']}, Not Met: {row['not_met_count']})"
                    )
                passed = False
            else:
                print(f"PASSED: All {len(expectation_rows)} custom expectations met.")
        else:
            print("WARNING: No custom expectations found in this evaluation.")
            # Fallback: check basic tool invocation if we want

    else:
        # Strict overall pass/fail based on the server
        if overall_status != "PASSED":
            passed = False

    return passed


def run_eval(args: argparse.Namespace) -> None:
    """Handles the 'run' command."""

    print(f"Triggering evaluation: {args.evaluation_id} for App: {args.app_id}")
    eval_client = Evaluations(app_id=args.app_id)
    eval_utils = EvalUtils(app_id=args.app_id)

    try:
        # Step 1: Capture existing evaluation runs to diff against later
        df_initial = eval_utils.evals_to_dataframe().get("summary", pd.DataFrame())
        old_result_ids = set()
        if not df_initial.empty and "eval_result_id" in df_initial.columns:
            old_result_ids = set(df_initial["eval_result_id"].unique())

        # Step 2: Trigger evaluation
        eval_client.run_evaluation(evaluations=[args.evaluation_id], app_id=args.app_id)
        print("Evaluation triggered successfully based on CLI call.")

        # Step 3: Wait and Assess
        if args.wait:
            df_new_run = wait_for_evaluation_completion(
                eval_utils, old_result_ids, args.app_id
            )
            pass_status = filter_metrics_and_assess(
                df_new_run, args.filter_auto_metrics
            )

            if pass_status:
                print("\nFINAL RESULT: PASS")
                sys.exit(0)
            else:
                print("\nFINAL RESULT: FAIL")
                sys.exit(1)

    except Exception as e:
        print(f"Failed to run evaluation: {e}")
        sys.exit(1)


def test_tools(args: argparse.Namespace) -> None:
    """Handles the 'test-tools' command."""

    print(f"Running tool tests for App: {args.app_id} using file: {args.test_file}")
    eval_utils = EvalUtils(app_id=args.app_id)

    try:
        test_cases = eval_utils.load_tool_test_cases_from_file(args.test_file)
        if not test_cases:
            print(f"No valid test cases found in {args.test_file}")
            sys.exit(1)

        results = eval_utils.run_tool_tests(test_cases, debug=args.debug)

        # Check overall status
        failed_count = sum(1 for r in results if r.get("status") != "SUCCESS")

        if failed_count > 0:
            print(f"\nFINAL RESULT: FAIL ({failed_count} tools failed)")
            sys.exit(1)
        else:
            print(f"\nFINAL RESULT: PASS (All {len(results)} tools passed)")
            sys.exit(0)

    except Exception as e:
        print(f"Failed to run tool tests: {e}")
        sys.exit(1)



def deploy_agent(args: argparse.Namespace) -> None:
    """Handles the 'deploy' command."""

    print(f"Deploying agent from {args.agent_dir}...")

    agent_dir = args.agent_dir if args.agent_dir else "."

    temp_dir = tempfile.mkdtemp()

    # We must wrap the agent files in a top-level directory inside the zip, otherwise the CES API rejects it
    inner_dir = os.path.join(temp_dir, "agent")
    os.makedirs(inner_dir)

    # Valid roots for CX Agent Builder to avoid 400 errors
    valid_roots = [
        "app.yaml", "app.json", "global_instruction.txt", "environment.json",
        "agents", "tools", "examples", "guardrails", "toolsets",
        "evaluations", "evaluationDatasets", "evaluationExpectations", "workflows"
    ]

    for item in valid_roots:
        src_path = os.path.join(agent_dir, item)
        if os.path.exists(src_path):
            dst_path = os.path.join(inner_dir, item)
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dst_path)
            else:
                shutil.copy2(src_path, dst_path)

    # Zip the filtered agent directory
    temp_zip = tempfile.mktemp(suffix=".zip")
    shutil.make_archive(temp_zip.replace(".zip", ""), "zip", temp_dir)

    try:
        with open(temp_zip, "rb") as f:
            app_content = f.read()

        apps_client = Apps(project_id=args.project_id, location=args.location)

        display_name = args.display_name if args.display_name else "Deployed Agent"

        print(f"Uploading generic zip to CES...")
        result = apps_client.import_app(
            app_content=app_content,
            display_name=display_name,
        )

        if hasattr(result, "result"):
            print("Waiting for import to complete...")
            imported_app = result.result()
            print(f"Agent successfully deployed: {imported_app.name}")
            return imported_app.name
        else:
            print(f"Agent successfully deployed")
            return getattr(result, "name", None)

    except Exception as e:
        print(f"Failed to deploy agent: {e}")
        sys.exit(1)
    finally:
        if os.path.exists(temp_zip):
            os.remove(temp_zip)


def ci_test(args: argparse.Namespace) -> None:
    """Handles the 'ci-test' command."""

    print("Starting CI Test Lifecycle...")

    if hasattr(args, "display_name") and args.display_name:
        temp_display_name = args.display_name
    else:
        temp_display_name = f"[CI] PR Test {uuid.uuid4().hex[:8]}"

    args.display_name = temp_display_name
    args.app_id = None  # Force create by default

    apps_client = Apps(project_id=args.project_id, location=args.location)

    existing_app = apps_client.get_app_by_display_name(temp_display_name)
    if existing_app:
        print(f"Found existing temp agent: {existing_app.name}. Updating...")
        args.app_id = existing_app.name

    temp_app_name = deploy_agent(args)

    if not temp_app_name:
        print("Failed to get deployed temp app name. CI Test aborting.")
        sys.exit(1)

    try:
        # Run test-tools

        test_file = os.path.join(args.agent_dir, "tests", "tool_tests.yaml")
        if os.path.exists(test_file):
            print(f"\\n--- Running Tool Tests on {temp_app_name} ---")
            cmd = [
                "cxas-eval",
                "test-tools",
                "--app_id",
                temp_app_name,
                "--test_file",
                test_file,
            ]
            print(f"Executing: {' '.join(cmd)}")
            res = subprocess.run(cmd)
            if res.returncode != 0:
                print("Tool tests failed.")
                sys.exit(1)

        # We also need to run evaluations using the SDK or CLI
        print(f"\\n--- Running Evaluations on {temp_app_name} ---")

        evals_client = Evaluations(app_id=temp_app_name)
        evals_map = evals_client.get_evaluations_map()

        if not evals_map or (
            not evals_map.get("goldens") and not evals_map.get("scenarios")
        ):
            print("No evaluations found in the temp app. Skipping run_eval.")
        else:
            all_eval_ids = list(evals_map.get("goldens", {}).values()) + list(
                evals_map.get("scenarios", {}).values()
            )
            for eval_id in all_eval_ids:
                cmd = [
                    "cxas-eval",
                    "run",
                    "--app_id",
                    temp_app_name,
                    "--evaluation_id",
                    eval_id,
                    "--wait",
                    "--filter-auto-metrics",
                ]
                print(f"Executing: {' '.join(cmd)}")
                res = subprocess.run(cmd)
                if res.returncode != 0:
                    print(f"Evaluation '{eval_id}' failed.")
                    sys.exit(1)

        print(
            "\\nCI Test Lifecycle Completed Successfully! Temp agent persists for review."
        )

    except Exception as e:
        print(f"Failed to execute CI Tests: {e}")
        sys.exit(1)


def delete_app(args: argparse.Namespace) -> None:
    """Handles the 'delete' command."""

    if args.app_id:
        print(f"Deleting App: {args.app_id}")
        project_id = Common._get_project_id(args.app_id)
        location = Common._get_location(args.app_id)
        app_id = args.app_id
    elif args.display_name and args.project_id and args.location:
        print(f"Deleting App by Display Name: {args.display_name}")
        project_id = args.project_id
        location = args.location
        app_id = None
    else:
        print(
            "Error: Must provide either --app_id OR (--display_name, --project_id, --location)"
        )
        sys.exit(1)

    if not project_id or not location:
        print("Error: Could not determine project_id or location.")
        sys.exit(1)

    apps_client = Apps(project_id=project_id, location=location)

    try:
        if not app_id:
            # Lookup by display name
            app = apps_client.get_app_by_display_name(args.display_name)
            if app:
                app_id = app.name
                print(f"Found app ID: {app_id}")
            else:
                print(
                    f"App with display name '{args.display_name}' not found. Nothing to delete."
                )
                return

        apps_client.delete_app(app_id=app_id, force=args.force)
        print(f"Successfully deleted {app_id}")
    except Exception as e:
        print(f"Failed to delete app: {e}")
        sys.exit(1)


def local_test(args: argparse.Namespace) -> None:
    """Handles the 'local-test' command."""

    agent_dir = os.path.abspath(args.agent_dir)
    agent_name = os.path.basename(agent_dir.rstrip(os.sep)).lower().replace(" ", "-")
    tag = f"{agent_name}-local-test"

    print(f"Building Docker image for {agent_name}...")
    # We need to build from the agent_dir
    build_cmd = ["docker", "build", "-t", tag, agent_dir]
    if subprocess.call(build_cmd) != 0:
        print("Docker build failed.")
        sys.exit(1)

    print(f"Running tests in Docker container...")

    # Detect ADC
    home = os.path.expanduser("~")
    # Default gcloud location
    adc_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not adc_path:
        adc_path = os.path.join(home, ".config/gcloud/application_default_credentials.json")

    docker_cmd = [
        "docker", "run", "--rm",
        "-v", f"{agent_dir}:/workspace",
        "-w", "/workspace",
        "-e", f"PROJECT_ID={args.project_id}",
        "-e", f"LOCATION={args.location}",
    ]

    oauth_token = os.environ.get("CXAS_OAUTH_TOKEN")

    if oauth_token:
        print("Using provided CXAS_OAUTH_TOKEN.")
        docker_cmd.extend(["-e", "CXAS_OAUTH_TOKEN"])
    elif os.path.exists(adc_path):
        print(f"Mounting credentials from {adc_path}")
        docker_cmd.extend([
            "-e", "GOOGLE_APPLICATION_CREDENTIALS=/tmp/keys/adc.json",
            "-v", f"{adc_path}:/tmp/keys/adc.json:ro"
        ])
    else:
        print("Warning: Application Default Credentials not found. Authentication may fail.")

    display_name = f"[Local] {agent_name}"

    # The command passed to the container
    inner_cmd = [
        tag,
        "ci-test",
        "--agent_dir", "/workspace",
        "--project_id", args.project_id,
        "--location", args.location,
        "--display_name", display_name
    ]

    docker_cmd.extend(inner_cmd)

    print(f"Executing: {' '.join(docker_cmd)}")
    sys.exit(subprocess.call(docker_cmd))

def get_parser() -> argparse.ArgumentParser:
    """Sets up the argument parser."""
    parser = argparse.ArgumentParser(
        description="CXAS SCRAPI Evaluation Runner for CI/CD.",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "--oauth_token",
        help="Optional: OAuth token string for CES API authentication. Alternatively, set CXAS_OAUTH_TOKEN env var.",
        required=False,
    )

    subparsers = parser.add_subparsers(title="Commands", dest="command", required=True)

    # Parser for 'init-github-action'
    parser_init_gh = subparsers.add_parser(
        "init-github-action",
        help="Generate a GitHub Actions workflow file for testing the agent.",
    )
    parser_init_gh.add_argument(
        "--agent_dir",
        help="Optional: The path to the agent directory (e.g., 'pilot') to extract app_id and agent_name from app.yaml.",
    )
    parser_init_gh.add_argument(
        "--app_id",
        help="Optional: The CXAS App ID (projects/.../locations/.../apps/...). If missing, extracts from agent_dir/app.yaml.",
    )
    parser_init_gh.add_argument(
        "--agent_name",
        help="Optional: The name of the agent directory to scope the workflow to (e.g., 'pilot').",
    )
    parser_init_gh.add_argument(
        "--auth_method",
        choices=["wif", "sa_key", "api_key", "oauth_token"],
        default="wif",
        help="Optional: The auth method to configure in the generated workflow. Defaults to 'wif' (Workload Identity).",
    )
    parser_init_gh.add_argument(
        "--evaluation_id",
        help="Optional: The evaluation resource name to run full regression tests.",
    )
    parser_init_gh.add_argument(
        "--workload_identity_provider",
        help="Optional: GCP Workload Identity Provider string.",
    )
    parser_init_gh.add_argument(
        "--service_account",
        help="Optional: GCP Service Account email.",
    )
    parser_init_gh.add_argument(
        "--output",
        help="Optional: Override path where the workflow file will be saved. Defaults to .github/workflows/test_{agent_name}.yml",
    )
    parser_init_gh.add_argument(
        "--branch",
        default="main",
        help="Optional: Target branch for deploy trigger (e.g. main). Defaults to 'main'.",
    )
    parser_init_gh.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Optional: Skip generation of the cleanup workflow.",
    )
    parser_init_gh.add_argument(
        "--install-hook",
        action="store_true",
        help="Optional: Install a git pre-push hook to run local-test automatically.",
    )

    parser_init_gh.set_defaults(func=init_github_action)

    # Parser for 'test-tools'
    parser_test_tools = subparsers.add_parser(
        "test-tools", help="Run local tool unit tests against the deployed agent."
    )
    parser_test_tools.add_argument(
        "--app_id",
        required=True,
        help="The CXAS App ID (projects/.../locations/.../apps/...).",
    )
    parser_test_tools.add_argument(
        "--test_file",
        required=True,
        help="Path to the YAML/JSON file containing tool test definitions.",
    )
    parser_test_tools.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging for tool executions.",
    )

    parser_test_tools.set_defaults(func=test_tools)

    # Parser for 'export'
    parser_export = subparsers.add_parser(
        "export", help="Export an evaluation to YAML or JSON format."
    )
    parser_export.add_argument(
        "--app_id",
        required=True,
        help="The CXAS App ID (projects/.../locations/.../apps/...).",
    )
    parser_export.add_argument(
        "--evaluation_id",
        required=True,
        help="The evaluation resource name (projects/.../locations/.../apps/.../evaluations/...).",
    )
    parser_export.add_argument(
        "--format",
        choices=["yaml", "json"],
        default="yaml",
        help="Export format (yaml or json). Defaults to yaml.",
    )
    parser_export.add_argument(
        "--output",
        help="Path to save the exported evaluation. If not provided, prints to stdout.",
    )

    parser_export.set_defaults(func=export_eval)

    # Parser for 'run'
    parser_run = subparsers.add_parser(
        "run", help="Run an evaluation and assert results."
    )
    parser_run.add_argument(
        "--app_id",
        required=True,
        help="The CXAS App ID (projects/.../locations/.../apps/...).",
    )
    parser_run.add_argument(
        "--evaluation_id",
        required=True,
        help="The evaluation resource name (projects/.../locations/.../apps/.../evaluations/...).",
    )
    parser_run.add_argument(
        "--wait",
        action="store_true",
        help="Wait for evaluation to complete and return exit code 0 on pass or 1 on fail.",
    )
    parser_run.add_argument(
        "--filter-auto-metrics",
        action="store_true",
        help="Filter out automated metrics (semantic similarity, hallucination) and only evaluate custom expectations.",
    )

    parser_run.set_defaults(func=run_eval)

    # Parser for 'deploy'
    parser_deploy = subparsers.add_parser(
        "deploy", help="Zips agent directory and deploys it to CES."
    )
    parser_deploy.add_argument(
        "--agent_dir",
        default=".",
        help="Path to the agent directory to deploy. Defaults to current directory.",
    )
    parser_deploy.add_argument(
        "--project_id",
        required=True,
        help="The GCP Project ID.",
    )
    parser_deploy.add_argument(
        "--location",
        required=True,
        help="The GCP Location (e.g., global, us-central1).",
    )
    parser_deploy.add_argument(
        "--app_id",
        help="Optional: Existing app Resource Name to overwrite (e.g. projects/.../apps/...).",
    )
    parser_deploy.add_argument(
        "--display_name",
        help="Optional: Display name for the newly created app (ignored if --app_id is provided).",
    )
    parser_deploy.set_defaults(func=deploy_agent)

    # Parser for 'ci-test'
    parser_ci_test = subparsers.add_parser(
        "ci-test", help="Runs standard integration tests on a temporary agent."
    )
    parser_ci_test.add_argument(
        "--agent_dir",
        default=".",
        help="Path to the agent directory to test. Defaults to current directory.",
    )
    parser_ci_test.add_argument(
        "--display_name",
        help="Optional: Deterministic display name for the temp agent (e.g. [CI] PR-123). Overwrites existing.",
    )
    parser_ci_test.add_argument(
        "--project_id",
        required=True,
        help="The GCP Project ID.",
    )
    parser_ci_test.add_argument(
        "--location",
        required=True,
        help="The GCP Location (e.g., global, us-central1).",
    )
    parser_ci_test.set_defaults(func=ci_test)

    # Parser for 'delete'
    parser_delete = subparsers.add_parser(
        "delete", help="Deletes a specified agent/app."
    )
    parser_delete.add_argument(
        "--app_id",
        help="The CXAS App ID (projects/.../locations/.../apps/...). Required if --display_name not provided.",
    )
    parser_delete.add_argument(
        "--display_name",
        help="The Display Name of the app to delete. Required if --app_id not provided.",
    )
    parser_delete.add_argument(
        "--project_id",
        help="The GCP Project ID. Required if using --display_name.",
    )
    parser_delete.add_argument(
        "--location",
        help="The GCP Location. Required if using --display_name.",
    )
    parser_delete.add_argument(
        "--force",
        action="store_true",
        help="Force delete even if there are child resources.",
    )
    parser_delete.set_defaults(func=delete_app)

    # Parser for 'local-test'
    parser_local_test = subparsers.add_parser(
        "local-test", help="Runs the agent tests locally using Docker."
    )
    parser_local_test.add_argument(
        "--agent_dir",
        default=".",
        help="Path to the agent directory. Defaults to current directory.",
    )
    parser_local_test.add_argument(
        "--project_id",
        required=True,
        help="The GCP Project ID.",
    )
    parser_local_test.add_argument(
        "--location",
        required=True,
        help="The GCP Location.",
    )
    parser_local_test.set_defaults(func=local_test)


    return parser


def main() -> None:
    parser = get_parser()
    args = parser.parse_args()

    if getattr(args, "oauth_token", None):
        os.environ["CXAS_OAUTH_TOKEN"] = args.oauth_token

    # Configure logging
    log_level = logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
