import React, { useState, useRef, useEffect } from 'react';
import { View, ConditionData, ConditionStatus, UserProfile } from '../../types';
import { FEATURE_FLAGS } from '../../constants/featureFlags';

interface ProfileViewProps {
    onViewChange?: (view: View) => void;
    medicalConditions: ConditionData[];
    userProfile: UserProfile;
    onUpdateNickname?: (nickname: string) => Promise<void> | void;
}

const ProfileView: React.FC<ProfileViewProps> = ({ onViewChange, medicalConditions, userProfile, onUpdateNickname }) => {
    const [name, setName] = useState(userProfile.nickname || '用户');
    const [isEditingName, setIsEditingName] = useState(false);
    const [showCopyFeedback, setShowCopyFeedback] = useState(false);

    const nameInputRef = useRef<HTMLInputElement>(null);
    const avatar = userProfile.avatarUrl || '/images/user-avatar.png';
    const metabolicId = userProfile.id ? `PRISM-${String(userProfile.id).padStart(6, '0')}` : '未登录';

    useEffect(() => {
        if (isEditingName && nameInputRef.current) {
            nameInputRef.current.focus();
        }
    }, [isEditingName]);

    useEffect(() => {
        setName(userProfile.nickname || '用户');
    }, [userProfile.nickname]);

    const handleNameBlur = () => {
        setIsEditingName(false);
        if (name.trim() === '') {
            setName(userProfile.nickname || '用户');
            return;
        }
        void onUpdateNickname?.(name);
    };

    const handleNameKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            handleNameBlur();
        }
    };

    const handleCopyId = () => {
        navigator.clipboard.writeText(metabolicId);
        setShowCopyFeedback(true);
        setTimeout(() => setShowCopyFeedback(false), 2000);
    };

    const getStatusLabel = (status: ConditionStatus) => {
        switch (status) {
            case 'ACTIVE': return '活跃';
            case 'MONITORING': return '监测中';
            case 'STABLE': return '平稳';
            case 'ALERT': return '过敏';
            default: return '未知';
        }
    };

    // Helper to determine visual style of cards
    const getCardStyle = (item: ConditionData) => {
        if (item.type === 'ALLERGY') {
            return {
                bg: 'bg-red-500/10',
                iconColor: 'text-red-400',
                textColor: 'text-slate-400'
            };
        }
        // Chronic conditions
        if (item.status === 'ACTIVE' || item.status === 'ALERT') {
            return {
                bg: 'bg-ochre/10',
                iconColor: 'text-ochre',
                textColor: 'text-ochre'
            };
        }
        // Stable/Monitoring
        return {
            bg: 'bg-[#45b7aa]/10',
            iconColor: 'text-[#45b7aa]',
            textColor: 'text-[#45b7aa]'
        };
    };

    return (
        <div className="flex flex-col w-full pb-24">
            <div className="relative">
                {/* Glow blob decoration preserved */}
                <div className="absolute -top-20 -right-20 w-64 h-64 bg-primary/5 rounded-full blur-3xl pointer-events-none z-0"></div>

                {/* Nav Header */}
                <div className="relative z-10 flex items-center p-4 pb-2 justify-between">
                    <button
                        onClick={() => onViewChange && onViewChange(View.HOME)}
                        className="text-white flex size-10 shrink-0 items-center justify-center rounded-full hover:bg-white/5 transition-colors"
                    >
                        <span className="material-symbols-outlined">arrow_back</span>
                    </button>
                    <h2 className="text-white text-lg font-bold leading-tight tracking-wide flex-1 text-center font-serif">个人主页</h2>
                    <button
                        onClick={() => onViewChange && onViewChange(View.SETTINGS)}
                        className="text-white flex size-10 shrink-0 items-center justify-center rounded-full hover:bg-white/5 transition-colors"
                    >
                        <span className="material-symbols-outlined">settings</span>
                    </button>
                </div>

                {/* Avatar Section */}
                <div className="relative z-10 px-6 py-6 flex flex-col items-center gap-4">
                    <div className={`relative group ${FEATURE_FLAGS.profileAvatarUpload ? 'cursor-pointer' : ''}`}>
                        <div className="size-28 rounded-full p-1 bg-gradient-to-tr from-primary/30 to-ochre/30 transition-transform duration-300 group-active:scale-95">
                            <div
                                className="w-full h-full rounded-full bg-cover bg-center border-4 border-background-dark relative overflow-hidden"
                                style={{ backgroundImage: `url("${avatar}")` }}
                            >
                                {!FEATURE_FLAGS.profileAvatarUpload && (
                                    <div className="absolute bottom-1 left-1 right-1 rounded-full bg-black/40 px-2 py-0.5 text-center">
                                        <span className="text-[9px] text-white/60 font-serif">头像上传未开放</span>
                                    </div>
                                )}
                            </div>
                        </div>
                        <div className="absolute -bottom-2 -right-2 bg-surface-dark border border-white/10 p-1.5 px-3 rounded-full flex items-center gap-1.5 shadow-lg pointer-events-none">
                            <span className="material-symbols-outlined text-primary text-[18px]">ecg_heart</span>
                            <span className="text-xs font-bold tracking-wide text-white font-serif">{medicalConditions.length}</span>
                        </div>
                    </div>

                    <div className="text-center flex flex-col items-center gap-1">
                        {isEditingName ? (
                            <input
                                ref={nameInputRef}
                                type="text"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                onBlur={handleNameBlur}
                                onKeyDown={handleNameKeyDown}
                                className="text-2xl font-bold tracking-wide text-white font-serif bg-transparent border-b border-primary/50 outline-none text-center w-48 pb-1"
                            />
                        ) : (
                            <h1
                                onClick={() => setIsEditingName(true)}
                                className="text-2xl font-bold tracking-wide text-white font-serif cursor-pointer hover:text-white/90 flex items-center gap-2 group"
                            >
                                {name}
                                <span className="material-symbols-outlined text-white/20 text-sm group-hover:text-white/50 transition-colors">edit</span>
                            </h1>
                        )}

                        <div className="flex items-center gap-2 mt-1 relative">
                            <p className="text-slate-400 text-sm font-bold tracking-wide font-serif">Metabolic ID: {metabolicId}</p>
                            <button
                                onClick={handleCopyId}
                                className="flex items-center justify-center w-6 h-6 rounded-md bg-white/5 text-slate-400 hover:text-white hover:bg-white/10 transition-all active:scale-95"
                                title="复制 ID"
                            >
                                <span className="material-symbols-outlined text-[14px]">
                                    {showCopyFeedback ? 'check' : 'content_copy'}
                                </span>
                            </button>
                            {showCopyFeedback && (
                                <span className="text-[10px] text-[#45b7aa] animate-fade-in absolute -right-12 font-serif font-bold tracking-wide">已复制</span>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            <div className="relative z-10 flex flex-col gap-6 px-4">
                {/* Medical History Grid */}
                <div className="flex flex-col gap-3">
                    <div className="flex items-center justify-between px-2">
                        <h3 className="text-white text-base font-bold font-serif tracking-wide">病史背景</h3>
                        <button
                            onClick={() => onViewChange && onViewChange(View.MEDICAL_ARCHIVES)}
                            className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/5 border border-white/10 hover:bg-white/10 hover:border-white/20 transition-all active:scale-95 group backdrop-blur-sm"
                        >
                            <span className="text-xs text-slate-300 group-hover:text-white font-bold font-serif tracking-wide">编辑</span>
                            <span className="material-symbols-outlined text-[14px] text-slate-400 group-hover:text-primary transition-colors">edit</span>
                        </button>
                    </div>

                    {medicalConditions.length > 0 ? (
                        <div className="grid grid-cols-2 gap-3">
                            {medicalConditions.map(item => {
                                const style = getCardStyle(item);
                                return (
                                    <div
                                        key={item.id}
                                        className="flex items-start gap-3 p-3 rounded-xl bg-surface-dark border border-white/5 shadow-sm hover:bg-white/5 transition-colors cursor-pointer"
                                    >
                                        <div className={`shrink-0 size-8 rounded-lg ${style.bg} flex items-center justify-center ${style.iconColor}`}>
                                            <span className="material-symbols-outlined text-[20px]">{item.icon}</span>
                                        </div>
                                        <div className="flex flex-col">
                                            <span className="text-sm font-bold font-serif text-white tracking-wide">{item.title}</span>
                                            <span className={`text-[10px] uppercase font-bold font-serif tracking-wider mt-0.5 ${style.textColor}`}>
                                                {getStatusLabel(item.status)}
                                            </span>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    ) : (
                        <div className="flex flex-col items-center justify-center py-6 border border-dashed border-white/10 rounded-xl bg-white/5">
                            <span className="text-xs text-slate-500 font-serif font-bold tracking-wide">暂无病史记录</span>
                        </div>
                    )}
                </div>

                {/* Scan Archives List */}
                <div className="flex flex-col gap-3 mt-4">
                    <div className="flex items-center justify-between px-2">
                        <h3 className="text-white text-base font-bold font-serif tracking-wide">体检档案</h3>
                        {/* Filter button removed */}
                    </div>
                    <button
                        onClick={() => onViewChange && onViewChange(View.HEALTH_REPORT_ARCHIVES)}
                        className="group relative flex items-center gap-4 p-4 rounded-2xl bg-[#131b1d]/80 backdrop-blur-md border border-white/5 shadow-sm active:scale-[0.98] transition-all hover:border-primary/20 hover:bg-[#131b1d] cursor-pointer"
                    >
                        <div className="relative shrink-0 size-12 rounded-xl bg-white/5 flex items-center justify-center text-slate-400 border border-white/10">
                            <span className="material-symbols-outlined text-[24px]">description</span>
                        </div>
                        <div className="flex-1 min-w-0 text-left">
                            <h4 className="text-sm font-bold font-serif text-white truncate group-hover:text-primary transition-colors tracking-wide">体检原始档案</h4>
                            <p className="text-xs text-slate-400 mt-1 flex items-center gap-1.5 font-serif font-bold tracking-wide">
                                暂未接入真实上传与分析接口
                            </p>
                        </div>
                        <div className="shrink-0 flex items-center gap-3">
                            <div className="px-2.5 py-1 rounded-md bg-white/5 border border-white/10">
                                <span className="text-[10px] font-bold font-serif text-white/40 tracking-wide">未开放</span>
                            </div>
                            <span className="material-symbols-outlined text-slate-500 group-hover:text-white transition-colors text-xl">chevron_right</span>
                        </div>
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ProfileView;
