/**
 * Prism Metabolic Console - API 客户端
 * 封装与后端 API 的通信
 */

// API 基础配置
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

// Token 存储键
const ACCESS_TOKEN_KEY = 'prism_access_token';
const REFRESH_TOKEN_KEY = 'prism_refresh_token';

// ==================== Token 管理 ====================

export const TokenManager = {
    getAccessToken: (): string | null => {
        return localStorage.getItem(ACCESS_TOKEN_KEY);
    },

    getRefreshToken: (): string | null => {
        return localStorage.getItem(REFRESH_TOKEN_KEY);
    },

    setTokens: (accessToken: string, refreshToken: string): void => {
        localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
        localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
    },

    clearTokens: (): void => {
        localStorage.removeItem(ACCESS_TOKEN_KEY);
        localStorage.removeItem(REFRESH_TOKEN_KEY);
    },

    isAuthenticated: (): boolean => {
        return !!localStorage.getItem(ACCESS_TOKEN_KEY);
    }
};

// ==================== HTTP 请求封装 ====================

interface ApiResponse<T> {
    success: boolean;
    data?: T;
    message?: string;
    error?: string;
}

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

        // 处理 401 错误：尝试刷新 Token
        if (response.status === 401 && requiresAuth) {
            // 防止多个请求同时刷新
            if (!this.isRefreshing) {
                this.isRefreshing = true;
                this.refreshPromise = this.refreshAccessToken();
            }

            const refreshed = await this.refreshPromise;
            this.isRefreshing = false;
            this.refreshPromise = null;

            if (refreshed) {
                // 重试原请求
                const newHeaders = await this.getHeaders(true);
                const retryResponse = await fetch(url, {
                    ...options,
                    headers: { ...newHeaders, ...options.headers }
                });

                if (!retryResponse.ok) {
                    throw new Error(await this.parseError(retryResponse));
                }
                return retryResponse.json();
            } else {
                // 刷新失败，需要重新登录
                window.dispatchEvent(new CustomEvent('auth:logout'));
                throw new Error('登录已过期，请重新登录');
            }
        }

        if (!response.ok) {
            throw new Error(await this.parseError(response));
        }

        // 处理空响应
        const text = await response.text();
        return text ? JSON.parse(text) : {} as T;
    }

    private async parseError(response: Response): Promise<string> {
        try {
            const data = await response.json();
            return data.detail || data.message || '请求失败';
        } catch {
            return `请求失败 (${response.status})`;
        }
    }

    // GET 请求
    get<T>(endpoint: string, requiresAuth = true): Promise<T> {
        return this.request<T>(endpoint, { method: 'GET' }, requiresAuth);
    }

    // POST 请求
    post<T>(endpoint: string, data?: unknown, requiresAuth = true): Promise<T> {
        return this.request<T>(endpoint, {
            method: 'POST',
            body: data ? JSON.stringify(data) : undefined
        }, requiresAuth);
    }

    // PUT 请求
    put<T>(endpoint: string, data?: unknown, requiresAuth = true): Promise<T> {
        return this.request<T>(endpoint, {
            method: 'PUT',
            body: data ? JSON.stringify(data) : undefined
        }, requiresAuth);
    }

    // DELETE 请求
    delete<T>(endpoint: string, requiresAuth = true): Promise<T> {
        return this.request<T>(endpoint, { method: 'DELETE' }, requiresAuth);
    }

    // 文件上传
    async upload<T>(endpoint: string, file: File | Blob, fieldName = 'file'): Promise<T> {
        const formData = new FormData();
        formData.append(fieldName, file);

        const token = TokenManager.getAccessToken();
        const headers: HeadersInit = {};
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch(`${this.baseUrl}${endpoint}`, {
            method: 'POST',
            headers,
            body: formData
        });

        if (!response.ok) {
            throw new Error(await this.parseError(response));
        }

        return response.json();
    }
}

// 导出 API 客户端单例
export const apiClient = new ApiClient(API_BASE_URL);

// ==================== 业务 API ====================

// 认证相关
export const AuthAPI = {
    register: (phone: string, password: string, nickname?: string) =>
        apiClient.post('/auth/register', { phone, password, nickname }, false),

    login: (phone: string, password: string) =>
        apiClient.post('/auth/login', { phone, password }, false),

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

// 饮食记录相关
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

    update: (id: number, data: Partial<{
        name: string;
        portion: string;
        calories: number;
        sodium: number;
        purine: number;
        note: string;
    }>) => apiClient.put(`/meals/${id}`, data),

    delete: (id: number) => apiClient.delete(`/meals/${id}`),

    sync: (meals: unknown[], lastSyncAt?: string) =>
        apiClient.post('/meals/sync', { meals, last_sync_at: lastSyncAt })
};

// AI 对话相关
export const ChatAPI = {
    createSession: (title?: string) =>
        apiClient.post('/chat/sessions', { title }),

    listSessions: (page = 1, size = 20) =>
        apiClient.get(`/chat/sessions?page=${page}&size=${size}`),

    getSession: (sessionId: number) =>
        apiClient.get(`/chat/sessions/${sessionId}`),

    sendMessage: (sessionId: number, content: string, attachments?: Record<string, unknown>) =>
        apiClient.post(`/chat/sessions/${sessionId}/messages`, { content, attachments }),

    deleteSession: (sessionId: number) =>
        apiClient.delete(`/chat/sessions/${sessionId}`),

    recognizeFood: (imageBase64: string, imageType = 'jpeg') =>
        apiClient.post('/chat/recognize-food', {
            image_base64: imageBase64,
            image_type: imageType
        }),

    recognizeFoodUpload: (file: File) =>
        apiClient.upload('/chat/recognize-food/upload', file)
};

// 健康档案相关
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

// 消息通知相关
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
