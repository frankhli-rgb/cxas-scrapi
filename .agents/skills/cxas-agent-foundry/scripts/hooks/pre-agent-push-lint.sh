#!/bin/bash
# Runs cxas lint before pushing to CXAS.
# Blocks the push if any lint errors are found.
# Works with both Claude Code and Gemini CLI.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../.agents/skills/cxas-agent-foundry/scripts/resolve-project.sh"

input=$(cat)

agent=$(echo "$input" | jq -r 'if .tool_input then "claude" else "gemini" end')
cmd=$(echo "$input" | jq -r '.tool_input.command // .arguments.command // ""')

# Only act if pushing to CXAS
if echo "$cmd" | grep -qE 'cxas(-eval)? push'; then
  project_dir=$(resolve_project_dir)
  lint_app_arg=""
  if [ -n "$project_dir" ]; then
    lint_app_arg="--app-dir $project_dir"
  fi

  lint_output=$(cxas lint --json $lint_app_arg 2>/dev/null || echo "[]")
  error_count=$(echo "$lint_output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(sum(1 for r in data if r.get('severity') == 'error'))
" 2>/dev/null || echo "0")

  if [ "$error_count" -gt 0 ]; then
    error_summary=$(echo "$lint_output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
errors = [r for r in data if r.get('severity') == 'error']
lines = []
for e in errors[:10]:
    loc = e['file']
    if e.get('line'):
        loc += f\":{e['line']}\"
    lines.append(f\"  [E] {loc} [{e['rule_id']}] {e['message']}\")
if len(errors) > 10:
    lines.append(f'  ... and {len(errors) - 10} more errors')
print('\n'.join(lines))
" 2>/dev/null || echo "  Lint errors found")

    msg="LINT BLOCKED: ${error_count} error(s) found. Fix before pushing.\n${error_summary}\nRun 'cxas lint --fix $lint_app_arg' for suggestions."
    if [ "$agent" = "claude" ]; then
      echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"blockToolExecution\":true,\"additionalContext\":\"$msg\"}}"
    else
      echo "{\"decision\":\"block\",\"context_update\":\"$msg\"}"
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