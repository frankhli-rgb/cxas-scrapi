"""Tier 2: LLM-powered lint rules (Gemini).

Deep analysis of instruction quality, progressive disclosure,
voice naturalness, routing completeness, and callback conflicts.
Runs only with --deep flag.
"""

import json
import os
import re
from pathlib import Path

from . import LintContext, LintReport, LintResult, Rule, Severity


GEMINI_LINT_PROMPT = """You are a GECX (Google Customer Engagement Suite) voice agent quality linter.
Analyze the following agent instruction and return a JSON array of issues found.

For each issue, return:
{{"severity": "ERROR|WARNING|INFO", "rule": "category-name", "message": "description", "fix_suggestion": "how to fix"}}

Check for these anti-patterns from the GECX design guide:

1. **Progressive disclosure violations**: Are instructions loading all context upfront instead of
   embedding instructions in tool responses? Large instruction blocks that could be triggered
   dynamically should use the progressive disclosure pattern (embed rules in tool response text).

2. **Voice naturalness**: Does the <persona> produce human-sounding output? Flag:
   - IVR-style language ("Your call is important to us", "Press 1 for...", "Please listen carefully")
   - Robotic/stiff phrasing that doesn't sound natural in conversation
   - Missing cadence/pacing guidance for voice interactions

3. **Taskflow completeness**: Does the <taskflow> cover all use cases described in the instruction?
   Are there caller intents that wouldn't match any <subtask> or <step> trigger?

4. **Routing completeness**: For root agents with {{@AGENT:}} references — are there caller intents
   that aren't routed to any sub-agent?

5. **Callback conflicts**: Could any instruction behavior conflict with callbacks?
   (e.g., instruction says to greet, but a before_model greeting callback already handles it)

6. **Ambiguous triggers**: Are <trigger> conditions specific enough, or could the LLM interpret
   them too broadly or too narrowly?

7. **Instruction density**: Are there sections that are unnecessarily verbose or redundant?
   Could any sections be simplified without losing meaning?

Return ONLY the JSON array. If no issues found, return [].

Agent instruction file: {filename}
---
{content}
"""


def lint_with_gemini(instructions: dict[str, Path], project_root: Path,
                     report: LintReport):
    """Run Tier 2 LLM-powered linting using Gemini."""
    try:
        from google import genai
    except ImportError:
        print("  [SKIP] Tier 2: google-genai not installed. Run: pip install google-genai")
        return

    client = genai.Client()

    for agent_name, inst_path in instructions.items():
        content = inst_path.read_text()
        rel = str(inst_path.relative_to(project_root))
        print(f"  Tier 2: Analyzing {agent_name}...")

        prompt = GEMINI_LINT_PROMPT.format(filename=rel, content=content)

        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            text = response.text.strip()
            json_match = re.search(r'\[.*\]', text, re.DOTALL)
            if json_match:
                issues = json.loads(json_match.group())
                for issue in issues:
                    sev_str = issue.get("severity", "INFO").lower()
                    try:
                        sev = Severity.from_str(sev_str)
                    except ValueError:
                        sev = Severity.INFO
                    report.add(LintResult(
                        file=issue.get("file", rel),
                        rule_id=f"LLM-{issue.get('rule', 'unknown')}",
                        severity=sev,
                        message=issue.get("message", ""),
                        fix_suggestion=issue.get("fix_suggestion", ""),
                    ))
        except Exception as e:
            print(f"  [WARN] Tier 2 failed for {agent_name}: {e}")
