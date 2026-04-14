#!/bin/bash
# Blocks creation of throwaway .py scripts in the workspace.
# Gemini tends to write build_app.py, test_session.py, etc. instead of
# using inline python or the bundled eval scripts. This hook prevents that.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../scripts/resolve-project.sh"

input=$(cat)

filepath=$(echo "$input" | jq -r '.tool_input.file_path // .tool_input.path // ""')

# Allow: cxas_app/, evals/, .agents/
# Block: any other .py file in the workspace root
if echo "$filepath" | grep -qE '\.py$'; then
  # Allowed paths (root-level and project-level)
  project_dir=$(resolve_project_dir)
  project_name=""
  if [ -n "$project_dir" ]; then
    project_name="$(basename "$project_dir")/"
  fi
  if echo "$filepath" | grep -qE "(${project_name}cxas_app/|${project_name}evals/|cxas_app/|evals/|\.agents/)"; then
    echo '{}'
    exit 0
  fi

  echo "{\"decision\":\"deny\",\"reason\":\"BLOCKED: Do not create standalone Python scripts. Instead: (1) For SCRAPI calls, use inline python via run_shell_command with python -c. (2) For evals, use the bundled scripts in .agents/skills/cxas-agent-foundry/scripts/. (3) For testing sessions, use inline: sessions.run(session_id=..., text=...).\"}"
  exit 0
fi

echo '{}'
