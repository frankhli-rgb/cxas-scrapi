#!/bin/bash
# Reminds to run callback tests after callback code changes
# Works with both Claude Code and Gemini CLI

input=$(cat)

filepath=$(echo "$input" | jq -r '.tool_input.file_path // .arguments.file_path // .arguments.path // ""')
agent=$(echo "$input" | jq -r 'if .tool_input then "claude" else "gemini" end')

if echo "$filepath" | grep -qE 'callback_tests/agents/.*/python_code\.py'; then
  msg="REMINDER: Callback code was written. Run all callback tests to verify they still pass."
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
