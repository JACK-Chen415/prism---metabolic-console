import React, { useEffect, useState } from 'react';
import { View, UserProfile } from '../../types';
import { AuthAPI, TokenManager } from '../../services/api';
import { APP_BUILD, APP_DISPLAY_NAME, APP_VERSION } from '../../constants/app';
import { CacheCleanupService } from '../../services/offline';

interface SettingsViewProps {
    onViewChange: (view: View) => void;
    userProfile: UserProfile;
    currentUserId: number | null;
    onUpdateProfile: (profile: UserProfile) => void;
    onLogout?: () => void;
}

type ModalType =
    | 'BODY_PARAMS'
    | 'GENDER_SELECT'
    | 'CLEAN_DATA'
    | 'ABOUT'
    | 'LOGOUT_CONFIRM'
    | null;

type CacheStats = {
    totalCount: number;
    syncedCount: number;
    pendingCount: number;
    oldestDate: string | null;
    newestDate: string | null;
    estimatedSizeKB: number;
};

interface ModalProps {
    title: string;
    onClose: () => void;
    children: React.ReactNode;
}

const Modal: React.FC<ModalProps> = ({ title, onClose, children }) => (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
        <div className="bg-[#131b1d] border border-white/10 w-full max-w-xs rounded-2xl p-5 shadow-2xl relative">
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

const DisabledBadge = ({ label = '未开放' }: { label?: string }) => (
    <span className="text-[10px] bg-white/5 border border-white/10 px-2 py-0.5 rounded text-white/40 font-serif font-bold tracking-wide">
        {label}
    </span>
);

const SettingsView: React.FC<SettingsViewProps> = ({ onViewChange, userProfile, currentUserId, onUpdateProfile, onLogout }) => {
    const [editProfile, setEditProfile] = useState<UserProfile>(userProfile);
    const [activeModal, setActiveModal] = useState<ModalType>(null);
    const [isCleaning, setIsCleaning] = useState(false);
    const [cacheStats, setCacheStats] = useState<CacheStats | null>(null);

    const appVersionLabel = `v${APP_VERSION}${APP_BUILD !== 'local' ? ` (${APP_BUILD})` : ''}`;

    const loadCacheStats = async () => {
        if (!currentUserId) {
            setCacheStats(null);
            return;
        }
        try {
            setCacheStats(await CacheCleanupService.getStats(currentUserId));
        } catch (error) {
            console.error('读取缓存统计失败:', error);
            setCacheStats(null);
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
        setActiveModal('BODY_PARAMS');
    };

    const openGenderModal = () => {
        setEditProfile(userProfile);
        setActiveModal('GENDER_SELECT');
    };

    const saveProfileChanges = async () => {
        onUpdateProfile(editProfile);
        setActiveModal(null);

        if (TokenManager.isAuthenticated()) {
            try {
                await AuthAPI.updateProfile({
                    gender: editProfile.gender,
                    age: editProfile.age,
                    height: editProfile.height,
                    weight: editProfile.weight
                });
            } catch (error) {
                console.error('保存个人资料失败:', error);
            }
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

    const handleLogout = () => {
        if (onLogout) {
            onLogout();
        } else {
            TokenManager.clearTokens();
            onViewChange(View.LOGIN);
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

                            <button
                                onClick={saveProfileChanges}
                                className="w-full bg-primary/20 text-primary py-3 rounded-xl font-bold mt-2 border border-primary/20 hover:bg-primary/30 transition-colors font-serif tracking-wide"
                            >
                                保存
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
                            <button
                                onClick={saveProfileChanges}
                                className="w-full bg-primary/20 text-primary py-3 rounded-xl font-bold mt-2 border border-primary/20 hover:bg-primary/30 transition-colors font-serif tracking-wide"
                            >
                                保存
                            </button>
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
                                <p className="text-[11px] text-slate-500 leading-relaxed pt-1">
                                    清理只会删除本账号已同步且超过 30 天的本地离线缓存，不会删除服务器饮食记录或 AI 对话。
                                </p>
                            </div>
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
                            <div className="w-full py-3 flex items-center justify-between text-sm text-slate-500 px-2 rounded-lg font-serif font-bold tracking-wide">
                                <span>用户协议</span>
                                <DisabledBadge label="未接入" />
                            </div>
                            <div className="w-full py-3 flex items-center justify-between text-sm text-slate-500 px-2 rounded-lg font-serif font-bold tracking-wide">
                                <span>隐私政策</span>
                                <DisabledBadge label="未接入" />
                            </div>
                            <div className="w-full py-3 flex items-center justify-between text-sm text-slate-500 px-2 rounded-lg font-serif font-bold tracking-wide">
                                <span>检查更新</span>
                                <DisabledBadge label="未接入" />
                            </div>
                        </div>
                    </Modal>
                );
            case 'LOGOUT_CONFIRM':
                return (
                    <Modal title="退出登录" onClose={() => setActiveModal(null)}>
                        <div className="text-center py-2">
                            <p className="text-slate-300 text-sm leading-relaxed mb-6 font-serif tracking-wide">
                                确定要退出当前账号吗？<br />
                                本地敏感缓存会被清理，未同步的数据可能会丢失。
                            </p>
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
                                    确认退出
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
                    </div>
                </div>

                <div>
                    <SectionTitle title="AI 助手配置" />
                    <div className="bg-[#131b1d]/80 backdrop-blur-sm border border-mineral/20 rounded-xl px-4 overflow-hidden">
                        <ListItem
                            icon="psychology"
                            label="全局助手偏好"
                            value="请在 AI 页面临时切换"
                            action={<DisabledBadge />}
                            disabled
                        />
                        <ListItem
                            icon="tune"
                            label="干预强度"
                            value="待后端规则接入"
                            action={<DisabledBadge />}
                            disabled
                        />
                    </div>
                </div>

                <div>
                    <SectionTitle title="数据与设备" />
                    <div className="bg-[#131b1d]/80 backdrop-blur-sm border border-mineral/20 rounded-xl px-4 overflow-hidden">
                        <ListItem
                            icon="download"
                            label="健康报表导出"
                            value="PDF / CSV"
                            action={<DisabledBadge />}
                            disabled
                        />
                        <ListItem
                            icon="cleaning_services"
                            label="本地离线缓存"
                            value={cacheStats ? `${cacheStats.estimatedSizeKB} KB` : '无本地缓存'}
                            onClick={() => {
                                void loadCacheStats();
                                setActiveModal('CLEAN_DATA');
                            }}
                        />
                    </div>
                </div>

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

                <div className="pt-4 pb-8">
                    <button
                        onClick={() => setActiveModal('LOGOUT_CONFIRM')}
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
