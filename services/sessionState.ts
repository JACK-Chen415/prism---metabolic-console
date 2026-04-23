import { SESSION_STORAGE_KEYS } from '../constants/storage';

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

