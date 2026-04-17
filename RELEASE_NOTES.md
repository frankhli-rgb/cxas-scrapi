# Release Notes - 0.1.6

## Summary
This is a major release that introduces significant new capabilities, including a powerful linter, expanded migration tools for Dialogflow CX (DFCX), enhanced simulation capabilities, and a unified CLI.

## New Features
- **Unified CLI (`cxas`)**: Renamed from `cxas-evals` to `cxas` and expanded to support more operations.
- **CXAS Linter**: Added `cxas lint` command with over 60 rules to validate agent configurations.
- **DFCX Migration Tools**: Added `DFCXAgentIR` data models, exporter module, and visualization tools using `graphviz`.
- **New Skills**: 
  - `cxas_sim_eval` for converting goldens to simulations.
  - `cxas-agent-foundry` (renamed and updated).
- **Expectations in Scenarios**: Support for expectations in both text and audio modalities.

## Improvements
- **Simulation Enhancements**: Support for variable injection and DTMF input in simulations.
- **Multi-Turn Evals**: Support for multiple agent turns in evaluations.
- **Prompt Improvements**: Improved user simulation prompts for better handling of DTMF and user utterances.
- **Diagnostic Info**: Better transcript display in DiagnosticInfo.

## Bug Fixes
- Fixed missing `__init__.py` file for local package in utils.
- Fixed client sending empty text chunks.
- Various formatting and linting fixes.

## Documentation/Other
- Added license headers to missing files and hooks.
- Unnested skills for better compatibility.
