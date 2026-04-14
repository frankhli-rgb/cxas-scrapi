#!/bin/bash
# Blocks shell commands that write .py scripts via cat/echo/heredoc.
# Gemini often uses: cat << 'EOF' > build_app.py
# This is the shell equivalent of write_file and bypasses the write_file hook.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../scripts/resolve-project.sh"

input=$(cat)

cmd=$(echo "$input" | jq -r '.tool_input.command // ""')

# Block: cat/echo writing to .py files outside allowed dirs
if echo "$cmd" | grep -qE '(cat\s+<<|[>])\s*\S*\.py(\s|$|")' ; then
  # Allow writes to cxas_app/, evals/, .agents/ (root-level and project-level)
  project_dir=$(resolve_project_dir)
  project_name=""
  if [ -n "$project_dir" ]; then
    project_name="$(basename "$project_dir")/"
  fi
  if echo "$cmd" | grep -qE "(${project_name}cxas_app/|${project_name}evals/|cxas_app/|evals/|\.agents/).*\.py"; then
    echo '{}'
    exit 0
  fi
  echo "{\"decision\":\"deny\",\"reason\":\"BLOCKED: Do not create Python scripts via shell heredoc. Use inline python -c for SCRAPI calls, or use the bundled scripts in .agents/skills/cxas-agent-foundry/scripts/.\"}"
  exit 0
fi

echo '{}'
