import React, { useState } from 'react';
import { View, UserProfile } from '../../types';
import { AuthAPI, TokenManager } from '../../services/api';

interface SettingsViewProps {
    onViewChange: (view: View) => void;
    userProfile: UserProfile;
    onUpdateProfile: (profile: UserProfile) => void;
    onLogout?: () => void;
}

type ModalType =
    | 'BODY_PARAMS'
    | 'GENDER_SELECT'
    | 'HEALTH_TAGS'
    | 'RESTRICTIONS'
    | 'INTERVENTION'
    | 'EXPORT_DATA'
    | 'CLEAN_DATA'
    | 'ABOUT'
    | 'LOGOUT_CONFIRM'
    | null;

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

const SettingsView: React.FC<SettingsViewProps> = ({ onViewChange, userProfile, onUpdateProfile, onLogout }) => {
    // Config State
    const [aiStyle, setAiStyle] = useState<'strict' | 'gentle'>('strict');

    // Editable Data State (Local buffer for modal editing)
    const [editProfile, setEditProfile] = useState<UserProfile>(userProfile);

    // Other Settings
    const [healthTags, setHealthTags] = useState<string[]>(['高尿酸', '高血压']);
    const [restrictions, setRestrictions] = useState('花生 · 海鲜');
    const [intervention, setIntervention] = useState('标准');

    // System Data State
    const [storageSize, setStorageSize] = useState('245 MB');
    const [isCleaning, setIsCleaning] = useState(false);
    const [exportFormat, setExportFormat] = useState<'PDF' | 'CSV'>('PDF');
    const [exportRange, setExportRange] = useState('30DAYS');
    const [isExporting, setIsExporting] = useState(false);

    // Modal State
    const [activeModal, setActiveModal] = useState<ModalType>(null);

    // Constants
    const AVAILABLE_TAGS = ['高尿酸', '高血压', '糖尿病', '高血脂', '乳糖不耐受', '麸质过敏', '脂肪肝'];
    const INTENSITY_OPTIONS = ['轻度', '标准', '频繁'];

    // Initialize edit buffer when opening body params modal
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

        // 同步到后端
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

    const SectionTitle = ({ title }: { title: string }) => (
        <h3 className="text-white/60 text-xs font-serif font-bold tracking-widest uppercase mb-3 px-1">{title}</h3>
    );

    const ListItem = ({
        icon,
        label,
        value,
        action,
        onClick
    }: {
        icon: string;
        label: string;
        value?: string | React.ReactNode;
        action?: React.ReactNode;
        onClick?: () => void;
    }) => (
        <div
            onClick={onClick}
            className={`flex items-center justify-between py-3 border-b border-white/5 last:border-0 ${onClick ? 'cursor-pointer active:bg-white/5 transition-colors' : ''}`}
        >
            <div className="flex items-center gap-3">
                <span className="material-symbols-outlined text-white/40 text-lg">{icon}</span>
                <span className="text-white/90 text-sm font-bold tracking-wide font-serif">{label}</span>
            </div>
            <div className="flex items-center gap-2">
                {value && <span className="text-white/40 text-xs font-serif font-bold tracking-wide max-w-[150px] truncate text-right">{value}</span>}
                {action || <span className="material-symbols-outlined text-white/20 text-lg">chevron_right</span>}
            </div>
        </div>
    );

    const handleDataClean = () => {
        setIsCleaning(true);
        setTimeout(() => {
            setStorageSize('12 KB'); // Reset to minimal size
            setIsCleaning(false);
            setActiveModal(null);
        }, 1500);
    };

    const handleExport = () => {
        setIsExporting(true);
        setTimeout(() => {
            setIsExporting(false);
            setActiveModal(null);
        }, 2000);
    };

    const handleLogout = () => {
        if (onLogout) {
            onLogout();
        } else {
            TokenManager.clearTokens();
            onViewChange(View.LOGIN);
        }
    };

    // Render specific modal content based on activeModal state
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
            case 'HEALTH_TAGS':
                return (
                    <Modal title="健康状态标签" onClose={() => setActiveModal(null)}>
                        <div className="flex flex-wrap gap-2 mb-6">
                            {AVAILABLE_TAGS.map(tag => {
                                const isSelected = healthTags.includes(tag);
                                return (
                                    <button
                                        key={tag}
                                        onClick={() => {
                                            if (isSelected) {
                                                setHealthTags(healthTags.filter(t => t !== tag));
                                            } else {
                                                setHealthTags([...healthTags, tag]);
                                            }
                                        }}
                                        className={`px-3 py-1.5 rounded-full text-xs font-serif font-bold tracking-wide transition-all duration-200 ${isSelected ? 'bg-primary/20 text-primary border border-primary/30' : 'bg-white/5 text-slate-400 border border-transparent hover:bg-white/10'}`}
                                    >
                                        {tag}
                                    </button>
                                );
                            })}
                        </div>
                        <button
                            onClick={() => setActiveModal(null)}
                            className="w-full bg-primary/20 text-primary py-3 rounded-xl font-bold border border-primary/20 hover:bg-primary/30 transition-colors font-serif tracking-wide"
                        >
                            完成
                        </button>
                    </Modal>
                );
            case 'RESTRICTIONS':
                return (
                    <Modal title="饮食避忌" onClose={() => setActiveModal(null)}>
                        <div className="space-y-4">
                            <p className="text-xs text-slate-400 font-serif font-bold tracking-wide">请输入您忌口的食物，如花生、海鲜等。</p>
                            <textarea
                                value={restrictions}
                                onChange={(e) => setRestrictions(e.target.value)}
                                rows={4}
                                className="w-full bg-black/20 border border-white/10 rounded-lg p-3 text-white focus:border-primary/50 outline-none text-sm resize-none font-serif tracking-wide"
                                placeholder="例如：香菜, 羊肉"
                            />
                            <button
                                onClick={() => setActiveModal(null)}
                                className="w-full bg-primary/20 text-primary py-3 rounded-xl font-bold mt-2 border border-primary/20 hover:bg-primary/30 transition-colors font-serif tracking-wide"
                            >
                                保存
                            </button>
                        </div>
                    </Modal>
                );
            case 'INTERVENTION':
                return (
                    <Modal title="干预强度" onClose={() => setActiveModal(null)}>
                        <div className="space-y-2 mb-4">
                            {INTENSITY_OPTIONS.map(opt => (
                                <button
                                    key={opt}
                                    onClick={() => {
                                        setIntervention(opt);
                                        setActiveModal(null);
                                    }}
                                    className={`w-full py-3 px-4 rounded-xl flex items-center justify-between transition-all active:scale-[0.98] ${intervention === opt ? 'bg-primary/10 border border-primary/30' : 'bg-white/5 border border-transparent hover:bg-white/10'}`}
                                >
                                    <span className={`text-sm font-bold font-serif tracking-wide ${intervention === opt ? 'text-primary' : 'text-slate-300'}`}>{opt}</span>
                                    {intervention === opt && <span className="material-symbols-outlined text-primary text-sm">check</span>}
                                </button>
                            ))}
                        </div>
                    </Modal>
                );
            case 'EXPORT_DATA':
                return (
                    <Modal title="导出健康报表" onClose={() => !isExporting && setActiveModal(null)}>
                        <div className="space-y-4">
                            <div>
                                <p className="text-xs text-slate-400 mb-2 font-serif font-bold tracking-wide">选择时间范围</p>
                                <div className="flex gap-2">
                                    <button
                                        onClick={() => setExportRange('7DAYS')}
                                        className={`flex-1 py-2 rounded-lg text-xs font-serif font-bold tracking-wide border ${exportRange === '7DAYS' ? 'bg-primary/10 border-primary text-primary' : 'border-white/10 text-slate-400'}`}
                                    >近7天</button>
                                    <button
                                        onClick={() => setExportRange('30DAYS')}
                                        className={`flex-1 py-2 rounded-lg text-xs font-serif font-bold tracking-wide border ${exportRange === '30DAYS' ? 'bg-primary/10 border-primary text-primary' : 'border-white/10 text-slate-400'}`}
                                    >近30天</button>
                                    <button
                                        onClick={() => setExportRange('ALL')}
                                        className={`flex-1 py-2 rounded-lg text-xs font-serif font-bold tracking-wide border ${exportRange === 'ALL' ? 'bg-primary/10 border-primary text-primary' : 'border-white/10 text-slate-400'}`}
                                    >全部</button>
                                </div>
                            </div>
                            <div>
                                <p className="text-xs text-slate-400 mb-2 font-serif font-bold tracking-wide">导出格式</p>
                                <div className="flex gap-4">
                                    <button
                                        onClick={() => setExportFormat('PDF')}
                                        className={`flex items-center gap-2 px-4 py-2 rounded-lg border transition-all ${exportFormat === 'PDF' ? 'border-primary text-primary bg-primary/5' : 'border-white/10 text-slate-400'}`}
                                    >
                                        <span className="material-symbols-outlined text-lg">picture_as_pdf</span>
                                        <span className="text-xs font-bold font-serif tracking-wide">PDF 报告</span>
                                    </button>
                                    <button
                                        onClick={() => setExportFormat('CSV')}
                                        className={`flex items-center gap-2 px-4 py-2 rounded-lg border transition-all ${exportFormat === 'CSV' ? 'border-primary text-primary bg-primary/5' : 'border-white/10 text-slate-400'}`}
                                    >
                                        <span className="material-symbols-outlined text-lg">table_chart</span>
                                        <span className="text-xs font-bold font-serif tracking-wide">CSV 数据</span>
                                    </button>
                                </div>
                            </div>
                            <button
                                onClick={handleExport}
                                disabled={isExporting}
                                className="w-full bg-primary/20 text-primary py-3 rounded-xl font-bold mt-2 border border-primary/20 hover:bg-primary/30 transition-colors font-serif tracking-wide flex items-center justify-center gap-2 disabled:opacity-50"
                            >
                                {isExporting ? (
                                    <>
                                        <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                                        生成中...
                                    </>
                                ) : '确认导出'}
                            </button>
                        </div>
                    </Modal>
                );
            case 'CLEAN_DATA':
                return (
                    <Modal title="存储空间清理" onClose={() => !isCleaning && setActiveModal(null)}>
                        <div className="space-y-4">
                            <div className="bg-black/20 rounded-lg p-4 flex items-center justify-between">
                                <div className="flex flex-col">
                                    <span className="text-slate-400 text-xs font-serif font-bold tracking-wide">当前占用</span>
                                    <span className="text-white font-serif tracking-wide text-xl font-bold">{storageSize}</span>
                                </div>
                                <span className="material-symbols-outlined text-white/20 text-4xl">database</span>
                            </div>
                            <div className="space-y-2">
                                <div className="flex items-center justify-between p-2 rounded hover:bg-white/5">
                                    <div className="flex items-center gap-2">
                                        <span className="material-symbols-outlined text-slate-400 text-sm">image</span>
                                        <span className="text-sm text-slate-300 font-serif font-bold tracking-wide">图片缓存</span>
                                    </div>
                                    <span className="text-xs text-white/40 font-serif font-bold tracking-wide">182 MB</span>
                                </div>
                                <div className="flex items-center justify-between p-2 rounded hover:bg-white/5">
                                    <div className="flex items-center gap-2">
                                        <span className="material-symbols-outlined text-slate-400 text-sm">chat</span>
                                        <span className="text-sm text-slate-300 font-serif font-bold tracking-wide">对话记录</span>
                                    </div>
                                    <span className="text-xs text-white/40 font-serif font-bold tracking-wide">63 MB</span>
                                </div>
                            </div>
                            <button
                                onClick={handleDataClean}
                                disabled={isCleaning || storageSize === '12 KB'}
                                className="w-full bg-red-500/10 text-red-400 py-3 rounded-xl font-bold mt-2 border border-red-500/20 hover:bg-red-500/20 transition-colors font-serif tracking-wide flex items-center justify-center gap-2 disabled:opacity-50 disabled:grayscale"
                            >
                                {isCleaning ? (
                                    <>
                                        <span className="material-symbols-outlined animate-spin text-sm">rotate_right</span>
                                        清理中...
                                    </>
                                ) : storageSize === '12 KB' ? '系统已是最新' : '立即清理'}
                            </button>
                        </div>
                    </Modal>
                );
            case 'ABOUT':
                return (
                    <Modal title="关于食鉴" onClose={() => setActiveModal(null)}>
                        <div className="flex flex-col items-center justify-center py-4">
                            <div className="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center border border-primary/20 mb-3 shadow-[0_0_20px_rgba(17,196,212,0.15)]">
                                <svg className="w-8 h-8 drop-shadow-lg" fill="none" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                    <path d="M12 2L2 19L12 14L12 2Z" fill="#11c4d4" fillOpacity="0.9"></path>
                                    <path d="M12 2L22 19L12 14L12 2Z" fill="#7aa0a0" fillOpacity="0.9"></path>
                                </svg>
                            </div>
                            <h4 className="text-white text-lg font-display font-bold">PRISM</h4>
                            <p className="text-white/40 text-xs font-serif tracking-widest mt-1">版本 v2.4.0 (Build 892)</p>
                        </div>
                        <div className="space-y-1 border-t border-white/5 pt-2">
                            <button className="w-full py-3 flex items-center justify-between text-sm text-slate-300 hover:bg-white/5 px-2 rounded-lg transition-colors font-serif font-bold tracking-wide">
                                <span>用户协议</span>
                                <span className="material-symbols-outlined text-xs text-white/30">chevron_right</span>
                            </button>
                            <button className="w-full py-3 flex items-center justify-between text-sm text-slate-300 hover:bg-white/5 px-2 rounded-lg transition-colors font-serif font-bold tracking-wide">
                                <span>隐私政策</span>
                                <span className="material-symbols-outlined text-xs text-white/30">chevron_right</span>
                            </button>
                            <button className="w-full py-3 flex items-center justify-between text-sm text-slate-300 hover:bg-white/5 px-2 rounded-lg transition-colors font-serif font-bold tracking-wide">
                                <span>检查更新</span>
                                <span className="text-[10px] bg-white/10 px-2 py-0.5 rounded text-white/60">已是最新</span>
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
                                未同步的数据可能会丢失。
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
    }

    return (
        <div className="flex flex-col w-full h-full">
            {/* Background is now handled by App.tsx to ensure global consistency */}

            {/* Header */}
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
                        src="/images/user-avatar.png"
                        alt="User"
                        className="w-full h-full object-cover rounded-full"
                    />
                </button>
            </div>

            {/* Scrollable Content */}
            <div className="relative z-10 flex-1 overflow-y-auto p-4 pb-24 space-y-6">

                {/* Profile Section */}
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
                            label="健康状态标签"
                            value={healthTags.length > 0 ? healthTags.join(' · ') : '无'}
                            onClick={() => setActiveModal('HEALTH_TAGS')}
                        />
                        <ListItem
                            icon="no_food"
                            label="饮食避忌"
                            value={restrictions}
                            onClick={() => setActiveModal('RESTRICTIONS')}
                        />
                    </div>
                </div>

                {/* AI Config Section */}
                <div>
                    <SectionTitle title="AI 助手配置" />
                    <div className="bg-[#131b1d]/80 backdrop-blur-sm border border-mineral/20 rounded-xl px-4 overflow-hidden">
                        <div className="flex items-center justify-between py-3 border-b border-white/5">
                            <div className="flex items-center gap-3">
                                <span className="material-symbols-outlined text-white/40 text-lg">psychology</span>
                                <span className="text-white/90 text-sm font-bold tracking-wide font-serif">助手风格</span>
                            </div>
                            <div className="flex bg-black/40 rounded-lg p-0.5 border border-white/5">
                                <button
                                    onClick={() => setAiStyle('strict')}
                                    className={`px-3 py-1 rounded-md text-[10px] transition-all font-serif font-bold tracking-wide ${aiStyle === 'strict' ? 'bg-mineral text-background-dark' : 'text-slate-400'}`}
                                >
                                    分析师
                                </button>
                                <button
                                    onClick={() => setAiStyle('gentle')}
                                    className={`px-3 py-1 rounded-md text-[10px] transition-all font-serif font-bold tracking-wide ${aiStyle === 'gentle' ? 'bg-primary text-background-dark' : 'text-slate-400'}`}
                                >
                                    教练
                                </button>
                            </div>
                        </div>
                        <ListItem
                            icon="tune"
                            label="干预强度"
                            value={intervention}
                            onClick={() => setActiveModal('INTERVENTION')}
                        />
                    </div>
                </div>

                {/* Data & IoT Section */}
                <div>
                    <SectionTitle title="数据与设备" />
                    <div className="bg-[#131b1d]/80 backdrop-blur-sm border border-mineral/20 rounded-xl px-4 overflow-hidden">
                        <ListItem
                            icon="download"
                            label="健康报表导出"
                            value="PDF / CSV"
                            onClick={() => setActiveModal('EXPORT_DATA')}
                        />
                        <ListItem
                            icon="cleaning_services"
                            label="数据清理"
                            value={storageSize}
                            onClick={() => setActiveModal('CLEAN_DATA')}
                        />
                    </div>
                </div>

                {/* General Section */}
                <div>
                    <SectionTitle title="通用设置" />
                    <div className="bg-[#131b1d]/80 backdrop-blur-sm border border-mineral/20 rounded-xl px-4 overflow-hidden">
                        <ListItem
                            icon="info"
                            label="关于食鉴"
                            value="v2.4.0"
                            onClick={() => setActiveModal('ABOUT')}
                        />
                    </div>
                </div>

                {/* Logout Button */}
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

            {/* Render Active Modal */}
            {renderModalContent()}
        </div>
    );
};

export default SettingsView;