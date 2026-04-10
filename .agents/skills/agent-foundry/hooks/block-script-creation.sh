#!/bin/bash
# Blocks creation of throwaway .py scripts in the workspace.
# Gemini tends to write build_app.py, test_session.py, etc. instead of
# using inline python or the bundled eval scripts. This hook prevents that.

input=$(cat)

filepath=$(echo "$input" | jq -r '.tool_input.file_path // .tool_input.path // ""')

# Allow: cxas_app/, evals/, .agents/, scripts/configure.py, scripts/lint.py
# Block: any other .py file in the workspace root or scripts/
if echo "$filepath" | grep -qE '\.py$'; then
  # Allowed paths
  if echo "$filepath" | grep -qE '(cxas_app/|evals/|\.agents/|scripts/configure\.py|scripts/lint\.py)'; then
    echo '{}'
    exit 0
  fi

  echo "{\"decision\":\"deny\",\"reason\":\"BLOCKED: Do not create standalone Python scripts. Instead: (1) For SCRAPI calls, use inline python via run_shell_command with python -c. (2) For evals, use the bundled scripts in .agents/skills/agent-foundry/scripts/. (3) For testing sessions, use inline: sessions.run(session_id=..., text=...).\"}"
  exit 0
fi

echo '{}'
