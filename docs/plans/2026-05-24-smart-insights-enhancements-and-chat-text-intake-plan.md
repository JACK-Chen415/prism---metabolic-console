# Smart insights enhancements and chat text intake implementation plan

## Goal
Complete four smart-insight enhancements plus AI conversational text meal logging, using smallest-verifiable slices with Codex execution and Gemini review after each meaningful slice.

## Architecture
Reuse the existing deterministic `insights.py` evaluator, persisted `AppMessage` smart-insight pipeline, and `IntakeDraftSession` confirmation flow. Do not build a parallel ingestion system for chat text logging; instead, let chat text intent detection produce the same draft-session/candidate structures already used by voice/photo intake so frontend confirmation, reevaluation, and final meal writes stay unified.

## Scope
1. Configurable breakfast/lunch/dinner meal windows
2. Insight prioritization / grouping / anti-spam compression
3. Auto-refresh smart insights after profile/condition changes
4. Actionable meal coaching copy for insight messages
5. New AI chat text-to-meal logging flow:
   - detect meal-log intent from free text in chat
   - decide whether information is sufficient
   - ask for missing required info when insufficient
   - infer approximate values when user answer is fuzzy
   - refuse when data is too incomplete to record safely
   - write to meal log via existing intake confirmation/logging pipeline

## Existing code anchors
- Backend insight engine: `backend/app/services/insights.py`
- Insight persistence/API: `backend/app/api/routes/insights.py`
- Frontend auto-refresh state: `hooks/useAppData.ts`
- Chat UI + pending intake sheet flow: `components/views/ChatView.tsx`
- Intake routes: `backend/app/api/routes/intake.py`
- Intake parsing/writing service: `backend/app/services/intake.py`
- Chat routes/streaming: `backend/app/api/routes/chat.py`
- Shared intake schemas: `backend/app/schemas/intake.py`

## Slice order

### Slice 1
Backend-only configurable meal windows for smart insights.
- Keep default windows intact.
- Add testable override mechanism in insight service.
- No frontend settings UI yet.
- Verify with targeted backend tests.

### Slice 2
Backend insight prioritization / grouping / anti-spam compression.
- Prevent too many simultaneous insights for same meal/day.
- Introduce explicit ranking and message compression rules.
- Verify with targeted backend tests.

### Slice 3
Backend actionable coaching copy.
- Upgrade candidate message/title generation to provide next-step suggestions.
- Keep deterministic and rules-based.
- Verify with targeted backend tests.

### Slice 4
Frontend refresh hook for profile and condition mutations.
- After profile update and conditions CRUD, refresh smart insights/messages.
- Keep guest mode safe.
- Verify with frontend build.

### Slice 5
Backend chat text-intent detection and draft-session generation.
- Add a text-intake parse endpoint or chat-integrated backend helper.
- Reuse `IntakeDraftSessionResponse` schema where possible.
- Detect sufficient vs missing-info vs refusal.
- Add targeted tests for intent detection and missing-field prompts.

### Slice 6
Frontend ChatView integration for text meal logging drafts.
- When user sends text that looks like a meal-log request, route to text-intake parser instead of ordinary chat completion.
- If sufficient: open pending intake confirmation sheet.
- If missing info: AI/system asks structured follow-up in chat and waits for user answer.
- If impossible: respond with refusal and explanation.
- Verify with frontend build.

### Slice 7
Backend fuzzy-answer completion / approximate inference.
- Allow vague answers like "一小碗", "有点咸", "还好" to fill candidate estimates.
- Mark inferred values in `estimated_fields` / `estimated_notes`.
- Verify with targeted tests.

### Slice 8
Frontend conversational follow-up state machine for text intake.
- Persist pending text-intake clarification state inside chat session UI.
- Merge follow-up answers into draft candidates.
- Auto-confirm path if enough information becomes available.
- Verify with frontend build.

### Slice 9
End-to-end polish and final review.
- Run backend targeted test suite for insights/intake/chat slices.
- Run frontend build.
- Gemini final review of files/diffs/logs.

## Acceptance notes
- Keep one slice in progress at a time.
- Gemini must independently review each meaningful slice.
- Do not ask user whether to continue between slices.
- Preserve dirty-worktree awareness: Codex prompts must explicitly forbid unrelated edits.
- Smart-insight popup rules from previous slice remain unchanged unless directly needed.
