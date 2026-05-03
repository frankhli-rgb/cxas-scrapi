# Migration Configuration Options Reference

Detailed documentation for each configuration parameter in the DFCX-to-CXAS migration.

## Source Agent

### Agent ID
- **Format:** `projects/<project_id>/locations/<location>/agents/<uuid>`
- **When to use:** When the source DFCX agent is deployed and accessible via the Conversational Agents API. Requires active `gcloud` authentication with appropriate permissions.

### Zip File
- **Format:** Local file path to a `.zip` export
- **When to use:** When you have a local export of the DFCX agent, or when the agent is not directly accessible via API (e.g., different project, restricted access). Export the agent from the Dialogflow CX console first.

## Configuration Parameters

### Google Cloud Project ID
- **Required:** Yes
- **Description:** The GCP project where the new CXAS agent will be created. This is the *target* project -- it may differ from the source agent's project.

### Target Agent Name
- **Default:** `migrated_agent_<YYYYMMDD_HHMMSS>`
- **Description:** The display name for the new CXAS application. This name appears in the CXAS console and is used as a prefix for exported files (reports, visualizations).

### Environment
- **Options:** `PROD`, `AUTOPUSH`
- **Default:** `PROD`
- **Description:**
  - `PROD` -- Standard production API endpoints. Use for all regular migrations.
  - `AUTOPUSH` -- Pre-production API endpoints for testing new platform features. Only use if specifically directed by the CXAS team.

### Global App Model
- **Options:**
  - `gemini-3.0-flash-001` -- Latest Flash model, best balance of speed and quality
  - `gemini-3.0-pro-001` -- Pro-tier model for complex reasoning tasks
  - `gemini-2.5-flash-001` -- Stable Flash model (default)
  - `gemini-2.5-flash-native-audio-preview` -- Flash with native audio support (preview)
  - `gemini-3-flash-native-audio` -- Flash with native audio support (GA)
- **Default:** `gemini-2.5-flash-001`
- **Description:** The Gemini model assigned to all agents in the migrated app. Individual agent models can be changed post-migration in the CXAS console. Choose audio-capable models if the source agent handles voice interactions.

### Logic Version
- **Options:** `1.0`, `2.0`
- **Default:** `2.0`
- **Description:**
  - `1.0` -- Legacy migration logic. Only supports Playbook-based agents. Use for simple agents with only Playbooks.
  - `2.0` -- Current migration logic. Supports Playbooks, Flows, and Hybrid (Playbooks + Flows) agents. **Required** for any agent containing Flows.
- **Important:** If your source agent has Flows and you select version 1.0, the Flows will be skipped.

### Generate Migration Report
- **Default:** `yes`
- **Description:** Produces a detailed Markdown report documenting the migration, including:
  - All converted tools and their mapping
  - All generated agents with descriptions
  - Parameter migrations
  - Warnings and issues encountered
  - The report is downloaded as `<target_name>_migration_report.md`.

### Generate Unit Tests (Auto-Fix)
- **Default:** `yes`
- **Description:** Automatically generates unit tests for the migrated tools and agents. When enabled, the migration system will also attempt to auto-fix common issues detected by the tests.

### Generate Hillclimbing Evals
- **Default:** `no`
- **Description:** Generates iterative optimization evaluations that progressively improve agent quality. These evals run the agent through scenarios and use the results to suggest instruction improvements. This is an advanced feature for post-migration optimization.

### Eval Target
- **Options:** `Custom API Runner`, `Native Product Eval (Stub)`
- **Default:** `Custom API Runner`
- **Description:**
  - `Custom API Runner` -- Uses the SCRAPI evaluation framework to run tests via the API. Full-featured with detailed reporting.
  - `Native Product Eval (Stub)` -- Placeholder for native CXAS evaluation integration. Limited functionality.

### Optimize for CXAS
- **Default:** `no`
- **Description:** Applies CXAS-specific optimizations to the generated instructions and agent configuration. When enabled, the migration may restructure instructions to better leverage CXAS-specific features like agent routing syntax, tool invocation patterns, and callback hooks.

## Resource Selection

### Playbooks
Playbooks are the primary building blocks in Playbook-based DFCX agents. Each playbook maps to a CXAS Agent with:
- Converted instructions (with `{@AGENT:}` and `{@TOOL:}` routing syntax)
- Linked tools and toolsets
- Model settings

### Flows
Flows are state-machine-based conversation logic in Flow-based DFCX agents. Each flow is processed through a multi-step AI pipeline:
1. **Step 2A:** Architecture blueprinting (analyzes flow structure)
2. **Step 2B:** Instruction generation (produces PIF XML instructions)
3. **Step 2C:** Tool and callback generation (creates Python tools and callbacks)

Each flow maps to a CXAS Agent with AI-generated instructions, tools, and callbacks.

## Migration Types

| Type | Selected Resources | Logic Version |
|------|-------------------|---------------|
| Pure Playbooks | Only Playbooks | 1.0 or 2.0 |
| Pure Flows | Only Flows | 2.0 required |
| Hybrid Agent | Playbooks + Flows | 2.0 required |
