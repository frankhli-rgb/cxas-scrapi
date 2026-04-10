import os
import sys
import logging
import json
import re
import concurrent.futures
import uuid
import argparse
import pandas as pd
import ast

from cxas_scrapi import SimulationEvals
from google import genai

class TeeStdout:
    _ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def __init__(self, filename, quiet=False):
        self.filename = filename
        self.file = None
        self.stdout = sys.stdout
        self.quiet = quiet
        self.buffer = []

    def __enter__(self):
        self.file = open(self.filename, "w", encoding="utf-8")
        sys.stdout = self
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self.stdout
        if self.file:
            self.file.close()

    def write(self, data):
        if not self.quiet:
            self.stdout.write(data)
        self.buffer.append(data)
        stripped_data = self._ansi_escape.sub('', data)
        self.file.write(stripped_data)

    def flush(self):
        self.stdout.flush()
        self.file.flush()

    def isatty(self):
        return True

def run_single_eval(item, evals_dir, app_name, skip_analysis=False):
    json_path = os.path.join(evals_dir, item)
    log_path = json_path.replace(".json", ".log")
    session_id = str(uuid.uuid4())
    os.environ["FORCE_COLOR"] = "1"
    os.environ["CLICOLOR_FORCE"] = "1"
    
    with TeeStdout(log_path, quiet=True) as tee:
        print(f"\n==================================================")
        print(f"Running test case: {item}")
        print(f"==================================================")
        with open(json_path, "r") as f:
            test_case = json.load(f)

        # Initialize the Simulator per test case
        sim_evals = SimulationEvals(app_name)
        eval_conv = sim_evals.simulate_conversation(
            test_case=test_case, console_logging=True, session_id=session_id
        )
        
        report = eval_conv.generate_report()
        
        # Print full report to tee (so it is stripped for file)
        print("\n=== Full Report ===", file=tee)
        print(report, file=tee)
        
        # Determine pass/fail
        all_goals_completed = all(report.goals_df['status'] == 'Completed')
        all_expectations_met = True
        if report.expectations_df is not None:
            all_expectations_met = all(report.expectations_df['status'] == 'Met')
        
        passed = all_goals_completed and all_expectations_met
        
        colored_trace = "".join(tee.buffer)
        
        # Strip the goal progress from the trace for HTML
        trace_marker = "--- Conversation Complete ---"
        if trace_marker in colored_trace:
            colored_trace = colored_trace.split(trace_marker)[0]
        
        # Read log file for analysis if failed
        analysis_results = []
        llm_suggestions = ""
        if not passed and not skip_analysis:
            try:
                tee.flush()
                with open(log_path, 'r', encoding='utf-8') as f:
                    log_content = f.read()
                    pattern = re.compile(r"TOOL CALL: \[([^\]]+)\] intercept_and_score_reasoning -- Args: (\{.*\})")
                    calls = []
                    for line in log_content.splitlines():
                        match = pattern.search(line)
                        if match:
                            agent_name = match.group(1)
                            args_str = match.group(2)
                            try:
                                args = ast.literal_eval(args_str)
                                calls.append({
                                    "agent": agent_name,
                                    "planned_action": args.get("planned_action"),
                                    "internal_monologue": args.get("internal_monologue")
                                })
                            except Exception as e:
                                pass
                    
                    for call in calls:
                        monologue = call['internal_monologue'] or ""
                        length = len(monologue)
                        issues = []
                        if length > 600:
                            issues.append("Severe overthinking (> 600 chars)")
                        elif length > 350:
                            issues.append("Moderate overthinking (> 350 chars)")
                            
                        hedging = re.findall(r"\b(might|guess|assume|maybe|unsure)\b", monologue, re.IGNORECASE)
                        if hedging:
                            issues.append(f"Detected hedging: {list(set(hedging))}")
                            
                        backtracking = re.findall(r"\b(wait|actually|on second thought)\b", monologue, re.IGNORECASE)
                        if backtracking:
                            issues.append(f"Detected backtracking: {list(set(backtracking))}")
                            
                        analysis_results.append({
                            "agent": call['agent'],
                            "planned_action": call['planned_action'],
                            "monologue": monologue,
                            "issues": issues
                        })
                        
                    # Perform LLM analysis if calls were found
                    if calls:
                        try:
                            output_dir = os.path.abspath(os.path.join(evals_dir, ".."))
                            global_inst_path = os.path.join(output_dir, 'app', 'global_instruction.txt')
                            global_inst = ""
                            if os.path.exists(global_inst_path):
                                with open(global_inst_path, 'r', encoding='utf-8') as f:
                                    global_inst = f.read()
                                    
                            agent_instructions = {}
                            agent_names = set(c['agent'] for c in calls)
                            for agent_name in agent_names:
                                inst_path = os.path.join(output_dir, 'app', 'agents', agent_name, 'instruction.txt')
                                if os.path.exists(inst_path):
                                    with open(inst_path, 'r', encoding='utf-8') as f:
                                        agent_instructions[agent_name] = f.read()
                                        
                            # Construct prompt
                            prompt = f"""
You are an expert AI developer task with analyzing failed CXAS simulation evaluations.
Your goal is to identify why the agent failed and suggest specific edits to its instructions to fix the issues.

**Failed Evaluation:** {item}

**Global Instructions:**
{global_inst}

"""
                            for agent_name, inst in agent_instructions.items():
                                prompt += f"""
**Instructions for Agent '{agent_name}':**
{inst}
"""

                            prompt += f"""
**Conversation Trace & Logs:**
{log_content}

**Extracted Reasoning Turns:**
"""
                            for i, call in enumerate(calls, 1):
                                prompt += f"""
--- Turn {i} ({call['agent']}) ---
Planned Action: {call['planned_action']}
Internal Monologue: {call['internal_monologue']}
"""

                            prompt += """
**Task:**
1. Analyze the conversation trace and the agent's internal monologue.
2. Identify where the agent struggled (e.g., overthinking, hesitation, backtracking, missing edge cases).
3. Correlate these struggles with the provided instructions.
4. Suggest specific, actionable edits to the `global_instruction.txt` or agent-specific `instruction.txt` to improve the agent's performance and prevent this failure. Be specific about which part of the instruction is causing the problem and how to fix it.

Output your analysis and suggestions in a clear, structured markdown format.
"""
                            # Extract project and location from app_name
                            parts = app_name.split("/")
                            project = parts[1] if len(parts) > 1 else "ces-deployment-dev"
                            location = parts[3] if len(parts) > 3 else "us-central1"
                            if location == "us":
                                location = "us-central1"
                                
                            client = genai.Client(vertexai=True, project=project, location=location)
                            response = client.models.generate_content(
                                model="gemini-2.5-flash",
                                contents=prompt,
                            )
                            llm_suggestions = response.text
                        except Exception as e:
                            print(f"Error calling Gemini for {item}: {e}")
                            llm_suggestions = f"Error calling Gemini for analysis: {e}"
                            
            except Exception as e:
                print(f"Error analyzing log for {item}: {e}")

        goals_html = report.goals_df.to_html(classes='table', index=False)
        exp_html = ""
        if report.expectations_df is not None:
            exp_html = report.expectations_df.to_html(classes='table', index=False)

        return {
            "name": item,
            "session_id": session_id,
            "passed": passed,
            "log_path": log_path,
            "colored_trace": colored_trace,
            "goals_html": goals_html,
            "expectations_html": exp_html,
            "analysis_results": analysis_results,
            "llm_suggestions": llm_suggestions
        }

def ansi_to_html(text):
    import html
    escaped = html.escape(text)
    
    span_open = False
    def replace_ansi(match):
        nonlocal span_open
        codes = match.group(1).split(';')
        if '0' in codes or not codes or codes == ['']:
            res = '</span>' if span_open else ''
            span_open = False
            return res
            
        styles = []
        for code in codes:
            if code == '1': styles.append('font-weight: bold;')
            elif code == '31': styles.append('color: red;')
            elif code == '32': styles.append('color: green;')
            elif code == '33': styles.append('color: yellow;')
            elif code == '34': styles.append('color: blue;')
            elif code == '35': styles.append('color: magenta;')
            elif code == '36': styles.append('color: cyan;')
            elif code == '90': styles.append('color: gray;')
            
        if styles:
            prefix = '</span>' if span_open else ''
            span_open = True
            return f'{prefix}<span style="{" ".join(styles)}">'
        return ''
        
    result = re.sub(r'\x1b\[([0-9;]*)m', replace_ansi, escaped)
    if span_open:
        result += '</span>'
    return result

def generate_html_report(results, evals_dir, app_name):
    html_content = """
    <html>
    <head>
        <title>Simulation Run Results</title>
        <style>
            body { font-family: 'Inter', sans-serif; margin: 20px auto; max-width: 1200px; padding: 0 50px; background-color: #f4f7f6; color: #333; }
            h1, h2 { color: #2c3e50; }
            table { border-collapse: collapse; width: 100%; background-color: #fff; margin-bottom: 20px; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
            th, td { border: 1px solid #e2e8f0; padding: 12px 16px; text-align: left; }
            th { background-color: #f8fafc; font-weight: 600; color: #475569; }
            tr:nth-child(even) { background-color: #f8fafc; }
            .pass { color: #10b981; font-weight: 600; }
            .fail { color: #ef4444; font-weight: 600; }
            
            /* Card style for details */
            details.eval-details {
                background-color: #fff;
                border-radius: 8px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.05);
                margin-bottom: 15px;
                border: 1px solid #e2e8f0;
                overflow: hidden;
            }
            summary.eval-summary {
                padding: 15px 20px;
                background-color: #f8fafc;
                cursor: pointer;
                font-weight: 600;
                display: flex;
                justify-content: space-between;
                align-items: center;
                outline: none;
            }
            summary.eval-summary:hover {
                background-color: #f1f5f9;
            }
            .eval-content {
                padding: 20px;
                border-top: 1px solid #e2e8f0;
            }
            .eval-name { font-size: 1.1em; color: #1e293b; }
            .eval-status { padding: 4px 8px; border-radius: 4px; font-size: 0.9em; }
            .eval-status.pass { background-color: #d1fae5; color: #065f46; }
            .eval-status.fail { background-color: #fee2e2; color: #991b1b; }
            
            pre { background-color: #1e293b; color: #f8fafc; padding: 15px; border-radius: 6px; max-height: 500px; overflow-y: auto; font-family: monospace; font-size: 0.9em; }
        </style>
        <script>
          function expandOnHash() {
            var hash = window.location.hash;
            if (hash) {
              var elem = document.querySelector(hash);
              if (elem && elem.tagName === 'DETAILS') {
                elem.open = true;
              }
            }
          }
          window.addEventListener('hashchange', expandOnHash);
          window.addEventListener('load', expandOnHash);
        </script>
    </head>
    <body>
        <h1>Simulation Run Results</h1>
        
        <h2>Summary</h2>
        <table>
            <tr>
                <th>Name</th>
                <th>Result</th>
                <th>Details</th>
                <th>Session Link</th>
            </tr>
    """
    
    for res in results:
        name = res['name']
        passed = res['passed']
        status_class = "pass" if passed else "fail"
        status_text = "Pass" if passed else "Fail"
        
        log_rel_path = os.path.join("sim_evals", os.path.basename(res['log_path']))
        
        parts = app_name.split("/")
        project = parts[1]
        location = parts[3]
        app_id = parts[5]
        session_id = res['session_id']
        
        console_link = f"https://ces.cloud.google.com/projects/{project}/locations/{location}/apps/{app_id}?panel=conversation_list&id={session_id}&source=LIVE"
        
        anchor = name.replace(" ", "_").replace(".", "_")
        
        html_content += f"""
            <tr>
                <td>{name}</td>
                <td class="{status_class}">{status_text}</td>
                <td><a href="#{anchor}">View Details</a> (<a href="{log_rel_path}" target="_blank">Log File</a>)</td>
                <td><a href="{console_link}" target="_blank">Session Link</a></td>
            </tr>
        """
        
    html_content += """
        </table>
        
        <h2>Detailed Status</h2>
    """
    
    for res in results:
        name = res['name']
        anchor = name.replace(" ", "_").replace(".", "_")
        
        goals_html = res['goals_html']
        goals_html = goals_html.replace('<td>Completed</td>', '<td class="pass">Completed</td>')
        goals_html = goals_html.replace('<td>In Progress</td>', '<td class="pass">In Progress</td>')
        goals_html = goals_html.replace('<td>Not Started</td>', '<td class="fail">Not Started</td>')
        
        exp_html = res['expectations_html']
        if exp_html:
            exp_html = exp_html.replace('<td>Met</td>', '<td class="pass">Met</td>')
            exp_html = exp_html.replace('<td>Not Met</td>', '<td class="fail">Not Met</td>')
            
        escaped_log = ansi_to_html(res['colored_trace'])
        
        status_class = "pass" if res['passed'] else "fail"
        status_text = "Pass" if res['passed'] else "Fail"
        
        html_content += f"""
        <details class="eval-details" id="{anchor}">
            <summary class="eval-summary">
                <span class="eval-name">{name}</span>
                <span class="eval-status {status_class}">{status_text}</span>
            </summary>
            <div class="eval-content">
                <h4>Goal Progress</h4>
                {goals_html}
        """
        
        if exp_html:
            html_content += f"""
                <h4>Expectations</h4>
                {exp_html}
            """
            
        analysis_results = res.get('analysis_results', [])
        if analysis_results:
            analysis_html = "<h4>Cognitive Diagnostics</h4><ul>"
            for analysis in analysis_results:
                issues_str = ", ".join(analysis['issues']) if analysis['issues'] else "None"
                analysis_html += f"""
                <li>
                    <b>Agent:</b> {analysis['agent']}<br/>
                    <b>Planned Action:</b> {analysis['planned_action']}<br/>
                    <b>Issues:</b> {issues_str}<br/>
                    <details style="margin-top: 5px;">
                        <summary style="font-size: 0.9em; color: #64748b;">View Monologue</summary>
                        <pre style="background-color: #f8fafc; color: #333; padding: 10px; border: 1px solid #e2e8f0; font-size: 0.85em; max-height: 200px; overflow-y: auto;">{analysis['monologue']}</pre>
                    </details>
                </li>
                """
            analysis_html += "</ul>"
            
            html_content += f"""
                {analysis_html}
            """
            
        llm_suggestions = res.get('llm_suggestions', '')
        if llm_suggestions:
            html_content += f"""
                <h4>Actionable Suggestions</h4>
                <pre style="background-color: #f0fdf4; color: #166534; padding: 15px; border: 1px solid #bbf7d0; border-radius: 5px; white-space: pre-wrap; font-family: inherit;">{llm_suggestions}</pre>
            """
            
        html_content += f"""
                <h4>Conversation Trace</h4>
                <pre>{escaped_log}</pre>
            </div>
        </details>
        """
        
    html_content += """
    </body>
    </html>
    """
    
    output_path = os.path.abspath(os.path.join(evals_dir, "..", "summary.html"))
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"\\nGenerated HTML summary report at: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Run CXAS Simulation Evaluations.")
    parser.add_argument("--app_name", required=True, help="Full resource name of the app (projects/.../locations/.../apps/...)")
    parser.add_argument("--output_dir", required=True, help="Base output directory containing sim_evals/")
    parser.add_argument("--parallelism", type=int, default=5, help="Number of parallel workers")
    parser.add_argument("--start_index", type=int, default=0, help="Start index of files to run")
    parser.add_argument("--end_index", type=int, default=10, help="End index of files to run")
    parser.add_argument("--skip_analysis", action="store_true", help="Skip cognitive diagnostics and LLM analysis")
    args = parser.parse_args()

    evals_dir = os.path.join(args.output_dir, 'sim_evals')
    if not os.path.exists(evals_dir):
        print(f"Error: Directory {evals_dir} does not exist.")
        sys.exit(1)

    files = sorted([f for f in os.listdir(evals_dir) if f.endswith(".json")])
    files_to_run = files[args.start_index:args.end_index]
    
    print(f"Running evaluations from index {args.start_index} to {args.end_index} (total files: {len(files)})")

    results_list = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.parallelism) as executor:
        future_to_item = {
            executor.submit(run_single_eval, item, evals_dir, args.app_name, args.skip_analysis): item
            for item in files_to_run
        }
        for future in concurrent.futures.as_completed(future_to_item):
            item = future_to_item[future]
            try:
                result = future.result()
                results_list.append(result)
                print(f"Completed: {result['name']} - {'Pass' if result['passed'] else 'Fail'}")
            except Exception as exc:
                print(f"{item} generated an exception: {exc}")
                results_list.append({
                    "name": item,
                    "session_id": "N/A",
                    "passed": False,
                    "log_path": os.path.join(evals_dir, item.replace(".json", ".log")),
                    "colored_trace": f"Exception occurred during execution:\n{exc}",
                    "goals_df": pd.DataFrame(columns=['status']),
                    "expectations_df": None
                })

    generate_html_report(results_list, evals_dir, args.app_name)

if __name__ == "__main__":
    main()
