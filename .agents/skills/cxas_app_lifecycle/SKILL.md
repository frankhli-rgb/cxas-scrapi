---
name: cxas-app-lifecycle
description: Manages Google Cloud CX Agent Studio Apps via the cxas CLI. Use when you need to pull, push, list, branch, create, or get details of CXAS apps. Do not use for general Google Cloud functions outside of CX Agent Studio.
---

# CXAS App Lifecycle Management

This cheatsheet provides the exact commands for managing CX Agent Studio apps locally using `cxas`. Always run `source .venv/bin/activate` before executing these commands.

> [!IMPORTANT]
> **App Identifiers Gotcha:** When specifying an app identifier (e.g., in `pull`, `get`, `push`):
> - If you use a raw **UUID**, the CLI will assume it is a **display name** and fail if it doesn't match a display name.
> - To pull/get by UUID, use the full resource path: `projects/{project_id}/locations/{location}/apps/{app_id}`
> - Alternatively, use the human-readable display name.

## Commands

### 1. List Apps
List all apps in a project:
```bash
cxas apps list --project_id {project_id} --location {location}
```
Example: `cxas apps list --project_id polysynth-test --location us`

### 2. Get App Details
Retrieve details by display name or resource ID:
```bash
# Using Display Name
cxas apps get "{display_name}" --project_id {project_id} --location {location}

# Using UUID
cxas apps get projects/{project_id}/locations/{location}/apps/{app_id}
```

### 3. Create a New App
Bootstrap a new app in CXAS:
```bash
cxas create "{display_name}" --project_id {project_id} --location {location}
```
- Optional: `--description "{description_text}"`
- Optional: `--app_id {specific_uuid}`

### 4. Pull an App
Download and unpack an app into a local directory:
```bash
# Using Display Name
cxas pull "{display_name}" --project_id {project_id} --location {location} --target_dir {local_dir}

# Using UUID
cxas pull projects/{project_id}/locations/{location}/apps/{app_id} --target_dir {local_dir}
```

### 5. Push Local Files
Upload the local agent directory to CXAS. Validate the local agent before pushing.
```bash
cxas validate --app {local_dir}

# Using Display Name
cxas push --agent_dir {local_dir} --to "{display_name}" --project_id {project_id} --location {location}

# Using UUID
cxas push --agent_dir {local_dir} --to projects/{project_id}/locations/{location}/apps/{app_id}
```
*Note: You can also use `--app_id` instead of `--to`, but it still requires the full resource path if passing a UUID.*

### 6. Branch an App
Duplicate an existing app (pulls source -> creates new -> pushes content):
```bash
# Using Display Name
cxas branch "{display_name}" --new_name "{new_display_name}" --project_id {project_id} --location {location}

# Using UUID
cxas branch projects/{project_id}/locations/{location}/apps/{app_id} --new_name "{new_display_name}"
```
