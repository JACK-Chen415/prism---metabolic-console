import { SESSION_STORAGE_KEYS, UI_STORAGE_KEYS } from '../constants/storage';

export type ChatMode = 'STRICT' | 'GENTLE';
export type AssistantIntensity = 'LOW' | 'STANDARD' | 'HIGH';

export const CHAT_PREFERENCE_CHANGED_EVENT = 'prism:chat-preferences-updated';

export function getChatSessionId(): number | null {
  const raw = sessionStorage.getItem(SESSION_STORAGE_KEYS.chatSessionId);
  const parsed = raw ? Number.parseInt(raw, 10) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : null;
}

export function setChatSessionId(sessionId: number): void {
  sessionStorage.setItem(SESSION_STORAGE_KEYS.chatSessionId, String(sessionId));
}

export function clearChatSessionId(): void {
  sessionStorage.removeItem(SESSION_STORAGE_KEYS.chatSessionId);
}

export function getChatMode(): ChatMode {
  return localStorage.getItem(UI_STORAGE_KEYS.chatMode) === 'GENTLE' ? 'GENTLE' : 'STRICT';
}

export function setChatMode(mode: ChatMode): void {
  localStorage.setItem(UI_STORAGE_KEYS.chatMode, mode);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(CHAT_PREFERENCE_CHANGED_EVENT, {
      detail: {
        chatMode: mode,
        assistantIntensity: getAssistantIntensity(),
      },
    }));
  }
}

export function getAssistantIntensity(): AssistantIntensity {
  const raw = localStorage.getItem(UI_STORAGE_KEYS.assistantIntensity);
  return raw === 'LOW' || raw === 'HIGH' ? raw : 'STANDARD';
}

export function setAssistantIntensity(intensity: AssistantIntensity): void {
  localStorage.setItem(UI_STORAGE_KEYS.assistantIntensity, intensity);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(CHAT_PREFERENCE_CHANGED_EVENT, {
      detail: {
        chatMode: getChatMode(),
        assistantIntensity: intensity,
      },
    }));
  }
}

export function saveFoodScanResult(result: unknown): void {
  sessionStorage.setItem(SESSION_STORAGE_KEYS.foodScanResult, JSON.stringify(result));
}

export function consumeFoodScanResult<T>(): T | null {
  const raw = sessionStorage.getItem(SESSION_STORAGE_KEYS.foodScanResult);
  if (!raw) return null;
  sessionStorage.removeItem(SESSION_STORAGE_KEYS.foodScanResult);

  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function clearSensitiveSessionState(): void {
  clearChatSessionId();
  sessionStorage.removeItem(SESSION_STORAGE_KEYS.foodScanResult);
}
