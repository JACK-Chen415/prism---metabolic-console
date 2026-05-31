# Prism Mobile-First Cleanup and Roadmap Implementation Plan

> For Hermes: Use the PM workflow. Hermes plans and verifies; Codex executes each step; Gemini reviews when a step becomes cross-cutting or high risk.

Goal: Re-align the app around a mobile-first product strategy, remove obviously unfinished/placeholder mobile UI that harms perceived quality, and then iteratively strengthen the core mobile flows.

Architecture: Keep the current mobile shell and camera-driven intake flow as first-class. Remove dead-end placeholder entry points first, then polish the existing mobile core flows, then add missing mobile-value features in small slices. Each step must end with a build verification before the next step starts.

Tech Stack: React + TypeScript + Vite frontend, FastAPI backend, Codex CLI for implementation, Hermes for verification.

---

## Step 1: Remove the dead-end health report archive flow
Objective: Eliminate the empty mobile detour that leads users into an unavailable report archive screen.

Files likely involved:
- Modify: App.tsx
- Modify: components/AppShell.tsx
- Modify: components/views/ProfileView.tsx
- Modify: constants/featureFlags.ts
- Modify: types.ts
- Delete: components/views/HealthReportArchivesView.tsx

Acceptance:
- The profile page no longer exposes the unavailable health report archive card.
- The app no longer routes to HEALTH_REPORT_ARCHIVES.
- The deleted screen is no longer imported or referenced.
- Frontend build passes.

## Step 2: Remove visible "未开放" placeholder noise from core mobile surfaces
Objective: Improve product completeness perception on mobile by removing obvious placeholder UI that the user can see immediately.

Files likely involved:
- Modify: components/views/HomeView.tsx
- Modify: components/views/ProfileView.tsx
- Modify: constants/featureFlags.ts

Acceptance:
- Home no longer shows the unopened recommendation placeholder card.
- Profile no longer shows the avatar-upload-unavailable badge.
- Frontend build passes.

## Step 3: Strengthen the mobile-first camera entry and fallback copy
Objective: Keep camera as a core mobile action while making the entry and fallback states clearer.

Files likely involved:
- Modify: components/BottomNav.tsx
- Modify: components/views/CameraView.tsx
- Possibly modify: components/views/HomeView.tsx

Acceptance:
- Mobile camera entry remains prominent.
- Camera page copy clearly supports both live capture and gallery import.
- Error/fallback wording feels intentional rather than broken.
- Frontend build passes.

## Step 4: Tighten message-center positioning without removing useful insight data
Objective: Keep AI insight data but reduce the feeling that message center is a top-level destination competing with core mobile flows.

Files likely involved:
- Modify: components/views/HomeView.tsx
- Modify: components/views/MessageView.tsx
- Possibly modify: App.tsx or navigation-related files if needed

Acceptance:
- Home still exposes latest insight and unread state.
- Message page copy/structure feels secondary to core logging and AI flows.
- Frontend build passes.

## Step 5: Improve the mobile intake-confirmation loop
Objective: Make the camera/chat/intake flow the strongest path in the app.

Files likely involved:
- Modify: components/views/ChatView.tsx
- Modify: services/api.ts
- Inspect/modify related backend intake/chat files only if needed

Acceptance:
- Candidate confirmation is clearer on small screens.
- Estimated fields/warnings are more visible and understandable.
- Frontend build passes; backend touched only if necessary.

## Step 6: Improve mobile log review for daily use
Objective: Make the log page better for day-by-day phone usage before broader feature expansion.

Files likely involved:
- Modify: components/views/LogView.tsx
- Possibly modify: hooks/useAppData.ts

Acceptance:
- Daily browsing/editing feels smoother on mobile.
- Important nutrition/risk information is easier to scan quickly.
- Frontend build passes.

## Execution rules
- One step at a time.
- No step is considered complete until Hermes verifies the changed files and a frontend build passes.
- If a step touches multiple surfaces or feels risky, add Gemini review before moving on.
- Do not silently expand scope inside a step.
