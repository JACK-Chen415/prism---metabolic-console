/**
 * Prism Metabolic Console - API 客户端
 * 封装与后端 API 的通信
 */

import { AUTH_STORAGE_KEYS } from '../constants/storage';
import { ChatStreamEvent, IntakeCandidate, IntakeDraftSession } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export const TokenManager = {
    getAccessToken: (): string | null => {
        return localStorage.getItem(AUTH_STORAGE_KEYS.accessToken);
    },

    getRefreshToken: (): string | null => {
        return localStorage.getItem(AUTH_STORAGE_KEYS.refreshToken);
    },

    setTokens: (accessToken: string, refreshToken: string): void => {
        localStorage.setItem(AUTH_STORAGE_KEYS.accessToken, accessToken);
        localStorage.setItem(AUTH_STORAGE_KEYS.refreshToken, refreshToken);
    },

    clearTokens: (): void => {
        localStorage.removeItem(AUTH_STORAGE_KEYS.accessToken);
        localStorage.removeItem(AUTH_STORAGE_KEYS.refreshToken);
    },

    isAuthenticated: (): boolean => {
        return !!localStorage.getItem(AUTH_STORAGE_KEYS.accessToken);
    }
};

type MealUpdatePayload = Partial<{
    name: string;
    portion: string;
    calories: number;
    sodium: number;
    purine: number;
    protein: number;
    carbs: number;
    fat: number;
    fiber: number;
    meal_type: 'BREAKFAST' | 'LUNCH' | 'DINNER' | 'SNACK';
    category: 'STAPLE' | 'MEAT' | 'VEG' | 'DRINK' | 'SNACK';
    note: string;
}>;

class ApiClient {
    private baseUrl: string;
    private isRefreshing: boolean = false;
    private refreshPromise: Promise<boolean> | null = null;

    constructor(baseUrl: string) {
        this.baseUrl = baseUrl;
    }

    private async getHeaders(includeAuth: boolean = true): Promise<HeadersInit> {
        const headers: HeadersInit = {
            'Content-Type': 'application/json',
        };

        if (includeAuth) {
            const token = TokenManager.getAccessToken();
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
        }

        return headers;
    }

    private async refreshAccessToken(): Promise<boolean> {
        const refreshToken = TokenManager.getRefreshToken();
        if (!refreshToken) return false;

        try {
            const response = await fetch(`${this.baseUrl}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken })
            });

            if (response.ok) {
                const data = await response.json();
                TokenManager.setTokens(data.access_token, data.refresh_token);
                return true;
            }
        } catch (error) {
            console.error('Token refresh failed:', error);
        }

        TokenManager.clearTokens();
        return false;
    }

    async request<T>(
        endpoint: string,
        options: RequestInit = {},
        requiresAuth: boolean = true
    ): Promise<T> {
        const url = `${this.baseUrl}${endpoint}`;
        const headers = await this.getHeaders(requiresAuth);

        const response = await fetch(url, {
            ...options,
            headers: { ...headers, ...options.headers }
        });

        if (response.status === 401 && requiresAuth) {
            if (!this.isRefreshing) {
                this.isRefreshing = true;
                this.refreshPromise = this.refreshAccessToken();
            }

            const refreshed = await this.refreshPromise;
            this.isRefreshing = false;
            this.refreshPromise = null;

            if (refreshed) {
                const newHeaders = await this.getHeaders(true);
                const retryResponse = await fetch(url, {
                    ...options,
                    headers: { ...newHeaders, ...options.headers }
                });

                if (!retryResponse.ok) {
                    throw new Error(await this.parseError(retryResponse));
                }

                const retryText = await retryResponse.text();
                return retryText ? JSON.parse(retryText) : {} as T;
            }

            window.dispatchEvent(new CustomEvent('auth:logout'));
            throw new Error('登录已过期，请重新登录');
        }

        if (!response.ok) {
            throw new Error(await this.parseError(response));
        }

        const text = await response.text();
        return text ? JSON.parse(text) : {} as T;
    }

    async streamSse(
        endpoint: string,
        data: unknown,
        onEvent: (event: ChatStreamEvent) => void,
        requiresAuth: boolean = true
    ): Promise<void> {
        const url = `${this.baseUrl}${endpoint}`;
        const fetchStream = async () => {
            const headers = await this.getHeaders(requiresAuth);
            return fetch(url, {
                method: 'POST',
                headers,
                body: JSON.stringify(data)
            });
        };

        let response = await fetchStream();

        if (response.status === 401 && requiresAuth) {
            if (!this.isRefreshing) {
                this.isRefreshing = true;
                this.refreshPromise = this.refreshAccessToken();
            }

            const refreshed = await this.refreshPromise;
            this.isRefreshing = false;
            this.refreshPromise = null;

            if (!refreshed) {
                window.dispatchEvent(new CustomEvent('auth:logout'));
                throw new Error('登录已过期，请重新登录');
            }

            response = await fetchStream();
        }

        if (!response.ok) {
            throw new Error(await this.parseError(response));
        }

        if (!response.body) {
            throw new Error('当前浏览器不支持流式响应');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        const dispatchBlock = (block: string) => {
            const lines = block.split(/\r?\n/);
            let eventName = 'message';
            const dataLines: string[] = [];

            for (const line of lines) {
                if (line.startsWith('event:')) {
                    eventName = line.slice(6).trim();
                } else if (line.startsWith('data:')) {
                    dataLines.push(line.slice(5).trimStart());
                }
            }

            if (!dataLines.length) return;
            const rawData = dataLines.join('\n');
            try {
                onEvent({ event: eventName, data: JSON.parse(rawData) });
            } catch {
                onEvent({ event: eventName, data: { message: rawData } });
            }
        };

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const blocks = buffer.split(/\r?\n\r?\n/);
            buffer = blocks.pop() || '';
            blocks.forEach(dispatchBlock);
        }

        buffer += decoder.decode();
        if (buffer.trim()) {
            dispatchBlock(buffer);
        }
    }

    private async parseError(response: Response): Promise<string> {
        try {
            const data = await response.json();
            return data.detail || data.message || data.error || '请求失败';
        } catch {
            return `请求失败 (${response.status})`;
        }
    }

    get<T>(endpoint: string, requiresAuth = true): Promise<T> {
        return this.request<T>(endpoint, { method: 'GET' }, requiresAuth);
    }

    post<T>(endpoint: string, data?: unknown, requiresAuth = true): Promise<T> {
        return this.request<T>(endpoint, {
            method: 'POST',
            body: data ? JSON.stringify(data) : undefined
        }, requiresAuth);
    }

    put<T>(endpoint: string, data?: unknown, requiresAuth = true): Promise<T> {
        return this.request<T>(endpoint, {
            method: 'PUT',
            body: data ? JSON.stringify(data) : undefined
        }, requiresAuth);
    }

    delete<T>(endpoint: string, requiresAuth = true): Promise<T> {
        return this.request<T>(endpoint, { method: 'DELETE' }, requiresAuth);
    }

    async upload<T>(
        endpoint: string,
        file: File | Blob,
        fieldName = 'file',
        fields?: Record<string, string | number | boolean | null | undefined>
    ): Promise<T> {
        const buildFormData = () => {
            const formData = new FormData();
            formData.append(fieldName, file);

            if (fields) {
                Object.entries(fields).forEach(([key, value]) => {
                    if (value !== undefined && value !== null) {
                        formData.append(key, String(value));
                    }
                });
            }

            return formData;
        };

        const fetchUpload = async () => {
            const token = TokenManager.getAccessToken();
            const headers: HeadersInit = {};

            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }

            return fetch(`${this.baseUrl}${endpoint}`, {
                method: 'POST',
                headers,
                body: buildFormData()
            });
        };

        let response = await fetchUpload();

        if (response.status === 401) {
            if (!this.isRefreshing) {
                this.isRefreshing = true;
                this.refreshPromise = this.refreshAccessToken();
            }

            const refreshed = await this.refreshPromise;
            this.isRefreshing = false;
            this.refreshPromise = null;

            if (!refreshed) {
                window.dispatchEvent(new CustomEvent('auth:logout'));
                throw new Error('登录已过期，请重新登录');
            }

            response = await fetchUpload();
        }

        if (!response.ok) {
            throw new Error(await this.parseError(response));
        }

        const text = await response.text();
        return text ? JSON.parse(text) : {} as T;
    }
}

export const apiClient = new ApiClient(API_BASE_URL);

export const AuthAPI = {
    register: (phone: string, password: string, nickname?: string) =>
        apiClient.post('/auth/register', { phone, password, nickname }, false),

    login: (phone: string, password: string) =>
        apiClient.post('/auth/login', { phone, password }, false),

    sendCode: (phone: string, purpose: 'login' | 'reset_password') =>
        apiClient.post('/auth/send-code', { phone, purpose }, false),

    loginWithCode: (phone: string, code: string) =>
        apiClient.post('/auth/login-code', { phone, code }, false),

    resetPassword: (phone: string, code: string, newPassword: string) =>
        apiClient.post('/auth/reset-password', {
            phone,
            code,
            new_password: newPassword
        }, false),

    getProfile: () => apiClient.get('/auth/me'),

    updateProfile: (data: {
        nickname?: string;
        gender?: 'MALE' | 'FEMALE';
        age?: number;
        height?: number;
        weight?: number;
    }) => apiClient.put('/auth/me', data),

    changePassword: (oldPassword: string, newPassword: string) =>
        apiClient.post('/auth/change-password', {
            old_password: oldPassword,
            new_password: newPassword
        }),

    getDailyTargets: () => apiClient.get('/auth/daily-targets')
};

export const MealsAPI = {
    create: (meal: {
        client_id: string;
        name: string;
        portion: string;
        calories: number;
        sodium: number;
        purine: number;
        meal_type: 'BREAKFAST' | 'LUNCH' | 'DINNER' | 'SNACK';
        category: 'STAPLE' | 'MEAT' | 'VEG' | 'DRINK' | 'SNACK';
        record_date: string;
        note?: string;
        protein?: number;
        carbs?: number;
        fat?: number;
        fiber?: number;
        ai_recognized?: boolean;
        source?: 'manual' | 'voice' | 'photo' | 'ai_quick_log';
        source_detail?: string;
        confidence?: number;
        estimated_fields_json?: string[];
        rule_warnings_json?: string[];
        recognition_meta_json?: Record<string, unknown>;
    }) => apiClient.post('/meals', meal),

    list: (params?: {
        record_date?: string;
        start_date?: string;
        end_date?: string;
        page?: number;
        page_size?: number;
    }) => {
        const query = params ? '?' + new URLSearchParams(
            Object.entries(params)
                .filter(([, v]) => v !== undefined)
                .map(([k, v]) => [k, String(v)])
        ).toString() : '';
        return apiClient.get(`/meals${query}`);
    },

    getToday: () => apiClient.get('/meals/today'),

    getSummary: (targetDate?: string) => {
        const query = targetDate ? `?target_date=${targetDate}` : '';
        return apiClient.get(`/meals/summary${query}`);
    },

    get: (id: number) => apiClient.get(`/meals/${id}`),

    update: (id: number, data: MealUpdatePayload) => apiClient.put(`/meals/${id}`, data),

    updateMeal: (id: number, data: MealUpdatePayload) => apiClient.put(`/meals/${id}`, data),

    delete: (id: number) => apiClient.delete(`/meals/${id}`),

    deleteMeal: (id: number) => apiClient.delete(`/meals/${id}`),

    sync: (meals: unknown[], lastSyncAt?: string) =>
        apiClient.post('/meals/sync', { meals, last_sync_at: lastSyncAt })
};

export const ChatAPI = {
    createSession: (title?: string) =>
        apiClient.post('/chat/sessions', { title }),

    listSessions: (page = 1, size = 20) =>
        apiClient.get(`/chat/sessions?page=${page}&size=${size}`),

    getSession: (sessionId: number) =>
        apiClient.get(`/chat/sessions/${sessionId}`),

    sendMessage: (sessionId: number, content: string, attachments?: Record<string, unknown>) =>
        apiClient.post(`/chat/sessions/${sessionId}/messages`, { content, attachments }),

    sendMessageStream: (
        sessionId: number,
        content: string,
        attachments: Record<string, unknown> | undefined,
        onEvent: (event: ChatStreamEvent) => void
    ) => apiClient.streamSse(`/chat/sessions/${sessionId}/messages/stream`, { content, attachments }, onEvent),

    deleteSession: (sessionId: number) =>
        apiClient.delete(`/chat/sessions/${sessionId}`),

    recognizeFood: (imageBase64: string, imageType = 'jpeg', prompt?: string) =>
        apiClient.post('/chat/recognize-food', {
            image_base64: imageBase64,
            image_type: imageType,
            prompt
        }),

    recognizeFoodUpload: (file: File, prompt?: string) =>
        apiClient.upload('/chat/recognize-food/upload', file, 'file', { prompt }),

    quickLog: (
        foodItem: {
            food_name: string;
            estimated_portion?: string;
            category?: string;
            nutrition: {
                calories: number;
                sodium: number;
                purine: number;
                protein?: number;
                carbs?: number;
                fat?: number;
                fiber?: number;
            };
        },
        mealType: 'BREAKFAST' | 'LUNCH' | 'DINNER' | 'SNACK' = 'DINNER',
        sessionId?: number
    ) => apiClient.post('/chat/quick-log', {
        session_id: sessionId,
        meal_type: mealType,
        food_item: foodItem
    })
};

export const IntakeAPI = {
    recognizeAndParsePhotoUpload: (file: File, prompt?: string, mealTimeHint?: string, recordDate?: string) =>
        apiClient.upload<IntakeDraftSession>('/intake/photo/recognize-parse-upload', file, 'file', {
            prompt,
            meal_time_hint: mealTimeHint,
            record_date: recordDate,
            fast: true,
        }),

    parseVoice: (
        transcript: string,
        mealTimeHint?: string,
        recordDate?: string
    ) =>
        apiClient.post<IntakeDraftSession>('/intake/voice/parse', {
            transcript,
            meal_time_hint: mealTimeHint,
            record_date: recordDate,
        }),

    autoLogVoice: (
        transcript: string,
        mealTimeHint?: string,
        recordDate?: string
    ) =>
        apiClient.post<{
            meals: unknown[];
            meal_ids: number[];
            warning_summary: string[];
            failed_items: Array<{ draft_id: string; food_name: string; reason: string }>;
            should_refresh_log: boolean;
            should_refresh_home: boolean;
        }>('/intake/voice/auto-log', {
            transcript,
            meal_time_hint: mealTimeHint,
            record_date: recordDate,
            auto_confirm: true,
        }),

    parsePhotoResult: (payload: {
        recognized_foods: unknown[];
        ai_response?: string;
        meal_time_hint?: string;
    }) => apiClient.post<IntakeDraftSession>('/intake/photo/parse-result', payload),

    confirm: (payload: {
        source: 'voice' | 'photo' | 'ai_quick_log';
        raw_input_text?: string | null;
        raw_summary?: string | null;
        record_date?: string;
        candidates: IntakeCandidate[];
    }) => apiClient.post<{
        meals: unknown[];
        meal_ids: number[];
        warning_summary: string[];
        failed_items: Array<{ draft_id: string; food_name: string; reason: string }>;
        should_refresh_log: boolean;
        should_refresh_home: boolean;
    }>('/intake/confirm', payload),

    reevaluateCandidate: (candidate: IntakeCandidate) =>
        apiClient.post<IntakeCandidate>('/intake/candidate/reevaluate', candidate),
};

export const ConditionsAPI = {
    create: (condition: {
        condition_code: string;
        title: string;
        icon?: string;
        condition_type: 'CHRONIC' | 'ALLERGY';
        status?: 'ACTIVE' | 'MONITORING' | 'STABLE' | 'ALERT';
        value?: string;
        unit?: string;
    }) => apiClient.post('/conditions', condition),

    list: () => apiClient.get('/conditions'),

    listChronic: () => apiClient.get('/conditions/chronic'),

    listAllergies: () => apiClient.get('/conditions/allergies'),

    get: (id: number) => apiClient.get(`/conditions/${id}`),

    update: (id: number, data: Partial<{
        status: 'ACTIVE' | 'MONITORING' | 'STABLE' | 'ALERT';
        trend: 'IMPROVED' | 'WORSENING' | 'STABLE';
        value: string;
        unit: string;
        dictum: string;
        attribution: string;
    }>) => apiClient.put(`/conditions/${id}`, data),

    delete: (id: number) => apiClient.delete(`/conditions/${id}`)
};

export const MessagesAPI = {
    list: (params?: { unread_only?: boolean; message_type?: string; limit?: number }) => {
        const query = params ? '?' + new URLSearchParams(
            Object.entries(params)
                .filter(([, v]) => v !== undefined)
                .map(([k, v]) => [k, String(v)])
        ).toString() : '';
        return apiClient.get(`/messages${query}`);
    },

    getUnreadCount: () => apiClient.get('/messages/unread-count'),

    get: (id: number) => apiClient.get(`/messages/${id}`),

    markAsRead: (id: number) => apiClient.post(`/messages/${id}/read`),

    markAllAsRead: () => apiClient.post('/messages/read-all'),

    delete: (id: number) => apiClient.delete(`/messages/${id}`)
};

export default apiClient;
