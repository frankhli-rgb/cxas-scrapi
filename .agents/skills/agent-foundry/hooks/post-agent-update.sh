#!/bin/bash
# Reminds to sync callbacks and update tests after agent changes
# Also auto-pulls latest agent state to local files after SCRAPI updates
# Works with both Claude Code and Gemini CLI

input=$(cat)

cmd=$(echo "$input" | jq -r '.tool_input.command // .arguments.command // ""')
agent=$(echo "$input" | jq -r 'if .tool_input then "claude" else "gemini" end')

if echo "$cmd" | grep -qE 'update_agent'; then
  # Auto-pull latest agent state to keep local files in sync
  config_file="gecx-config.json"
  pull_msg=""
  if [ -f "$config_file" ]; then
    app_dir=$(jq -r '.app_dir // "cxas_app/"' "$config_file")
    project=$(jq -r '.gcp_project_id' "$config_file")
    location=$(jq -r '.location' "$config_file")
    app_id=$(jq -r '.deployed_app_id' "$config_file")
    app_resource="projects/${project}/locations/${location}/apps/${app_id}"
    if GOOGLE_CLOUD_PROJECT="$project" cxas-eval pull "$app_resource" --project_id "$project" --location "$location" --target_dir "$app_dir" 2>/dev/null; then
      pull_msg="AUTO-SYNC: Pulled latest agent state to $app_dir. "
    fi
  fi

  msg="${pull_msg}REMINDER: Agent was updated. (1) Sync callback code from platform to evals/callback_tests/agents/. (2) Update or add callback tests. (3) Run all callback tests. (4) Update TDD changelog."
  if [ "$agent" = "claude" ]; then
    echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolUse\",\"additionalContext\":\"$msg\"}}"
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
