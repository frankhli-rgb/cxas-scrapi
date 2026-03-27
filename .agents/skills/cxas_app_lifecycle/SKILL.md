---
name: cxas-app-lifecycle
description: Manages Google Cloud CX Agent Studio Apps via the cxas CLI. Use when you need to pull, push, list, branch, create, or get details of CXAS apps. Do not use for general Google Cloud functions outside of CX Agent Studio.
---

# CXAS App Lifecycle Management

This cheatsheet provides the exact commands for managing CX Agent Studio apps locally using `cxas-eval`. Always run `source .venv/bin/activate` before executing these commands.

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
cxas apps get {app_identifier} --project_id {project_id} --location {location}
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
cxas pull {app_identifier} --project_id {project_id} --location {location} --target_dir {local_dir}
```

### 5. Push Local Files
Upload the local agent directory to CXAS:
```bash
cxas push --agent_dir {local_dir} --to {app_identifier} --project_id {project_id} --location {location}
```
*To force-overwrite a specific app instead of using display name, use `--app_id {target_uuid}` instead of `--to`.*

### 6. Branch an App
Duplicate an existing app (pulls source -> creates new -> pushes content):
```bash
cxas branch "{source_app}" --new_name "{new_display_name}" --project_id {project_id} --location {location}
```
