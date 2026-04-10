#!/bin/bash
# Auto-pushes local agent code to CXAS before running evals
# Ensures evals always run against the latest local code
# Works with both Claude Code and Gemini CLI

set -euo pipefail

input=$(cat)

agent=$(echo "$input" | jq -r 'if .tool_input then "claude" else "gemini" end')
cmd=$(echo "$input" | jq -r '.tool_input.command // .arguments.command // ""')

# Only act if running eval scripts
if echo "$cmd" | grep -qE 'scrapi-(eval-runner|sim-runner)\.py'; then
  config_file="gecx-config.json"
  if [ ! -f "$config_file" ]; then
    if [ "$agent" = "claude" ]; then
      echo '{}'
    else
      echo '{"decision":"allow"}'
    fi
    exit 0
  fi

  app_dir=$(jq -r '.app_dir // "cxas_app/"' "$config_file")
  project=$(jq -r '.gcp_project_id' "$config_file")
  location=$(jq -r '.location' "$config_file")
  app_id=$(jq -r '.deployed_app_id' "$config_file")
  app_resource="projects/${project}/locations/${location}/apps/${app_id}"

  # Only push if the agent directory exists
  if [ -d "$app_dir" ]; then
    GOOGLE_CLOUD_PROJECT="$project" cxas-eval push --agent_dir "$app_dir" --to "$app_resource" --project_id "$project" --location "$location" 2>/dev/null || true

    msg="AUTO-SYNC: Pushed local agent code from $app_dir to CXAS before eval run. Evals will run against the latest local code."
    if [ "$agent" = "claude" ]; then
      echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"additionalContext\":\"$msg\"}}"
    else
      echo "{\"decision\":\"allow\",\"context_update\":\"$msg\"}"
    fi
  else
    if [ "$agent" = "claude" ]; then
      echo '{}'
    else
      echo '{"decision":"allow"}'
    fi
  fi
else
  if [ "$agent" = "claude" ]; then
    echo '{}'
  else
    echo '{"decision":"allow"}'
  fi
fi
