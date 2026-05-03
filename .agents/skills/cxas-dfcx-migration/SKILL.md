---
name: cxas-dfcx-migration
description: >-
  Migrate Dialogflow CX (DFCX) agents to CXAS (Customer Experience Agent Studio) agents.
  Use this skill when the user mentions DFCX migration, migrating agents, converting DFCX to CXAS,
  porting agents, or agent migration. Guides users through source agent loading, configuration,
  resource selection, dependency analysis, and automated migration execution.
---

# DFCX to CXAS Migration

End-to-end migration of Dialogflow CX agents to CXAS generative agents.

## Quick Reference

```bash
# Run migration interactively (prompts for all options)
python .agents/skills/cxas-dfcx-migration/scripts/run_migration.py

# Run migration with arguments
python .agents/skills/cxas-dfcx-migration/scripts/run_migration.py \
  --source-agent-id "projects/<proj>/locations/<loc>/agents/<uuid>" \
  --project-id <target_project> \
  --target-name "my_migrated_agent" \
  --model "gemini-2.5-flash-001"

# Run migration from a local zip export
python .agents/skills/cxas-dfcx-migration/scripts/run_migration.py \
  --zip-file "/path/to/exported_agent.zip" \
  --project-id <target_project> \
  --target-name "my_migrated_agent"
```

## Migration Flow

Follow these steps in order. Ask the user for each piece of information **one at a time** -- do not batch all questions into a single message. If the user provides details upfront, skip those questions.

### Step 1: Environment Check

Verify the environment is ready before proceeding:

```bash
python -c "from cxas_scrapi.migration.service import MigrationService; print('cxas_scrapi OK')"
```

```bash
gcloud auth list
```

If `cxas_scrapi` is not installed, install it:
```bash
pip install -e <path_to_cxas_scrapi>
```

If `gcloud` is not authenticated:
```bash
gcloud auth login
gcloud auth application-default login
```

### Step 2: Load Source Agent

Ask the user how to load the source DFCX agent:

| Option | Details |
|--------|---------|
| **Agent ID** | Full resource name: `projects/<project>/locations/<location>/agents/<uuid>` |
| **Zip File** | Path to a local `.zip` export of the DFCX agent |

- If **Agent ID**: the script will fetch agent data via the Conversational Agents API.
- If **Zip File**: the script will parse the exported zip to extract agent data locally.

### Step 3: Migration Configuration

Collect these configuration values from the user. Show the default in parentheses and accept it if the user presses enter or confirms the default.

| Parameter | Description | Options / Default |
|-----------|-------------|-------------------|
| **Google Cloud Project ID** | Target GCP project where the CXAS agent will be created | *(required, no default)* |
| **Target Agent Name** | Display name for the new CXAS agent | Default: `migrated_agent_<timestamp>` |
| **Environment** | Deployment environment | `PROD` (default) or `AUTOPUSH` |
| **Global App Model** | Gemini model for all agents | See model list below. Default: `gemini-2.5-flash-001` |
| **Logic Version** | Migration logic version | `2.0` (default, supports Flows + Playbooks) or `1.0` (legacy, Playbooks only) |
| **Generate Migration Report** | Produce a markdown report of the migration | `yes` (default) or `no` |
| **Generate Unit Tests** | Auto-generate and auto-fix unit tests | `yes` (default) or `no` |
| **Generate Hillclimbing Evals** | Generate iterative optimization evals | `yes` or `no` (default) |
| **Eval Target** | Evaluation runner backend | `Custom API Runner` (default) or `Native Product Eval (Stub)` |
| **Optimize for CXAS** | Apply CXAS-specific optimizations | `yes` or `no` (default) |

#### Available Models

- `gemini-3.0-flash-001`
- `gemini-3.0-pro-001`
- `gemini-2.5-flash-001` (default)
- `gemini-2.5-flash-native-audio-preview`
- `gemini-3-flash-native-audio`

> **Note:** For migrating agents with Flows or Hybrid (Flows + Playbooks), **Logic Version must be `2.0`**.

### Step 4: Resource Selection

After loading the source agent, display the available resources:

1. List all **Playbooks** with their display names
2. List all **Flows** with their display names
3. Ask the user which resources to include in the migration:
   - Default: **all selected**
   - User can exclude specific resources by number
   - User can start with **none** and include specific resources by number

Classify the migration type based on selection:
- Only Playbooks selected -> **Pure Playbooks**
- Only Flows selected -> **Pure Flows** (requires Logic Version 2.0)
- Both selected -> **Hybrid Agent** (requires Logic Version 2.0)

### Step 5: Dependency Analysis (Optional)

Ask the user if they want to run dependency analysis. If yes:

1. Identify **outgoing dependencies** -- resources referenced by the selection but not included
2. Identify **incoming references** -- unselected resources that reference the selection
3. Display warnings for missing dependencies
4. Suggest adding missing dependencies to the selection

### Step 6: Visualization (Optional)

Ask the user if they want to generate visualizations:

1. **Topology graph** (SVG) -- high-level view of selected resources and relationships
2. **Detailed resources** (Markdown) -- resource trees with full detail

Files are exported as `<target_name>_topology.svg` and `<target_name>_detailed_resources.md`.

### Step 7: Review and Confirm

Before starting migration, display a summary:

```
Target Agent:        <target_name>
Project:             <project_id>
Environment:         <env>
Model:               <model>
Logic Version:       <version>
Selected Playbooks:  <count>
Selected Flows:      <count>
Migration Type:      Pure Playbooks / Pure Flows / Hybrid
```

Ask: **"Proceed to Migration?"**

- If no, offer to re-configure and re-select resources
- If yes, proceed to Step 8

### Step 8: Execute Migration

Run the migration:

```bash
python .agents/skills/cxas-dfcx-migration/scripts/run_migration.py \
  --source-agent-id "<agent_id>" \
  --project-id "<project_id>" \
  --target-name "<target_name>" \
  --env "<env>" \
  --model "<model>" \
  --migration-version "<version>" \
  --gen-report \
  --gen-unit-tests
```

Or execute programmatically:

```python
import asyncio
from cxas_scrapi.migration.service import MigrationService
from cxas_scrapi.migration.data_models import MigrationConfig

service = MigrationService(project_id="<project_id>", location="global")
config = MigrationConfig(
    project_id="<project_id>",
    target_name="<target_name>",
    env="PROD",
    model="gemini-2.5-flash-001",
    source_agent_data_override=filtered_data,
)
asyncio.run(service.run_migration(source_cx_agent_id="<agent_id>", config=config))
```

The migration will:
1. Export and preprocess the source DFCX agent data
2. Generate agent descriptions using AI
3. Extract and migrate parameters/variables
4. Convert tools, webhooks, and code blocks
5. Compile playbooks and flows into CXAS agents
6. Deploy base resources (App, Variables, Tools)
7. Deploy agents
8. Process flows with AI-generated instructions
9. Link topology and finalize
10. Generate migration report

### Post-Migration

After migration completes:
- The CXAS agent URL will be displayed
- A migration report will be downloaded (if enabled)
- Review the migration status table for any failed resources

## Detailed Reference

For detailed documentation of each configuration option, see `references/migration-options.md`.
