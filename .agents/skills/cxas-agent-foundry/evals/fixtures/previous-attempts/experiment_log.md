# Experiment Log

Tracking what was tried and whether it helped or hurt.

## Iteration 1 — 2026-04-08
**Change:** baseline
**Result:** 37/55 (67.3%) — baseline
**Status:** baseline (+0)

## Iteration 2 — 2026-04-08
**Change:** Simplified instruction — removed examples and verbose context to make it cleaner
**Result:** 22/55 (40.0%) — regressed from 37/55 (67.3%)
**Status:** reverted (-15)
**Lesson:** Wholesale instruction rewrites lose context the LLM depends on. Never simplify by removing examples.

## Iteration 3 — 2026-04-09
**Change:** Added hardcoded phrase list to before_model_callback for profanity detection
**Result:** 40/55 (72.7%) — improved from 37/55 (67.3%)
**Status:** reverted (+3)
**Lesson:** Passed goldens but sims dropped from 7/7 to 3/7. Hardcoded phrases miss natural language variations. Keep detection in LLM instructions, not callbacks.

## Iteration 4 — 2026-04-09
**Change:** Added hide_tool() to prevent LLM from calling update_payload directly
**Result:** 32/55 (58.2%) — regressed from 37/55 (67.3%)
**Status:** reverted (-5)
**Lesson:** hide_tool() reduced LLM's overall tool awareness. Agent stopped calling other tools too. Don't use hide_tool() as a primary strategy.

## Iteration 5 — 2026-04-09
**Change:** Added negative condition to trigger: "Customer describes issue that is NOT home internet"
**Result:** 35/55 (63.6%) — regressed from 37/55 (67.3%)
**Status:** reverted (-2)
**Lesson:** Negative conditions in triggers confuse the LLM. Use positive triggers + separate earlier step for excluded category.
