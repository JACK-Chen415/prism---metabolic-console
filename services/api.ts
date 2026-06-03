/**
 * Prism Metabolic Console - API 客户端
 * 封装与后端 API 的通信
 */

import { AUTH_STORAGE_KEYS, LEGACY_AUTH_STORAGE_KEYS } from '../constants/storage';
import { AdminActivationMetricsSummary, AdminAITelemetrySummary, AdminCommercializationSummary, AdminFeedbackItem, AdminKnowledgeBacklogSummary, AdminReleaseReadinessSummary, AdminUserItem, AIFeedbackItem, AIFeedbackType, BillingProviderItem, BillingUsageSnapshot, ChatStreamEvent, CheckoutSession, DataRightsRequestResponse, DeviceSessionItem, EntitlementSnapshot, FeedbackStatus, HealthMetric, HealthMetricCreateInput, HealthMetricProvider, HealthMetricType, InsightFeedbackPayload, IntakeCandidate, IntakeDraftSession, KnowledgeAuditItem, MetabolicReport, PlanCatalogItem, PlanTier, SecurityAuditItem, SubscriptionLifecycleResponse, SubscriptionStatus, UserDataExportBundle, UserRole } from '../types';

const LOCAL_API_FALLBACK = 'http://127.0.0.1:8000/api';

const isLocalHostname = (hostname?: string): boolean => {
    if (!hostname) return true;
    return hostname === 'localhost'
        || hostname === '127.0.0.1'
        || hostname === '0.0.0.0'
        || hostname.endsWith('.local');
};

const parseApiUrl = (apiUrl: string, locationRef?: Location): { url: URL; isAbsolute: boolean } => {
    const isAbsolute = /^[a-z][a-z0-9+.-]*:\/\//i.test(apiUrl);
    try {
        return {
            url: isAbsolute ? new URL(apiUrl) : new URL(apiUrl, locationRef?.origin || 'http://localhost'),
            isAbsolute,
        };
    } catch (error) {
        throw new Error('VITE_API_URL 必须是完整 API 地址或同源路径，例如 https://api.example.com/api');
    }
};

export const resolveApiBaseUrl = (): string => {
    const configuredApiUrl = (import.meta.env.VITE_API_URL || '').trim();
    const apiUrl = configuredApiUrl || LOCAL_API_FALLBACK;
    const locationRef = typeof window !== 'undefined' ? window.location : undefined;
    const parsed = parseApiUrl(apiUrl, locationRef);
    const appEnv = (import.meta.env.VITE_APP_ENV || '').toLowerCase();
    const isProductionRuntime = appEnv === 'production'
        || Boolean(locationRef && locationRef.protocol === 'https:' && !isLocalHostname(locationRef.hostname));

    if (isProductionRuntime) {
        if (!configuredApiUrl) {
            throw new Error('生产前端必须配置 VITE_API_URL，不能回退到本地 API。');
        }
        if (parsed.isAbsolute && isLocalHostname(parsed.url.hostname)) {
            throw new Error('生产前端的 VITE_API_URL 不能指向 localhost、127.0.0.1 或 0.0.0.0。');
        }
        if (locationRef?.protocol === 'https:' && parsed.isAbsolute && parsed.url.protocol === 'http:') {
            throw new Error('HTTPS 前端必须使用 HTTPS API 地址，避免浏览器混合内容拦截。');
        }
    }

    return apiUrl.replace(/\/+$/, '');
};

const API_BASE_URL = resolveApiBaseUrl();
let inMemoryAccessToken: string | null = null;

const canUseLocalStorage = (): boolean => typeof localStorage !== 'undefined';
const AUTH_MUTATION_CLIENT_HEADERS: HeadersInit = {
    'X-Prism-Client': 'web',
};

export const REGISTRATION_CONSENT_VERSION = '2026-05-30';

export interface RegistrationConsentPayload {
    terms_accepted: boolean;
    privacy_accepted: boolean;
    ai_use_accepted: boolean;
    health_disclaimer_accepted: boolean;
    consent_version: string;
}

export const TokenManager = {
    getAccessToken: (): string | null => {
        if (inMemoryAccessToken) return inMemoryAccessToken;
        if (!canUseLocalStorage()) return null;
        inMemoryAccessToken = localStorage.getItem(AUTH_STORAGE_KEYS.accessToken);
        return inMemoryAccessToken;
    },

    setTokens: (accessToken: string): void => {
        inMemoryAccessToken = accessToken;
        if (!canUseLocalStorage()) return;
        localStorage.setItem(AUTH_STORAGE_KEYS.accessToken, accessToken);
        localStorage.removeItem(LEGACY_AUTH_STORAGE_KEYS.sessionToken);
    },

    clearTokens: (): void => {
        inMemoryAccessToken = null;
        if (!canUseLocalStorage()) return;
        localStorage.removeItem(AUTH_STORAGE_KEYS.accessToken);
        localStorage.removeItem(LEGACY_AUTH_STORAGE_KEYS.sessionToken);
    },

    isAuthenticated: (): boolean => {
        return !!TokenManager.getAccessToken();
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

type UploadOptions = {
    signal?: AbortSignal;
};

type ChatPreferencePayload = {
    aiMode?: 'STRICT' | 'GENTLE';
    interventionIntensity?: 'LOW' | 'STANDARD' | 'HIGH';
};

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
        try {
            const response = await fetch(`${this.baseUrl}/auth/refresh`, {
                method: 'POST',
                headers: AUTH_MUTATION_CLIENT_HEADERS,
                credentials: 'include'
            });

            if (response.ok) {
                const data = await response.json();
                TokenManager.setTokens(data.access_token);
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
            credentials: 'include',
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
                    credentials: 'include',
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
                credentials: 'include',
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

    async getText(endpoint: string, requiresAuth = true): Promise<string> {
        const url = `${this.baseUrl}${endpoint}`;
        const fetchText = async () => {
            const headers = await this.getHeaders(requiresAuth);
            return fetch(url, { method: 'GET', headers, credentials: 'include' });
        };

        let response = await fetchText();

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

            response = await fetchText();
        }

        if (!response.ok) {
            throw new Error(await this.parseError(response));
        }

        return response.text();
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

    patch<T>(endpoint: string, data?: unknown, requiresAuth = true): Promise<T> {
        return this.request<T>(endpoint, {
            method: 'PATCH',
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
        fields?: Record<string, string | number | boolean | null | undefined>,
        options: UploadOptions = {}
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
                credentials: 'include',
                body: buildFormData(),
                signal: options.signal
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
    register: (phone: string, password: string, consent: RegistrationConsentPayload, nickname?: string) =>
        apiClient.post('/auth/register', { phone, password, nickname, ...consent }, false),

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

    logout: async () => {
        const token = TokenManager.getAccessToken();
        const headers: HeadersInit = {
            'Content-Type': 'application/json',
            ...AUTH_MUTATION_CLIENT_HEADERS,
        };
        if (token) {
            headers.Authorization = `Bearer ${token}`;
        }
        const response = await fetch(`${API_BASE_URL}/auth/logout`, {
            method: 'POST',
            headers,
            credentials: 'include',
            body: JSON.stringify({}),
        });
        if (!response.ok && response.status !== 401) {
            throw new Error('退出登录失败');
        }
    },

    getProfile: () => apiClient.get('/auth/me'),

    listSessions: () => apiClient.get<DeviceSessionItem[]>('/auth/sessions'),

    revokeSession: (sessionId: string) =>
        apiClient.request<DataRightsRequestResponse>(`/auth/sessions/${sessionId}`, {
            method: 'DELETE',
            body: JSON.stringify({ confirm: 'REVOKE_SESSION' }),
        }),

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

export const AccountAPI = {
    exportData: () => apiClient.get<UserDataExportBundle>('/account/export'),

    deleteData: () => apiClient.post<DataRightsRequestResponse>('/account/delete-data', {
        confirm: 'DELETE_DATA',
    }),

    deleteAccount: () => apiClient.request<DataRightsRequestResponse>('/account', {
        method: 'DELETE',
        body: JSON.stringify({ confirm: 'DELETE_ACCOUNT' }),
    }),
};

type ReportRequestOptions = {
    endDate?: string;
    targetMonth?: string;
};

function buildQuery(params: Record<string, string | undefined>): string {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value) search.set(key, value);
    });
    const query = search.toString();
    return query ? `?${query}` : '';
}

export const ReportsAPI = {
    getWeekly: (options: ReportRequestOptions = {}) =>
        apiClient.get<MetabolicReport>(`/reports/weekly${buildQuery({ end_date: options.endDate })}`),
    getMonthly: (options: ReportRequestOptions = {}) =>
        apiClient.get<MetabolicReport>(`/reports/monthly${buildQuery({ target_month: options.targetMonth })}`),
    getWeeklyCsv: (options: ReportRequestOptions = {}) =>
        apiClient.getText(`/reports/weekly.csv${buildQuery({ end_date: options.endDate })}`),
    getMonthlyCsv: (options: ReportRequestOptions = {}) =>
        apiClient.getText(`/reports/monthly.csv${buildQuery({ target_month: options.targetMonth })}`),
};

export const BillingAPI = {
    getPlans: () => apiClient.get<PlanCatalogItem[]>('/billing/plans'),
    getProviders: () => apiClient.get<BillingProviderItem[]>('/billing/providers'),
    getEntitlements: () => apiClient.get<EntitlementSnapshot>('/billing/entitlements'),
    getUsage: () => apiClient.get<BillingUsageSnapshot>('/billing/usage'),
    createCheckout: (plan: PlanTier) => apiClient.post<CheckoutSession>('/billing/checkout', { plan }),
    cancelSubscription: () => apiClient.post<SubscriptionLifecycleResponse>('/billing/subscription/cancel', {
        confirm: 'CANCEL_SUBSCRIPTION',
    }),
};

export const AdminAPI = {
    listSecurityAudit: (limit = 20, q?: string, eventStatus?: string) =>
        apiClient.get<SecurityAuditItem[]>(`/admin/audit/security${buildQuery({ limit: String(limit), q, event_status: eventStatus })}`),
    listKnowledgeAudit: (
        limit = 20,
        q?: string,
        origin?: string,
        fallbackStatus?: string,
        calledCloud?: boolean,
    ) =>
        apiClient.get<KnowledgeAuditItem[]>(`/admin/audit/knowledge${buildQuery({
            limit: String(limit),
            q,
            origin,
            fallback_status: fallbackStatus,
            called_cloud: calledCloud == null ? undefined : String(calledCloud),
        })}`),
    getKnowledgeBacklog: (limit = 50, includeClosed = false) =>
        apiClient.get<AdminKnowledgeBacklogSummary>(`/admin/knowledge/backlog${buildQuery({
            limit: String(limit),
            include_closed: includeClosed ? 'true' : undefined,
        })}`),
    getActivationMetrics: (windowDays = 7) =>
        apiClient.get<AdminActivationMetricsSummary>(`/admin/activation/metrics?window_days=${windowDays}`),
    getCommercializationSummary: (windowDays = 30) =>
        apiClient.get<AdminCommercializationSummary>(`/admin/commercialization/summary?window_days=${windowDays}`),
    getAITelemetry: (limit = 50) => apiClient.get<AdminAITelemetrySummary>(`/admin/ai/telemetry?limit=${limit}`),
    getReleaseReadiness: (limit = 50) => apiClient.get<AdminReleaseReadinessSummary>(`/admin/release/readiness?limit=${limit}`),
    listFeedback: (status?: FeedbackStatus, limit = 30, feedbackType?: AIFeedbackType) =>
        apiClient.get<AdminFeedbackItem[]>(`/admin/feedback${buildQuery({
            status,
            feedback_type: feedbackType,
            limit: String(limit),
        })}`),
    updateFeedbackStatus: (feedbackId: number, status: FeedbackStatus) =>
        apiClient.patch<AdminFeedbackItem>(`/admin/feedback/${feedbackId}/status`, { status }),
    listUsers: (
        limit = 30,
        options: {
            q?: string;
            role?: UserRole;
            subscriptionPlan?: PlanTier;
            subscriptionStatus?: SubscriptionStatus;
        } = {},
    ) => apiClient.get<AdminUserItem[]>(`/admin/users${buildQuery({
        limit: String(limit),
        q: options.q,
        role: options.role,
        subscription_plan: options.subscriptionPlan,
        subscription_status: options.subscriptionStatus,
    })}`),
    updateUserRole: (userId: number, role: UserRole) =>
        apiClient.patch<AdminUserItem>(`/admin/users/${userId}/role`, { role }),
    updateUserSubscription: (userId: number, plan: PlanTier, status: SubscriptionStatus) =>
        apiClient.patch<AdminUserItem>(`/admin/users/${userId}/subscription`, { plan, status }),
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

    sync: (meals: unknown[], lastSyncAt?: string, operations: unknown[] = []) =>
        apiClient.post('/meals/sync', { meals, operations, last_sync_at: lastSyncAt })
};

export const ChatAPI = {
    createSession: (title?: string) =>
        apiClient.post('/chat/sessions', { title }),

    listSessions: (page = 1, size = 20) =>
        apiClient.get(`/chat/sessions?page=${page}&size=${size}`),

    getSession: (sessionId: number) =>
        apiClient.get(`/chat/sessions/${sessionId}`),

    sendMessage: (
        sessionId: number,
        content: string,
        attachments?: Record<string, unknown>,
        assistantPreferences?: ChatPreferencePayload
    ) =>
        apiClient.post(`/chat/sessions/${sessionId}/messages`, {
            content,
            attachments,
            ai_mode: assistantPreferences?.aiMode,
            intervention_intensity: assistantPreferences?.interventionIntensity,
        }),

    sendMessageStream: (
        sessionId: number,
        content: string,
        attachments: Record<string, unknown> | undefined,
        assistantPreferences: ChatPreferencePayload | undefined,
        onEvent: (event: ChatStreamEvent) => void
    ) => apiClient.streamSse(`/chat/sessions/${sessionId}/messages/stream`, {
        content,
        attachments,
        ai_mode: assistantPreferences?.aiMode,
        intervention_intensity: assistantPreferences?.interventionIntensity,
    }, onEvent),

    sendMessageFeedback: (messageId: number, payload: {
        feedback_type: AIFeedbackType;
        rating?: number;
        tags?: string[];
        correction_text?: string;
        metadata?: Record<string, unknown>;
    }) => apiClient.post(`/chat/messages/${messageId}/feedback`, payload),

    listMessageFeedback: (messageId: number) =>
        apiClient.get<AIFeedbackItem[]>(`/chat/messages/${messageId}/feedback`),

    deleteSession: (sessionId: number) =>
        apiClient.delete(`/chat/sessions/${sessionId}`),

    recognizeFood: (imageBase64: string, imageType = 'jpeg', prompt?: string) =>
        apiClient.post('/chat/recognize-food', {
            image_base64: imageBase64,
            image_type: imageType,
            prompt
        }),

    recognizeFoodUpload: (file: File, prompt?: string, sessionId?: number, options: UploadOptions = {}) =>
        apiClient.upload('/chat/recognize-food/upload', file, 'file', { prompt, session_id: sessionId }, options),

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

export const HealthMetricsAPI = {
    listProviders: () => apiClient.get<HealthMetricProvider[]>('/health-metrics/providers'),

    list: (metricType?: HealthMetricType, limit = 50) => {
        const params = new URLSearchParams({ limit: String(limit) });
        if (metricType) params.set('metric_type', metricType);
        return apiClient.get<HealthMetric[]>(`/health-metrics?${params.toString()}`);
    },

    latest: () => apiClient.get<Partial<Record<HealthMetricType, HealthMetric>>>('/health-metrics/latest'),

    create: (data: HealthMetricCreateInput) =>
        apiClient.post<HealthMetric>('/health-metrics', data),

    delete: (id: number) => apiClient.delete(`/health-metrics/${id}`),
};

export const IntakeAPI = {
    recognizeAndParsePhotoUpload: (
        file: File,
        prompt?: string,
        mealTimeHint?: string,
        recordDate?: string,
        options: UploadOptions = {}
    ) =>
        apiClient.upload<IntakeDraftSession>('/intake/photo/recognize-parse-upload', file, 'file', {
            prompt,
            meal_time_hint: mealTimeHint,
            record_date: recordDate,
            fast: true,
        }, options),

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

    parseText: (
        text: string,
        contextText?: string,
        mealTimeHint?: string,
        recordDate?: string
    ) =>
        apiClient.post<IntakeDraftSession>('/intake/text/parse', {
            text,
            context_text: contextText,
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

export const InsightsAPI = {
    refresh: () => apiClient.post('/insights/refresh'),

    getToday: () => apiClient.get('/insights/today'),

    sendFeedback: (messageId: number, payload: InsightFeedbackPayload) =>
        apiClient.post<AIFeedbackItem>(`/insights/${messageId}/feedback`, payload),

    listFeedback: (messageId: number) =>
        apiClient.get<AIFeedbackItem[]>(`/insights/${messageId}/feedback`)
};

export default apiClient;
