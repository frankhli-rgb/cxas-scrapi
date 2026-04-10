#!/bin/bash
# After pushing to CXAS:
# 1. If deployed_app_id is null in gecx-config.json, extract the app ID from
#    the push command output and update the config.
# 2. Remind to commit local changes to git.
# Works with both Claude Code and Gemini CLI

input=$(cat)

agent=$(echo "$input" | jq -r 'if .tool_input then "claude" else "gemini" end')
cmd=$(echo "$input" | jq -r '.tool_input.command // .arguments.command // ""')
tool_output=$(echo "$input" | jq -r '.tool_output // .result // ""')

if echo "$cmd" | grep -qE 'cxas-eval push'; then
  config_file="gecx-config.json"
  extra_msg=""

  # If deployed_app_id is null, try to extract the real app ID
  if [ -f "$config_file" ]; then
    current_app_id=$(jq -r '.deployed_app_id // "null"' "$config_file")
    if [ "$current_app_id" = "null" ] || [ -z "$current_app_id" ]; then
      # Try to extract UUID from the push command or its output
      # Common patterns: apps/<uuid>, app_id=<uuid>
      extracted_id=$(echo "$tool_output" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1)
      if [ -z "$extracted_id" ]; then
        extracted_id=$(echo "$cmd" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1)
      fi

      if [ -n "$extracted_id" ]; then
        # Update gecx-config.json with the real app ID
        jq --arg id "$extracted_id" '.deployed_app_id = $id | .environments.dev.app_id = $id' "$config_file" > "${config_file}.tmp" \
          && mv "${config_file}.tmp" "$config_file"
        extra_msg="AUTO-UPDATE: Set deployed_app_id to $extracted_id in gecx-config.json. "
      else
        extra_msg="WARNING: deployed_app_id is still null in gecx-config.json. Update it manually with the app's UUID. "
      fi
    fi
  fi

  msg="${extra_msg}REMINDER: Agent code was pushed to CXAS. Commit your local changes to git: git add cxas_app/ gecx-config.json && git commit -m 'description of changes'"
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
