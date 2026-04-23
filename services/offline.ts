/**
 * Prism Metabolic Console - 离线缓存服务
 * 使用 Dexie.js 封装 IndexedDB，实现按用户隔离的饮食日志离线存储与同步。
 */

import Dexie, { Table } from 'dexie';
import { getLocalDateString } from './date';

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
    syncStatus: 'PENDING' | 'SYNCED' | 'CONFLICT';
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
        return db.meals.where('[userId+syncStatus]').equals([userId, 'PENDING']).toArray();
    },

    async update(userId: number, id: number, changes: Partial<CachedMeal>): Promise<void> {
        const meal = await db.meals.get(id);
        if (!meal || meal.userId !== userId) return;

        await db.meals.update(id, {
            ...changes,
            userId,
            updatedAt: new Date(),
            syncStatus: 'PENDING'
        });
    },

    async delete(userId: number, id: number): Promise<void> {
        const meal = await db.meals.get(id);
        if (meal?.userId === userId) {
            await db.meals.delete(id);
        }
    },

    async markSynced(userId: number, clientId: string, serverId: number): Promise<void> {
        const meal = await db.meals.where('[userId+clientId]').equals([userId, clientId]).first();
        if (meal?.id) {
            await db.meals.update(meal.id, {
                serverId,
                syncStatus: 'SYNCED',
                updatedAt: new Date()
            });
        }
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
                    syncStatus: 'SYNCED' as const,
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
        const meals = await this.getToday(userId);

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
        oldestDate: string | null;
        newestDate: string | null;
        estimatedSizeKB: number;
    }> {
        const allMeals = await db.meals.where('userId').equals(userId).toArray();
        const synced = allMeals.filter(m => m.syncStatus === 'SYNCED');
        const pending = allMeals.filter(m => m.syncStatus === 'PENDING');
        const dates = allMeals.map(m => m.recordDate).sort();
        const estimatedSizeKB = Math.max(1, Math.round(JSON.stringify(allMeals).length / 1024));

        return {
            totalCount: allMeals.length,
            syncedCount: synced.length,
            pendingCount: pending.length,
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
    private syncInterval: number | null = null;
    private isOnline: boolean = navigator.onLine;
    private currentUserId: number | null = null;

    constructor() {
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

        this.syncInterval = window.setInterval(() => {
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

        try {
            await SyncMetaService.setSyncStatus(userId, 'syncing');
            const pendingMeals = await OfflineMealsService.getPending(userId);

            if (pendingMeals.length === 0) {
                await SyncMetaService.setSyncStatus(userId, 'idle');
                return;
            }

            const mealsToSync = pendingMeals.map(m => ({
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
                ai_recognized: m.aiRecognized
            }));

            const { MealsAPI } = await import('./api');
            const lastSyncTime = await SyncMetaService.getLastSyncTime(userId);
            const response = await MealsAPI.sync(mealsToSync, lastSyncTime?.toISOString()) as {
                synced_count: number;
                conflicts: string[];
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
                }>;
            };

            for (const meal of pendingMeals) {
                if (!response.conflicts.includes(meal.clientId)) {
                    const serverMeal = response.server_meals.find(sm => sm.client_id === meal.clientId);
                    if (serverMeal) {
                        await OfflineMealsService.markSynced(userId, meal.clientId, serverMeal.id);
                    }
                }
            }

            if (response.server_meals.length > 0) {
                await OfflineMealsService.mergeFromServer(userId, response.server_meals);
            }

            await SyncMetaService.setLastSyncTime(userId);
            await SyncMetaService.setSyncStatus(userId, 'idle');
            await CacheCleanupService.cleanupExpired(userId);
        } catch (error) {
            console.error('[Sync] 同步失败:', error);
            await SyncMetaService.setSyncStatus(userId, 'error');
        }
    }
}

export const syncScheduler = new SyncScheduler();

export default db;
