export const AUTH_STORAGE_KEYS = {
  accessToken: 'prism_access_token',
  refreshToken: 'prism_refresh_token',
} as const;

export const SESSION_STORAGE_KEYS = {
  chatSessionId: 'prism.chat.sessionId',
  foodScanResult: 'prism.foodScan.result',
} as const;

export const UI_STORAGE_KEYS = {
  chatMode: 'prism.chat.mode',
  assistantIntensity: 'prism.assistant.intensity',
} as const;
