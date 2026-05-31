/**
 * Prism Metabolic Console - 离线缓存服务
 * 使用 Dexie.js 封装 IndexedDB，实现按用户隔离的饮食日志离线存储与同步。
 */

import Dexie, { Table } from 'dexie';
import { getLocalDateString } from './date';
import { MealsAPI } from './api';

const LEGACY_USER_ID = -1;

export interface CachedMeal {
    id?: number;
    userId: number;
    clientId: string;
    serverId?: number;
    name: string;
    portion: string;
    calories: number;
    sodium: number;
    purine: number;
    protein?: number;
    carbs?: number;
    fat?: number;
    fiber?: number;
    mealType: 'BREAKFAST' | 'LUNCH' | 'DINNER' | 'SNACK';
    category: 'STAPLE' | 'MEAT' | 'VEG' | 'DRINK' | 'SNACK';
    recordDate: string;
    note?: string;
    imageUrl?: string;
    aiRecognized: boolean;
    source?: 'manual' | 'voice' | 'photo' | 'ai_quick_log';
    sourceDetail?: string;
    confidence?: number;
    estimatedFields?: string[];
    ruleWarnings?: string[];
    recognitionMeta?: Record<string, unknown>;
    syncStatus: 'PENDING' | 'SYNCED' | 'CONFLICT' | 'FAILED';
    pendingDelete?: boolean;
    lastSyncError?: string;
    retryCount?: number;
    createdAt: Date;
    updatedAt: Date;
}

export interface SyncMeta {
    key: string;
    value: string | number | Date;
}

type MealDraft = Omit<CachedMeal, 'id' | 'userId' | 'clientId' | 'syncStatus' | 'createdAt' | 'updatedAt'> & {
    clientId?: string;
};

class PrismDatabase extends Dexie {
    meals!: Table<CachedMeal, number>;
    syncMeta!: Table<SyncMeta, string>;

    constructor() {
        super('PrismMetabolicConsole');

        this.version(1).stores({
            meals: '++id, clientId, serverId, recordDate, syncStatus, mealType, createdAt',
            syncMeta: 'key'
        });

        this.version(2).stores({
            meals: '++id, userId, [userId+recordDate], [userId+syncStatus], [userId+clientId], serverId, recordDate, syncStatus, mealType, createdAt',
            syncMeta: 'key'
        }).upgrade(async tx => {
            await tx.table('meals').toCollection().modify(meal => {
                meal.userId = LEGACY_USER_ID;
                meal.syncStatus = 'CONFLICT';
            });
        });
    }
}

const db = new PrismDatabase();

export function generateClientId(): string {
    return crypto.randomUUID();
}

export function getTodayDateString(): string {
    return getLocalDateString();
}

function syncMetaKey(userId: number, key: string): string {
    return `user:${userId}:${key}`;
}

export const OfflineMealsService = {
    async add(userId: number, meal: MealDraft): Promise<CachedMeal> {
        const now = new Date();
        const newMeal: CachedMeal = {
            ...meal,
            userId,
            clientId: meal.clientId || generateClientId(),
            syncStatus: 'PENDING',
            pendingDelete: false,
            aiRecognized: meal.aiRecognized ?? false,
            createdAt: now,
            updatedAt: now
        };

        const id = await db.meals.add(newMeal);
        return { ...newMeal, id };
    },

    async getToday(userId: number): Promise<CachedMeal[]> {
        return this.getByDate(userId, getTodayDateString());
    },

    async getByDate(userId: number, date: string): Promise<CachedMeal[]> {
        return db.meals.where('[userId+recordDate]').equals([userId, date]).toArray();
    },

    async getByDateRange(userId: number, startDate: string, endDate: string): Promise<CachedMeal[]> {
        return db.meals
            .where('userId')
            .equals(userId)
            .and(meal => meal.recordDate >= startDate && meal.recordDate <= endDate)
            .toArray();
    },

    async getPending(userId: number): Promise<CachedMeal[]> {
        const pending = await db.meals.where('[userId+syncStatus]').equals([userId, 'PENDING']).toArray();
        const failed = await db.meals.where('[userId+syncStatus]').equals([userId, 'FAILED']).toArray();
        return [...pending, ...failed].sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime());
    },

    async getQueue(userId: number): Promise<CachedMeal[]> {
        const statuses: CachedMeal['syncStatus'][] = ['PENDING', 'FAILED', 'CONFLICT'];
        const groups = await Promise.all(
            statuses.map(status => db.meals.where('[userId+syncStatus]').equals([userId, status]).toArray())
        );
        return groups
            .flat()
            .sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime());
    },

    async update(userId: number, id: number, changes: Partial<CachedMeal>): Promise<void> {
        const meal = await db.meals.get(id);
        if (!meal || meal.userId !== userId) return;

        await db.meals.update(id, {
            ...changes,
            userId,
            updatedAt: new Date(),
            syncStatus: 'PENDING',
            pendingDelete: false,
            lastSyncError: undefined,
            retryCount: 0
        });
    },

    async delete(userId: number, id: number): Promise<void> {
        const meal = await db.meals.get(id);
        if (!meal || meal.userId !== userId) return;

        if (meal.serverId) {
            await db.meals.update(id, {
                syncStatus: 'PENDING',
                pendingDelete: true,
                lastSyncError: undefined,
                retryCount: 0,
                updatedAt: new Date()
            });
        } else {
            await db.meals.delete(id);
        }
    },

    async getByClientId(userId: number, clientId: string): Promise<CachedMeal | undefined> {
        return db.meals.where('[userId+clientId]').equals([userId, clientId]).first();
    },

    async getByServerId(userId: number, serverId: number): Promise<CachedMeal | undefined> {
        return db.meals.where('serverId').equals(serverId).and(meal => meal.userId === userId).first();
    },

    async updateByClientId(userId: number, clientId: string, changes: Partial<CachedMeal>): Promise<void> {
        const meal = await this.getByClientId(userId, clientId);
        if (meal?.id) {
            await this.update(userId, meal.id, changes);
        }
    },

    async updateByServerId(userId: number, serverId: number, changes: Partial<CachedMeal>): Promise<void> {
        const meal = await this.getByServerId(userId, serverId);
        if (meal?.id) {
            await this.update(userId, meal.id, changes);
        }
    },

    async deleteByClientId(userId: number, clientId: string): Promise<void> {
        const meal = await this.getByClientId(userId, clientId);
        if (meal?.id) {
            await this.delete(userId, meal.id);
        }
    },

    async deleteByServerId(userId: number, serverId: number): Promise<void> {
        const meal = await this.getByServerId(userId, serverId);
        if (meal?.id) {
            await this.delete(userId, meal.id);
        }
    },

    async removeByClientId(userId: number, clientId: string): Promise<void> {
        const meal = await this.getByClientId(userId, clientId);
        if (meal?.id && meal.userId === userId) {
            await db.meals.delete(meal.id);
        }
    },

    async markSynced(userId: number, clientId: string, serverId: number): Promise<void> {
        const meal = await db.meals.where('[userId+clientId]').equals([userId, clientId]).first();
        if (meal?.id) {
            await db.meals.update(meal.id, {
                serverId,
                syncStatus: 'SYNCED',
                pendingDelete: false,
                lastSyncError: undefined,
                retryCount: 0,
                updatedAt: new Date()
            });
        }
    },

    async markConflict(userId: number, clientId: string, reason = 'server_conflict'): Promise<void> {
        const meal = await db.meals.where('[userId+clientId]').equals([userId, clientId]).first();
        if (meal?.id) {
            await db.meals.update(meal.id, {
                syncStatus: 'CONFLICT',
                lastSyncError: reason.slice(0, 160),
                updatedAt: new Date()
            });
        }
    },

    async markRetry(userId: number, clientId: string): Promise<void> {
        const meal = await db.meals.where('[userId+clientId]').equals([userId, clientId]).first();
        if (!meal?.id || meal.userId !== userId) return;
        if (!['PENDING', 'FAILED', 'CONFLICT'].includes(meal.syncStatus)) return;

        await db.meals.update(meal.id, {
            syncStatus: 'PENDING',
            lastSyncError: undefined,
            updatedAt: new Date()
        });
    },

    async discardLocal(userId: number, clientId: string): Promise<void> {
        const meal = await db.meals.where('[userId+clientId]').equals([userId, clientId]).first();
        if (!meal?.id || meal.userId !== userId) return;
        if (!['PENDING', 'FAILED', 'CONFLICT'].includes(meal.syncStatus)) return;

        await db.meals.delete(meal.id);
    },

    async markFailed(userId: number, clientIds: string[], reason: string): Promise<void> {
        const safeReason = reason.slice(0, 160);
        await db.transaction('rw', db.meals, async () => {
            for (const clientId of clientIds) {
                const meal = await db.meals.where('[userId+clientId]').equals([userId, clientId]).first();
                if (!meal?.id || meal.syncStatus === 'SYNCED' || meal.syncStatus === 'CONFLICT') continue;
                await db.meals.update(meal.id, {
                    syncStatus: 'FAILED',
                    lastSyncError: safeReason,
                    retryCount: (meal.retryCount || 0) + 1,
                    updatedAt: new Date()
                });
            }
        });
    },

    async mergeFromServer(userId: number, serverMeals: Array<{
        id: number;
        client_id: string;
        name: string;
        portion: string;
        calories: number;
        sodium: number;
        purine: number;
        protein?: number;
        carbs?: number;
        fat?: number;
        fiber?: number;
        meal_type: string;
        category: string;
        record_date: string;
        note?: string;
        ai_recognized: boolean;
        source?: string;
        source_detail?: string;
        confidence?: number;
        estimated_fields_json?: string[];
        rule_warnings_json?: string[];
        recognition_meta_json?: Record<string, unknown>;
    }>): Promise<void> {
        await db.transaction('rw', db.meals, async () => {
            for (const serverMeal of serverMeals) {
                const localMeal = await db.meals
                    .where('[userId+clientId]')
                    .equals([userId, serverMeal.client_id])
                    .first();

                const payload = {
                    userId,
                    serverId: serverMeal.id,
                    name: serverMeal.name,
                    portion: serverMeal.portion,
                    calories: serverMeal.calories,
                    sodium: serverMeal.sodium,
                    purine: serverMeal.purine,
                    protein: serverMeal.protein,
                    carbs: serverMeal.carbs,
                    fat: serverMeal.fat,
                    fiber: serverMeal.fiber,
                    mealType: serverMeal.meal_type as CachedMeal['mealType'],
                    category: serverMeal.category as CachedMeal['category'],
                    recordDate: serverMeal.record_date,
                    note: serverMeal.note,
                    aiRecognized: serverMeal.ai_recognized,
                    source: (serverMeal.source || 'manual') as CachedMeal['source'],
                    sourceDetail: serverMeal.source_detail || undefined,
                    confidence: serverMeal.confidence ?? undefined,
                    estimatedFields: Array.isArray(serverMeal.estimated_fields_json) ? serverMeal.estimated_fields_json : [],
                    ruleWarnings: Array.isArray(serverMeal.rule_warnings_json) ? serverMeal.rule_warnings_json : [],
                    recognitionMeta: serverMeal.recognition_meta_json || undefined,
                    syncStatus: 'SYNCED' as const,
                    pendingDelete: false,
                    updatedAt: new Date()
                };

                if (localMeal?.id) {
                    await db.meals.update(localMeal.id, payload);
                } else {
                    await db.meals.add({
                        ...payload,
                        clientId: serverMeal.client_id,
                        createdAt: new Date(),
                    });
                }
            }
        });
    },

    async getTodaySummary(userId: number): Promise<{
        calories: number;
        sodium: number;
        purine: number;
        protein: number;
        carbs: number;
        fat: number;
        mealCount: number;
    }> {
        const meals = (await this.getToday(userId)).filter(meal => !meal.pendingDelete);

        return {
            calories: meals.reduce((sum, m) => sum + m.calories, 0),
            sodium: meals.reduce((sum, m) => sum + m.sodium, 0),
            purine: meals.reduce((sum, m) => sum + m.purine, 0),
            protein: meals.reduce((sum, m) => sum + (m.protein || 0), 0),
            carbs: meals.reduce((sum, m) => sum + (m.carbs || 0), 0),
            fat: meals.reduce((sum, m) => sum + (m.fat || 0), 0),
            mealCount: meals.length
        };
    },

    async clearUserData(userId: number): Promise<void> {
        const meals = await db.meals.where('userId').equals(userId).toArray();
        await db.meals.bulkDelete(meals.map(meal => meal.id!).filter(Boolean));
    },

    async clearLegacyData(): Promise<void> {
        const meals = await db.meals.where('userId').equals(LEGACY_USER_ID).toArray();
        await db.meals.bulkDelete(meals.map(meal => meal.id!).filter(Boolean));
    }
};

export const SyncMetaService = {
    async getLastSyncTime(userId: number): Promise<Date | null> {
        const meta = await db.syncMeta.get(syncMetaKey(userId, 'lastSyncTime'));
        return meta ? new Date(meta.value as string) : null;
    },

    async setLastSyncTime(userId: number, time: Date = new Date()): Promise<void> {
        await db.syncMeta.put({ key: syncMetaKey(userId, 'lastSyncTime'), value: time.toISOString() });
    },

    async getSyncStatus(userId: number): Promise<'idle' | 'syncing' | 'error'> {
        const meta = await db.syncMeta.get(syncMetaKey(userId, 'syncStatus'));
        return (meta?.value as 'idle' | 'syncing' | 'error') || 'idle';
    },

    async setSyncStatus(userId: number, status: 'idle' | 'syncing' | 'error'): Promise<void> {
        await db.syncMeta.put({ key: syncMetaKey(userId, 'syncStatus'), value: status });
    },

    async clearUserMeta(userId: number): Promise<void> {
        const rows = await db.syncMeta.filter(meta => meta.key.startsWith(`user:${userId}:`)).toArray();
        await db.syncMeta.bulkDelete(rows.map(row => row.key));
    }
};

export const CacheCleanupService = {
    async cleanupExpired(userId: number): Promise<number> {
        const thirtyDaysAgo = new Date();
        thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
        const cutoffDate = getLocalDateString(thirtyDaysAgo);

        const toDelete = await db.meals
            .where('[userId+syncStatus]')
            .equals([userId, 'SYNCED'])
            .and(meal => meal.recordDate < cutoffDate)
            .toArray();

        const idsToDelete = toDelete.map(m => m.id!).filter(Boolean);
        await db.meals.bulkDelete(idsToDelete);

        return idsToDelete.length;
    },

    async getStats(userId: number): Promise<{
        totalCount: number;
        syncedCount: number;
        pendingCount: number;
        failedCount: number;
        conflictCount: number;
        oldestDate: string | null;
        newestDate: string | null;
        estimatedSizeKB: number;
    }> {
        const allMeals = await db.meals.where('userId').equals(userId).toArray();
        const synced = allMeals.filter(m => m.syncStatus === 'SYNCED');
        const pending = allMeals.filter(m => m.syncStatus === 'PENDING');
        const failed = allMeals.filter(m => m.syncStatus === 'FAILED');
        const conflict = allMeals.filter(m => m.syncStatus === 'CONFLICT');
        const dates = allMeals.map(m => m.recordDate).sort();
        const estimatedSizeKB = Math.max(1, Math.round(JSON.stringify(allMeals).length / 1024));

        return {
            totalCount: allMeals.length,
            syncedCount: synced.length,
            pendingCount: pending.length,
            failedCount: failed.length,
            conflictCount: conflict.length,
            oldestDate: dates[0] || null,
            newestDate: dates[dates.length - 1] || null,
            estimatedSizeKB
        };
    },

    async clearUserLocalData(userId: number): Promise<void> {
        await OfflineMealsService.clearUserData(userId);
        await SyncMetaService.clearUserMeta(userId);
    },

    async clearAll(): Promise<void> {
        await db.meals.clear();
        await db.syncMeta.clear();
    }
};

export class SyncScheduler {
    private syncInterval: ReturnType<typeof setInterval> | null = null;
    private isOnline: boolean = typeof navigator === 'undefined' ? true : navigator.onLine;
    private currentUserId: number | null = null;

    constructor() {
        if (typeof window === 'undefined') return;

        window.addEventListener('online', () => {
            this.isOnline = true;
            void this.triggerSync();
        });

        window.addEventListener('offline', () => {
            this.isOnline = false;
        });
    }

    start(userId: number, intervalMs: number = 5 * 60 * 1000): void {
        this.currentUserId = userId;
        if (this.syncInterval) {
            clearInterval(this.syncInterval);
        }

        this.syncInterval = setInterval(() => {
            void this.triggerSync();
        }, intervalMs);

        void this.triggerSync();
    }

    stop(): void {
        if (this.syncInterval) {
            clearInterval(this.syncInterval);
            this.syncInterval = null;
        }
        this.currentUserId = null;
    }

    async triggerSync(userId: number | null = this.currentUserId): Promise<void> {
        if (!userId) return;

        if (!this.isOnline) {
            console.log('[Sync] 离线状态，跳过同步');
            return;
        }

        const currentStatus = await SyncMetaService.getSyncStatus(userId);
        if (currentStatus === 'syncing') {
            console.log('[Sync] 同步进行中，跳过');
            return;
        }

        let pendingMeals: CachedMeal[] = [];
        try {
            await SyncMetaService.setSyncStatus(userId, 'syncing');
            pendingMeals = await OfflineMealsService.getPending(userId);

            if (pendingMeals.length === 0) {
                await SyncMetaService.setSyncStatus(userId, 'idle');
                return;
            }

            const mealCreates = pendingMeals
                .filter(m => !m.serverId && !m.pendingDelete)
                .map(m => ({
                    client_id: m.clientId,
                    name: m.name,
                    portion: m.portion,
                    calories: m.calories,
                    sodium: m.sodium,
                    purine: m.purine,
                    protein: m.protein,
                    carbs: m.carbs,
                    fat: m.fat,
                    fiber: m.fiber,
                    meal_type: m.mealType,
                    category: m.category,
                    record_date: m.recordDate,
                    note: m.note,
                    image_url: m.imageUrl,
                    ai_recognized: m.aiRecognized,
                    source: m.source || 'manual',
                    source_detail: m.sourceDetail,
                    confidence: m.confidence,
                    estimated_fields_json: m.estimatedFields || [],
                    rule_warnings_json: m.ruleWarnings || [],
                    recognition_meta_json: m.recognitionMeta
                }));

            const mealOperations = pendingMeals
                .filter(m => !!m.serverId)
                .map(m => ({
                    op_type: m.pendingDelete ? 'delete' as const : 'update' as const,
                    client_id: m.clientId,
                    server_id: m.serverId,
                    changes: m.pendingDelete ? undefined : {
                        name: m.name,
                        portion: m.portion,
                        calories: m.calories,
                        sodium: m.sodium,
                        purine: m.purine,
                        protein: m.protein,
                        carbs: m.carbs,
                        fat: m.fat,
                        fiber: m.fiber,
                        meal_type: m.mealType,
                        category: m.category,
                        note: m.note,
                        source_detail: m.sourceDetail,
                        confidence: m.confidence,
                        estimated_fields_json: m.estimatedFields || [],
                        rule_warnings_json: m.ruleWarnings || [],
                        recognition_meta_json: m.recognitionMeta
                    }
                }));

            const mealsToSync = mealCreates;

            const lastSyncTime = await SyncMetaService.getLastSyncTime(userId);
            const response = await MealsAPI.sync(mealsToSync, lastSyncTime?.toISOString(), mealOperations) as {
                synced_count: number;
                conflicts: string[];
                deleted_client_ids: string[];
                server_meals: Array<{
                    id: number;
                    client_id: string;
                    name: string;
                    portion: string;
                    calories: number;
                    sodium: number;
                    purine: number;
                    protein?: number;
                    carbs?: number;
                    fat?: number;
                    fiber?: number;
                    meal_type: string;
                    category: string;
                    record_date: string;
                    note?: string;
                    ai_recognized: boolean;
                    source?: string;
                    source_detail?: string;
                    confidence?: number;
                    estimated_fields_json?: string[];
                    rule_warnings_json?: string[];
                    recognition_meta_json?: Record<string, unknown>;
                }>;
            };

            for (const meal of pendingMeals) {
                if (response.conflicts.includes(meal.clientId)) {
                    await OfflineMealsService.markConflict(userId, meal.clientId);
                    continue;
                }

                if (response.deleted_client_ids?.includes(meal.clientId)) {
                    await OfflineMealsService.removeByClientId(userId, meal.clientId);
                    continue;
                }

                const serverMeal = response.server_meals.find(sm => sm.client_id === meal.clientId);
                if (serverMeal) {
                    await OfflineMealsService.markSynced(userId, meal.clientId, serverMeal.id);
                }
            }

            if (response.server_meals.length > 0) {
                await OfflineMealsService.mergeFromServer(userId, response.server_meals);
            }

            await SyncMetaService.setLastSyncTime(userId);
            await SyncMetaService.setSyncStatus(userId, 'idle');
            await CacheCleanupService.cleanupExpired(userId);
            window.dispatchEvent(new CustomEvent('prism:meals-synced', { detail: { userId } }));
        } catch (error) {
            console.error('[Sync] 同步失败:', error);
            if (pendingMeals.length > 0) {
                await OfflineMealsService.markFailed(
                    userId,
                    pendingMeals.map(meal => meal.clientId),
                    error instanceof Error ? error.message : 'sync_failed',
                );
            }
            await SyncMetaService.setSyncStatus(userId, 'error');
        }
    }
}

export const syncScheduler = new SyncScheduler();

export default db;
