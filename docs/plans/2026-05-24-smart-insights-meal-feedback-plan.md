# Smart Insights meal-feedback implementation plan

## Goal
Build a usable end-to-end “智能洞察” feature that:
- detects missing breakfast/lunch/dinner logs during configured meal windows
- evaluates logged meals against user profile, daily targets, chronic conditions, allergies, and food knowledge rules
- generates actionable insight messages for the home page and message center
- shows mobile in-app popup alerts for new critical insights
- supports continuous regeneration after meal changes without requiring manual chat interaction

## Current baseline
Confirmed from code audit:
- Frontend already renders `latestMessage` on `HomeView` and full history in `MessageView`.
- Frontend loads `profile`, `dailyTargets`, `meals`, `conditions`, `messages` through `useAppData`.
- Backend already has persisted `meals`, `health_conditions`, `app_messages`.
- Backend already has `calculate_daily_targets(...)` and a local-first `KnowledgeService` for food-vs-condition evaluation.
- There is currently no meal-window missing-log detector, no insight-generation service, no insight-specific API, and no popup notification loop.
- There is currently no browser/system push infrastructure; the realistic first delivery is in-app popup + persisted messages. True OS push can be a later phase.

## Product scope for this implementation
This implementation should cover:
1. Missing meal reminders for breakfast/lunch/dinner.
2. Meal quality feedback after logs exist:
   - calories too high / too low for the meal window and day progress
   - sodium too high
   - purine too high for gout users
   - likely macro imbalance (carbs/protein/fat skewed)
   - fiber likely too low
   - condition-based caution from local knowledge rules
   - allergy / explicit restriction conflict when identifiable
3. Helpful positive feedback when meal quality is acceptable.
4. Persisted insight messages that feed Home + Message Center.
5. Mobile in-app popup for newly created warning-level insights.

## Non-goals for this round
- True APNs/FCM/native push delivery
- Background server scheduler / cron-based delivery outside active app use
- Medical-grade diagnosis or prescription logic
- Complex per-user configurable meal windows UI

## Delivery strategy
Follow smallest viable slices with independent verification after each slice.
Default chain for each slice:
- Hermes plans
- Codex implements
- Gemini independently reviews changed files + tests/logs
- Hermes accepts/rejects and advances automatically

## Proposed slices

### Slice 1 — backend insight contracts + pure evaluation engine
Create a backend service that, given user/profile/conditions/meals/date/time, produces structured insight candidates without yet wiring persistence everywhere.

Deliverables:
- new backend schemas/contracts for insight candidate output
- pure evaluation logic for:
  - missing breakfast/lunch/dinner detection
  - calorie high/low heuristics by meal type
  - sodium excess detection
  - purine excess detection for gout target users
  - macro balance heuristic using available protein/carbs/fat grams
  - low fiber heuristic when data exists
  - condition/allergy food caution aggregation via `KnowledgeService`
- unit tests for core heuristics

Acceptance:
- pytest for new insight tests passes
- no existing tests regress

### Slice 2 — backend persistence + API endpoint
Wire the evaluator to persisted `AppMessage` generation and expose an endpoint to refresh/fetch smart insights.

Deliverables:
- service to upsert/deduplicate insight messages for today
- stable message titles/content/type generation
- API route such as `POST /insights/refresh` and/or `GET /insights/today`
- dedupe strategy to avoid repeated spam for same date/meal/risk
- route tests

Acceptance:
- endpoint returns generated insight summary
- messages persist and appear in `/messages`
- repeated refresh is idempotent enough for the same state

### Slice 3 — frontend data integration
Make app load/generate insights as part of home/log lifecycle.

Deliverables:
- frontend API client methods for insight refresh/fetch
- `useAppData` integration to trigger refresh after login and after meal add/update/delete
- local state refresh so HomeView and MessageView show new insights immediately

Acceptance:
- after meal mutations, insight list refreshes without app restart
- home card reflects latest message

### Slice 4 — mobile in-app popup alerts
Show a lightweight mobile popup when a new warning insight arrives.

Deliverables:
- popup/toast component at app shell level
- show only for newly created warning-level insights
- avoid re-showing already surfaced popup in the same session
- graceful fallback if notification permission/system APIs unavailable

Acceptance:
- simulated warning insight appears as popup
- repeated renders do not spam duplicate popups

### Slice 5 — copy, thresholds, UX polish, and review hardening
Refine titles/content and ensure output is useful and not noisy.

Deliverables:
- clearer Chinese copy for each insight type
- cap number of simultaneous insights
- ensure positive feedback appears only when no stronger warning exists
- regression checks for home/message mobile presentation

Acceptance:
- build passes
- pytest passes
- Gemini review signs off or returns bounded follow-up fixes

## Heuristic notes for first implementation
To keep scope controlled, the first implementation should use deterministic rules rather than LLM generation.

### Meal windows
Suggested defaults:
- breakfast reminder window: 08:30–10:00
- lunch reminder window: 12:00–14:00
- dinner reminder window: 18:00–20:00
Only remind for the current local date and only if the corresponding meal type is absent.

### Meal calorie heuristics
Use daily recommended target when available; otherwise fallback to `dailyTargets.calories`.
Suggested meal shares:
- breakfast: 20–30%
- lunch: 30–40%
- dinner: 30–35%
- snack: informational only unless clearly excessive
Flag if a meal is far above or below its band.

### Daily energy progression
Also compare current total consumed vs time-of-day progress:
- by lunch window, total intake too low may trigger under-eating reminder
- by dinner window, total intake already too high may trigger caution

### Macro heuristics
When protein/carbs/fat all present, compute energy ratio using 4/4/9 kcal per g.
Simple imbalance hints:
- carbs > 65% => carbs heavy
- fat > 40% => fat heavy
- protein < 15% => protein weak
Only emit strongest macro imbalance message per meal.

### Condition/allergy logic
Leverage existing `KnowledgeService.evaluate_food_for_user(...)` per meal item where possible.
Use returned signals for:
- AVOID / LIMIT -> warning
- MODERATE / CONDITIONAL -> advice
- hard blocks -> highest severity warning
Aggregate duplicate food-level cautions into one meal-level insight.

## Implementation order now
Start immediately with Slice 1 because:
- it is the smallest backend-only foundation
- it minimizes UI churn
- it enables deterministic tests before persistence wiring

## Verification commands
Backend:
- run targeted pytest for new smart insight tests first
- then broader pytest subset if needed
Frontend:
- run build after frontend slices

## Risks
- Knowledge DB coverage may be incomplete for some foods; fallback copy must acknowledge partial coverage.
- Existing messages table has only generic message fields; dedupe must rely on stable titles/content or a lightweight signature strategy in the service layer.
- Without true push infra, “弹窗提示” will be implemented as in-app popup for this round.

## Done definition
Feature is considered complete for this round when:
- missing meal reminders work
- meal feedback works against profile + conditions + allergies + daily targets
- insights persist into message center
- home page shows latest insight
- app shows in-app popup for new warning insights
- backend tests and frontend build pass
- Gemini reviews each implementation round
