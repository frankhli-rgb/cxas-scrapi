#!/bin/bash
# Auto-pulls latest agent state from CXAS before editing agent files
# Prevents editing stale local files when someone changed the platform directly
# Works with both Claude Code and Gemini CLI

set -euo pipefail

input=$(cat)

# Detect which agent (Claude Code vs Gemini CLI)
agent=$(echo "$input" | jq -r 'if .tool_input then "claude" else "gemini" end')

# Get the file path being edited
filepath=$(echo "$input" | jq -r '.tool_input.file_path // .arguments.file_path // .arguments.path // ""')

# Only act if editing files in the agent directory
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

# Match only the app_dir (e.g. agents/) but not .agents/
if echo "$filepath" | grep -qE "(^|/[^.])${app_dir%/}/" || echo "$filepath" | grep -qE "^${app_dir}"; then
  project=$(jq -r '.gcp_project_id' "$config_file")
  location=$(jq -r '.location' "$config_file")
  app_id=$(jq -r '.deployed_app_id' "$config_file")
  app_resource="projects/${project}/locations/${location}/apps/${app_id}"

  # Auto-pull latest state from platform
  GOOGLE_CLOUD_PROJECT="$project" cxas-eval pull "$app_resource" --project_id "$project" --location "$location" --target_dir "$app_dir" 2>/dev/null || true

  msg="AUTO-SYNC: Pulled latest agent state from CXAS before editing. Local files in $app_dir are now up to date."
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
