#!/bin/bash
# run-and-report.sh — Run evals, poll until complete, fetch results, generate report
#
# Usage:
#   ./scripts/run-and-report.sh [OPTIONS]
#
# Options:
#   --name NAME          Display name for the run (default: auto-generated)
#   --runs N             Runs per evaluation (default: 5)
#   --audio              Run in AUDIO channel mode
#   --priority P0|P1|P2  Filter evals by priority (default: P0)
#   --poll-interval N    Seconds between polls (default: 90)
#   --report-dir DIR     Directory for reports (default: ./eval-reports)

set -euo pipefail

# --- Defaults (read from scenarios.yaml) ---
EVALS_YAML="$(cd "$(dirname "$0")/.." && pwd)/evals/scenarios/scenarios.yaml"
PROJECT=$(python3 -c "import yaml; d=yaml.safe_load(open('$EVALS_YAML')); print(d['meta']['project'])")
LOCATION=$(python3 -c "import yaml; d=yaml.safe_load(open('$EVALS_YAML')); print(d['meta']['location'])")
APP_ID=$(python3 -c "import yaml; d=yaml.safe_load(open('$EVALS_YAML')); print(d['meta']['app_id'])")
RUNS_PER_EVAL=5
CHANNEL="TEXT"
PRIORITY="P0"
POLL_INTERVAL=90
REPORT_DIR="$(cd "$(dirname "$0")/.." && pwd)/eval-reports"
RUN_NAME=""

# --- Parse args ---
while [[ $# -gt 0 ]]; do
  case $1 in
    --name) RUN_NAME="$2"; shift 2 ;;
    --runs) RUNS_PER_EVAL="$2"; shift 2 ;;
    --audio) CHANNEL="AUDIO"; shift ;;
    --priority) PRIORITY="$2"; shift 2 ;;
    --poll-interval) POLL_INTERVAL="$2"; shift 2 ;;
    --report-dir) REPORT_DIR="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

BASE="https://ces.googleapis.com/v1beta/projects/${PROJECT}/locations/${LOCATION}/apps/${APP_ID}"
mkdir -p "$REPORT_DIR"

# --- Helper: get fresh token ---
get_token() {
  gcloud auth print-access-token
}

# --- Step 1: Build eval list from YAML ---
echo "==> Reading evals from $EVALS_YAML (priority=$PRIORITY)..."

EVAL_JSON=$(python3 -c "
import yaml, json, sys
with open('$EVALS_YAML') as f:
    data = yaml.safe_load(f)
evals = []
for e in data.get('evals', []):
    if e.get('priority') == '$PRIORITY' and e.get('eval_id'):
        evals.append({
            'id': e['eval_id'],
            'name': e['name'],
            'resource': 'projects/$PROJECT/locations/$LOCATION/apps/$APP_ID/evaluations/' + e['eval_id'],
            'prd_id': e.get('prd_id', ''),
            'description': e.get('description', ''),
            'severity': e.get('severity', ''),
        })
print(json.dumps(evals))
")

EVAL_COUNT=$(echo "$EVAL_JSON" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")
echo "    Found $EVAL_COUNT $PRIORITY evals"

if [ "$EVAL_COUNT" -eq 0 ]; then
  echo "ERROR: No $PRIORITY evals with eval_id found in $EVALS_YAML"
  exit 1
fi

EVAL_RESOURCES=$(echo "$EVAL_JSON" | python3 -c "
import json, sys
evals = json.load(sys.stdin)
print(json.dumps([e['resource'] for e in evals]))
")

# --- Step 2: Kick off the run ---
CHANNEL_LOWER=$(echo "$CHANNEL" | tr '[:upper:]' '[:lower:]')
if [ -z "$RUN_NAME" ]; then
  RUN_NAME="${PRIORITY} ${CHANNEL_LOWER} - $(date +%Y-%m-%d_%H:%M)"
fi

echo "==> Starting run: $RUN_NAME ($EVAL_COUNT evals x $RUNS_PER_EVAL runs, channel=$CHANNEL)..."

RUN_BODY="{
  \"displayName\": \"$RUN_NAME\",
  \"evaluations\": $EVAL_RESOURCES,
  \"runsPerEvaluation\": $RUNS_PER_EVAL"

if [ "$CHANNEL" = "AUDIO" ]; then
  RUN_BODY="$RUN_BODY, \"config\": {\"evaluationChannel\": \"AUDIO\"}"
fi

RUN_BODY="$RUN_BODY}"

TOKEN=$(get_token)
curl -s -X POST "${BASE}:runEvaluation" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$RUN_BODY" > /tmp/run_response.json

# Wait for run to appear in evaluationRuns
sleep 15
TOKEN=$(get_token)
RUN_ID=$(curl -s -H "Authorization: Bearer $TOKEN" "${BASE}/evaluationRuns" | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
for r in d.get('evaluationRuns', []):
    if r.get('displayName') == '$RUN_NAME':
        print(r['name'].split('/')[-1])
        break
")

if [ -z "$RUN_ID" ]; then
  echo "ERROR: Could not find run ID for '$RUN_NAME'"
  exit 1
fi

EXPECTED_RESULTS=$((EVAL_COUNT * RUNS_PER_EVAL))
echo "    Run ID: $RUN_ID"
echo "    Expected results: $EXPECTED_RESULTS"

# --- Step 3: Poll until complete ---
echo "==> Polling every ${POLL_INTERVAL}s..."

while true; do
  TOKEN=$(get_token)
  RUN_DATA=$(curl -s -H "Authorization: Bearer $TOKEN" "${BASE}/evaluationRuns/${RUN_ID}")

  STATE=$(echo "$RUN_DATA" | python3 -c "import json,sys; print(json.load(sys.stdin).get('state','UNKNOWN'))")
  PROGRESS=$(echo "$RUN_DATA" | python3 -c "
import json,sys
p = json.load(sys.stdin).get('progress', {})
print(f\"passed={p.get('passedCount',0)} failed={p.get('failedCount',0)} total={p.get('totalCount',0)}\")
")

  echo "    $(date +%H:%M:%S) state=$STATE $PROGRESS"

  if [ "$STATE" = "COMPLETED" ] || [ "$STATE" = "FAILED" ]; then
    echo "$RUN_DATA" > /tmp/run_data.json
    break
  fi

  sleep "$POLL_INTERVAL"
done

echo "    Run $STATE"

# --- Step 4: Fetch all individual results ---
echo "==> Fetching individual results..."

RESULT_REFS=$(echo "$RUN_DATA" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for ref in d.get('evaluationResults', []):
    print(ref)
")

RESULT_COUNT=$(echo "$RESULT_REFS" | wc -l | tr -d ' ')
echo "    $RESULT_COUNT results to fetch"

RESULTS_DIR="/tmp/eval_results_$$"
mkdir -p "$RESULTS_DIR"

echo "$RESULT_REFS" | while read -r ref; do
  result_id=$(echo "$ref" | sed 's|.*/results/||')
  TOKEN=$(get_token)
  curl -s -H "Authorization: Bearer $TOKEN" \
    "https://ces.googleapis.com/v1beta/${ref}" > "${RESULTS_DIR}/${result_id}.json" &

  # Limit parallelism to 15
  if (( $(jobs -r | wc -l) >= 15 )); then
    wait -n 2>/dev/null || wait
  fi
done
wait

echo "    Fetched all results to $RESULTS_DIR"

# --- Step 5: Generate report ---
echo "==> Generating report..."

TIMESTAMP=$(date +%Y-%m-%d_%H%M)
REPORT_FILE="${REPORT_DIR}/${PRIORITY}_${CHANNEL_LOWER}_${TIMESTAMP}.md"

export RUN_ID RUN_NAME CHANNEL PRIORITY RUNS_PER_EVAL REPORT_FILE EVALS_YAML RESULTS_DIR

python3 << 'PYEOF'
import json, os, glob, yaml, sys
from datetime import datetime

run_id = os.environ.get('RUN_ID', '')
run_name = os.environ.get('RUN_NAME', '')
channel = os.environ.get('CHANNEL', 'TEXT')
priority = os.environ.get('PRIORITY', 'P0')
runs_per_eval = int(os.environ.get('RUNS_PER_EVAL', '5'))
report_file = os.environ.get('REPORT_FILE', 'report.md')
evals_yaml_path = os.environ.get('EVALS_YAML', 'evals.yaml')
results_dir = os.environ.get('RESULTS_DIR', '/tmp/eval_results')

# Load YAML for metadata
with open(evals_yaml_path) as f:
    evals_yaml = yaml.safe_load(f)

id_to_meta = {}
for e in evals_yaml.get('evals', []):
    eid = e.get('eval_id', '')
    if eid:
        id_to_meta[eid] = {
            'name': e.get('name', ''),
            'prd_id': e.get('prd_id', ''),
            'description': (e.get('description', '') or '').strip()[:80],
            'severity': e.get('severity', ''),
            'priority': e.get('priority', ''),
        }

# Parse all results
eval_results = {}  # eval_name -> [(score, exec_state, explanation)]

for fname in glob.glob(os.path.join(results_dir, '*.json')):
    try:
        with open(fname) as f:
            d = json.load(f)
    except:
        continue

    result_name = d.get('name', '')
    parts = result_name.split('/')
    if len(parts) < 10:
        continue
    eval_id = parts[7]
    meta = id_to_meta.get(eval_id, {})
    eval_name = meta.get('name', eval_id[:12])

    sr = d.get('scenarioResult', {})
    ugs = sr.get('userGoalSatisfactionResult', {})
    goal_score = ugs.get('score')
    all_expectations_satisfied = sr.get('allExpectationsSatisfied')
    task_completed = sr.get('taskCompleted')
    explanation = (ugs.get('explanation', '') or '')[:250]
    exec_state = d.get('executionState', '')
    error_msg = ''
    if d.get('errorInfo'):
        error_msg = d['errorInfo'].get('errorMessage', '')[:200]
        exec_state = 'ERROR'

    # Platform-consistent pass/fail
    # For AUDIO channel: skip taskCompleted check (unreliable in audio mode —
    # returns False even when goal judge confirms success)
    # For TEXT channel: full check including taskCompleted
    channel = os.environ.get('CHANNEL', 'TEXT')
    if exec_state == 'ERROR':
        platform_passed = None  # error, not scored
    elif channel == 'AUDIO':
        # Audio: goal + expectations only
        if all_expectations_satisfied != False and goal_score == 1:
            platform_passed = True
        elif goal_score is not None:
            platform_passed = False
        else:
            platform_passed = None
    else:
        # Text: full platform-consistent check
        if all_expectations_satisfied and task_completed != False and goal_score == 1:
            platform_passed = True
        elif goal_score is not None:
            platform_passed = False
        else:
            platform_passed = None  # no score

    # Expectation results
    exp_results = []
    for er in sr.get('expectationResults', sr.get('evaluationExpectationResults', [])):
        raw_name = er.get('name', er.get('expectationName', ''))
        exp_name = raw_name.split('/')[-1] if '/' in raw_name else raw_name
        if not exp_name:
            exp_name = er.get('displayName', 'unknown')
        exp_result = er.get('result', er.get('status', ''))
        exp_results.append((exp_name, exp_result))

    if eval_name not in eval_results:
        eval_results[eval_name] = {
            'meta': meta,
            'results': [],
        }
    eval_results[eval_name]['results'].append({
        'score': goal_score,
        'platform_passed': platform_passed,
        'all_expectations_satisfied': all_expectations_satisfied,
        'task_completed': task_completed,
        'exec_state': exec_state,
        'explanation': explanation,
        'error': error_msg,
        'expectations': exp_results,
    })

# Compute per-eval stats
eval_stats = []
for eval_name, data in sorted(eval_results.items()):
    results = data['results']
    meta = data['meta']
    passed = sum(1 for r in results if r['platform_passed'] == True)
    failed = sum(1 for r in results if r['platform_passed'] == False)
    errors = sum(1 for r in results if r['exec_state'] == 'ERROR')
    no_score = sum(1 for r in results if r['score'] is None and r['exec_state'] != 'ERROR')
    scored = passed + failed

    # Per-expectation stats
    exp_stats = {}
    for r in results:
        for exp_name, exp_result in r['expectations']:
            if exp_name not in exp_stats:
                exp_stats[exp_name] = {'pass': 0, 'fail': 0}
            if exp_result == 'PASS':
                exp_stats[exp_name]['pass'] += 1
            else:
                exp_stats[exp_name]['fail'] += 1

    # Failure explanations (include platform failures, not just goal=0)
    failure_explanations = []
    for r in results:
        if r['platform_passed'] == False:
            reason_parts = []
            if r['score'] == 0:
                reason_parts.append('Goal not satisfied')
            elif r['task_completed'] == False:
                reason_parts.append('Task not completed')
            if r['all_expectations_satisfied'] == False:
                reason_parts.append('Expectations not satisfied')
            reason = ' + '.join(reason_parts) if reason_parts else 'Unknown'
            failure_explanations.append(f'[{reason}] {r["explanation"]}')
    error_messages = [r['error'] for r in results if r['error']]

    eval_stats.append({
        'name': eval_name,
        'prd_id': meta.get('prd_id', ''),
        'description': meta.get('description', ''),
        'severity': meta.get('severity', ''),
        'passed': passed,
        'failed': failed,
        'errors': errors,
        'scored': scored,
        'exp_stats': exp_stats,
        'failure_explanations': failure_explanations,
        'error_messages': error_messages,
    })

# Sort: worst first
eval_stats.sort(key=lambda e: (e['passed'] / max(e['scored'], 1), e['name']))

# Overall stats
total_passed = sum(e['passed'] for e in eval_stats)
total_failed = sum(e['failed'] for e in eval_stats)
total_errors = sum(e['errors'] for e in eval_stats)
total_scored = total_passed + total_failed
overall_rate = total_passed / total_scored * 100 if total_scored else 0

perfect_count = sum(1 for e in eval_stats if e['failed'] == 0 and e['scored'] >= runs_per_eval)
at_threshold = sum(1 for e in eval_stats if e['scored'] > 0 and e['passed'] / e['scored'] >= 0.8)

nogo_evals = [e for e in eval_stats if e['severity'] == 'NO-GO']
nogo_failures = [e for e in nogo_evals if e['failed'] > 0]

# Gate status
dev_gate = overall_rate >= 75 and len(nogo_failures) == 0
staging_gate = overall_rate >= 85 and all(e['failed'] == 0 and e['scored'] >= runs_per_eval for e in nogo_evals)
prod_gate = overall_rate >= 90 and all(
    e['passed'] / max(e['scored'], 1) >= 0.8
    for e in eval_stats if e['severity'] in ('NO-GO', 'HIGH')
)

# Write report
with open(report_file, 'w') as f:
    f.write(f"# Eval Report — {run_name}\n\n")
    f.write(f"**App:** {evals_yaml.get('meta', {}).get('project', '')}"
            f" / {evals_yaml.get('meta', {}).get('app_id', '')}\n")
    f.write(f"**Run ID:** `{run_id}`\n")
    f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    f.write(f"**Channel:** {channel}\n")
    f.write(f"**Pass Rate:** {overall_rate:.1f}% ({total_passed}/{total_scored})\n")
    actual_total = total_scored + total_errors
    f.write(f"**{len(eval_stats)} {priority} evals, "
            f"{actual_total} total results** "
            f"({total_errors} errors)\n\n")

    # Verdict
    if prod_gate:
        verdict = "Ready for production ramp"
    elif staging_gate:
        verdict = "Ready for staging approval"
    elif dev_gate:
        verdict = "Development complete — address failures before staging"
    else:
        blockers = sum(1 for e in eval_stats if e['scored'] > 0 and e['passed'] / e['scored'] < 0.8)
        verdict = f"{blockers} blockers remain"
    f.write(f"**Verdict:** {verdict}\n\n")
    f.write("---\n\n")

    # Gate status
    f.write("## Gate Status\n\n")
    f.write("| Gate | Requirement | Current | Status |\n")
    f.write("|------|------------|---------|--------|\n")
    f.write(f"| Development Complete | 75%+ overall, 0 NO-GO failures | {overall_rate:.1f}% | "
            f"{'Pass' if dev_gate else 'Fail'} |\n")
    f.write(f"| Staging Approval | 85%+ overall, all NO-GO at 5/5 | {overall_rate:.1f}% | "
            f"{'Pass' if staging_gate else 'Fail'} |\n")
    f.write(f"| Production Ramp | 90%+ overall, all HIGH at 4/5+ | {overall_rate:.1f}% | "
            f"{'Pass' if prod_gate else 'Fail'} |\n\n")

    # NO-GO items
    if nogo_evals:
        f.write("## NO-GO Items\n\n")
        f.write("| Eval | PRD | Score | Status |\n")
        f.write("|------|-----|-------|--------|\n")
        for e in nogo_evals:
            score_str = f"{e['passed']}/{e['scored']}" if e['scored'] else "N/A"
            status = "PASS" if e['failed'] == 0 and e['scored'] >= runs_per_eval else "FAIL"
            f.write(f"| {e['name']} | {e['prd_id']} | {score_str} | {status} |\n")
        f.write("\n")

    # Results by score
    f.write("## Results by Score\n\n")

    # Group by score bucket
    buckets = {}
    for e in eval_stats:
        if e['scored'] == 0:
            key = "No results"
        else:
            key = f"{e['passed']}/{e['scored']}"
        if key not in buckets:
            buckets[key] = []
        buckets[key].append(e)

    f.write("| Score | Count | Evals |\n")
    f.write("|-------|-------|-------|\n")
    for key in sorted(buckets.keys(), key=lambda k: (
        -1 if k == "No results" else -int(k.split('/')[0]) / max(int(k.split('/')[1]), 1)
    )):
        names = ', '.join(e['name'] for e in buckets[key])
        f.write(f"| {key} | {len(buckets[key])} | {names} |\n")
    f.write("\n")

    # Full results table
    f.write("## All Evals (worst first)\n\n")
    f.write("| Score | Eval | PRD | Severity | Description |\n")
    f.write("|-------|------|-----|----------|-------------|\n")
    for e in eval_stats:
        score_str = f"{e['passed']}/{e['scored']}" if e['scored'] else "ERR"
        desc = e['description'][:60] + ('...' if len(e['description']) > 60 else '')
        f.write(f"| {score_str} | {e['name']} | {e['prd_id']} | {e['severity']} | {desc} |\n")
    f.write("\n")

    # Failure details
    failing = [e for e in eval_stats if e['failed'] > 0 or e['errors'] > 0]
    if failing:
        f.write("## Failure Details\n\n")
        for e in failing:
            f.write(f"### {e['name']} ({e['passed']}/{e['scored']})\n\n")

            if e['failure_explanations']:
                for i, exp in enumerate(e['failure_explanations'][:3], 1):
                    f.write(f"**Failure {i}:** {exp}\n\n")

            if e['error_messages']:
                for msg in e['error_messages'][:2]:
                    f.write(f"**Error:** `{msg}`\n\n")

            if e['exp_stats']:
                f.write("**Expectation results:**\n\n")
                f.write("| Expectation | Pass | Fail |\n")
                f.write("|-------------|------|------|\n")
                for exp_name, stats in sorted(e['exp_stats'].items()):
                    f.write(f"| {exp_name} | {stats['pass']} | {stats['fail']} |\n")
                f.write("\n")

    # Summary stats
    f.write("---\n\n")
    f.write("## Summary\n\n")
    f.write(f"- **Overall:** {total_passed}/{total_scored} ({overall_rate:.1f}%)\n")
    f.write(f"- **Perfect ({runs_per_eval}/{runs_per_eval}):** {perfect_count}/{len(eval_stats)}\n")
    f.write(f"- **At 4/5+:** {at_threshold}/{len(eval_stats)}\n")
    f.write(f"- **Errors:** {total_errors}\n")
    f.write(f"\n_Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n")

print(f"Report written to {report_file}")
PYEOF

echo "==> Done!"
echo "    Run ID:  $RUN_ID"
echo "    Report:  $REPORT_FILE"

# --- Step 6: Update YAML scores ---
echo "==> Updating evals.yaml with scores..."

python3 << 'PYUPDATE'
import json, os, glob, yaml

evals_yaml_path = os.environ.get('EVALS_YAML', 'evals.yaml')
results_dir = os.environ.get('RESULTS_DIR', '/tmp/eval_results')
run_id = os.environ.get('RUN_ID', '')

with open(evals_yaml_path) as f:
    raw = f.read()

# Parse results
eval_scores = {}  # eval_id -> (passed, scored)
for fname in glob.glob(os.path.join(results_dir, '*.json')):
    try:
        with open(fname) as f:
            d = json.load(f)
    except:
        continue
    result_name = d.get('name', '')
    parts = result_name.split('/')
    if len(parts) < 10:
        continue
    eval_id = parts[7]
    score = d.get('scenarioResult', {}).get('userGoalSatisfactionResult', {}).get('score')
    if score is not None:
        if eval_id not in eval_scores:
            eval_scores[eval_id] = [0, 0]
        eval_scores[eval_id][1] += 1
        if score == 1:
            eval_scores[eval_id][0] += 1

# Update YAML in-place (preserve formatting)
for eval_id, (passed, scored) in eval_scores.items():
    score_str = f"{passed}/{scored}"
    # Replace last_run_score for this eval_id
    import re
    pattern = rf'(eval_id: {re.escape(eval_id)}\n\s*last_run_score:).*'
    raw = re.sub(pattern, rf'\1 "{score_str}"', raw)
    pattern2 = rf'(eval_id: {re.escape(eval_id)}\n\s*last_run_score:.*\n\s*last_run_id:).*'
    raw = re.sub(pattern2, rf'\1 {run_id}', raw)

with open(evals_yaml_path, 'w') as f:
    f.write(raw)

print(f"    Updated {len(eval_scores)} eval scores in {evals_yaml_path}")
PYUPDATE

echo "==> All done!"
