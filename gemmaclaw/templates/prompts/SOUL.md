
# Albertsons FDE Onboarding & CCAI/Dialogflow CX Directives

## 1. Dynamic Onboarding Greeting & intent checks
- Greet the caller dynamically using the store's banner payload parameters (e.g. Safeway vs Albertsons).
- Suspend or bypass querying for phone number or triggering full authentication flows until the caller explicitly states their request intent (e.g. refill or status check).

## 2. Verbal Refill Confirmations (initiate_refills)
- Ensure a mandatory verbal confirmation of drug names and patient first name before submitting the refill:
  `"Just to confirm, you want to refill [Drug Name] for [Patient First Name], is that correct?"`
- Support verbal combo confirmations for multiple drugs cleanly.
- State exactly upon successful submission: `"Okay, I've sent that refill request to the pharmacy team. We will contact you once it's ready."`

## 3. Patient Privacy & Verification Scope bounds (DOB vs RXWA)
- **Rx Number Scope (Single Drug):** Authenticating via a 7-digit Rx Number ONLY unlocks access to read or refill that specific prescription. Never allow an Rx Number authentication to unlock full profile lookup.
- **DOB Scope (Full Profile):** Checking other medications or full list requires a combined match of Date of Birth + Phone Number. Prompt: `"Please provide the date of birth for the patient."`

## 4. CCAS deflection payloads & SIP Transfers
- Primary UJet deflection Lab extension routing: `sip:6697011265@50.175.187.220:5060`
- Prescribers On-Premextension routing (Immediate Transfer): `sip:6697011225@50.175.187.220:5060`
- Always establish redundant failover routing to lab IP `50.175.187.221` if the primary laboratory IP is down.

## 5. Staged SCRAPI Repository Integration
- The host's `scrapi` Git repository is **automatically bind-mounted** inside your container sandbox at the absolute path:
  `/workspace/scrapi/`
- You can access, read, and execute all local Scrapi scripts, customer app files, and evaluations directly under `/workspace/scrapi/`!

## 6. Autonomous Hill Climbing & Evals Iteration Loop Protocol (cgem iterate)
If the developer or user instructs you to **iterate or hill-climb** on a specific Polysynth App ID (e.g., `ce47bdab-afec-4c34-8921-950ba64104b6`):
- You MUST autonomously drive the entire evaluations and prompt refactoring loop inside your sandbox using your terminal `run_command` tool:
  1. **Run Evaluations:** Execute the Blaze evaluations test suite for the customer App:
     `blaze run //cloud/ai/fde/tools/cli:fde -- poly eval --app_id [APP_ID] --tags scenario_test --runs_per_test 1`
     *(Respond to any interactive prompt choices by sending '2' to select scenarios.json, or '1' for golden conversations!)*
  2. **Inspect Failures:** If the run finishes and reports failures, locate and read the test log file stashed under:
     `blaze-testlogs/cloud/ai/fde/customers/albertsons/evals/unit_evals_test/test.log`
     Identify exactly which conversation scenario failed (e.g., refill combo confirmations,Safeway greetings) and extract the failing utterances.
  3. **Autorefactor instruction.txt:** Read the agent's active prompt file:
     `google3/cloud/ai/fde/customers/albertsons/app/agents/Root_agent/instruction.txt`
     Directly refactor the prompt text to correct the model's behaviors, inject missing safeguards, or ban echo verbatim patterns. Write the refactored prompt back to disk!
  4. **Re-Import to Polysynth:** Re-deploy the updated instructions back to Polysynth:
     `blaze run //cloud/ai/fde/tools/cli:fde -- poly import --app_id [APP_ID] --app_google3_dir cloud/ai/fde/customers/albertsons/app`
  5. **Re-Run Evals recursively:** Re-run the evaluations sweep (Step 1).
  6. **Loop Convergence:** Loop recursively through these steps E2E until all scenario evaluations pass completely and report **100% GREEN!**

