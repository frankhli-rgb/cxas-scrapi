import argparse
import os
import stat
import subprocess
import yaml

from cxas_scrapi.core.common import Common
from cxas_scrapi.core.evaluations import Evaluations
"""Templates used by the CXAS SCRAPI CLI."""

GITHUB_ACTION_TEMPLATE_TEST = """name: "CI Test {agent_name}"

on:
  pull_request:
    paths:
      - '{path_filter}/*.yaml'
      - '{path_filter}/*.json'
  workflow_call:

env:
  PROJECT_ID: "{project_id}"
  LOCATION: "{location}"
{auth_env}

jobs:
  test-{agent_name_lower}:
    runs-on: ubuntu-latest

    permissions:
      contents: 'read'
      id-token: 'write'

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Free Disk Space (Ubuntu)
        uses: jlumbroso/free-disk-space@main
        with:
          tool-cache: false
          android: true
          dotnet: true
          haskell: true
          large-packages: true
          docker-images: true
          swap-storage: true

{auth_step}

{setup_gcloud_step}

      - name: Download cxas-scrapi CLI Wheel
        run: |
          gsutil cp gs://cxas-scrapi-github/cxas_scrapi-0.1.3-py3-none-any.whl {github_context_path}/

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build Docker Image
        uses: docker/build-push-action@v5
        with:
          context: {github_context_path}
          load: true
          tags: agent-image
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Run CI Test Lifecycle (Docker)
        run: |
          docker run --rm \\
            -v ${{{{ github.workspace }}}}:/workspace \\
            -w /workspace \\
            -e PROJECT_ID=${{{{ env.PROJECT_ID }}}} \\
            -e LOCATION=${{{{ env.LOCATION }}}} \\
{docker_auth_args}
            agent-image \\
            ci-test --agent_dir {github_context_path} \\
                      --project_id ${{{{ env.PROJECT_ID }}}} \\
                      --location ${{{{ env.LOCATION }}}} \\
                      --display_name "[CI] PR-${{{{ github.event.pull_request.number }}}} {agent_name}"

"""

GITHUB_ACTION_TEMPLATE_DEPLOY = """name: "Deploy {agent_name}"

on:
  push:
    branches:
      - {target_branch}
    paths:
      - '{path_filter}/*.yaml'
      - '{path_filter}/*.json'

env:
  PROJECT_ID: "{project_id}"
  LOCATION: "{location}"
  APP_ID: "{app_id}"
  DISPLAY_NAME: "{agent_name}"
{auth_env}

jobs:
  test-{agent_name_lower}:
    uses: ./.github/workflows/ci_test_{agent_name_lower}.yml
    secrets: inherit

  deploy-{agent_name_lower}:
    needs: test-{agent_name_lower}
    runs-on: ubuntu-latest

    permissions:
      contents: 'read'
      id-token: 'write'

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

{auth_step}

{setup_gcloud_step}

      - name: Install cxas-scrapi CLI
        run: |
          python -m pip install --upgrade pip
          wget https://storage.googleapis.com/gassets-api-ai/ces-client-libraries/v1beta/ces-v1beta-py.tar
          pip install ces-v1beta-py.tar --quiet
          gsutil cp gs://cxas-scrapi-github/cxas_scrapi-0.1.3-py3-none-any.whl .
          pip install cxas_scrapi-0.1.3-py3-none-any.whl

      - name: Deploy to CX Agent Studio
        run: |
          cxas-eval deploy --agent_dir {github_context_path} \\
                           --project_id ${{{{ env.PROJECT_ID }}}} \\
                           --location ${{{{ env.LOCATION }}}} \\
                           --app_id ${{{{ env.APP_ID }}}} \\
                           --display_name "${{{{ env.DISPLAY_NAME }}}}"
"""

GITHUB_ACTION_TEMPLATE_CLEANUP = """name: "Cleanup {agent_name}"

on:
  pull_request:
    types: [closed]
    paths:
      - '{path_filter}/*.yaml'
      - '{path_filter}/*.json'

env:
  PROJECT_ID: "{project_id}"
  LOCATION: "{location}"
{auth_env}

jobs:
  cleanup-{agent_name_lower}:
    runs-on: ubuntu-latest
    if: github.event.pull_request.merged == true || github.event.pull_request.closed == true

    permissions:
      contents: 'read'
      id-token: 'write'

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

{auth_step}

{setup_gcloud_step}

      - name: Install cxas-scrapi CLI
        run: |
          python -m pip install --upgrade pip
          wget https://storage.googleapis.com/gassets-api-ai/ces-client-libraries/v1beta/ces-v1beta-py.tar
          pip install ces-v1beta-py.tar --quiet
          gsutil cp gs://cxas-scrapi-github/cxas_scrapi-0.1.3-py3-none-any.whl .
          pip install cxas_scrapi-0.1.3-py3-none-any.whl

      - name: Run Cleanup
        run: |
          cxas-eval delete --display_name "[CI] PR-${{{{ github.event.pull_request.number }}}} {agent_name}" \\
                   --project_id ${{{{ env.PROJECT_ID }}}} \\
                   --location ${{{{ env.LOCATION }}}}
"""



DOCKERFILE_TEMPLATE = """# Use an official Python runtime as a parent image
FROM python:3.11-slim


# Set the working directory to /app
WORKDIR /app

# Install git and wget (required for pip install git+... and downloading CES lib)
RUN apt-get update && apt-get install -y git wget && rm -rf /var/lib/apt/lists/*

# Install CES Client Library (Pre-requisite) - Cached Layer
RUN wget https://storage.googleapis.com/gassets-api-ai/ces-client-libraries/v1beta/ces-v1beta-py.tar && \\
    pip install ces-v1beta-py.tar --quiet && \\
    rm ces-v1beta-py.tar

# Copy the CLI wheel downloaded by GitHub Actions into the container
COPY cxas_scrapi-*.whl /dist/

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies and local CLI wheel
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install /dist/cxas_scrapi-*.whl

# Copy the agent code into the container
COPY . .

# Set the entrypoint to cxas-scrapi
ENTRYPOINT ["cxas-eval"]
"""


def init_github_action(args: argparse.Namespace) -> None:
    """Handles the 'init-github-action' command."""

    print("Generating GitHub Actions workflow template...")

    agent_name = args.agent_name
    app_id = args.app_id

    # Try to extract details from app.yaml if available
    agent_dir = args.agent_dir if args.agent_dir else "."
    app_yaml_path = os.path.join(agent_dir, "app.yaml")

    if os.path.exists(app_yaml_path):
        try:
            with open(app_yaml_path, "r") as f:
                app_data = yaml.safe_load(f)
                if not agent_name and "displayName" in app_data:
                    agent_name = app_data["displayName"]
                if not app_id and "name" in app_data:
                    app_id = app_data["name"]
        except Exception as e:
            print(f"Warning: Could not parse {app_yaml_path}: {e}")

    # Fallback to defaults
    if not agent_name:
        agent_name = "agent"

    # Extract project_id and location from app_id if it exists
    extracted_project = Common._get_project_id(app_id) if app_id else None
    extracted_location = Common._get_location(app_id) if app_id else None

    project_id = getattr(args, "project_id", None) or extracted_project or "YOUR_PROJECT_ID"
    location = getattr(args, "location", None) or extracted_location or "global"

    if not app_id:
        app_basename = os.path.basename(os.path.abspath(agent_dir))
        app_id = f"projects/{project_id}/locations/{location}/apps/{app_basename}"
        print(
            f"Warning: No --app_id provided and could not retrieve 'name' from {app_yaml_path}."
        )
        print(f"Synthesizing app identifier from directory name: {app_id}")

    output_path = (
        args.output
        if args.output
        else f".github/workflows/test_{agent_name.lower()}.yml"
    )

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    eval_id = args.evaluation_id
    eval_comments = ""

    # Try to fetch real evaluations if app_id is valid
    if not eval_id and app_id and "YOUR_PROJECT_ID" not in app_id:
        try:

            print(f"Fetching evaluations for {app_id}...")
            eval_client = Evaluations(app_id=app_id)
            evals_map = eval_client.get_evaluations_map()

            if evals_map and (evals_map.get("goldens") or evals_map.get("scenarios")):
                all_evals = list(evals_map.get("goldens", {}).keys()) + list(
                    evals_map.get("scenarios", {}).keys()
                )
                eval_id = all_evals[0]
                print(
                    f"Found {len(all_evals)} evaluations. Using '{eval_id}' as default."
                )

                if len(all_evals) > 1:
                    eval_comments = "\n  # Other evaluations found for reference:\n"
                    for name in all_evals[1:]:
                        # Reverse lookup the display names from the maps
                        display_name = evals_map.get("goldens", {}).get(
                            name
                        ) or evals_map.get("scenarios", {}).get(name)
                        eval_comments += f"  # - {name} ({display_name})\n"
            else:
                print(f"No evaluations found for {app_id}. Using placeholder.")
                eval_id = f"{app_id}/evaluations/YOUR_EVAL_ID"
        except Exception as e:
            print(f"Warning: Could not fetch evaluations: {e}")
            eval_id = f"{app_id}/evaluations/YOUR_EVAL_ID"
    elif not eval_id:
        eval_id = f"{app_id}/evaluations/YOUR_EVAL_ID"


    wip = (
        args.workload_identity_provider
        if args.workload_identity_provider
        else "projects/YOUR_PROJECT_NUMBER/locations/global/workloadIdentityPools/YOUR_POOL/providers/YOUR_PROVIDER"
    )
    sa = (
        args.service_account
        if args.service_account
        else "YOUR_SERVICE_ACCOUNT@YOUR_PROJECT.iam.gserviceaccount.com"
    )

    # Generate the path string. If they used an absolute path like `/Users/.../pilot`, just use `pilot/**`
    agent_basename = os.path.basename(agent_dir.rstrip(os.sep))
    path_filter = f"{agent_basename}/**" if agent_dir != "." else "**"
    github_context_path = agent_basename if agent_dir != "." else "."

    # Configure auth blocks
    auth_method = args.auth_method
    if auth_method == "wif":
        auth_env = f"""  GCP_WORKLOAD_IDENTITY_PROVIDER: "{wip}"
  GCP_SERVICE_ACCOUNT: "{sa}" """
        auth_step = f"""      # Authenticate to Google Cloud via Workload Identity Federation
      # See https://github.com/google-github-actions/auth for configuration instructions
      - name: Authenticate to Google Cloud
        id: auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{{{ env.GCP_WORKLOAD_IDENTITY_PROVIDER }}}}
          service_account: ${{{{ env.GCP_SERVICE_ACCOUNT }}}}"""
        setup_gcloud_step = """      - name: Set up Cloud SDK
        uses: google-github-actions/setup-gcloud@v2

      - name: Configure Docker Auth
        run: gcloud auth configure-docker us-central1-docker.pkg.dev"""
        docker_auth_args = """            -e GOOGLE_APPLICATION_CREDENTIALS=/workspace/application_default_credentials.json \\
            -v ${{ steps.auth.outputs.credentials_file_path }}:/workspace/application_default_credentials.json \\"""
    elif auth_method == "sa_key":
        auth_env = "  # Ensure GCP_CREDENTIALS containing your JSON key is in your GitHub Secrets"
        auth_step = f"""      # Authenticate to Google Cloud using a Service Account JSON Key
      - name: Authenticate to Google Cloud
        id: auth
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{{{ secrets.GCP_CREDENTIALS }}}}"""
        setup_gcloud_step = """      - name: Set up Cloud SDK
        uses: google-github-actions/setup-gcloud@v2

      - name: Configure Docker Auth
        run: gcloud auth configure-docker us-central1-docker.pkg.dev"""
        docker_auth_args = """            -e GOOGLE_APPLICATION_CREDENTIALS=/workspace/application_default_credentials.json \\
            -v ${{ steps.auth.outputs.credentials_file_path }}:/workspace/application_default_credentials.json \\"""
    elif auth_method == "api_key":
        auth_env = "  # Store your API Key string (starting with AIza) in GitHub Secrets\n  GOOGLE_API_KEY: ${{ secrets.GCP_API_KEY }}"
        auth_step = """      # Authentication is handled via the GOOGLE_API_KEY environment variable defined above.
      # No separate auth step is necessary."""
        setup_gcloud_step = ""
        docker_auth_args = """            -e GOOGLE_API_KEY=${{ env.GOOGLE_API_KEY }} \\"""
    elif auth_method == "oauth_token":
        auth_env = "  # Store your OAuth Token string in GitHub Secrets\n  CXAS_OAUTH_TOKEN: ${{ secrets.CXAS_OAUTH_TOKEN }}"
        auth_step = """      # Authentication is handled via the CXAS_OAUTH_TOKEN environment variable defined above.
      # No separate auth step is necessary."""
        setup_gcloud_step = ""
        docker_auth_args = """            -e CXAS_OAUTH_TOKEN=${{ env.CXAS_OAUTH_TOKEN }} \\"""


    import re
    safe_agent_name = agent_name.lower().replace(" ", "_")
    safe_agent_name = re.sub(r'[^a-z0-9_-]', '', safe_agent_name)

    test_template = GITHUB_ACTION_TEMPLATE_TEST.format(
        agent_name=agent_name.capitalize(),
        agent_name_lower=safe_agent_name,
        path_filter=path_filter,
        github_context_path=github_context_path,
        project_id=project_id,
        location=location,
        auth_env=auth_env,
        auth_step=auth_step,
        setup_gcloud_step=setup_gcloud_step,
        docker_auth_args=docker_auth_args,
    )

    deploy_template = GITHUB_ACTION_TEMPLATE_DEPLOY.format(
        agent_name=agent_name.capitalize(),
        agent_name_lower=safe_agent_name,
        target_branch=args.branch,
        path_filter=path_filter,
        github_context_path=github_context_path,
        app_id=app_id,
        project_id=project_id,
        location=location,
        auth_env=auth_env,
        auth_step=auth_step,
        setup_gcloud_step=setup_gcloud_step,
    )


    # We want to output the GitHub Actions workflows into the `.github/workflows` directory
    # of the target agent's Git repository, rather than the directory where the user happens
    # to be running the `cxas-eval` command from. We use `git rev-parse` to find this root.
    try:
        agent_abs_path = os.path.abspath(agent_dir)
        git_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=agent_abs_path,
            text=True,
            stderr=subprocess.DEVNULL
        ).strip()

        # Security/Sanity Check: Ensure the git_root we found actually encapsulates the agent_dir.
        # If the user runs the CLI from a git repo (cxas-scrapi) but points --agent_dir to an
        # un-tracked sibling folder (/tmp/agent), `git` might accidentally resolve the cxas-scrapi repo!
        if os.path.commonpath([git_root, agent_abs_path]) != git_root:
            raise ValueError("Discovered Git root does not encapsulate the agent directory.")

    except Exception:
        # Fallback to the provided agent directory if it's not a git repository
        git_root = os.path.abspath(agent_dir)

    workflows_dir = os.path.join(git_root, ".github", "workflows")
    os.makedirs(workflows_dir, exist_ok=True)

    test_output_path = (
        args.output
        if args.output
        else os.path.join(workflows_dir, f"ci_test_{safe_agent_name}.yml")
    )
    deploy_output_path = (
        args.output
        if args.output
        else os.path.join(workflows_dir, f"deploy_{safe_agent_name}.yml")
    )

    with open(test_output_path, "w") as f:
        f.write(test_template)

    if not args.output:
        with open(deploy_output_path, "w") as f:
            f.write(deploy_template)

    if not args.no_cleanup:
        cleanup_template = GITHUB_ACTION_TEMPLATE_CLEANUP.format(
            agent_name=agent_name.capitalize(),
            agent_name_lower=safe_agent_name,
            path_filter=path_filter,
            github_context_path=github_context_path,
            project_id=project_id,
            location=location,
            auth_env=auth_env,
            auth_step=auth_step,
            setup_gcloud_step=setup_gcloud_step,
        )
        cleanup_output_path = (
            os.path.join(os.path.dirname(args.output), f"cleanup_{safe_agent_name}.yml")
            if args.output
            else os.path.join(workflows_dir, f"cleanup_{safe_agent_name}.yml")
        )

        with open(cleanup_output_path, "w") as f:
            f.write(cleanup_template)
        print(f"Generated cleanup workflow: {cleanup_output_path}")

    # Generate Dockerfile if it doesn't exist

    dockerfile_path = os.path.join(agent_dir, "Dockerfile")
    if not os.path.exists(dockerfile_path):
        print(f"Generating Dockerfile at {dockerfile_path}...")
        with open(dockerfile_path, "w") as f:
            f.write(DOCKERFILE_TEMPLATE)
    else:
        print(f"Dockerfile already exists at {dockerfile_path}. Skipping generation.")

    # Generate requirements.txt if it doesn't exist
    requirements_path = os.path.join(agent_dir, "requirements.txt")
    if not os.path.exists(requirements_path):
        print(f"Generating requirements.txt at {requirements_path}...")
        with open(requirements_path, "w") as f:
            f.write("# Add your agent dependencies here\n")
            f.write("cxas-scrapi  # Required for CI/CD workflows\n")
            f.write("# google-cloud-ces  # Uncomment if needed\n")
    else:
        print(f"requirements.txt already exists at {requirements_path}. Skipping generation.")

    print(
        f"Successfully generated GitHub Actions workflows to {os.path.dirname(test_output_path)}"
    )

    if args.install_hook:
        hook_path = os.path.join(git_root, ".git", "hooks", "pre-push")
        git_dir = os.path.join(git_root, ".git")
        if os.path.exists(git_dir):
            os.makedirs(os.path.dirname(hook_path), exist_ok=True)
            print(f"Installing pre-push hook at {hook_path}...")

            hook_content = f"""#!/bin/sh
# CXAS SCRAPI Auto-generated Hook
echo "Running local tests before push..."
cxas-eval local-test --agent_dir "{agent_dir}" --project_id "{project_id}" --location "{location}"
"""
            with open(hook_path, "w") as f:
                f.write(hook_content)

            # Make executable
            st = os.stat(hook_path)
            os.chmod(hook_path, st.st_mode | stat.S_IEXEC)
            print("Pre-push hook installed successfully.")
        else:
            print("Warning: Not a git repository root. Skipping hook installation.")
