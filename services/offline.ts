/**
 * Prism Metabolic Console - 离线缓存服务
 * 使用 Dexie.js 封装 IndexedDB，实现饮食日志离线存储与同步
 */

import Dexie, { Table } from 'dexie';

// ==================== 数据类型定义 ====================

export interface CachedMeal {
    id?: number;                    // 本地自增 ID
    clientId: string;               // 客户端生成的唯一 ID (UUID)
    serverId?: number;              // 服务器端 ID（同步后填充）
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
    recordDate: string;             // ISO 日期字符串 YYYY-MM-DD
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

// ==================== 数据库定义 ====================

class PrismDatabase extends Dexie {
    meals!: Table<CachedMeal, number>;
    syncMeta!: Table<SyncMeta, string>;

    constructor() {
        super('PrismMetabolicConsole');

        // 定义数据库版本和表结构
        this.version(1).stores({
            meals: '++id, clientId, serverId, recordDate, syncStatus, mealType, createdAt',
            syncMeta: 'key'
        });
    }
}

// 数据库单例
const db = new PrismDatabase();

// ==================== 工具函数 ====================

/**
 * 生成客户端唯一 ID
 */
export function generateClientId(): string {
    return crypto.randomUUID();
}

/**
 * 获取今日日期字符串
 */
export function getTodayDateString(): string {
    return new Date().toISOString().split('T')[0];
}

// ==================== 饮食记录离线操作 ====================

export const OfflineMealsService = {
    /**
     * 添加饮食记录（离线优先）
     */
    async add(meal: Omit<CachedMeal, 'id' | 'clientId' | 'syncStatus' | 'createdAt' | 'updatedAt'>): Promise<CachedMeal> {
        const now = new Date();
        const newMeal: CachedMeal = {
            ...meal,
            clientId: generateClientId(),
            syncStatus: 'PENDING',
            aiRecognized: meal.aiRecognized ?? false,
            createdAt: now,
            updatedAt: now
        };

        const id = await db.meals.add(newMeal);
        return { ...newMeal, id };
    },

    /**
     * 获取今日饮食记录
     */
    async getToday(): Promise<CachedMeal[]> {
        const today = getTodayDateString();
        return db.meals.where('recordDate').equals(today).toArray();
    },

    /**
     * 获取指定日期的饮食记录
     */
    async getByDate(date: string): Promise<CachedMeal[]> {
        return db.meals.where('recordDate').equals(date).toArray();
    },

    /**
     * 获取日期范围内的饮食记录
     */
    async getByDateRange(startDate: string, endDate: string): Promise<CachedMeal[]> {
        return db.meals
            .where('recordDate')
            .between(startDate, endDate, true, true)
            .toArray();
    },

    /**
     * 获取所有待同步的记录
     */
    async getPending(): Promise<CachedMeal[]> {
        return db.meals.where('syncStatus').equals('PENDING').toArray();
    },

    /**
     * 更新记录
     */
    async update(id: number, changes: Partial<CachedMeal>): Promise<void> {
        await db.meals.update(id, {
            ...changes,
            updatedAt: new Date(),
            syncStatus: 'PENDING'  // 修改后重新标记为待同步
        });
    },

    /**
     * 删除记录
     */
    async delete(id: number): Promise<void> {
        await db.meals.delete(id);
    },

    /**
     * 标记为已同步
     */
    async markSynced(clientId: string, serverId: number): Promise<void> {
        const meal = await db.meals.where('clientId').equals(clientId).first();
        if (meal && meal.id) {
            await db.meals.update(meal.id, {
                serverId,
                syncStatus: 'SYNCED',
                updatedAt: new Date()
            });
        }
    },

    /**
     * 批量标记为已同步
     */
    async markMultipleSynced(items: Array<{ clientId: string; serverId: number }>): Promise<void> {
        await db.transaction('rw', db.meals, async () => {
            for (const item of items) {
                await this.markSynced(item.clientId, item.serverId);
            }
        });
    },

    /**
     * 从服务器数据合并（处理服务器推送的更新）
     */
    async mergeFromServer(serverMeals: Array<{
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
                // 检查本地是否存在
                const localMeal = await db.meals
                    .where('clientId')
                    .equals(serverMeal.client_id)
                    .first();

                if (localMeal) {
                    // 更新本地记录
                    await db.meals.update(localMeal.id!, {
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
                        syncStatus: 'SYNCED',
                        updatedAt: new Date()
                    });
                } else {
                    // 新增本地记录
                    await db.meals.add({
                        clientId: serverMeal.client_id,
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
                        syncStatus: 'SYNCED',
                        createdAt: new Date(),
                        updatedAt: new Date()
                    });
                }
            }
        });
    },

    /**
     * 计算今日摄入汇总
     */
    async getTodaySummary(): Promise<{
        calories: number;
        sodium: number;
        purine: number;
        protein: number;
        carbs: number;
        fat: number;
        mealCount: number;
    }> {
        const meals = await this.getToday();

        return {
            calories: meals.reduce((sum, m) => sum + m.calories, 0),
            sodium: meals.reduce((sum, m) => sum + m.sodium, 0),
            purine: meals.reduce((sum, m) => sum + m.purine, 0),
            protein: meals.reduce((sum, m) => sum + (m.protein || 0), 0),
            carbs: meals.reduce((sum, m) => sum + (m.carbs || 0), 0),
            fat: meals.reduce((sum, m) => sum + (m.fat || 0), 0),
            mealCount: meals.length
        };
    }
};

// ==================== 同步元数据管理 ====================

export const SyncMetaService = {
    /**
     * 获取上次同步时间
     */
    async getLastSyncTime(): Promise<Date | null> {
        const meta = await db.syncMeta.get('lastSyncTime');
        return meta ? new Date(meta.value as string) : null;
    },

    /**
     * 更新上次同步时间
     */
    async setLastSyncTime(time: Date = new Date()): Promise<void> {
        await db.syncMeta.put({ key: 'lastSyncTime', value: time.toISOString() });
    },

    /**
     * 获取同步状态
     */
    async getSyncStatus(): Promise<'idle' | 'syncing' | 'error'> {
        const meta = await db.syncMeta.get('syncStatus');
        return (meta?.value as 'idle' | 'syncing' | 'error') || 'idle';
    },

    /**
     * 设置同步状态
     */
    async setSyncStatus(status: 'idle' | 'syncing' | 'error'): Promise<void> {
        await db.syncMeta.put({ key: 'syncStatus', value: status });
    }
};

// ==================== 缓存清理策略 ====================

export const CacheCleanupService = {
    /**
     * 清理过期缓存
     * 删除已同步且超过 30 天的记录
     */
    async cleanupExpired(): Promise<number> {
        const thirtyDaysAgo = new Date();
        thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
        const cutoffDate = thirtyDaysAgo.toISOString().split('T')[0];

        // 只删除已同步的旧数据
        const toDelete = await db.meals
            .where('syncStatus')
            .equals('SYNCED')
            .and(meal => meal.recordDate < cutoffDate)
            .toArray();

        const idsToDelete = toDelete.map(m => m.id!).filter(id => id !== undefined);
        await db.meals.bulkDelete(idsToDelete);

        return idsToDelete.length;
    },

    /**
     * 获取缓存统计信息
     */
    async getStats(): Promise<{
        totalCount: number;
        syncedCount: number;
        pendingCount: number;
        oldestDate: string | null;
        newestDate: string | null;
        estimatedSizeKB: number;
    }> {
        const allMeals = await db.meals.toArray();
        const synced = allMeals.filter(m => m.syncStatus === 'SYNCED');
        const pending = allMeals.filter(m => m.syncStatus === 'PENDING');

        const dates = allMeals.map(m => m.recordDate).sort();

        // 粗略估算存储大小
        const estimatedSizeKB = Math.round(JSON.stringify(allMeals).length / 1024);

        return {
            totalCount: allMeals.length,
            syncedCount: synced.length,
            pendingCount: pending.length,
            oldestDate: dates[0] || null,
            newestDate: dates[dates.length - 1] || null,
            estimatedSizeKB
        };
    },

    /**
     * 清空所有缓存（用于登出时）
     */
    async clearAll(): Promise<void> {
        await db.meals.clear();
        await db.syncMeta.clear();
    }
};

// ==================== 同步调度器 ====================

export class SyncScheduler {
    private syncInterval: number | null = null;
    private isOnline: boolean = navigator.onLine;

    constructor() {
        // 监听网络状态变化
        window.addEventListener('online', () => {
            this.isOnline = true;
            this.triggerSync();
        });

        window.addEventListener('offline', () => {
            this.isOnline = false;
        });
    }

    /**
     * 启动定时同步
     * @param intervalMs 同步间隔（毫秒），默认 5 分钟
     */
    start(intervalMs: number = 5 * 60 * 1000): void {
        if (this.syncInterval) {
            clearInterval(this.syncInterval);
        }

        this.syncInterval = window.setInterval(() => {
            this.triggerSync();
        }, intervalMs);

        // 启动时立即同步一次
        this.triggerSync();
    }

    /**
     * 停止定时同步
     */
    stop(): void {
        if (this.syncInterval) {
            clearInterval(this.syncInterval);
            this.syncInterval = null;
        }
    }

    /**
     * 触发同步
     */
    async triggerSync(): Promise<void> {
        if (!this.isOnline) {
            console.log('[Sync] 离线状态，跳过同步');
            return;
        }

        const currentStatus = await SyncMetaService.getSyncStatus();
        if (currentStatus === 'syncing') {
            console.log('[Sync] 同步进行中，跳过');
            return;
        }

        try {
            await SyncMetaService.setSyncStatus('syncing');

            // 获取待同步数据
            const pendingMeals = await OfflineMealsService.getPending();

            if (pendingMeals.length === 0) {
                console.log('[Sync] 无待同步数据');
                await SyncMetaService.setSyncStatus('idle');
                return;
            }

            console.log(`[Sync] 开始同步 ${pendingMeals.length} 条记录`);

            // 转换为 API 格式
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

            // 调用同步 API
            const { MealsAPI } = await import('./api');
            const lastSyncTime = await SyncMetaService.getLastSyncTime();

            const response = await MealsAPI.sync(
                mealsToSync,
                lastSyncTime?.toISOString()
            ) as {
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

            // 处理同步结果
            console.log(`[Sync] 同步完成: ${response.synced_count} 条成功, ${response.conflicts.length} 条冲突`);

            // 标记已同步的记录
            for (const meal of pendingMeals) {
                if (!response.conflicts.includes(meal.clientId)) {
                    // 从服务器响应中找到对应的 serverId
                    const serverMeal = response.server_meals.find(
                        sm => sm.client_id === meal.clientId
                    );
                    if (serverMeal) {
                        await OfflineMealsService.markSynced(meal.clientId, serverMeal.id);
                    }
                }
            }

            // 合并服务器端更新
            if (response.server_meals.length > 0) {
                await OfflineMealsService.mergeFromServer(response.server_meals);
            }

            // 更新同步时间
            await SyncMetaService.setLastSyncTime();
            await SyncMetaService.setSyncStatus('idle');

            // 定期清理过期缓存
            const cleaned = await CacheCleanupService.cleanupExpired();
            if (cleaned > 0) {
                console.log(`[Sync] 清理了 ${cleaned} 条过期缓存`);
            }

        } catch (error) {
            console.error('[Sync] 同步失败:', error);
            await SyncMetaService.setSyncStatus('error');
        }
    }
}

// 导出同步调度器单例
export const syncScheduler = new SyncScheduler();

export default db;
