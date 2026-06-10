import React, { useEffect, useState } from 'react';
import { ComplianceDocumentKey, DeviceSessionItem, View, UserProfile } from '../../types';
import { AccountAPI, AuthAPI, IntakeAPI, ReportsAPI, TokenManager } from '../../services/api';
import { APP_BUILD, APP_DISPLAY_NAME, APP_VERSION } from '../../constants/app';
import { CacheCleanupService, CachedIntakeDraft, CachedMeal, IntakeDraftQueueService, OfflineMealsService, SyncMetaService, syncScheduler } from '../../services/offline';
import { AssistantIntensity, ChatMode, getAssistantIntensity, getChatMode, setAssistantIntensity, setChatMode } from '../../services/sessionState';

interface SettingsViewProps {
    onViewChange: (view: View) => void;
    userProfile: UserProfile;
    currentUserId: number | null;
    onUpdateProfile: (profile: UserProfile) => Promise<void> | void;
    onLogout?: () => void;
    onOpenCompliance?: (documentKey: ComplianceDocumentKey) => void;
    onDataDeleted?: () => void;
    onOpenLogDate?: (date: string) => void | Promise<void>;
}

type ModalType =
    | 'BODY_PARAMS'
    | 'GENDER_SELECT'
    | 'ASSISTANT_PREF'
    | 'INTENSITY_SELECT'
    | 'CLEAN_DATA'
    | 'OFFLINE_QUEUE'
    | 'DELETE_DATA_CONFIRM'
    | 'DELETE_ACCOUNT_CONFIRM'
    | 'DATA_RIGHTS_NOTICE'
    | 'ABOUT'
    | 'LOGOUT_CONFIRM'
    | null;

type CacheStats = {
    totalCount: number;
    syncedCount: number;
    pendingCount: number;
    failedCount: number;
    conflictCount: number;
    intakeDraftCount: number;
    pendingReviewCount: number;
    inReviewCount: number;
    highRiskDraftCount: number;
    lowConfidenceDraftCount: number;
    hardBlockDraftCount: number;
    intakeDraftSourceCounts: Record<string, number>;
    intakeDraftStatusCounts: Record<string, number>;
    oldestDate: string | null;
    newestDate: string | null;
    estimatedSizeKB: number;
};

interface ModalProps {
    title: string;
    onClose: () => void;
    children: React.ReactNode;
    maxWidthClass?: string;
}

const Modal: React.FC<ModalProps> = ({ title, onClose, children, maxWidthClass = 'max-w-xs' }) => (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
        <div className={`bg-[#131b1d] border border-white/10 w-full rounded-2xl p-5 shadow-2xl relative ${maxWidthClass}`}>
            <h3 className="text-white font-serif text-lg font-bold mb-4 text-center tracking-wide">{title}</h3>
            {children}
            <button
                onClick={onClose}
                className="absolute top-3 right-3 text-white/40 hover:text-white"
            >
                <span className="material-symbols-outlined">close</span>
            </button>
        </div>
    </div>
);

const queueStatusLabelMap: Record<CachedMeal['syncStatus'], string> = {
    PENDING: '待同步',
    SYNCED: '已同步',
    FAILED: '同步失败',
    CONFLICT: '冲突待处理',
};

const queueStatusClassMap: Record<CachedMeal['syncStatus'], string> = {
    PENDING: 'border-primary/20 bg-primary/10 text-primary',
    SYNCED: 'border-emerald-400/15 bg-emerald-500/10 text-emerald-200',
    FAILED: 'border-red-400/25 bg-red-500/10 text-red-200',
    CONFLICT: 'border-amber-300/25 bg-amber-500/10 text-amber-100',
};

const mealTypeLabelMap: Record<CachedMeal['mealType'], string> = {
    BREAKFAST: '早餐',
    LUNCH: '午餐',
    DINNER: '晚餐',
    SNACK: '加餐',
};

const sourceLabelMap: Record<string, string> = {
    manual: '手动',
    voice: '语音',
    photo: '拍照',
    ai_quick_log: 'AI',
};

const intakeReviewStatusLabelMap: Record<CachedIntakeDraft['status'], string> = {
    PENDING_REVIEW: '待复核',
    IN_REVIEW: '复核中',
    CONFIRMED: '已确认',
    DISCARDED: '已丢弃',
};

const intakeReviewStatusClassMap: Record<CachedIntakeDraft['status'], string> = {
    PENDING_REVIEW: 'border-amber-300/25 bg-amber-500/10 text-amber-100',
    IN_REVIEW: 'border-primary/20 bg-primary/10 text-primary',
    CONFIRMED: 'border-emerald-400/15 bg-emerald-500/10 text-emerald-200',
    DISCARDED: 'border-white/10 bg-white/5 text-slate-400',
};

const assistantModeLabelMap: Record<ChatMode, string> = {
    STRICT: '分析师模式',
    GENTLE: '教练模式',
};

const assistantIntensityLabelMap: Record<AssistantIntensity, string> = {
    LOW: '轻提示',
    STANDARD: '平衡',
    HIGH: '强干预',
};

const formatDeviceSessionLabel = (rawLabel?: string | null): string => {
    const label = (rawLabel || '').trim();
    if (!label) return '未知设备';
    if (!/Mozilla\/|AppleWebKit|Chrome\/|Safari\/|Firefox\//i.test(label)) return label;

    const os = /Windows NT/i.test(label)
        ? 'Windows'
        : /Mac OS X|Macintosh/i.test(label)
            ? 'macOS'
            : /iPhone|iPad/i.test(label)
                ? 'iOS'
                : /Android/i.test(label)
                    ? 'Android'
                    : /Linux/i.test(label)
                        ? 'Linux'
                        : '浏览器设备';
    const browser = /Edg\//i.test(label)
        ? 'Edge'
        : /OPR\//i.test(label)
            ? 'Opera'
            : /Firefox\//i.test(label)
                ? 'Firefox'
                : /Chrome\//i.test(label)
                    ? 'Chrome'
                    : /Safari\//i.test(label)
                        ? 'Safari'
                        : '浏览器';

    return `${os} · ${browser}`;
};

const SettingsView: React.FC<SettingsViewProps> = ({ onViewChange, userProfile, currentUserId, onUpdateProfile, onLogout, onOpenCompliance, onDataDeleted, onOpenLogDate }) => {
    const [editProfile, setEditProfile] = useState<UserProfile>(userProfile);
    const [activeModal, setActiveModal] = useState<ModalType>(null);
    const [isCleaning, setIsCleaning] = useState(false);
    const [isSavingProfile, setIsSavingProfile] = useState(false);
    const [profileError, setProfileError] = useState<string | null>(null);
    const [cacheStats, setCacheStats] = useState<CacheStats | null>(null);
    const [syncStatus, setSyncStatus] = useState<'idle' | 'syncing' | 'error' | null>(null);
    const [lastSyncTime, setLastSyncTime] = useState<string | null>(null);
    const [isSyncingOffline, setIsSyncingOffline] = useState(false);
    const [isSubmittingReviewTelemetry, setIsSubmittingReviewTelemetry] = useState(false);
    const [reviewTelemetryNotice, setReviewTelemetryNotice] = useState<string | null>(null);
    const [offlineQueueItems, setOfflineQueueItems] = useState<CachedMeal[]>([]);
    const [intakeDraftQueueItems, setIntakeDraftQueueItems] = useState<CachedIntakeDraft[]>([]);
    const [queueActionClientId, setQueueActionClientId] = useState<string | null>(null);
    const [intakeDraftActionClientId, setIntakeDraftActionClientId] = useState<string | null>(null);
    const [queueNotice, setQueueNotice] = useState<string | null>(null);
    const [deviceSessions, setDeviceSessions] = useState<DeviceSessionItem[]>([]);
    const [sessionActionId, setSessionActionId] = useState<string | null>(null);
    const [sessionNotice, setSessionNotice] = useState<string | null>(null);
    const [assistantMode, setAssistantModeState] = useState<ChatMode>(() => getChatMode());
    const [assistantIntensity, setAssistantIntensityState] = useState<AssistantIntensity>(() => getAssistantIntensity());
    const [dataRightsLoading, setDataRightsLoading] = useState<string | null>(null);
    const [dataRightsNotice, setDataRightsNotice] = useState<string | null>(null);

    const appVersionLabel = `v${APP_VERSION}${APP_BUILD !== 'local' ? ` (${APP_BUILD})` : ''}`;
    const offlineRiskCount = cacheStats
        ? cacheStats.pendingCount + cacheStats.failedCount + cacheStats.conflictCount + cacheStats.pendingReviewCount + cacheStats.inReviewCount
        : 0;

    const loadCacheStats = async () => {
        if (!currentUserId) {
            setCacheStats(null);
            setSyncStatus(null);
            setLastSyncTime(null);
            setOfflineQueueItems([]);
            setIntakeDraftQueueItems([]);
            setDeviceSessions([]);
            return;
        }
        try {
            const [stats, status, lastSync, queueItems, intakeDraftItems, sessions] = await Promise.all([
                CacheCleanupService.getStats(currentUserId),
                SyncMetaService.getSyncStatus(currentUserId),
                SyncMetaService.getLastSyncTime(currentUserId),
                OfflineMealsService.getQueue(currentUserId),
                IntakeDraftQueueService.getQueue(currentUserId),
                AuthAPI.listSessions(),
            ]);
            setCacheStats(stats);
            setSyncStatus(status);
            setLastSyncTime(lastSync ? lastSync.toLocaleString('zh-CN', { hour12: false }) : null);
            setOfflineQueueItems(queueItems);
            setIntakeDraftQueueItems(intakeDraftItems);
            setDeviceSessions(sessions);
        } catch (error) {
            console.error('读取缓存统计失败:', error);
            setCacheStats(null);
            setSyncStatus(null);
            setLastSyncTime(null);
            setOfflineQueueItems([]);
            setIntakeDraftQueueItems([]);
            setDeviceSessions([]);
        }
    };

    useEffect(() => {
        setEditProfile(userProfile);
    }, [userProfile]);

    useEffect(() => {
        void loadCacheStats();
    }, [currentUserId]);

    const openBodyParamsModal = () => {
        setEditProfile(userProfile);
        setProfileError(null);
        setActiveModal('BODY_PARAMS');
    };

    const openGenderModal = () => {
        setEditProfile(userProfile);
        setProfileError(null);
        setActiveModal('GENDER_SELECT');
    };

    const openAssistantModeModal = () => {
        setAssistantModeState(getChatMode());
        setActiveModal('ASSISTANT_PREF');
    };

    const openAssistantIntensityModal = () => {
        setAssistantIntensityState(getAssistantIntensity());
        setActiveModal('INTENSITY_SELECT');
    };

    const saveProfileChanges = async () => {
        setIsSavingProfile(true);
        setProfileError(null);
        try {
            await onUpdateProfile(editProfile);
            setActiveModal(null);
        } catch (error) {
            console.error('保存个人资料失败:', error);
            setProfileError(error instanceof Error ? error.message : '保存个人资料失败，请稍后再试。');
        } finally {
            setIsSavingProfile(false);
        }
    };

    const handleDataClean = async () => {
        if (!currentUserId) return;
        setIsCleaning(true);
        try {
            await CacheCleanupService.cleanupExpired(currentUserId);
            await loadCacheStats();
        } finally {
            setIsCleaning(false);
        }
    };

    const handleRetryOfflineSync = async () => {
        if (!currentUserId) return;
        setIsSyncingOffline(true);
        try {
            await syncScheduler.triggerSync(currentUserId);
            await loadCacheStats();
        } finally {
            setIsSyncingOffline(false);
        }
    };

    const handleSubmitReviewTelemetry = async () => {
        if (!currentUserId) return;
        setIsSubmittingReviewTelemetry(true);
        setReviewTelemetryNotice(null);
        try {
            const stats = await CacheCleanupService.getStats(currentUserId);
            await IntakeAPI.submitReviewTelemetry({
                total_count: stats.intakeDraftCount,
                pending_review_count: stats.pendingReviewCount,
                in_review_count: stats.inReviewCount,
                low_confidence_count: stats.lowConfidenceDraftCount,
                high_risk_count: stats.highRiskDraftCount,
                hard_block_count: stats.hardBlockDraftCount,
                source_counts: stats.intakeDraftSourceCounts,
                status_counts: stats.intakeDraftStatusCounts,
            });
            setCacheStats(stats);
            setReviewTelemetryNotice('复核指标已同步：仅上传聚合计数和来源/状态分布，不包含候选内容。');
        } catch (error) {
            setReviewTelemetryNotice(error instanceof Error ? error.message : '复核指标同步失败，请稍后再试。');
        } finally {
            setIsSubmittingReviewTelemetry(false);
        }
    };

    const handleRetryOfflineItem = async (item: CachedMeal) => {
        if (!currentUserId) return;
        setQueueActionClientId(item.clientId);
        setQueueNotice(null);
        try {
            await OfflineMealsService.markRetry(currentUserId, item.clientId);
            await syncScheduler.triggerSync(currentUserId);
            await loadCacheStats();
            setQueueNotice('该记录已重新进入同步队列。');
        } catch (error) {
            setQueueNotice(error instanceof Error ? error.message : '重试失败，请稍后再试。');
        } finally {
            setQueueActionClientId(null);
        }
    };

    const handleDiscardOfflineItem = async (item: CachedMeal) => {
        if (!currentUserId) return;
        const confirmed = window.confirm(`确认丢弃「${item.name || '未命名记录'}」的本地未同步草稿？这不会删除云端已有记录。`);
        if (!confirmed) return;

        setQueueActionClientId(item.clientId);
        setQueueNotice(null);
        try {
            await OfflineMealsService.discardLocal(currentUserId, item.clientId);
            await loadCacheStats();
            setQueueNotice('本地草稿已丢弃，云端记录不会受影响。');
        } catch (error) {
            setQueueNotice(error instanceof Error ? error.message : '丢弃失败，请稍后再试。');
        } finally {
            setQueueActionClientId(null);
        }
    };

    const handleOpenQueueItemInLog = async (item: CachedMeal) => {
        setActiveModal(null);
        setQueueNotice(null);
        if (onOpenLogDate) {
            await onOpenLogDate(item.recordDate);
            return;
        }
        onViewChange(View.LOG);
    };

    const handleOpenIntakeReviewDesk = () => {
        setActiveModal(null);
        setQueueNotice(null);
        onViewChange(View.CHAT);
    };

    const handleDiscardIntakeDraftItem = async (draft: CachedIntakeDraft) => {
        if (!currentUserId) return;
        const confirmed = window.confirm('确认丢弃这条本地待复核候选？这不会创建或删除云端饮食记录。');
        if (!confirmed) return;

        setIntakeDraftActionClientId(draft.clientId);
        setQueueNotice(null);
        try {
            await IntakeDraftQueueService.discard(currentUserId, draft.clientId);
            await loadCacheStats();
            setQueueNotice('本地待复核候选已丢弃，不会写入饮食日志。');
        } catch (error) {
            setQueueNotice(error instanceof Error ? error.message : '丢弃候选失败，请稍后再试。');
        } finally {
            setIntakeDraftActionClientId(null);
        }
    };

    const handleRevokeDeviceSession = async (session: DeviceSessionItem) => {
        if (!currentUserId || session.is_current) return;
        const confirmed = window.confirm(`确认撤销设备会话「${formatDeviceSessionLabel(session.device_label) || session.session_id}」？这台设备将需要重新登录。`);
        if (!confirmed) return;

        setSessionActionId(session.session_id);
        setSessionNotice(null);
        try {
            await AuthAPI.revokeSession(session.session_id);
            await loadCacheStats();
            setSessionNotice('设备会话已撤销。');
        } catch (error) {
            setSessionNotice(error instanceof Error ? error.message : '撤销失败，请稍后再试。');
        } finally {
            setSessionActionId(null);
        }
    };

    const handleSelectAssistantMode = (mode: ChatMode) => {
        setAssistantModeState(mode);
        setChatMode(mode);
        setActiveModal(null);
    };

    const handleSelectAssistantIntensity = (intensity: AssistantIntensity) => {
        setAssistantIntensityState(intensity);
        setAssistantIntensity(intensity);
        setActiveModal(null);
    };

    const handleLogout = () => {
        if (onLogout) {
            onLogout();
        } else {
            TokenManager.clearTokens();
            onViewChange(View.LOGIN);
        }
    };

    const openLogoutConfirm = () => {
        void loadCacheStats();
        setQueueNotice(null);
        setActiveModal('LOGOUT_CONFIRM');
    };

    const downloadJson = (fileName: string, data: unknown) => {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = fileName;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    };

    const downloadText = (fileName: string, text: string, type = 'text/plain;charset=utf-8') => {
        const blob = new Blob([text], { type });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = fileName;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    };

    const handleExportData = async () => {
        setDataRightsLoading('export');
        try {
            const data = await AccountAPI.exportData();
            const date = new Date().toISOString().slice(0, 10);
            downloadJson(`prism-data-export-${date}.json`, data);
            setDataRightsNotice('个人数据导出已生成。导出内容仅供个人健康管理参考，不构成医疗诊断或治疗记录。');
            setActiveModal('DATA_RIGHTS_NOTICE');
        } catch (error) {
            setDataRightsNotice(error instanceof Error ? error.message : '导出失败，请稍后再试。');
            setActiveModal('DATA_RIGHTS_NOTICE');
        } finally {
            setDataRightsLoading(null);
        }
    };

    const handleExportReport = async (period: 'weekly' | 'monthly') => {
        setDataRightsLoading(`${period}-report`);
        try {
            const date = new Date().toISOString().slice(0, 10);
            const report = period === 'weekly'
                ? await ReportsAPI.getWeekly()
                : await ReportsAPI.getMonthly();
            const csv = period === 'weekly'
                ? await ReportsAPI.getWeeklyCsv()
                : await ReportsAPI.getMonthlyCsv();
            const label = period === 'weekly' ? 'weekly' : 'monthly';
            downloadJson(`prism-${label}-report-${date}.json`, report);
            downloadText(`prism-${label}-report-${date}.csv`, csv, 'text/csv;charset=utf-8');
            setDataRightsNotice('报告已导出为 JSON 与 CSV。报告仅用于个人记录回顾和营养估算，不构成医疗诊断或治疗建议。');
            setActiveModal('DATA_RIGHTS_NOTICE');
        } catch (error) {
            setDataRightsNotice(error instanceof Error ? error.message : '报告导出失败，请稍后再试。');
            setActiveModal('DATA_RIGHTS_NOTICE');
        } finally {
            setDataRightsLoading(null);
        }
    };

    const handleDeleteData = async () => {
        if (!currentUserId) return;
        setDataRightsLoading('delete-data');
        try {
            const result = await AccountAPI.deleteData();
            await CacheCleanupService.clearUserLocalData(currentUserId);
            onDataDeleted?.();
            await loadCacheStats();
            setDataRightsNotice(result.message || '云端个人内容删除请求已完成。');
            setActiveModal('DATA_RIGHTS_NOTICE');
        } catch (error) {
            setDataRightsNotice(error instanceof Error ? error.message : '删除数据失败，请稍后再试。');
            setActiveModal('DATA_RIGHTS_NOTICE');
        } finally {
            setDataRightsLoading(null);
        }
    };

    const handleDeleteAccount = async () => {
        setDataRightsLoading('delete-account');
        try {
            await AccountAPI.deleteAccount();
            if (currentUserId) {
                await CacheCleanupService.clearUserLocalData(currentUserId);
            }
            handleLogout();
        } catch (error) {
            setDataRightsNotice(error instanceof Error ? error.message : '注销账户失败，请稍后再试。');
            setActiveModal('DATA_RIGHTS_NOTICE');
        } finally {
            setDataRightsLoading(null);
        }
    };

    const SectionTitle = ({ title }: { title: string }) => (
        <h3 className="text-white/60 text-xs font-serif font-bold tracking-widest uppercase mb-3 px-1">{title}</h3>
    );

    const ListItem = ({
        icon,
        label,
        value,
        action,
        onClick,
        disabled = false,
    }: {
        icon: string;
        label: string;
        value?: string | React.ReactNode;
        action?: React.ReactNode;
        onClick?: () => void;
        disabled?: boolean;
    }) => (
        <div
            onClick={disabled ? undefined : onClick}
            className={`flex items-center justify-between py-3 border-b border-white/5 last:border-0 ${onClick && !disabled ? 'cursor-pointer active:bg-white/5 transition-colors' : ''} ${disabled ? 'opacity-70' : ''}`}
        >
            <div className="flex items-center gap-3">
                <span className="material-symbols-outlined text-white/40 text-lg">{icon}</span>
                <span className="text-white/90 text-sm font-bold tracking-wide font-serif">{label}</span>
            </div>
            <div className="flex items-center gap-2">
                {value && <span className="text-white/40 text-xs font-serif font-bold tracking-wide max-w-[150px] truncate text-right">{value}</span>}
                {action || (!disabled && <span className="material-symbols-outlined text-white/20 text-lg">chevron_right</span>)}
            </div>
        </div>
    );

    const formatSessionTime = (value: string) => {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return value;
        return date.toLocaleString('zh-CN', { hour12: false });
    };

    const renderModalContent = () => {
        switch (activeModal) {
            case 'BODY_PARAMS':
                return (
                    <Modal title="身体参数" onClose={() => setActiveModal(null)}>
                        <div className="space-y-4">
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="text-xs text-slate-400 mb-1 block font-serif font-bold tracking-wide">身高 (cm)</label>
                                    <input
                                        type="number"
                                        value={editProfile.height}
                                        onChange={(e) => setEditProfile({ ...editProfile, height: Number(e.target.value) })}
                                        className="w-full bg-black/20 border border-white/10 rounded-lg p-3 text-white focus:border-primary/50 outline-none font-serif tracking-wide"
                                    />
                                </div>
                                <div>
                                    <label className="text-xs text-slate-400 mb-1 block font-serif font-bold tracking-wide">体重 (kg)</label>
                                    <input
                                        type="number"
                                        value={editProfile.weight}
                                        onChange={(e) => setEditProfile({ ...editProfile, weight: Number(e.target.value) })}
                                        className="w-full bg-black/20 border border-white/10 rounded-lg p-3 text-white focus:border-primary/50 outline-none font-serif tracking-wide"
                                    />
                                </div>
                            </div>

                            <div>
                                <label className="text-xs text-slate-400 mb-1 block font-serif font-bold tracking-wide">年龄 (岁)</label>
                                <input
                                    type="number"
                                    value={editProfile.age}
                                    onChange={(e) => setEditProfile({ ...editProfile, age: Number(e.target.value) })}
                                    className="w-full bg-black/20 border border-white/10 rounded-lg p-3 text-white focus:border-primary/50 outline-none font-serif tracking-wide"
                                />
                            </div>

                            {profileError && (
                                <p className="text-xs text-red-300 bg-red-500/10 border border-red-500/20 rounded-lg p-2 font-serif tracking-wide">
                                    {profileError}
                                </p>
                            )}

                            <button
                                onClick={saveProfileChanges}
                                disabled={isSavingProfile}
                                className="w-full bg-primary/20 text-primary py-3 rounded-xl font-bold mt-2 border border-primary/20 hover:bg-primary/30 transition-colors font-serif tracking-wide disabled:opacity-50"
                            >
                                {isSavingProfile ? '保存中...' : '保存'}
                            </button>
                        </div>
                    </Modal>
                );
            case 'GENDER_SELECT':
                return (
                    <Modal title="性别" onClose={() => setActiveModal(null)}>
                        <div className="space-y-4">
                            <div className="flex p-1 bg-black/30 rounded-lg">
                                <button
                                    onClick={() => setEditProfile({ ...editProfile, gender: 'MALE' })}
                                    className={`flex-1 py-3 text-sm font-bold rounded-md transition-all font-serif tracking-wide ${editProfile.gender === 'MALE' ? 'bg-[#45b7aa] text-[#080c0d]' : 'text-slate-500'}`}
                                >
                                    男
                                </button>
                                <button
                                    onClick={() => setEditProfile({ ...editProfile, gender: 'FEMALE' })}
                                    className={`flex-1 py-3 text-sm font-bold rounded-md transition-all font-serif tracking-wide ${editProfile.gender === 'FEMALE' ? 'bg-ochre text-[#080c0d]' : 'text-slate-500'}`}
                                >
                                    女
                                </button>
                            </div>
                            {profileError && (
                                <p className="text-xs text-red-300 bg-red-500/10 border border-red-500/20 rounded-lg p-2 font-serif tracking-wide">
                                    {profileError}
                                </p>
                            )}
                            <button
                                onClick={saveProfileChanges}
                                disabled={isSavingProfile}
                                className="w-full bg-primary/20 text-primary py-3 rounded-xl font-bold mt-2 border border-primary/20 hover:bg-primary/30 transition-colors font-serif tracking-wide disabled:opacity-50"
                            >
                                {isSavingProfile ? '保存中...' : '保存'}
                            </button>
                        </div>
                    </Modal>
                );
            case 'ASSISTANT_PREF':
                return (
                    <Modal title="全局助手偏好" onClose={() => setActiveModal(null)}>
                        <div className="space-y-3">
                            {(['STRICT', 'GENTLE'] as ChatMode[]).map(mode => (
                                <button
                                    key={mode}
                                    type="button"
                                    onClick={() => handleSelectAssistantMode(mode)}
                                    className={`w-full rounded-xl border px-4 py-3 text-left transition-colors font-serif tracking-wide ${
                                        assistantMode === mode
                                            ? 'border-primary/30 bg-primary/15 text-primary'
                                            : 'border-white/10 bg-black/20 text-slate-300 hover:bg-white/5'
                                    }`}
                                >
                                    <span className="block text-sm font-bold">{assistantModeLabelMap[mode]}</span>
                                    <span className="mt-1 block text-[11px] text-slate-500">
                                        {mode === 'STRICT' ? '更偏结构化分析和风险边界。' : '更偏陪伴式解释和行动鼓励。'}
                                    </span>
                                </button>
                            ))}
                        </div>
                    </Modal>
                );
            case 'INTENSITY_SELECT':
                return (
                    <Modal title="干预强度" onClose={() => setActiveModal(null)}>
                        <div className="space-y-3">
                            {(['LOW', 'STANDARD', 'HIGH'] as AssistantIntensity[]).map(intensity => (
                                <button
                                    key={intensity}
                                    type="button"
                                    onClick={() => handleSelectAssistantIntensity(intensity)}
                                    className={`w-full rounded-xl border px-4 py-3 text-left transition-colors font-serif tracking-wide ${
                                        assistantIntensity === intensity
                                            ? 'border-primary/30 bg-primary/15 text-primary'
                                            : 'border-white/10 bg-black/20 text-slate-300 hover:bg-white/5'
                                    }`}
                                >
                                    <span className="block text-sm font-bold">{assistantIntensityLabelMap[intensity]}</span>
                                    <span className="mt-1 block text-[11px] text-slate-500">
                                        {intensity === 'LOW' && '只在明显风险或目标偏离时提醒。'}
                                        {intensity === 'STANDARD' && '保留必要提醒，兼顾记录体验。'}
                                        {intensity === 'HIGH' && '更主动提示风险、缺口和下一步。'}
                                    </span>
                                </button>
                            ))}
                        </div>
                    </Modal>
                );
            case 'CLEAN_DATA':
                return (
                    <Modal title="本地离线缓存" onClose={() => !isCleaning && setActiveModal(null)}>
                        <div className="space-y-4">
                            <div className="bg-black/20 rounded-lg p-4 flex items-center justify-between">
                                <div className="flex flex-col">
                                    <span className="text-slate-400 text-xs font-serif font-bold tracking-wide">本账号本地缓存</span>
                                    <span className="text-white font-serif tracking-wide text-xl font-bold">
                                        {cacheStats ? `${cacheStats.estimatedSizeKB} KB` : '未登录'}
                                    </span>
                                </div>
                                <span className="material-symbols-outlined text-white/20 text-4xl">database</span>
                            </div>
                            <div className="space-y-2 text-xs text-slate-400 font-serif font-bold tracking-wide">
                                <div className="flex items-center justify-between p-2 rounded bg-white/5">
                                    <span>记录总数</span>
                                    <span>{cacheStats?.totalCount ?? 0}</span>
                                </div>
                                <div className="flex items-center justify-between p-2 rounded bg-white/5">
                                    <span>待同步</span>
                                    <span>{cacheStats?.pendingCount ?? 0}</span>
                                </div>
                                <div className="flex items-center justify-between p-2 rounded bg-white/5">
                                    <span>冲突 / 失败</span>
                                    <span>{(cacheStats?.conflictCount ?? 0) + (cacheStats?.failedCount ?? 0)}</span>
                                </div>
                                <div className="flex items-center justify-between p-2 rounded bg-white/5">
                                    <span>待复核候选</span>
                                    <span>{cacheStats?.pendingReviewCount ?? 0}</span>
                                </div>
                                <div className="flex items-center justify-between p-2 rounded bg-white/5">
                                    <span>风险 / 低置信度候选</span>
                                    <span>{(cacheStats?.highRiskDraftCount ?? 0) + (cacheStats?.lowConfidenceDraftCount ?? 0)}</span>
                                </div>
                                <div className="flex items-center justify-between p-2 rounded bg-white/5">
                                    <span>同步状态</span>
                                    <span>{syncStatus || 'idle'}</span>
                                </div>
                                <div className="flex items-center justify-between p-2 rounded bg-white/5">
                                    <span>最近同步</span>
                                    <span className="max-w-[160px] truncate">{lastSyncTime || '暂无'}</span>
                                </div>
                                <p className="text-[11px] text-slate-500 leading-relaxed pt-1">
                                    清理只会删除本账号已同步且超过 30 天的本地离线缓存，不会删除服务器饮食记录或 AI 对话。冲突项会保留在本地，需回到日志中重新编辑确认。待复核候选只保存在本机，低置信度或风险候选不自动写入日志，退出前请到候选复核台处理。
                                </p>
                                <p className="text-[11px] text-slate-500 leading-relaxed">
                                    复核指标同步仅上传数量、来源和状态分布，不上传食物名、备注、健康文本、图片或候选草稿。
                                </p>
                                {reviewTelemetryNotice && (
                                    <p className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-[11px] leading-relaxed text-slate-200">
                                        {reviewTelemetryNotice}
                                    </p>
                                )}
                            </div>
                            <button
                                onClick={handleRetryOfflineSync}
                                disabled={isSyncingOffline || !currentUserId}
                                className="w-full bg-primary/10 text-primary py-3 rounded-xl font-bold mt-2 border border-primary/20 hover:bg-primary/20 transition-colors font-serif tracking-wide flex items-center justify-center gap-2 disabled:opacity-50 disabled:grayscale"
                            >
                                {isSyncingOffline ? (
                                    <>
                                        <span className="material-symbols-outlined animate-spin text-sm">rotate_right</span>
                                        同步中...
                                    </>
                                ) : '立即同步待处理队列'}
                            </button>
                            <button
                                onClick={() => {
                                    setQueueNotice(null);
                                    setActiveModal('OFFLINE_QUEUE');
                                }}
                                disabled={!currentUserId}
                                className="w-full bg-white/5 text-slate-200 py-3 rounded-xl font-bold mt-2 border border-white/10 hover:bg-white/10 transition-colors font-serif tracking-wide flex items-center justify-center gap-2 disabled:opacity-50"
                            >
                                <span className="material-symbols-outlined text-sm">list_alt</span>
                                查看待处理队列
                            </button>
                            <button
                                onClick={handleSubmitReviewTelemetry}
                                disabled={isSubmittingReviewTelemetry || !currentUserId}
                                className="w-full bg-emerald-500/10 text-emerald-200 py-3 rounded-xl font-bold mt-2 border border-emerald-300/20 hover:bg-emerald-500/20 transition-colors font-serif tracking-wide flex items-center justify-center gap-2 disabled:opacity-50 disabled:grayscale"
                            >
                                {isSubmittingReviewTelemetry ? (
                                    <>
                                        <span className="material-symbols-outlined animate-spin text-sm">rotate_right</span>
                                        同步指标中...
                                    </>
                                ) : (
                                    <>
                                        <span className="material-symbols-outlined text-sm">monitoring</span>
                                        同步复核指标
                                    </>
                                )}
                            </button>
                            <button
                                onClick={handleDataClean}
                                disabled={isCleaning || !currentUserId}
                                className="w-full bg-red-500/10 text-red-400 py-3 rounded-xl font-bold mt-2 border border-red-500/20 hover:bg-red-500/20 transition-colors font-serif tracking-wide flex items-center justify-center gap-2 disabled:opacity-50 disabled:grayscale"
                            >
                                {isCleaning ? (
                                    <>
                                        <span className="material-symbols-outlined animate-spin text-sm">rotate_right</span>
                                        清理中...
                                    </>
                                ) : '清理过期缓存'}
                            </button>
                        </div>
                    </Modal>
                );
            case 'OFFLINE_QUEUE':
                return (
                    <Modal
                        title="离线同步队列"
                        onClose={() => !queueActionClientId && !intakeDraftActionClientId && setActiveModal(null)}
                        maxWidthClass="max-w-md max-h-[86vh] overflow-y-auto"
                    >
                        <div className="space-y-4">
                            <div className="grid grid-cols-3 gap-2">
                                <div className="rounded-xl border border-white/5 bg-black/20 px-3 py-2 text-center">
                                    <p className="text-[10px] text-slate-500 font-serif font-bold tracking-wide">待同步</p>
                                    <p className="mt-1 text-lg text-primary font-serif font-bold">{cacheStats?.pendingCount ?? 0}</p>
                                </div>
                                <div className="rounded-xl border border-white/5 bg-black/20 px-3 py-2 text-center">
                                    <p className="text-[10px] text-slate-500 font-serif font-bold tracking-wide">失败</p>
                                    <p className="mt-1 text-lg text-red-200 font-serif font-bold">{cacheStats?.failedCount ?? 0}</p>
                                </div>
                                <div className="rounded-xl border border-white/5 bg-black/20 px-3 py-2 text-center">
                                    <p className="text-[10px] text-slate-500 font-serif font-bold tracking-wide">冲突</p>
                                    <p className="mt-1 text-lg text-amber-100 font-serif font-bold">{cacheStats?.conflictCount ?? 0}</p>
                                </div>
                            </div>

                            {queueNotice && (
                                <p className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-slate-200 leading-relaxed font-serif tracking-wide">
                                    {queueNotice}
                                </p>
                            )}

                            <button
                                onClick={handleRetryOfflineSync}
                                disabled={isSyncingOffline || !currentUserId || offlineQueueItems.length === 0}
                                className="w-full bg-primary/10 text-primary py-3 rounded-xl font-bold border border-primary/20 hover:bg-primary/20 transition-colors font-serif tracking-wide flex items-center justify-center gap-2 disabled:opacity-50"
                            >
                                <span className={`material-symbols-outlined text-sm ${isSyncingOffline ? 'animate-spin' : ''}`}>
                                    {isSyncingOffline ? 'rotate_right' : 'sync'}
                                </span>
                                {isSyncingOffline ? '同步中...' : '重试全部待处理项'}
                            </button>

                            <div className="rounded-2xl border border-amber-300/10 bg-amber-500/5 p-3.5 space-y-3">
                                <div className="flex items-start justify-between gap-3">
                                    <div>
                                        <p className="text-sm text-white font-serif font-bold tracking-wide">候选复核</p>
                                        <p className="mt-1 text-[11px] text-slate-500 font-serif leading-relaxed">
                                            只显示本地候选数量、来源和风险计数；食物名、备注和健康文本仍留在本机候选草稿内。
                                        </p>
                                    </div>
                                    <span className="rounded-full border border-amber-300/20 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-100 font-serif font-bold tracking-wide">
                                        {intakeDraftQueueItems.length}
                                    </span>
                                </div>

                                {intakeDraftQueueItems.length === 0 ? (
                                    <div className="rounded-xl border border-dashed border-white/10 py-5 text-center">
                                        <p className="text-xs text-slate-500 font-serif font-bold tracking-wide">当前没有待复核候选</p>
                                    </div>
                                ) : (
                                    <div className="space-y-2">
                                        {intakeDraftQueueItems.map(draft => {
                                            const isBusy = intakeDraftActionClientId === draft.clientId;
                                            const sourceLabel = sourceLabelMap[draft.source || 'unknown'] || '未知';
                                            const updatedAt = draft.updatedAt.toLocaleString('zh-CN', { hour12: false });
                                            const riskCount = draft.highRiskCount + draft.hardBlockCount;
                                            return (
                                                <div key={draft.clientId} className="rounded-xl border border-white/10 bg-black/20 p-3 space-y-2">
                                                    <div className="flex items-start justify-between gap-3">
                                                        <div className="min-w-0">
                                                            <div className="flex flex-wrap items-center gap-1.5">
                                                                <span className={`rounded border px-1.5 py-0.5 text-[10px] font-serif font-bold tracking-wide ${intakeReviewStatusClassMap[draft.status]}`}>
                                                                    {intakeReviewStatusLabelMap[draft.status]}
                                                                </span>
                                                                <span className="rounded border border-white/10 bg-white/5 px-1.5 py-0.5 text-[10px] text-slate-300 font-serif font-bold tracking-wide">
                                                                    {sourceLabel}
                                                                </span>
                                                            </div>
                                                            <p className="mt-2 text-[11px] text-slate-400 font-serif leading-relaxed">
                                                                {draft.recordDate} · 更新 {updatedAt}
                                                            </p>
                                                        </div>
                                                        <div className="shrink-0 text-right">
                                                            <p className="text-sm text-white font-serif font-bold">{draft.candidateCount}</p>
                                                            <p className="text-[10px] text-slate-500 font-serif">候选</p>
                                                        </div>
                                                    </div>
                                                    <div className="grid grid-cols-3 gap-2 text-center">
                                                        <div className="rounded-lg border border-white/5 bg-white/[0.03] px-2 py-1.5">
                                                            <p className="text-[10px] text-slate-500 font-serif font-bold">低置信度</p>
                                                            <p className="text-xs text-slate-200 font-serif font-bold">{draft.lowConfidenceCount}</p>
                                                        </div>
                                                        <div className="rounded-lg border border-white/5 bg-white/[0.03] px-2 py-1.5">
                                                            <p className="text-[10px] text-slate-500 font-serif font-bold">风险候选</p>
                                                            <p className="text-xs text-amber-100 font-serif font-bold">{riskCount}</p>
                                                        </div>
                                                        <div className="rounded-lg border border-white/5 bg-white/[0.03] px-2 py-1.5">
                                                            <p className="text-[10px] text-slate-500 font-serif font-bold">AVOID</p>
                                                            <p className="text-xs text-red-200 font-serif font-bold">{draft.hardBlockCount}</p>
                                                        </div>
                                                    </div>
                                                    <div className="grid grid-cols-2 gap-2">
                                                        <button
                                                            onClick={handleOpenIntakeReviewDesk}
                                                            disabled={isBusy}
                                                            className="h-9 rounded-lg border border-primary/20 bg-primary/10 text-[11px] text-primary font-serif font-bold tracking-wide hover:bg-primary/20 disabled:opacity-50 flex items-center justify-center gap-1"
                                                        >
                                                            <span className="material-symbols-outlined text-[15px]">fact_check</span>
                                                            去复核台
                                                        </button>
                                                        <button
                                                            onClick={() => void handleDiscardIntakeDraftItem(draft)}
                                                            disabled={isBusy}
                                                            className="h-9 rounded-lg border border-red-500/20 bg-red-500/10 text-[11px] text-red-200 font-serif font-bold tracking-wide hover:bg-red-500/20 disabled:opacity-50 flex items-center justify-center gap-1"
                                                        >
                                                            <span className={`material-symbols-outlined text-[15px] ${isBusy ? 'animate-spin' : ''}`}>
                                                                {isBusy ? 'rotate_right' : 'delete'}
                                                            </span>
                                                            丢弃候选
                                                        </button>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>

                            <div className="space-y-3">
                                {offlineQueueItems.length === 0 ? (
                                    <div className="rounded-2xl border border-dashed border-white/10 py-8 text-center">
                                        <p className="text-xs text-slate-500 font-serif font-bold tracking-wide">当前没有待处理的离线记录</p>
                                    </div>
                                ) : offlineQueueItems.map(item => {
                                    const isBusy = queueActionClientId === item.clientId;
                                    const statusClass = queueStatusClassMap[item.syncStatus];
                                    const statusLabel = queueStatusLabelMap[item.syncStatus];
                                    const updatedAt = item.updatedAt.toLocaleString('zh-CN', { hour12: false });
                                    const sourceLabel = sourceLabelMap[item.source || 'manual'] || '记录';
                                    const ingredients = Array.isArray(item.recognitionMeta?.ingredients)
                                        ? item.recognitionMeta.ingredients.filter(value => typeof value === 'string').slice(0, 3).join('、')
                                        : '';
                                    return (
                                        <div key={item.clientId} className="rounded-2xl border border-white/10 bg-white/[0.03] p-3.5 space-y-3">
                                            <div className="flex items-start justify-between gap-3">
                                                <div className="min-w-0">
                                                    <p className="text-white text-sm font-serif font-bold tracking-wide break-words">
                                                        {item.name || '未命名记录'}
                                                    </p>
                                                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                                                        <span className={`rounded border px-1.5 py-0.5 text-[10px] font-serif font-bold tracking-wide ${statusClass}`}>
                                                            {statusLabel}
                                                        </span>
                                                        <span className="rounded border border-white/10 bg-white/5 px-1.5 py-0.5 text-[10px] text-slate-300 font-serif font-bold tracking-wide">
                                                            {sourceLabel}
                                                        </span>
                                                        <span className="rounded border border-white/10 bg-white/5 px-1.5 py-0.5 text-[10px] text-slate-400 font-serif font-bold tracking-wide">
                                                            {mealTypeLabelMap[item.mealType]}
                                                        </span>
                                                    </div>
                                                </div>
                                                <div className="shrink-0 text-right">
                                                    <p className="text-xs text-slate-300 font-serif font-bold">{Math.round(item.calories || 0)} kcal</p>
                                                    <p className="mt-1 text-[10px] text-slate-500 font-serif">{item.recordDate}</p>
                                                </div>
                                            </div>

                                            <div className="space-y-1 text-[11px] text-slate-400 font-serif leading-relaxed">
                                                <p>份量：{item.portion || '1份'} · 更新：{updatedAt}</p>
                                                {ingredients && <p>候选食材：{ingredients}</p>}
                                                {item.lastSyncError && <p className="text-amber-100">原因：{item.lastSyncError}</p>}
                                            </div>

                                            <div className="grid grid-cols-3 gap-2">
                                                <button
                                                    onClick={() => void handleOpenQueueItemInLog(item)}
                                                    disabled={isBusy}
                                                    className="h-9 rounded-lg border border-white/10 bg-white/5 text-[11px] text-slate-200 font-serif font-bold tracking-wide hover:bg-white/10 disabled:opacity-50 flex items-center justify-center gap-1"
                                                >
                                                    <span className="material-symbols-outlined text-[15px]">edit</span>
                                                    日志编辑
                                                </button>
                                                <button
                                                    onClick={() => void handleRetryOfflineItem(item)}
                                                    disabled={isBusy || isSyncingOffline}
                                                    className="h-9 rounded-lg border border-primary/20 bg-primary/10 text-[11px] text-primary font-serif font-bold tracking-wide hover:bg-primary/20 disabled:opacity-50 flex items-center justify-center gap-1"
                                                >
                                                    <span className={`material-symbols-outlined text-[15px] ${isBusy ? 'animate-spin' : ''}`}>
                                                        {isBusy ? 'rotate_right' : 'sync'}
                                                    </span>
                                                    {item.syncStatus === 'PENDING' ? '同步' : '重试'}
                                                </button>
                                                <button
                                                    onClick={() => void handleDiscardOfflineItem(item)}
                                                    disabled={isBusy}
                                                    className="h-9 rounded-lg border border-red-500/20 bg-red-500/10 text-[11px] text-red-200 font-serif font-bold tracking-wide hover:bg-red-500/20 disabled:opacity-50 flex items-center justify-center gap-1"
                                                >
                                                    <span className="material-symbols-outlined text-[15px]">delete</span>
                                                    丢弃
                                                </button>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </Modal>
                );
            case 'ABOUT':
                return (
                    <Modal title={`关于${APP_DISPLAY_NAME}`} onClose={() => setActiveModal(null)}>
                        <div className="flex flex-col items-center justify-center py-4">
                            <div className="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center border border-primary/20 mb-3 shadow-[0_0_20px_rgba(17,196,212,0.15)]">
                                <svg className="w-8 h-8 drop-shadow-lg" fill="none" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                    <path d="M12 2L2 19L12 14L12 2Z" fill="#11c4d4" fillOpacity="0.9"></path>
                                    <path d="M12 2L22 19L12 14L12 2Z" fill="#7aa0a0" fillOpacity="0.9"></path>
                                </svg>
                            </div>
                            <h4 className="text-white text-lg font-display font-bold">PRISM</h4>
                            <p className="text-white/40 text-xs font-serif tracking-widest mt-1">版本 {appVersionLabel}</p>
                        </div>
                        <div className="space-y-1 border-t border-white/5 pt-2">
                            {([
                                ['terms', '用户协议'],
                                ['privacy', '隐私政策'],
                                ['ai_use', 'AI 使用说明'],
                                ['health_disclaimer', '健康免责声明'],
                                ['data_rights', '数据导出与删除说明'],
                            ] as [ComplianceDocumentKey, string][]).map(([key, label]) => (
                                <button
                                    key={key}
                                    type="button"
                                    onClick={() => {
                                        onOpenCompliance?.(key);
                                        setActiveModal(null);
                                    }}
                                    className="w-full py-3 flex items-center justify-between text-sm text-white/80 hover:text-white px-2 rounded-lg font-serif font-bold tracking-wide"
                                >
                                    <span>{label}</span>
                                    <span className="material-symbols-outlined text-white/20 text-lg">chevron_right</span>
                                </button>
                            ))}
                        </div>
                    </Modal>
                );
            case 'DELETE_DATA_CONFIRM':
                return (
                    <Modal title="删除云端个人内容" onClose={() => setActiveModal(null)}>
                        <div className="space-y-4">
                            <p className="text-slate-300 text-sm leading-relaxed font-serif tracking-wide">
                                这会删除云端饮食记录、健康档案、聊天内容和消息提醒，并保留必要的安全审计记录。建议先导出数据。
                            </p>
                            {dataRightsNotice && (
                                <p className="text-xs text-amber-200 bg-amber-500/10 border border-amber-500/20 rounded-lg p-2 font-serif tracking-wide">
                                    {dataRightsNotice}
                                </p>
                            )}
                            <div className="flex gap-3">
                                <button
                                    onClick={() => setActiveModal(null)}
                                    className="flex-1 py-3 rounded-xl border border-white/10 text-slate-400 font-bold text-sm hover:bg-white/5 transition-colors font-serif tracking-wide"
                                >
                                    取消
                                </button>
                                <button
                                    onClick={handleDeleteData}
                                    disabled={dataRightsLoading === 'delete-data'}
                                    className="flex-1 py-3 rounded-xl bg-red-500/20 border border-red-500/30 text-red-300 font-bold text-sm hover:bg-red-500/30 transition-colors font-serif tracking-wide disabled:opacity-50"
                                >
                                    {dataRightsLoading === 'delete-data' ? '删除中...' : '确认删除'}
                                </button>
                            </div>
                        </div>
                    </Modal>
                );
            case 'DELETE_ACCOUNT_CONFIRM':
                return (
                    <Modal title="注销账户" onClose={() => setActiveModal(null)}>
                        <div className="space-y-4">
                            <p className="text-slate-300 text-sm leading-relaxed font-serif tracking-wide">
                                注销将删除你的云端个人内容，并关闭当前账号。完成后你将无法再使用原手机号登录。
                            </p>
                            {dataRightsNotice && (
                                <p className="text-xs text-amber-200 bg-amber-500/10 border border-amber-500/20 rounded-lg p-2 font-serif tracking-wide">
                                    {dataRightsNotice}
                                </p>
                            )}
                            <div className="flex gap-3">
                                <button
                                    onClick={() => setActiveModal(null)}
                                    className="flex-1 py-3 rounded-xl border border-white/10 text-slate-400 font-bold text-sm hover:bg-white/5 transition-colors font-serif tracking-wide"
                                >
                                    取消
                                </button>
                                <button
                                    onClick={handleDeleteAccount}
                                    disabled={dataRightsLoading === 'delete-account'}
                                    className="flex-1 py-3 rounded-xl bg-ochre/20 border border-ochre/30 text-ochre font-bold text-sm hover:bg-ochre/30 transition-colors font-serif tracking-wide disabled:opacity-50"
                                >
                                    {dataRightsLoading === 'delete-account' ? '注销中...' : '确认注销'}
                                </button>
                            </div>
                        </div>
                    </Modal>
                );
            case 'DATA_RIGHTS_NOTICE':
                return (
                    <Modal title="提示" onClose={() => setActiveModal(null)}>
                        <div className="space-y-4">
                            <p className="text-slate-300 text-sm leading-relaxed font-serif tracking-wide">
                                {dataRightsNotice || '操作已完成。'}
                            </p>
                            <button
                                onClick={() => setActiveModal(null)}
                                className="w-full py-3 rounded-xl bg-white/10 hover:bg-white/20 text-white font-bold text-sm transition-colors font-serif tracking-wide"
                            >
                                我知道了
                            </button>
                        </div>
                    </Modal>
                );
            case 'LOGOUT_CONFIRM':
                return (
                    <Modal title="退出登录" onClose={() => setActiveModal(null)}>
                        <div className="text-center py-2">
                            <p className="text-slate-300 text-sm leading-relaxed mb-6 font-serif tracking-wide">
                                确定要退出当前账号吗？<br />
                                本地敏感缓存会被清理，后端会撤销当前设备会话。
                            </p>
                            {offlineRiskCount > 0 && (
                                <div className="mb-5 rounded-xl border border-amber-400/25 bg-amber-500/10 p-3 text-left">
                                    <p className="text-xs text-amber-100 leading-relaxed font-serif tracking-wide">
                                        当前还有 {offlineRiskCount} 条离线记录未完成同步：
                                        待同步 {cacheStats?.pendingCount ?? 0} / 失败 {cacheStats?.failedCount ?? 0} / 冲突 {cacheStats?.conflictCount ?? 0} / 待复核候选 {cacheStats?.pendingReviewCount ?? 0}。
                                        确认退出会清理本账号本地队列；候选复核台中的低置信度或风险候选不会自动写入日志，请先重试、复核或进入队列处理。
                                    </p>
                                    <div className="mt-3 grid grid-cols-2 gap-2">
                                        <button
                                            type="button"
                                            onClick={() => {
                                                setQueueNotice(null);
                                                setActiveModal('OFFLINE_QUEUE');
                                            }}
                                            className="h-9 rounded-lg border border-white/10 bg-white/5 text-[11px] text-slate-100 font-serif font-bold tracking-wide hover:bg-white/10"
                                        >
                                            查看队列
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => void handleRetryOfflineSync()}
                                            disabled={isSyncingOffline}
                                            className="h-9 rounded-lg border border-primary/20 bg-primary/10 text-[11px] text-primary font-serif font-bold tracking-wide hover:bg-primary/20 disabled:opacity-50"
                                        >
                                            {isSyncingOffline ? '同步中...' : '先重试同步'}
                                        </button>
                                    </div>
                                </div>
                            )}
                            <div className="flex gap-3">
                                <button
                                    onClick={() => setActiveModal(null)}
                                    className="flex-1 py-3 rounded-xl border border-white/10 text-slate-400 font-bold text-sm hover:bg-white/5 transition-colors font-serif tracking-wide"
                                >
                                    取消
                                </button>
                                <button
                                    onClick={handleLogout}
                                    className="flex-1 py-3 rounded-xl bg-ochre/20 border border-ochre/30 text-ochre font-bold text-sm hover:bg-ochre/30 transition-colors font-serif tracking-wide"
                                >
                                    {offlineRiskCount > 0 ? '仍要退出并清理本地队列' : '确认退出'}
                                </button>
                            </div>
                        </div>
                    </Modal>
                );
            default:
                return null;
        }
    };

    return (
        <div className="flex flex-col w-full h-full">
            <div className="relative z-10 sticky top-0 bg-[#0c1416]/95 backdrop-blur-md border-b border-white/5 p-4 flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <button
                        onClick={() => onViewChange(View.HOME)}
                        className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/5 transition-colors"
                    >
                        <span className="material-symbols-outlined text-white">arrow_back</span>
                    </button>
                    <div className="flex flex-col">
                        <h1 className="text-white text-lg font-bold font-serif leading-none tracking-wide">设置</h1>
                        <span className="text-[10px] text-primary/50 font-display tracking-[0.2em] mt-1">SETTINGS</span>
                    </div>
                </div>

                <button
                    onClick={() => onViewChange(View.PROFILE)}
                    className="w-10 h-10 rounded-full border border-mineral/50 p-0.5 overflow-hidden"
                >
                    <img
                        src={userProfile.avatarUrl || '/images/user-avatar.png'}
                        alt="User"
                        className="w-full h-full object-cover rounded-full"
                    />
                </button>
            </div>

            <div className="relative z-10 flex-1 overflow-y-auto p-4 pb-24 space-y-6">
                <div>
                    <SectionTitle title="个人资料" />
                    <div className="bg-[#131b1d]/80 backdrop-blur-sm border border-mineral/20 rounded-xl px-4 overflow-hidden">
                        <ListItem
                            icon="accessibility_new"
                            label="身体参数"
                            value={`${userProfile.height}cm / ${userProfile.weight}kg / ${userProfile.age}岁`}
                            onClick={openBodyParamsModal}
                        />
                        <ListItem
                            icon="wc"
                            label="性别"
                            value={userProfile.gender === 'MALE' ? '男' : '女'}
                            onClick={openGenderModal}
                        />
                        <ListItem
                            icon="medical_services"
                            label="健康档案管理"
                            value="慢病 / 过敏"
                            onClick={() => onViewChange(View.MEDICAL_ARCHIVES)}
                        />
                        <ListItem
                            icon="monitor_heart"
                            label="健康指标"
                            value="体重 / 血压 / 血糖"
                            onClick={() => onViewChange(View.HEALTH_METRICS)}
                        />
                    </div>
                </div>

                <div>
                    <SectionTitle title="AI 助手配置" />
                    <div className="bg-[#131b1d]/80 backdrop-blur-sm border border-mineral/20 rounded-xl px-4 overflow-hidden">
                        <ListItem
                            icon="psychology"
                            label="全局助手偏好"
                            value={assistantModeLabelMap[assistantMode]}
                            onClick={openAssistantModeModal}
                        />
                        <ListItem
                            icon="tune"
                            label="干预强度"
                            value={assistantIntensityLabelMap[assistantIntensity]}
                            onClick={openAssistantIntensityModal}
                        />
                    </div>
                </div>

                <div>
                    <SectionTitle title="数据与设备" />
                    <div className="bg-[#131b1d]/80 backdrop-blur-sm border border-mineral/20 rounded-xl px-4 overflow-hidden">
                        <ListItem
                            icon="workspace_premium"
                            label="订阅与权益"
                            value="FREE / PRO / COACH · mock"
                            onClick={() => onViewChange(View.BILLING)}
                        />
                        <ListItem
                            icon="download"
                            label="导出个人数据"
                            value="JSON"
                            onClick={handleExportData}
                        />
                        <ListItem
                            icon="summarize"
                            label="导出 7 天报告"
                            value={dataRightsLoading === 'weekly-report' ? '生成中...' : 'JSON / CSV'}
                            onClick={() => void handleExportReport('weekly')}
                        />
                        <ListItem
                            icon="calendar_month"
                            label="导出本月报告"
                            value={dataRightsLoading === 'monthly-report' ? '生成中...' : 'JSON / CSV'}
                            onClick={() => void handleExportReport('monthly')}
                        />
                        <ListItem
                            icon="analytics"
                            label="报告中心"
                            value="周报 / 月报"
                            onClick={() => onViewChange(View.REPORTS)}
                        />
                        <ListItem
                            icon="admin_panel_settings"
                            label="运营后台"
                            value="管理员"
                            onClick={() => onViewChange(View.ADMIN)}
                        />
                        <ListItem
                            icon="cleaning_services"
                            label="本地离线缓存"
                            value={cacheStats ? `${cacheStats.estimatedSizeKB} KB · 待复核 ${cacheStats.intakeDraftCount}` : '无本地缓存'}
                            onClick={() => {
                                void loadCacheStats();
                                setActiveModal('CLEAN_DATA');
                            }}
                        />
                        <ListItem
                            icon="sync"
                            label="离线同步队列"
                            value={
                                cacheStats
                                    ? `待同步 ${cacheStats.pendingCount} / 失败 ${cacheStats.failedCount} / 冲突 ${cacheStats.conflictCount} / 待复核 ${cacheStats.pendingReviewCount}`
                                    : '无本地队列'
                            }
                            action={
                                <button
                                    type="button"
                                    onClick={(event) => {
                                        event.stopPropagation();
                                        void handleRetryOfflineSync();
                                    }}
                                    disabled={!currentUserId || isSyncingOffline}
                                    className="rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-[10px] font-serif font-bold tracking-wide text-primary transition-colors hover:bg-primary/15 disabled:opacity-50"
                                >
                                    {isSyncingOffline ? '同步中' : '立即重试'}
                                </button>
                            }
                            onClick={() => {
                                setQueueNotice(null);
                                void loadCacheStats();
                                setActiveModal('OFFLINE_QUEUE');
                            }}
                        />
                        <ListItem
                            icon="delete_forever"
                            label="删除云端个人内容"
                            value="云端清理"
                            onClick={() => {
                                setDataRightsNotice(null);
                                setActiveModal('DELETE_DATA_CONFIRM');
                            }}
                        />
                        <ListItem
                            icon="gavel"
                            label="注销账户"
                            value="关闭账号"
                            onClick={() => {
                                setDataRightsNotice(null);
                                setActiveModal('DELETE_ACCOUNT_CONFIRM');
                            }}
                        />
                    </div>
                </div>

                {currentUserId && (
                    <div>
                        <div className="mb-3 flex items-center justify-between px-1">
                            <SectionTitle title="登录设备" />
                            <button
                                type="button"
                                onClick={() => {
                                    setSessionNotice(null);
                                    void loadCacheStats();
                                }}
                                className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[10px] font-serif font-bold tracking-wide text-slate-300 hover:bg-white/10"
                            >
                                刷新
                            </button>
                        </div>
                        <div className="space-y-3">
                            {sessionNotice && (
                                <p className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-slate-200 leading-relaxed font-serif tracking-wide">
                                    {sessionNotice}
                                </p>
                            )}
                            {deviceSessions.length === 0 ? (
                                <div className="rounded-xl border border-white/10 bg-[#131b1d]/80 px-4 py-5 text-center">
                                    <p className="text-xs text-slate-500 font-serif font-bold tracking-wide">暂无可显示的设备会话</p>
                                </div>
                            ) : deviceSessions.map(session => {
                                const isBusy = sessionActionId === session.session_id;
                                const deviceLabel = formatDeviceSessionLabel(session.device_label);
                                return (
                                    <div key={session.session_id} className="rounded-xl border border-mineral/20 bg-[#131b1d]/80 p-4">
                                        <div className="flex items-start justify-between gap-3">
                                            <div className="min-w-0">
                                                <p className="truncate text-sm text-white font-serif font-bold tracking-wide">
                                                    {deviceLabel}
                                                </p>
                                                <p className="mt-1 text-[11px] text-slate-500 font-serif tracking-wide">
                                                    最近活动 {formatSessionTime(session.last_seen_at)}
                                                </p>
                                            </div>
                                            <span className={`shrink-0 rounded-full border px-2 py-1 text-[10px] font-serif font-bold tracking-wide ${
                                                session.is_revoked
                                                    ? 'border-red-400/20 bg-red-500/10 text-red-200'
                                                    : session.is_current
                                                        ? 'border-primary/20 bg-primary/10 text-primary'
                                                        : 'border-emerald-300/20 bg-emerald-500/10 text-emerald-200'
                                            }`}>
                                                {session.is_revoked ? '已撤销' : session.is_current ? '当前设备' : '已登录'}
                                            </span>
                                        </div>
                                        <div className="mt-3 flex items-center justify-between gap-3">
                                            <p className="min-w-0 truncate text-[10px] text-slate-600 font-serif tracking-wide">
                                                到期 {formatSessionTime(session.expires_at)}
                                            </p>
                                            {!session.is_current && !session.is_revoked && (
                                                <button
                                                    type="button"
                                                    onClick={() => void handleRevokeDeviceSession(session)}
                                                    disabled={isBusy}
                                                    className="shrink-0 rounded-full border border-red-500/20 bg-red-500/10 px-3 py-1.5 text-[10px] font-serif font-bold tracking-wide text-red-200 hover:bg-red-500/20 disabled:opacity-50"
                                                >
                                                    {isBusy ? '撤销中...' : '撤销会话'}
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}

                <div>
                    <SectionTitle title="通用设置" />
                    <div className="bg-[#131b1d]/80 backdrop-blur-sm border border-mineral/20 rounded-xl px-4 overflow-hidden">
                        <ListItem
                            icon="info"
                            label={`关于${APP_DISPLAY_NAME}`}
                            value={appVersionLabel}
                            onClick={() => setActiveModal('ABOUT')}
                        />
                    </div>
                </div>

                {currentUserId && (
                    <div>
                        <SectionTitle title="同步状态" />
                        <div className="bg-[#131b1d]/80 backdrop-blur-sm border border-mineral/20 rounded-xl px-4 overflow-hidden">
                            <ListItem
                                icon="event_available"
                                label="最近同步"
                                value={lastSyncTime || '暂无'}
                                disabled
                            />
                            <ListItem
                                icon="cloud_sync"
                                label="当前状态"
                                value={syncStatus || 'idle'}
                                action={
                                    <span className="text-[10px] bg-white/5 border border-white/10 px-2 py-0.5 rounded text-white/40 font-serif font-bold tracking-wide">
                                        {cacheStats ? `${cacheStats.pendingCount} pending` : '0 pending'}
                                    </span>
                                }
                                disabled
                            />
                        </div>
                    </div>
                )}

                <div className="pt-4 pb-8">
                    <button
                        onClick={openLogoutConfirm}
                        className="w-full py-3 rounded-xl border border-ochre/50 text-ochre/90 text-sm font-bold tracking-widest hover:bg-ochre/10 active:scale-[0.99] transition-all font-serif flex items-center justify-center gap-2"
                    >
                        <span className="material-symbols-outlined text-lg">logout</span>
                        退出登录
                    </button>
                    <p className="text-center text-[10px] text-slate-600 mt-4 font-display tracking-widest uppercase opacity-50">
                        Prism Metabolic Console
                    </p>
                </div>
            </div>

            {renderModalContent()}
        </div>
    );
};

export default SettingsView;
