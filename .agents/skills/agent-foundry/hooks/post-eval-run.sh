#!/bin/bash
# Reminds to generate combined report after eval runs
# Works with both Claude Code and Gemini CLI

input=$(cat)

cmd=$(echo "$input" | jq -r '.tool_input.command // .arguments.command // ""')
agent=$(echo "$input" | jq -r 'if .tool_input then "claude" else "gemini" end')

if echo "$cmd" | grep -qE 'scrapi-(eval-runner\.py results|sim-runner\.py run)'; then
  msg="REMINDER: Generate the combined report with all 4 eval types (goldens, sims, tools, callbacks). Run tool tests + callback tests, save results to eval-reports/, then run generate-combined-report.py with --golden-run, --sim-results, --tool-results, --callback-results flags."
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
