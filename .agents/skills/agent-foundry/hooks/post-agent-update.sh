#!/bin/bash
# Reminds to sync callbacks and update tests after agent changes
# Works with both Claude Code and Gemini CLI

input=$(cat)

cmd=$(echo "$input" | jq -r '.tool_input.command // .arguments.command // ""')
agent=$(echo "$input" | jq -r 'if .tool_input then "claude" else "gemini" end')

if echo "$cmd" | grep -qE 'update_agent'; then
  msg="REMINDER: Agent was updated. (1) Sync callback code from platform to evals/callback_tests/agents/. (2) Update or add callback tests. (3) Run all callback tests. (4) Update TDD changelog."
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
