# `components/views/ChatView.tsx` index

This is intentionally a single large component (1479 lines after the
header banner) because the chat, voice input, image attach, intake
confirmation, and intake re-evaluation flows are deeply coupled through
shared state (`messages`, `pendingIntakeSession`, `pendingTextClarification`).
Splitting into hooks / sub-components requires careful thought about
shared state ownership.

## Layout

| Lines (approx) | Section |
| --- | --- |
| 1-15 | Module header banner |
| 15-30 | Imports |
| 30-55 | Module-level helpers (`renderMarkdown`, marked config) |
| 55-110 | Types: `Message`, `RecognizedFood`, `RecognitionResponse`, `PendingImage`, `PendingTextClarification` |
| 110-170 | State + refs |
| 170-230 | Session lifecycle effects (init, history load, persist) |
| 230-380 | Chat send / stream handlers |
| 380-540 | Voice input handlers (start/stop recognition, transcript merge, text log mode) |
| 540-720 | Image input handlers (file pick, preview, attach to send) |
| 720-1080 | Intake session handling (`handleConfirmIntake`, re-evaluation, voice auto log, text log submission) |
| 1080-1480 | Render: header, messages list, input bar, intake sheet |

Line numbers are approximate; use `grep -n "^  const handle\|^  const send\|^  async function\|=>\s*{" components/views/ChatView.tsx` for exact locations.

## Refactor plan (not yet executed)

When this file becomes painful to navigate, extract the following:

1. `hooks/useChatStream.ts` — `messages`, `isSending`, `currentMode`,
   send/stream handlers.
2. `hooks/useVoiceInput.ts` — `isListening`, recognition start/stop,
   transcript merge with existing input value.
3. `hooks/useImageAttach.ts` — `pendingImage`, file pick, preview URL.
4. `hooks/useIntakeDraft.ts` — `pendingIntakeSession`, re-evaluation,
   confirmation submission, voice auto-log.
5. `components/MessageBubble.tsx` — single message row rendering.
6. `components/ChatInputBar.tsx` — text input + voice button + image attach
   button + send button.
7. `components/IntakeSessionHeader.tsx` — header banner shown when a
   pending intake session exists.
8. `utils/renderMarkdown.ts` — `renderMarkdown` helper (currently
   module-level).

This refactor should land in its own commit (not bundled with anything else)
once a follow-up ticket is filed.

## Public API contract

```
interface ChatViewProps {
  onViewChange: (view: View) => void;
  onMealLogged?: (recordDate?: string) => void | Promise<void>;
  pendingIntakeSession: IntakeDraftSession | null;
  onPendingIntakeSessionChange: (session: IntakeDraftSession | null) => void;
}
```

ChatView is consumed from `App.tsx`. It does not expose imperative methods.
