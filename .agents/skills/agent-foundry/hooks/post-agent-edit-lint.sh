#!/bin/bash
# Runs the GECX linter after editing agent files in cxas_app/.
# Detects the file category and runs targeted lint rules.
# Works with both Claude Code and Gemini CLI.

input=$(cat)

agent=$(echo "$input" | jq -r 'if .tool_input then "claude" else "gemini" end')
filepath=$(echo "$input" | jq -r '.tool_input.file_path // .arguments.file_path // .arguments.path // ""')

# Determine category from file path
category=""
if echo "$filepath" | grep -q "instruction.txt"; then
  category="instructions"
elif echo "$filepath" | grep -qE "(before|after)_(model|agent)_callbacks.*python_code\.py"; then
  category="callbacks"
elif echo "$filepath" | grep -q "python_function/python_code.py"; then
  category="tools"
elif echo "$filepath" | grep -qE '\.yaml$'; then
  category="evals"
elif echo "$filepath" | grep -qE '\.json$'; then
  category="config"
fi

# Only lint if we identified a category and the file is in cxas_app/ or evals/
config_file="gecx-config.json"
app_dir="cxas_app/"
if [ -f "$config_file" ]; then
  app_dir=$(jq -r '.app_dir // "cxas_app/"' "$config_file")
fi

if [ -n "$category" ] && (echo "$filepath" | grep -qE "^(${app_dir}|evals/)"); then
  lint_output=$(python scripts/lint.py --only "$category" --json 2>/dev/null || echo "[]")
  issue_count=$(echo "$lint_output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(len(data))
" 2>/dev/null || echo "0")

  if [ "$issue_count" -gt 0 ]; then
    summary=$(echo "$lint_output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
lines = []
for r in data[:5]:
    sev = {'error': 'E', 'warning': 'W', 'info': 'I'}.get(r['severity'], '?')
    loc = r['file']
    if r.get('line'):
        loc += f\":{r['line']}\"
    lines.append(f'  [{sev}] {loc} [{r[\"rule_id\"]}] {r[\"message\"]}')
if len(data) > 5:
    lines.append(f'  ... and {len(data) - 5} more issues')
print('\n'.join(lines))
" 2>/dev/null || echo "  Lint issues found")

    msg="LINT: ${issue_count} issue(s) in ${category}:\n${summary}"
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
else
  if [ "$agent" = "claude" ]; then
    echo '{}'
  else
    echo '{"decision":"allow"}'
  fi
fi
