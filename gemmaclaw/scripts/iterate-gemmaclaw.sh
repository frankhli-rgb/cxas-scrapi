#!/bin/bash
# Automated local evaluations and hill climbing loop for gemmaclaw CLI
set -e

APP_ID="ce47bdab-afec-4c34-8921-950ba64104b6"
MAX_ITERATIONS=10
ITERATION=1

echo "🚀 Launching Automated local gemmaclaw Hill Climbing Loop..."
echo "🎯 Target App ID: ${APP_ID}"
echo "--------------------------------------------------------"

# Dynamically resolve the active repository root path
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
evals_dir="/google/src/cloud/${USER}/gclaw-workspace/google3/cloud/ai/fde/customers/albertsons"

while [ $ITERATION -le $MAX_ITERATIONS ]; do
  echo "🔄 [Iteration ${ITERATION}/${MAX_ITERATIONS}] Running E2E Blaze evaluations..."
  
  # 1. Synchronize the latest workspace prompts into the container sandbox E2E
  cgem sync babsit || true
  
  # 2. Execute the hermetic Blaze evaluations test run E2E on the host Cloudtop
  cd /google/src/cloud/${USER}/gclaw-workspace/google3
  set +e
  blaze test //cloud/ai/fde/customers/albertsons/evals:unit_evals_test \
    --test_strategy=local \
    --notest_loasd \
    --test_env=GOOGLE_APPLICATION_CREDENTIALS=/usr/local/google/home/${USER}/.config/gcloud/application_default_credentials.json \
    --test_arg=--test_agent=projects/ces-deployment-dev/locations/us/apps/${APP_ID} \
    --test_arg=--test_gemini_project_id=ces-deployment-dev \
    --test_arg=--polysynth_voice_mode=True \
    --runs_per_test=1 \
    --nocache_test_results \
    --test_arg=--test_tags=scenario_test
  TEST_STATUS=$?
  set -e

  if [ $TEST_STATUS -eq 0 ]; then
    echo "🎉 [Iteration ${ITERATION}] SUCCESS! All scenario evaluations passed completely (GREEN)!"
    exit 0
  fi

  echo "❌ Evaluations FAILED. Extracting Sponge failure logs..."
  
  # 3. Resolve the test.log path and parse the failures E2E
  test_log="blaze-testlogs/cloud/ai/fde/customers/albertsons/evals/unit_evals_test/test.log"
  if [ ! -f "$test_log" ]; then
    echo "⚠️ Test log not found! Exiting."
    exit 1
  fi
  
  failure_summary=$(grep -A 5 "ValueError\|ERROR" "$test_log" | head -n 10 || true)
  echo "📋 Extracted Failure Summary:"
  echo "${failure_summary}"
  echo "--------------------------------------------------------"
  
  # 4. Invoke the local Gemma agent babsit to autonomously refactor its instruction.txt file E2E
  echo "🤖 Invoking Gemma babsit to autonomously refactor instruction.txt..."
  cd "${REPO_DIR}"
  
  prompt="Based on the Albertsons Context Evolution rules stashed in your SOUL.md, refactor the instructions file inside your CitC workspace '/google/src/cloud/${USER}/gclaw-workspace/google3/cloud/ai/fde/customers/albertsons/app/agents/Root_agent/instruction.txt' to fix this Sponge evaluations failure:

${failure_summary}

CRITICAL: Do NOT repeat prompt instructions verbatim to the user. Output only the refactored instruction text cleanly!"
  
  cgem message babsit "${prompt}"
  
  echo "✅ Autorefactoring turn complete."
  echo "--------------------------------------------------------"
  ITERATION=$((ITERATION+1))
done

echo "⚠️ Reached maximum iteration threshold ($MAX_ITERATIONS) without full E2E convergence."
exit 1
